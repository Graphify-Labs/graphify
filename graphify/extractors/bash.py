"""Bash extractor. Moved verbatim from graphify/extract.py."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from graphify.extractors.base import _file_stem, _make_id, _read_text


# Leading `${VAR}` / `$VAR` expansion segment(s) of a `source` path argument. The
# canonical `BENCH_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"` idiom makes
# such a variable resolve to the script's own directory, so the literal suffix that
# follows (`lib/x.sh`) can be resolved against the sourcing file's own dir (#2079).
_BASH_LEADING_EXPANSION = re.compile(
    r"^(?:(?:\$\{[^}]*\}|\$[A-Za-z_][A-Za-z0-9_]*)/?)+"
)


def _bash_source_suffix(raw: str) -> str | None:
    """Return the literal path suffix of a variable-built `source` argument, or
    None when the remainder is empty, still holds an expansion, or escapes upward
    with ``..``.  ``"${DIR}/lib/x.sh"`` -> ``"lib/x.sh"``."""
    suffix = _BASH_LEADING_EXPANSION.sub("", raw, count=1).lstrip("/")
    if not suffix or "$" in suffix:
        return None
    if ".." in suffix.split("/"):
        return None
    return suffix


# Name of the leading variable of a `source` argument: `${ROOT}/lib/x.sh` -> ROOT.
_BASH_LEADING_VAR = re.compile(
    r"^\$\{([A-Za-z_][A-Za-z0-9_]*)[^}]*\}|^\$([A-Za-z_][A-Za-z0-9_]*)"
)

# The `$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)` idiom, capturing the
# trailing `/..` hops applied to the dirname result.
_BASH_DIRNAME_IDIOM = re.compile(r"dirname[^)]*\)((?:/\.\.)*)")


def _bash_assignment_base(value: str, script_dir: Path) -> Path | None:
    """Resolve a top-level assignment's value to a directory, or None if untracked.

    Covers the two forms that make a ``source "${VAR}/lib/x.sh"`` target knowable
    statically (#2172):

    * the script-dir idiom ``"$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"``,
      including any number of trailing ``/..`` hops (and the ``$0`` spelling)
    * a literal path, absolute or relative to the script's own directory

    Anything else -- a value built from other variables, or command substitution
    we do not model -- is left untracked so the caller keeps its previous
    script-dir guess rather than binding somewhere invented.
    """
    val = value.strip().strip("'\"")
    if not val:
        return None
    if "dirname" in val and ("BASH_SOURCE" in val or "$0" in val):
        m = _BASH_DIRNAME_IDIOM.search(val)
        base = script_dir
        for _ in range((m.group(1).count("..") if m else 0)):
            base = base.parent
        return base
    if "$" in val or "`" in val:
        return None
    candidate = Path(val)
    return candidate if candidate.is_absolute() else script_dir / candidate


def extract_bash(path: Path) -> dict:
    """Extract functions, source imports, and cross-function calls from a .sh file."""
    try:
        import tree_sitter_bash as tsbash
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree-sitter-bash not installed"}

    try:
        language = Language(tsbash.language())
        parser = Parser(language)
        source = path.read_bytes()
        tree = parser.parse(source)
        root = tree.root_node
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    stem = _file_stem(path)
    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    # Cross-file resolution scaffolding consumed by resolve_bash_source_edges in
    # the extract pipeline: `bash_sources` records which files this one `source`s,
    # `raw_calls` records calls whose callee isn't defined in this file (candidate
    # calls into a sourced library). The extractor sees one file at a time and so
    # can't resolve these itself (#2141).
    raw_calls: list[dict] = []
    bash_sources: list[dict] = []
    raw_seen: set[tuple[str, str]] = set()
    seen_ids: set[str] = set()
    function_bodies: list[tuple[str, Any]] = []
    defined_functions: set[str] = set()

    from graphify.security import sanitize_metadata  # module-level cached import

    def add_node(nid: str, label: str, line: int, kind: str = "code") -> None:
        if nid and nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({"id": nid, "label": label, "file_type": "code",
                          "source_file": str_path, "source_location": f"L{line}",
                          "metadata": sanitize_metadata({"language": "bash", "kind": kind})})  # noqa: E501

    def add_edge(src: str, tgt: str, relation: str, line: int,
                 confidence: str = "EXTRACTED", weight: float = 1.0,
                 context: str | None = None,
                 target_file: str | None = None) -> None:
        if not src or not tgt or src == tgt:
            return
        edge = {"source": src, "target": tgt, "relation": relation,
                "confidence": confidence, "source_file": str_path,
                "source_location": f"L{line}", "weight": weight}
        if context:
            edge["context"] = context
        # Transient resolved-target hint (#1814/#2169), mirroring the Python/
        # markdown extractors: lets the extract() id-remap pass canonicalize a
        # target minted from an absolute path even when the target file is not
        # in the batch (incremental run) or lives out of root (#2243). Popped
        # before anything persists, never shipped into graph.json.
        if target_file is not None:
            edge["target_file"] = target_file
        edges.append(edge)

    file_nid = _make_id(str(path))
    # file_nid is fully path-derived and never produced by _make_id(stem, func_name),
    # so appending "__entry" guarantees a distinct ID from any function node.
    entry_nid = file_nid + "__entry"
    add_node(file_nid, path.name, 1, kind="file")
    add_node(entry_nid, f"{path.name} script", 1, kind="bash_entrypoint")
    add_edge(file_nid, entry_nid, "contains", 1)

    _BASH_SOURCE_COMMANDS = frozenset({"source", "."})
    _BASH_SCRIPT_RUNNERS = frozenset({"bash", "sh", "zsh", "ksh", "dash"})
    # Parent node types that mean a contained command is part of a substitution
    # or expansion, not a real function call. Token-level filtering misses
    # these because `$(build)` exposes `build` as a child command whose name
    # token has no metacharacters — only the parent does.
    _BASH_EXPANSION_PARENTS = frozenset({
        "command_substitution",
        "process_substitution",
    })

    def text(node) -> str:
        return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

    def is_inside_expansion(node) -> bool:
        parent = node.parent
        while parent is not None:
            if parent.type in _BASH_EXPANSION_PARENTS:
                return True
            parent = parent.parent
        return False

    def literal(node) -> str | None:
        # Token-level filter: rejects names containing shell metacharacters.
        # Combined with `is_inside_expansion` for parent-context rejection.
        raw = text(node).strip()
        if not raw:
            return None
        if raw[0:1] in {"'", '"'} and raw[-1:] == raw[0]:
            raw = raw[1:-1]
        if any(token in raw for token in ("$", "`", "$(", "<(", ">", "|", ";", "&")):
            return None
        return raw

    def _bash_func_name(node) -> str | None:
        """Get the name from a function_definition node."""
        # bash grammar: function_definition has a word child (the name)
        for child in node.children:
            if child.type == "word":
                return literal(child)
        return None

    def walk_calls(body_node, func_nid: str, seen_calls: set) -> None:
        if body_node is None:
            return
        for child in body_node.children:
            if child.type == "function_definition":
                # Skip nested function definitions — their bodies are walked
                # separately, so we don't attribute their calls to the
                # enclosing scope.
                continue
            if child.type == "command" and not is_inside_expansion(child):
                cmd_name_node = child.child_by_field_name("name")
                if cmd_name_node is None and child.children:
                    cmd_name_node = child.children[0]
                if cmd_name_node:
                    name = literal(cmd_name_node)
                    # Defined-functions wins. Skip-lists for external commands
                    # would create false negatives when a user defines a
                    # function shadowing an external (`install`, `find`, etc.).
                    if name and name in defined_functions:
                        tgt = _make_id(stem, name)
                        key = (func_nid, tgt)
                        if tgt and key not in seen_calls:
                            seen_calls.add(key)
                            add_edge(func_nid, tgt, "calls",
                                     child.start_point[0] + 1,
                                     confidence="EXTRACTED", context="call")
                    elif (name and name not in _BASH_SOURCE_COMMANDS
                          and name not in _BASH_SCRIPT_RUNNERS):
                        # Callee isn't defined in this file — it may be a function
                        # from a sourced library. Record an unresolved raw_call for
                        # resolve_bash_source_edges to bind against the files this
                        # script `source`s. A callee that is not a sourced function
                        # (a genuine external command) matches nothing there and
                        # yields no edge, so this can't over-connect the graph (#2141).
                        raw_key = (func_nid, name)
                        if raw_key not in raw_seen:
                            raw_seen.add(raw_key)
                            raw_calls.append({
                                "language": "bash",
                                "callee": name,
                                "caller_nid": func_nid,
                                "source_file": str_path,
                                "source_location": f"L{child.start_point[0] + 1}",
                            })
            walk_calls(child, func_nid, seen_calls)

    def walk(node, parent_nid: str) -> None:
        t = node.type
        if t == "function_definition":
            name = _bash_func_name(node)
            if name:
                fn_nid = _make_id(stem, name)
                line = node.start_point[0] + 1
                add_node(fn_nid, f"{name}()", line, kind="bash_function")
                add_edge(parent_nid, fn_nid, "defines", line)
                defined_functions.add(name)
                # find the compound_statement body
                body = None
                for child in node.children:
                    if child.type == "compound_statement":
                        body = child
                        break
                function_bodies.append((fn_nid, body))
                # Recurse into the body so nested function definitions are discovered
                # and added to function_bodies for the second-pass walk_calls.
                if body is not None:
                    walk(body, fn_nid)
            return

        if t == "command":
            if is_inside_expansion(node):
                return
            cmd_name_node = node.child_by_field_name("name")
            if cmd_name_node is None and node.children:
                cmd_name_node = node.children[0]
            if cmd_name_node:
                cmd = literal(cmd_name_node)
                args = [c for c in node.children
                        if c.type in ("word", "string", "concatenation")
                        and c != cmd_name_node]
                if cmd in _BASH_SOURCE_COMMANDS and cmd not in defined_functions:
                    # find the path argument (first word after command name)
                    if args:
                        raw = _read_text(args[0], source).strip().strip("'\"")
                        line = node.start_point[0] + 1
                        if raw.startswith((".", "/")):
                            resolved = (path.parent / raw).resolve()
                            # Only emit the edge if the target actually exists on
                            # disk — prevents graph pollution from crafted paths
                            # like `source ../../etc/passwd` that traverse outside
                            # the project tree (B-1).
                            if resolved.exists():
                                tgt_nid = _make_id(str(resolved))
                                add_edge(file_nid, tgt_nid, "imports_from", line,
                                         context="import",
                                         target_file=str(resolved))
                                # Record the sourced file so resolve_bash_source_edges
                                # can bind calls into its functions (#2141). Gated on
                                # existence like the edge above, so crafted traversal
                                # paths never enter the resolver's data.
                                bash_sources.append({
                                    "target_path": raw,
                                    "source_file": str_path,
                                    "source_location": f"L{line}",
                                })
                        elif "$" in raw:
                            # Variable-built path, e.g. the ubiquitous
                            # `source "${BENCH_DIR}/lib/x.sh"` idiom. The raw text
                            # bakes the unexpanded `${VAR}` into the id, which
                            # matches no node and is dropped as a dangling edge
                            # (#2079). Strip the leading expansion(s) and resolve
                            # the literal suffix against the script's own dir;
                            # emit INFERRED (the expansion can't be proven
                            # statically) only when it resolves to a real file,
                            # never a dead id.
                            suffix = _bash_source_suffix(raw)
                            if suffix:
                                # Resolve against the variable's tracked base when
                                # we know it, else fall back to the script's own
                                # directory as before (#2172).
                                base = path.parent
                                var_match = _BASH_LEADING_VAR.match(raw)
                                if var_match:
                                    var_name = var_match.group(1) or var_match.group(2)
                                    if var_name in var_bases:
                                        base = var_bases[var_name]
                                resolved = (base / suffix).resolve()
                                if resolved.is_file():
                                    add_edge(file_nid, _make_id(str(resolved)),
                                             "imports_from", line,
                                             confidence="INFERRED", context="import",
                                             target_file=str(resolved))
                                    # Integration (#2141 + #2079): record the resolved
                                    # sourced file so calls into its functions resolve
                                    # too, not just the source edge. target_path is
                                    # absolute here; resolve_bash_source_edges takes it
                                    # as-is.
                                    bash_sources.append({
                                        "target_path": str(resolved),
                                        "source_file": str_path,
                                        "source_location": f"L{line}",
                                    })
                        else:
                            # Bare `source lib.sh` (no leading ./ or /). Bash
                            # itself resolves such a name via $PATH at runtime,
                            # but in practice the file sits next to the script,
                            # so bind it when a sibling of that name exists
                            # (#2171). Same existence gate as the ./-prefixed
                            # branch above: a name that resolves to nothing keeps
                            # the old opaque `imports` edge and records no
                            # bash_sources entry, so nothing is fabricated.
                            sibling: Path | None = None
                            if raw:
                                try:
                                    candidate = path.parent / raw
                                    if candidate.is_file():
                                        sibling = candidate.resolve()
                                except OSError:
                                    sibling = None
                            if sibling is not None:
                                # A bare `source lib.sh` resolves via $PATH at
                                # runtime; binding it to the sibling of that name
                                # is a heuristic, so mark it INFERRED (#2171).
                                add_edge(file_nid, _make_id(str(sibling)),
                                         "imports_from", line,
                                         confidence="INFERRED", context="import",
                                         target_file=str(sibling))
                                bash_sources.append({
                                    "target_path": raw,
                                    "source_file": str_path,
                                    "source_location": f"L{line}",
                                })
                            else:
                                tgt_nid = _make_id(raw)
                                if tgt_nid:
                                    add_edge(file_nid, tgt_nid, "imports", line,
                                             context="import")
                elif cmd and cmd not in defined_functions:
                    raw = cmd if cmd.endswith(".sh") else None
                    if cmd in _BASH_SCRIPT_RUNNERS and args:
                        raw = literal(args[0])
                    if raw and raw.endswith(".sh"):
                        resolved = (path.parent / raw).resolve()
                        if resolved.is_file():
                            target_path = resolved
                            if not path.is_absolute():
                                try:
                                    target_path = resolved.relative_to(Path.cwd().resolve())
                                except ValueError:
                                    pass
                            caller_nid = entry_nid if parent_nid == file_nid else parent_nid
                            # target_file lets the extract() remap loop learn
                            # this script's canonical id even when it is not in
                            # the batch; the "__entry"-suffixed endpoint is
                            # rewritten there via the suffix-aware entry
                            # registration (#2243).
                            add_edge(caller_nid, _make_id(str(target_path)) + "__entry",
                                     "calls", node.start_point[0] + 1,
                                     context="script_invocation",
                                     target_file=str(target_path))
            return

        if t == "declaration_command":
            # export/declare/readonly VAR=value at program level
            if node.parent and node.parent.type == "program":
                for child in node.children:
                    if child.type == "variable_assignment":
                        var_node = child.child_by_field_name("name")
                        if var_node:
                            var = _read_text(var_node, source).strip()
                            if var:
                                var_nid = _make_id(stem, var)
                                line = child.start_point[0] + 1
                                add_node(var_nid, var, line)
                                add_edge(file_nid, var_nid, "defines", line)
            return

        for child in node.children:
            walk(child, parent_nid)

    # Pre-pass: collect all defined function names so the source-command handler
    # in walk() can detect user-defined functions that shadow 'source' / '.'
    # regardless of definition order in the file.
    def _prescan_functions(node) -> None:
        if node.type == "function_definition":
            name = _bash_func_name(node)
            if name:
                defined_functions.add(name)
            for child in node.children:
                _prescan_functions(child)
        else:
            for child in node.children:
                _prescan_functions(child)

    _prescan_functions(root)
    # Bases for `source "${VAR}/lib/x.sh"` resolution (#2172). #2079 always resolved
    # the literal suffix against the script's own directory, which is right for the
    # `DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"` idiom but wrong whenever
    # the variable points elsewhere -- e.g. ROOT=".../scripts/.." with a same-named
    # decoy under the script dir bound to the decoy. Track top-level assignments so
    # the real base is used; untracked variables keep the script-dir guess.
    var_bases: dict[str, Path] = {}
    for _assign in root.children:
        if _assign.type != "variable_assignment":
            continue
        _name_node = _assign.child_by_field_name("name")
        _value_node = _assign.child_by_field_name("value")
        if _name_node is None or _value_node is None:
            continue
        _name = _read_text(_name_node, source).strip()
        if not _name:
            continue
        _base = _bash_assignment_base(_read_text(_value_node, source), path.parent)
        if _base is not None:
            var_bases[_name] = _base

    walk(root, file_nid)

    # Second pass: cross-function calls
    top_seen: set = set()
    walk_calls(root, entry_nid, top_seen)  # top-level calls attributed to the entrypoint
    for fn_nid, body in function_bodies:
        walk_calls(body, fn_nid, set())

    return {"nodes": nodes, "edges": edges,
            "raw_calls": raw_calls, "bash_sources": bash_sources}
