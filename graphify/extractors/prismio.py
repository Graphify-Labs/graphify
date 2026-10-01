"""Deterministic structural extraction for Prismio (``.psm``) source files.

Prismio has no tree-sitter grammar, so this is a small hand-written scanner in
the style of the COBOL extractor: no new dependency, no network, no ambient
state. It runs in two stages:

1. ``_code_view`` blanks comments (``//``, nested ``/* */``) and the *text* of
   string literals (``"..."``, ``'...'``, ``\"\"\"...\"\"\"``) while keeping every
   offset and newline, and keeps the code inside ``${...}`` interpolations.
2. A token-level pass reads the declarations (``import``, ``fn``, ``prop``,
   ``extern fn``, ``struct``, ``enum``, ``trait``, ``impl``, ``let``) and scans
   function bodies for calls.

Heuristic boundaries (fail-closed, see CONTRIBUTING.md):

- A bare call ``f(a, b)`` links to a same-file free function only when exactly
  one has that name *and* arity; overloaded names are left unlinked rather than
  guessed. Otherwise it goes to the shared cross-file resolver.
- ``recv.f(x)`` has no receiver type here, so it is only linked directly when
  the receiver is ``self`` and the enclosing impl/trait declares exactly one
  matching method. A module-qualified call (``io.println``, ``std.io.println``)
  is treated as a plain call. Every other member call is passed on as
  ``is_member_call`` and never bound by name alone.
- An import resolves to a file by walking up from the importing file to the
  project root (a directory holding ``build.ums`` or ``.git``) and looking for
  ``a/b/c.psm``; an import that names no file on disk produces no edge.
- ``impl Trait for Type`` becomes an ``impl`` node with an ``implements`` edge
  to the trait and a ``references`` edge to the type. Both are bound by name
  within the file or its direct imports and dropped when they do not resolve
  (built-in types such as ``Int`` have no declaration to bind to).
"""
from __future__ import annotations

import bisect
import re
from pathlib import Path
from typing import Any

from graphify.extractors.base import _file_stem, _make_id

_TYPE_CONTEXT = "prismio_type:"
_TYPE_KINDS = frozenset({"struct", "enum", "trait"})

_MODIFIERS = frozenset({"public", "private", "internal", "cold"})
_DECLARATION_START = frozenset({
    "public", "private", "internal", "cold", "fn", "prop", "extern", "struct",
    "enum", "trait", "impl", "import", "let",
})
_NOT_CALLS = frozenset({
    "if", "while", "for", "match", "return", "throw", "loop", "repeat",
    "region", "and", "or", "not", "as", "in", "else", "fn", "prop", "let",
    "struct", "enum", "trait", "impl", "where", "extern", "sink", "inout",
})
_DECLARING_KEYWORDS = frozenset({
    "fn", "prop", "let", "struct", "enum", "trait", "impl", "type",
})
_TYPE_TOKEN = re.compile(r"[^\W\d]\w*|[?\[\].,<>]")
_TOKEN = re.compile(r"[^\W\d]\w*|\d\w*|->|=>|\S")
_IDENTIFIER = re.compile(r"[^\W\d]\w*")
_PAIRS = {"(": ")", "[": "]", "{": "}"}


def _code_view(source: str) -> str:
    """Return *source* with comments and string text blanked, offsets preserved."""
    out: list[str] = []
    i, n = 0, len(source)
    stack: list[list[Any]] = []  # ["str", delimiter] or ["interp", brace depth]

    def blank(text: str) -> str:
        return "".join(c if c == "\n" else " " for c in text)

    while i < n:
        c = source[i]
        top = stack[-1] if stack else None
        if top is not None and top[0] == "str":
            delimiter = top[1]
            if c == "\\":
                out.append(blank(source[i:i + 2]))
                i += 2
            elif source.startswith(delimiter, i):
                out.append(delimiter)
                i += len(delimiter)
                stack.pop()
            elif source.startswith("${", i):
                out.append("  ")
                i += 2
                stack.append(["interp", 0])
            elif c == "\n" and len(delimiter) == 1:
                # An unterminated single-line string ends at the line break.
                out.append(c)
                i += 1
                stack.pop()
            else:
                out.append(blank(c))
                i += 1
            continue
        if source.startswith("//", i):
            end = source.find("\n", i)
            end = n if end < 0 else end
            out.append(blank(source[i:end]))
            i = end
        elif source.startswith("/*", i):
            depth, j = 1, i + 2
            while j < n and depth:
                if source.startswith("/*", j):
                    depth += 1
                    j += 2
                elif source.startswith("*/", j):
                    depth -= 1
                    j += 2
                else:
                    j += 1
            out.append(blank(source[i:j]))
            i = j
        elif source.startswith('"""', i):
            out.append('"""')
            stack.append(["str", '"""'])
            i += 3
        elif c in "\"'":
            out.append(c)
            stack.append(["str", c])
            i += 1
        elif top is not None and c == "{":
            top[1] += 1
            out.append(c)
            i += 1
        elif top is not None and c == "}":
            if top[1] == 0:
                out.append(" ")
                stack.pop()
            else:
                top[1] -= 1
                out.append(c)
            i += 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


class _Tokens:
    """Token list with line numbers over the code view."""

    def __init__(self, code: str) -> None:
        self.text: list[str] = []
        self.line: list[int] = []
        starts = [m.end() for m in re.finditer("\n", code)]
        for match in _TOKEN.finditer(code):
            self.text.append(match.group())
            self.line.append(bisect.bisect_right(starts, match.start()) + 1)

    def __len__(self) -> int:
        return len(self.text)

    def at(self, index: int) -> str:
        return self.text[index] if 0 <= index < len(self.text) else ""

    def is_ident(self, index: int) -> bool:
        return 0 <= index < len(self.text) and _IDENTIFIER.fullmatch(self.text[index]) is not None

    def skip_group(self, index: int) -> int:
        """Index just past the group opened at *index* (``(``, ``[``, ``{`` or ``<``)."""
        opener = self.text[index]
        closer = ">" if opener == "<" else _PAIRS[opener]
        depth = 0
        for j in range(index, len(self.text)):
            tok = self.text[j]
            if tok == opener:
                depth += 1
            elif tok == closer:
                depth -= 1
                if depth == 0:
                    return j + 1
        return len(self.text)


def _split_arguments(tokens: _Tokens, start: int, end: int) -> list[tuple[int, int]]:
    """Split the token range ``[start, end)`` at top-level commas."""
    parts: list[tuple[int, int]] = []
    depth = 0
    piece = start
    for j in range(start, end):
        tok = tokens.text[j]
        if tok in ("(", "[", "{", "<"):
            depth += 1
        elif tok in (")", "]", "}", ">"):
            depth -= 1
        elif tok == "," and depth == 0:
            parts.append((piece, j))
            piece = j + 1
    if piece < end:
        parts.append((piece, end))
    return parts


def _type_name(tokens: _Tokens, start: int, end: int) -> str:
    """The last path segment before any ``<`` in a type: ``std.option.Option<T>`` -> ``Option``."""
    name = ""
    for j in range(start, end):
        tok = tokens.text[j]
        if tok == "<":
            break
        if _IDENTIFIER.fullmatch(tok) and tok not in ("dyn", "mut"):
            name = tok
        elif tok not in (".", "?"):
            break
    return name


def _resolve_module(importer: Path, parts: list[str]) -> Path | None:
    """File for module path *parts*, found by walking up to the project root."""
    if not parts:
        return None
    relative = Path(*parts[:-1]) / f"{parts[-1]}.psm"
    directory = importer.parent
    while True:
        candidate = directory / relative
        if candidate.is_file():
            return candidate
        if (directory / "build.ums").exists() or (directory / ".git").exists():
            return None
        if directory.parent == directory:
            return None
        directory = directory.parent


def _resolve_directory(importer: Path, parts: list[str]) -> list[Path]:
    """Every ``.psm`` file in the directory named by *parts*, sorted."""
    relative = Path(*parts)
    directory = importer.parent
    while True:
        candidate = directory / relative
        if candidate.is_dir():
            return sorted(p for p in candidate.glob("*.psm") if p != importer)
        if (directory / "build.ums").exists() or (directory / ".git").exists():
            return []
        if directory.parent == directory:
            return []
        directory = directory.parent


def resolve_prismio_type_references(
    _per_file: list[dict], all_nodes: list[dict], all_edges: list[dict]
) -> None:
    """Bind ``impl``/supertrait type names to declarations in the file or its imports.

    A name binds only when exactly one declaration is visible. Edges that stay
    unbound (built-in types, std declarations outside the scanned tree) are
    removed together with their placeholder node, so no phantom stub is left.
    """
    node_by_id = {node.get("id"): node for node in all_nodes}
    file_id_by_source = {
        str(node["source_file"]): node["id"]
        for node in all_nodes
        if node.get("source_file")
        and node.get("label") == Path(str(node["source_file"])).name
    }
    source_by_file_id = {nid: source for source, nid in file_id_by_source.items()}
    imported_sources: dict[str, set[str]] = {}
    for edge in all_edges:
        if edge.get("relation") != "imports_from":
            continue
        source_file = source_by_file_id.get(edge.get("source"))
        target_file = source_by_file_id.get(edge.get("target"))
        if source_file and target_file:
            imported_sources.setdefault(source_file, set()).add(target_file)

    declared: dict[tuple[str, str], list[str]] = {}
    for node in all_nodes:
        metadata = node.get("metadata")
        if (
            isinstance(metadata, dict)
            and metadata.get("language") == "prismio"
            and metadata.get("kind") in _TYPE_KINDS
            and node.get("source_file")
        ):
            declared.setdefault((str(node["source_file"]), str(node["label"])), []).append(node["id"])

    stubs = {
        node["id"] for node in all_nodes
        if not node.get("source_file")
        and isinstance(node.get("metadata"), dict)
        and node["metadata"].get("language") == "prismio"
        and node["metadata"].get("kind") == "external_type"
    }
    unbound: set[str] = set()
    for edge in all_edges:
        context = edge.get("context")
        if not isinstance(context, str) or not context.startswith(_TYPE_CONTEXT):
            continue
        source_node = node_by_id.get(edge.get("source"))
        if not source_node or not source_node.get("source_file"):
            continue
        source_file = str(source_node["source_file"])
        name = context[len(_TYPE_CONTEXT):]
        candidates = list(declared.get((source_file, name), []))
        if not candidates:
            for imported in sorted(imported_sources.get(source_file, set())):
                candidates.extend(declared.get((imported, name), []))
        if len(candidates) == 1:
            edge["target"] = candidates[0]
        else:
            unbound.add(edge["target"])
    all_edges[:] = [
        edge for edge in all_edges
        if not (
            edge.get("target") in unbound
            and str(edge.get("context", "")).startswith(_TYPE_CONTEXT)
        )
    ]
    referenced = {edge.get("source") for edge in all_edges} | {edge.get("target") for edge in all_edges}
    all_nodes[:] = [
        node for node in all_nodes
        if not (node.get("id") in stubs and node["id"] not in referenced)
    ]


def extract_prismio(path: Path) -> dict:
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"nodes": [], "edges": [], "error": str(exc)}

    source_file = str(path)
    stem = _file_stem(path)
    file_id = _make_id(source_file)
    tokens = _Tokens(_code_view(source))
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    raw_calls: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_edges: set[tuple[str, str, str]] = set()

    def add_node(
        nid: str,
        label: str,
        line: int,
        *,
        kind: str,
        source_backed: bool = True,
        callable_node: bool = False,
    ) -> str:
        if nid not in seen_ids:
            seen_ids.add(nid)
            item: dict[str, Any] = {
                "id": nid,
                "label": label,
                "file_type": "code",
                "source_location": f"L{line}",
                "metadata": {"language": "prismio", "kind": kind},
            }
            if source_backed:
                item["source_file"] = source_file
            if callable_node:
                item["_callable"] = True
            nodes.append(item)
        return nid

    def add_edge(
        source_id: str,
        target_id: str,
        relation: str,
        line: int,
        *,
        context: str | None = None,
        target_file: str | None = None,
    ) -> None:
        key = (source_id, target_id, relation)
        if not source_id or not target_id or source_id == target_id or key in seen_edges:
            return
        seen_edges.add(key)
        edge: dict[str, Any] = {
            "source": source_id,
            "target": target_id,
            "relation": relation,
            "confidence": "EXTRACTED",
            "source_file": source_file,
            "source_location": f"L{line}",
            "weight": 1.0,
        }
        if context:
            edge["context"] = context
        if target_file:
            edge["target_file"] = target_file
        edges.append(edge)

    def type_reference(source_id: str, name: str, relation: str, line: int) -> None:
        """Edge to a type or trait by name, bound later by the resolver."""
        if not name:
            return
        stub = _make_id("prismio", "type", name)
        add_node(stub, name, line, kind="external_type", source_backed=False)
        add_edge(source_id, stub, relation, line, context=f"{_TYPE_CONTEXT}{name}")

    add_node(file_id, path.name, 1, kind="file")

    n = len(tokens)
    imported_names: set[str] = set()
    # (name, arity) -> node ids, for same-file call resolution.
    free_functions: dict[tuple[str, int], list[str]] = {}
    methods: dict[tuple[str, str, int], list[str]] = {}
    pending_calls: list[dict[str, Any]] = []
    local_types: dict[str, str] = {}
    pending_type_edges: list[tuple[str, str, str, int]] = []

    def parse_import(i: int) -> int:
        line = tokens.line[i]
        i += 1

        def link(parts: list[str], alias: str = "") -> None:
            target = _resolve_module(path, parts)
            selected = ""
            if target is None and len(parts) > 1:
                target = _resolve_module(path, parts[:-1])
                selected = parts[-1]
            module = parts[-2] if selected else parts[-1]
            imported_names.add(alias or module)
            imported_names.add(".".join(parts[:-1] if selected else parts))
            if target is None or target == path:
                return
            add_edge(
                file_id, _make_id(str(target)), "imports_from", line, target_file=str(target)
            )

        def link_directory(parts: list[str]) -> None:
            for target in _resolve_directory(path, parts):
                add_edge(
                    file_id, _make_id(str(target)), "imports_from", line, target_file=str(target)
                )

        def path_parts(j: int) -> tuple[list[str], int]:
            parts: list[str] = []
            while tokens.is_ident(j):
                parts.append(tokens.text[j])
                if tokens.at(j + 1) == "." and tokens.is_ident(j + 2):
                    j += 2
                else:
                    j += 1
                    break
            return parts, j

        if tokens.at(i) == "{":
            close = tokens.skip_group(i)
            entries = [
                [tokens.text[k] for k in range(a, b) if tokens.is_ident(k)]
                for a, b in _split_arguments(tokens, i + 1, close - 1)
            ]
            j = close
            if tokens.at(j) == "from":
                directory, j = path_parts(j + 1)
                for entry in entries:
                    if entry:
                        alias = entry[2] if len(entry) >= 3 and entry[1] == "as" else ""
                        link(directory + [entry[0]], alias)
            return j
        if tokens.at(i) == "*":
            if tokens.at(i + 1) == "from":
                directory, j = path_parts(i + 2)
                link_directory(directory)
                return j
            return i + 1
        parts, j = path_parts(i)
        if not parts:
            return j
        if tokens.at(j) == "." and tokens.at(j + 1) == "*":
            link_directory(parts)
            return j + 2
        alias = ""
        if tokens.at(j) == "as" and tokens.is_ident(j + 1):
            alias = tokens.text[j + 1]
            j += 2
        link(parts, alias)
        return j

    def parse_params(start: int, end: int) -> tuple[list[str], list[str]]:
        names: list[str] = []
        types: list[str] = []
        for a, b in _split_arguments(tokens, start, end):
            colon = next((k for k in range(a, b) if tokens.text[k] == ":"), None)
            if colon is None:
                words = [tokens.text[k] for k in range(a, b) if tokens.is_ident(k)]
                names.append(words[-1] if words else "")
                types.append("self")
            else:
                names.append(tokens.text[colon - 1] if colon > a else "")
                types.append("".join(tokens.text[colon + 1:b]))
        return names, types

    def scan_calls(start: int, end: int, caller: str, owner: str) -> None:
        for p in range(start, end):
            if not tokens.is_ident(p) or tokens.text[p] in _NOT_CALLS:
                continue
            before = tokens.at(p - 1)
            if before in _DECLARING_KEYWORDS:
                continue
            q = p + 1
            if tokens.at(q) == "<":
                close = tokens.skip_group(q)
                if all(_TYPE_TOKEN.fullmatch(t) for t in tokens.text[q:close]):
                    q = close
            if q >= end or tokens.at(q) != "(":
                continue
            close = tokens.skip_group(q)
            arguments = len(_split_arguments(tokens, q + 1, close - 1))
            name = tokens.text[p]
            line = tokens.line[p]
            if before != ".":
                if name[0].isupper():
                    # `Type(...)` constructs a value; it is not a function call.
                    pending_type_edges.append((caller, name, "references", line))
                    continue
                pending_calls.append({
                    "caller": caller, "owner": owner, "name": name, "arity": arguments,
                    "member": False, "receiver": "", "line": line,
                })
                continue
            qualifier: list[str] = []
            k = p - 1
            while tokens.at(k) == "." and tokens.is_ident(k - 1):
                qualifier.append(tokens.text[k - 1])
                k -= 2
            qualifier.reverse()
            dotted = ".".join(qualifier)
            if qualifier and qualifier[0][:1].isupper():
                pending_type_edges.append((caller, qualifier[0], "references", line))
                continue
            module_qualified = bool(qualifier) and (
                dotted in imported_names or qualifier[-1] in imported_names
            )
            pending_calls.append({
                "caller": caller, "owner": owner, "name": name,
                "arity": arguments if module_qualified else arguments + 1,
                "member": not module_qualified, "receiver": dotted, "line": line,
            })

    def parse_function(i: int, owner: str, trait: str = "") -> tuple[int, str]:
        """Parse ``fn``/``prop`` at *i*; return the next index and the node id."""
        keyword = tokens.text[i]
        extern = i > 0 and tokens.at(i - 1) == "extern"
        if not tokens.is_ident(i + 1):
            return i + 1, ""
        name = tokens.text[i + 1]
        line = tokens.line[i]
        j = i + 2
        if tokens.at(j) == "<":
            j = tokens.skip_group(j)
        if tokens.at(j) != "(":
            return j, ""
        params_end = tokens.skip_group(j)
        _, types = parse_params(j + 1, params_end - 1)
        arity = len(types)
        signature = ",".join(types)
        if extern:
            kind = "extern_function"
        elif keyword == "prop":
            kind = "property"
        else:
            kind = "method" if owner else "function"
        nid = _make_id(*(part for part in (stem, owner, trait, kind, name, signature) if part))
        label = f".{name}()" if owner else f"{name}()"
        add_node(nid, label, line, kind=kind, callable_node=True)
        j = params_end
        last_line = tokens.line[params_end - 1]
        body: tuple[int, int] | None = None
        while j < n:
            tok = tokens.text[j]
            if tok == "{":
                close = tokens.skip_group(j)
                body = (j + 1, close - 1)
                j = close
                break
            if (
                tokens.line[j] > last_line
                and tok != "where"
                and tokens.at(j - 1) not in (",", "+", ":", "where", "->")
            ):
                break
            if tok in ("(", "[", "<"):
                j = tokens.skip_group(j)
                last_line = tokens.line[j - 1]
                continue
            last_line = tokens.line[j]
            j += 1
        if owner:
            methods.setdefault((owner, name, arity), []).append(nid)
        else:
            free_functions.setdefault((name, arity), []).append(nid)
        if body is not None:
            scan_calls(body[0], body[1], nid, owner)
        return j, nid

    def parse_members(start: int, end: int, parent: str, owner: str, trait: str) -> None:
        """Members of an ``impl`` or ``trait`` body."""
        j = start
        while j < end:
            tok = tokens.text[j]
            if tok in _MODIFIERS:
                j += 1
                continue
            if tok in ("fn", "prop") and tokens.is_ident(j + 1):
                line = tokens.line[j]
                j, nid = parse_function(j, owner, trait)
                if nid:
                    add_edge(parent, nid, "method", line)
                continue
            if tok in ("type", "let") and tokens.is_ident(j + 1):
                row = tokens.line[j]
                while j < end and tokens.line[j] == row:
                    j += 1
                continue
            j += 1

    def parse_declaration(i: int) -> int:
        tok = tokens.text[i]
        line = tokens.line[i]
        if tok == "import":
            return parse_import(i)
        if tok == "extern":
            nxt = tokens.at(i + 1)
            if nxt == "fn":
                j, nid = parse_function(i + 1, "")
                if nid:
                    add_edge(file_id, nid, "contains", line)
                return j
            if nxt == "let":
                return parse_declaration(i + 1)
            return i + 1
        if tok in ("fn", "prop"):
            j, nid = parse_function(i, "")
            if nid:
                add_edge(file_id, nid, "contains", line)
            return j
        if tok == "let":
            j = i + 1
            if tokens.at(j) == "mut":
                j += 1
            if not tokens.is_ident(j):
                return j
            name = tokens.text[j]
            nid = add_node(_make_id(stem, "variable", name), name, line, kind="variable")
            add_edge(file_id, nid, "contains", line)
            j += 1
            depth = 0
            while j < n:
                t = tokens.text[j]
                if depth == 0 and tokens.line[j] > tokens.line[j - 1] and (
                    t in _DECLARATION_START or t == "}"
                ):
                    break
                if t in ("(", "[", "{"):
                    depth += 1
                elif t in (")", "]", "}"):
                    depth = max(0, depth - 1)
                j += 1
            return j
        if tok in ("struct", "enum", "trait") and tokens.is_ident(i + 1):
            name = tokens.text[i + 1]
            nid = add_node(_make_id(stem, tok, name), name, line, kind=tok)
            add_edge(file_id, nid, "contains", line)
            local_types[name] = nid
            j = i + 2
            if tokens.at(j) == "<":
                j = tokens.skip_group(j)
            supertraits: list[tuple[str, int]] = []
            if tok == "trait" and tokens.at(j) == ":":
                j += 1
                while j < n and tokens.at(j) != "{":
                    if tokens.is_ident(j) and tokens.at(j + 1) in ("+", "{", "<", "where", ""):
                        supertraits.append((tokens.text[j], tokens.line[j]))
                    elif tokens.at(j) == "<":
                        j = tokens.skip_group(j)
                        continue
                    j += 1
            while j < n and tokens.at(j) != "{":
                if tokens.line[j] > tokens.line[j - 1] and tokens.text[j] in _DECLARATION_START:
                    return j
                j += 1
            if j >= n:
                return j
            close = tokens.skip_group(j)
            for super_name, super_line in supertraits:
                pending_type_edges.append((nid, super_name, "inherits", super_line))
            if tok == "enum":
                k = j + 1
                while k < close - 1:
                    if tokens.is_ident(k) and tokens.at(k - 1) in ("{", ","):
                        variant = tokens.text[k]
                        vid = add_node(
                            _make_id(nid, "variant", variant),
                            variant,
                            tokens.line[k],
                            kind="variant",
                        )
                        add_edge(nid, vid, "contains", tokens.line[k])
                        k += 1
                        if tokens.at(k) == "(":
                            k = tokens.skip_group(k)
                        continue
                    if tokens.at(k) in ("(", "[", "<"):
                        k = tokens.skip_group(k)
                        continue
                    k += 1
            elif tok == "trait":
                parse_members(j + 1, close - 1, nid, name, "")
            return close
        if tok == "impl":
            j = i + 1
            if tokens.at(j) == "<":
                j = tokens.skip_group(j)
            first_start = j
            while j < n and tokens.at(j) not in ("for", "where", "{"):
                if tokens.at(j) == "<":
                    j = tokens.skip_group(j)
                else:
                    j += 1
            first = _type_name(tokens, first_start, j)
            trait_name = ""
            target = first
            if tokens.at(j) == "for":
                trait_name = first
                second_start = j + 1
                j = second_start
                while j < n and tokens.at(j) not in ("where", "{"):
                    if tokens.at(j) == "<":
                        j = tokens.skip_group(j)
                    else:
                        j += 1
                target = _type_name(tokens, second_start, j)
            while j < n and tokens.at(j) != "{":
                j += 1
            if j >= n or not target:
                return j
            label = f"impl {trait_name} for {target}" if trait_name else f"impl {target}"
            nid = add_node(_make_id(stem, "impl", trait_name, target), label, line, kind="impl")
            add_edge(file_id, nid, "contains", line)
            if trait_name:
                pending_type_edges.append((nid, trait_name, "implements", line))
            pending_type_edges.append((nid, target, "references", line))
            close = tokens.skip_group(j)
            parse_members(j + 1, close - 1, nid, target, trait_name)
            return close
        return i + 1

    i = 0
    while i < n:
        tok = tokens.text[i]
        if tok in _MODIFIERS:
            i += 1
        elif tok in _DECLARATION_START or tok == "prop":
            i = max(parse_declaration(i), i + 1)
        else:
            i += 1

    for source_id, name, relation, line in pending_type_edges:
        local = local_types.get(name)
        if local is not None:
            add_edge(source_id, local, relation, line)
        else:
            type_reference(source_id, name, relation, line)

    for call in pending_calls:
        name, arity, caller, owner = call["name"], call["arity"], call["caller"], call["owner"]
        if not call["member"]:
            same_arity = free_functions.get((name, arity), [])
            if len(same_arity) == 1:
                add_edge(caller, same_arity[0], "calls", call["line"])
                continue
            if any(key[0] == name and key[1] == arity for key in free_functions):
                continue  # overloaded in this file: never guess between them
            raw_calls.append({
                "caller_nid": caller,
                "callee": name,
                "language": "prismio",
                "source_file": source_file,
                "source_location": f"L{call['line']}",
            })
            continue
        if call["receiver"] == "self" and owner:
            candidates = methods.get((owner, name, arity), [])
            if len(candidates) == 1:
                add_edge(caller, candidates[0], "calls", call["line"])
                continue
        raw_calls.append({
            "caller_nid": caller,
            "callee": name,
            "receiver": call["receiver"],
            "is_member_call": True,
            "language": "prismio",
            "source_file": source_file,
            "source_location": f"L{call['line']}",
        })

    clean_edges = [
        edge for edge in edges
        if edge["source"] in seen_ids
        and (edge["target"] in seen_ids or edge["relation"] == "imports_from")
    ]
    return {"nodes": nodes, "edges": clean_edges, "raw_calls": raw_calls}
