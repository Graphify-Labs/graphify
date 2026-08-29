"""Deterministic symbol indexing and conservative cross-file resolution helpers."""

from __future__ import annotations

import ast
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Sequence
from typing import Any

from graphify.ids import make_id as _shared_make_id
from graphify.paths import disambiguate_ambiguous_candidates
from graphify.security import sanitize_metadata



@dataclass(frozen=True)
class ImportedSymbol:
    """A Python imported name that can be used as deterministic resolution evidence."""

    local_name: str
    imported_name: str
    module_stem: str
    source_file: str
    source_location: str


@dataclass(frozen=True)
class PythonTypeAlias:
    """A source-backed, module-level Python type alias definition."""

    name: str
    module_stem: str
    source_file: str
    source_location: str


def _annotation_names(node: ast.AST | None) -> set[str]:
    """Return unqualified names occurring in a type expression."""

    if node is None:
        return set()
    return {
        child.id
        for child in ast.walk(node)
        if isinstance(child, ast.Name)
    }


def parse_python_type_aliases(path: Path) -> list[PythonTypeAlias]:
    """Discover conservative module-level aliases backed by typing forms."""

    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, SyntaxError):
        return []

    result: list[PythonTypeAlias] = []
    alias_value_names = {
        "Callable",
        "Union",
        "Literal",
        "Protocol",
        "Type",
        "Annotated",
    }
    for node in tree.body:
        name: str | None = None
        value: ast.AST | None = None
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            name = node.targets[0].id
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if "TypeAlias" in _annotation_names(node.annotation):
                name = node.target.id
                value = node.value
        elif hasattr(ast, "TypeAlias") and isinstance(node, ast.TypeAlias):
            name_node = getattr(node, "name", None)
            name = getattr(name_node, "id", None)
            value = getattr(node, "value", None)
        if not name or value is None:
            continue
        if not _annotation_names(value).intersection(alias_value_names):
            continue
        result.append(
            PythonTypeAlias(
                name=name,
                module_stem=path.stem,
                source_file=str(path),
                source_location=f"L{getattr(node, 'lineno', 1)}",
            )
        )
    return result


def _resolved_source(value: object) -> Path | None:
    """Resolve a graph source path defensively for equality/indexing."""

    if not value:
        return None
    try:
        return Path(str(value)).resolve()
    except (OSError, RuntimeError):
        return None


def _file_node_ids_by_resolved_path(
    nodes: Sequence[dict[str, Any]],
) -> dict[Path, str]:
    """Map source paths to their source-backed file-node IDs."""

    result: dict[Path, str] = {}
    for node in nodes:
        source = _resolved_source(node.get("source_file"))
        node_id = node.get("id")
        if source is None or not node_id:
            continue
        if str(node.get("label", "")) == Path(str(node["source_file"])).name:
            result[source] = str(node_id)
    return result


def _materialize_python_type_alias_nodes(
    paths: Sequence[Path],
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    file_ids: dict[Path, str],
) -> dict[tuple[str, str], list[str]]:
    """Create source-backed alias nodes and return their strict lookup index."""

    existing = {
        (
            _resolved_source(node.get("source_file")),
            str(node.get("label", "")).lower(),
        ): str(node["id"])
        for node in nodes
        if node.get("id") and node.get("node_kind") == "type_alias"
    }
    edge_keys = {
        (str(edge.get("source")), str(edge.get("target")), edge.get("relation"))
        for edge in edges
    }
    index: dict[tuple[str, str], list[str]] = {}
    for path in paths:
        if path.suffix.lower() not in {".py", ".pyw"}:
            continue
        source = _resolved_source(path)
        if source is None:
            continue
        file_id = file_ids.get(source)
        if file_id is None:
            continue
        for alias in parse_python_type_aliases(path):
            key = (source, alias.name.lower())
            alias_id = existing.get(key)
            if alias_id is None:
                alias_id = _shared_make_id(file_id, alias.name)
                nodes.append(
                    {
                        "id": alias_id,
                        "label": alias.name,
                        "file_type": "code",
                        "node_kind": "type_alias",
                        "source_file": alias.source_file,
                        "source_location": alias.source_location,
                    }
                )
                existing[key] = alias_id
            contains_key = (file_id, alias_id, "contains")
            if contains_key not in edge_keys:
                edges.append(
                    {
                        "source": file_id,
                        "target": alias_id,
                        "relation": "contains",
                        "confidence": "EXTRACTED",
                        "source_file": alias.source_file,
                        "source_location": alias.source_location,
                        "weight": 1.0,
                    }
                )
                edge_keys.add(contains_key)
            index.setdefault(
                (alias.module_stem, alias.name.lower()), []
            ).append(alias_id)
    return index


def canonicalize_python_type_aliases(
    paths: Sequence[Path],
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> None:
    """Materialize aliases and rewire uniquely import-supported local stubs."""

    file_ids = _file_node_ids_by_resolved_path(nodes)
    alias_index = _materialize_python_type_alias_nodes(
        paths, nodes, edges, file_ids
    )
    node_by_id = {
        str(node.get("id")): node for node in nodes if node.get("id")
    }
    edges_by_source: dict[Path, list[dict[str, Any]]] = {}
    for edge in edges:
        edge_source = _resolved_source(edge.get("source_file"))
        if edge_source is not None:
            edges_by_source.setdefault(edge_source, []).append(edge)
    rewired_stub_ids: set[str] = set()
    for path in paths:
        if path.suffix.lower() not in {".py", ".pyw"}:
            continue
        imports = parse_python_import_aliases(path)
        source = _resolved_source(path)
        if source is None:
            continue
        for edge in edges_by_source.get(source, ()):
            stub = node_by_id.get(str(edge.get("target")))
            if not stub or stub.get("source_file"):
                continue
            imported = imports.get(str(stub.get("label", "")))
            if imported is None:
                continue
            candidates = alias_index.get(
                (imported.module_stem, imported.imported_name.lower()), []
            )
            if len(candidates) != 1:
                continue
            edge["target"] = candidates[0]
            rewired_stub_ids.add(str(stub["id"]))

    referenced = {
        str(edge.get(key))
        for edge in edges
        for key in ("source", "target")
        if edge.get(key)
    }
    nodes[:] = [
        node
        for node in nodes
        if str(node.get("id")) not in rewired_stub_ids
        or str(node.get("id")) in referenced
    ]


_SOURCE_LINE_RE = re.compile(r"^L([1-9][0-9]*)")
_SYMBOL_KIND_PRIORITY = {
    "method": 0,
    "function": 1,
    "class": 2,
    "type_alias": 3,
}


def _source_line(node: dict[str, Any]) -> int | None:
    """Return a node's one-based starting line when present."""

    match = _SOURCE_LINE_RE.match(str(node.get("source_location", "")))
    return int(match.group(1)) if match else None


def resolve_markdown_code_references(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    root: Path | None = None,
) -> None:
    """Refine stamped Markdown code links to exact or preceding symbols.

    The target path and optional line are deterministic extraction evidence.
    When the line cannot identify a symbol, the canonical file node remains the
    target. No node is fabricated for a missing file.
    """

    by_path: dict[Path, list[tuple[int, int, str]]] = {}
    file_ids: dict[Path, str] = {}

    def resolved_graph_path(value: object) -> Path:
        path = Path(str(value))
        if root is not None and not path.is_absolute():
            path = root / path
        return path.resolve()

    for node in nodes:
        source_file = node.get("source_file")
        node_id = node.get("id")
        if (
            not source_file
            or not node_id
            or node.get("file_type") != "code"
        ):
            continue
        try:
            path = resolved_graph_path(source_file)
        except (OSError, RuntimeError):
            continue
        label = str(node.get("label", ""))
        if label == Path(str(source_file)).name:
            file_ids[path] = str(node_id)
            continue
        line = _source_line(node)
        if line is None:
            continue
        priority = _SYMBOL_KIND_PRIORITY.get(str(node.get("node_kind", "")), 10)
        by_path.setdefault(path, []).append((line, priority, str(node_id)))
    for candidates in by_path.values():
        candidates.sort(key=lambda item: (item[0], item[1], item[2]))

    for edge in edges:
        if edge.get("relation") != "references" or not edge.get("target_file"):
            continue
        raw_line = edge.pop("target_line", None)
        try:
            path = resolved_graph_path(edge["target_file"])
        except (OSError, RuntimeError):
            continue
        fallback = file_ids.get(path)
        if fallback is not None:
            edge["target"] = fallback
        if not isinstance(raw_line, int) or raw_line < 1:
            continue
        preceding = [item for item in by_path.get(path, []) if item[0] <= raw_line]
        if not preceding:
            continue
        best_line = preceding[-1][0]
        same_line = [item for item in preceding if item[0] == best_line]
        edge["target"] = min(same_line, key=lambda item: (item[1], item[2]))[2]


def normalise_callable_label(label: str) -> str:
    """Normalize a node label into the key used for call resolution."""

    return label.strip().strip("()").lstrip(".").lower()


def node_is_resolvable_symbol(node: dict[str, Any]) -> bool:
    """Return True when a node is suitable for deterministic symbol lookup.

    Requires ``file_type == "code"`` as the positive gate — only code-class
    nodes participate as call targets. ``_EXCLUDED_FILE_TYPES`` is kept as
    defensive-in-depth against legacy data, but the primary guard is the
    positive code check. Document/paper/image/concept nodes (e.g. a Markdown
    heading whose label happens to match a code identifier) MUST NOT become
    callees for a raw code call.
    """

    if node.get("file_type") != "code":
        return False
    label = str(node.get("label", "")).strip()
    if not label:
        return False
    if label.endswith((".py", ".js", ".ts", ".tsx", ".java", ".go", ".rs")):
        return False
    return bool(normalise_callable_label(label))


def build_label_index(nodes: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Build label -> node id list for conservative cross-file resolution."""

    index: dict[str, list[str]] = {}
    for node in nodes:
        if not node_is_resolvable_symbol(node):
            continue
        node_id = node.get("id")
        if not node_id:
            continue
        key = normalise_callable_label(str(node.get("label", "")))
        if not key:
            continue
        index.setdefault(key, []).append(str(node_id))
    return index


def existing_edge_pairs(edges: list[dict[str, Any]]) -> set[tuple[str, str, str]]:
    """Return all existing source/target/relation edge triples.

    Includes relation so that a prior "contains" or "method" edge does not
    suppress a semantically distinct "calls" edge between the same endpoints (#F5).
    """

    triples: set[tuple[str, str, str]] = set()
    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        relation = edge.get("relation", "")
        if source and target:
            triples.add((str(source), str(target), str(relation)))
    return triples


def iter_raw_calls(per_file: Sequence[object]) -> list[dict[str, Any]]:
    """Return raw calls from all per-file extraction fragments.

    Parameter is ``Sequence[object]`` (not ``Sequence[dict[str, Any] | None]``)
    because external extraction output may contain arbitrary deserialized
    JSON. Defensive against malformed fragments: non-dict per-file entries
    are skipped, non-list ``raw_calls`` are treated as empty, and non-dict
    items inside the list are silently dropped. The downstream resolvers
    assume every returned item is a dict and they expect this guarantee.
    """

    calls: list[dict[str, Any]] = []
    for result in per_file:
        if not isinstance(result, dict):
            continue
        raw_calls = result.get("raw_calls", [])
        if not isinstance(raw_calls, list):
            continue
        for raw_call in raw_calls:
            if isinstance(raw_call, dict):
                calls.append(raw_call)
    return calls


def _module_stem(module_name: str | None) -> str:
    """Return the final module component used to match Graphify source stems."""

    if not module_name:
        return ""
    return module_name.strip(".").split(".")[-1]


def parse_python_import_aliases(path: Path) -> dict[str, ImportedSymbol]:
    """Parse deterministic Python import aliases from one source file.

    Supported forms:
        from helper import transform
        from helper import transform as tx
        from .helper import transform

    The function deliberately does not resolve plain ``import helper`` member
    calls because current raw call records do not preserve the receiver name from
    ``helper.transform()``. That can be added later only after raw call facts are
    extended to include the receiver expression.
    """

    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source)
    except (OSError, SyntaxError):
        return {}

    aliases: dict[str, ImportedSymbol] = {}
    source_file = str(path)

    # Only top-level `from ... import ...` statements count as file-wide
    # evidence. Nested/function-local imports do NOT — they're only valid
    # inside their lexical scope, and our raw-call records don't currently
    # carry enough scope info to match the import site safely. Walking
    # ast.walk(tree) would incorrectly justify calls in other scopes.
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom):
            continue
        module_stem = _module_stem(node.module)
        if not module_stem:
            continue
        for alias in node.names:
            if alias.name == "*":
                continue
            local_name = alias.asname or alias.name
            aliases[local_name] = ImportedSymbol(
                local_name=local_name,
                imported_name=alias.name,
                module_stem=module_stem,
                source_file=source_file,
                source_location=f"L{getattr(node, 'lineno', 1)}",
            )

    return aliases


def _node_source_stem(node: dict[str, Any]) -> str:
    """Return the stem of a node's source file."""

    source_file = str(node.get("source_file", ""))
    if not source_file:
        return ""
    return Path(source_file).stem


def build_python_symbol_index(nodes: list[dict[str, Any]]) -> dict[tuple[str, str], list[str]]:
    """Build ``(module_stem, normalized_symbol_name) -> node_ids``.

    This index is stricter than the global label index. It uses both the module
    stem and the symbol label, which allows import evidence to resolve calls that
    global label uniqueness alone cannot safely resolve.
    """

    index: dict[tuple[str, str], list[str]] = {}
    for node in nodes:
        if not node_is_resolvable_symbol(node):
            continue
        source_stem = _node_source_stem(node)
        if not source_stem:
            continue
        label = normalise_callable_label(str(node.get("label", "")))
        if not label:
            continue
        node_id = node.get("id")
        if not node_id:
            continue
        index.setdefault((source_stem, label), []).append(str(node_id))
    return index


def find_unique_python_symbol(
    symbol_index: dict[tuple[str, str], list[str]],
    imported: ImportedSymbol,
) -> str | None:
    """Resolve one imported symbol to exactly one Graphify node id."""

    candidates = symbol_index.get((imported.module_stem, imported.imported_name.lower()), [])
    if len(candidates) == 1:
        return candidates[0]
    return None


def resolve_python_import_guided_calls(
    per_file: Sequence[object],
    paths: Sequence[Path],
    all_nodes: list[dict[str, Any]],
    all_edges: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Resolve raw Python calls using explicit import evidence.

    Only ``from module import symbol [as alias]`` forms are handled. Member calls
    remain skipped because the current raw call fact does not carry receiver
    information.

    Parameter ``per_file`` is ``Sequence[object]`` because external extraction
    output may contain arbitrary deserialized JSON. Non-dict slots are
    treated as empty fragments, and indices past ``len(per_file)`` are also
    treated as empty (paths longer than per_file is tolerated).
    """

    symbol_index = build_python_symbol_index(all_nodes)
    known_pairs = existing_edge_pairs(all_edges)
    # Build result_by_file defensively:
    #   - skip indices past the end of per_file (paths shorter than per_file
    #     also OK; the zip-like behavior is what callers expect)
    #   - non-dict per_file slots fall back to the empty fragment so the
    #     downstream `.get("raw_calls", [])` lookup never raises
    result_by_file: dict[str, dict[str, Any]] = {}
    for index, path in enumerate(paths):
        if path.suffix != ".py":
            continue
        slot: Any = per_file[index] if index < len(per_file) else None
        result_by_file[str(path)] = slot if isinstance(slot, dict) else {"nodes": [], "edges": []}
    resolved_edges: list[dict[str, Any]] = []

    for path in paths:
        if path.suffix != ".py":
            continue
        source_file = str(path)
        aliases = parse_python_import_aliases(path)
        if not aliases:
            continue
        file_result = result_by_file.get(source_file, {"raw_calls": []})
        raw_calls = file_result.get("raw_calls", [])
        if not isinstance(raw_calls, list):
            continue
        for raw_call in raw_calls:
            if not isinstance(raw_call, dict):
                continue
            if raw_call.get("is_member_call"):
                continue
            callee = str(raw_call.get("callee", "")).strip()
            if not callee:
                continue
            imported = aliases.get(callee)
            if imported is None:
                continue
            target = find_unique_python_symbol(symbol_index, imported)
            if target is None:
                continue
            caller = str(raw_call.get("caller_nid", ""))
            if not caller or caller == target:
                continue
            pair = (caller, target, "calls")
            if pair in known_pairs:
                continue
            known_pairs.add(pair)
            resolved_edges.append(
                {
                    "source": caller,
                    "target": target,
                    "relation": "calls",
                    "context": "import_guided_call",
                    "confidence": "EXTRACTED",
                    "confidence_score": 1.0,
                    "source_file": raw_call.get("source_file", source_file),
                    "source_location": raw_call.get("source_location") or imported.source_location,
                    "weight": 1.0,
                    "metadata": sanitize_metadata({
                        "resolver": "python_import_guided",
                        "local_name": imported.local_name,
                        "imported_name": imported.imported_name,
                        "module_stem": imported.module_stem,
                        "import_source_location": imported.source_location,
                    }),
                }
            )

    return resolved_edges


def resolve_cross_file_raw_calls(
    per_file: Sequence[dict[str, Any] | None],
    all_nodes: list[dict[str, Any]],
    all_edges: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Resolve unqualified raw calls conservatively after all files are known.

    This intentionally preserves Graphify's existing behavior:
    - member calls are skipped;
    - ambiguous labels are skipped;
    - only a single unique candidate is emitted;
    - emitted edges are INFERRED because the raw call alone is not import proof.
    """

    label_index = build_label_index(all_nodes)
    known_pairs = existing_edge_pairs(all_edges)
    # nid -> source_file, for the shared god-node tie-breakers (#1553) so a
    # same-named test mock no longer erases a real cross-file call.
    nid_to_source_file = {
        str(n.get("id")): str(n.get("source_file", ""))
        for n in all_nodes
        if n.get("id")
    }
    resolved: list[dict[str, Any]] = []

    for raw_call in iter_raw_calls(per_file):
        callee = str(raw_call.get("callee", "")).strip()
        if not callee:
            continue
        if raw_call.get("is_member_call"):
            continue
        candidates = label_index.get(callee.lower(), [])
        if not candidates:
            continue
        if len(candidates) == 1:
            target: str | None = candidates[0]
        else:
            # Ambiguous bare name. Apply the shared tie-breakers (non-test
            # preference, then path proximity); resolve only if exactly one
            # candidate survives, else preserve the god-node guard and skip.
            target = disambiguate_ambiguous_candidates(
                candidates,
                {c: nid_to_source_file.get(c, "") for c in candidates},
                str(raw_call.get("source_file", "")),
            )
            if target is None:
                continue
        caller = str(raw_call.get("caller_nid", ""))
        if not caller:
            continue
        if target == caller:
            continue
        pair = (caller, target, "calls")
        if pair in known_pairs:
            continue
        known_pairs.add(pair)
        resolved.append(
            {
                "source": caller,
                "target": target,
                "relation": "calls",
                "context": "call",
                "confidence": "INFERRED",
                # 0.85, not 0.8 — the extraction-spec rubric's INFERRED values
                # are a discrete set and 0.8 is not one of them (#2813).
                "confidence_score": 0.85,
                "source_file": raw_call.get("source_file", ""),
                "source_location": raw_call.get("source_location"),
                "weight": 1.0,
            }
        )

    return resolved


def _bash_make_id(*parts: str) -> str:
    """Bash symbol node ID via the single shared recipe (#1378).

    Previously an inline copy to dodge an import cycle; ``graphify.ids`` is
    dependency-free, so it can be imported directly.
    """
    return _shared_make_id(*parts)


from graphify.extractors.base import _file_stem as _bash_file_stem  # canonical recipe (no import cycle: base imports only graphify.ids)


def _file_node_id_for_path(path: Path, root: Path) -> str:
    # Produce the canonical {parent_dir}_{stem} file-node ID that extract()'s
    # id_remap generates (#1033), so bash `source` edges land on the real file
    # node instead of an orphan. _bash_make_id / _bash_file_stem are exact copies
    # of extract._make_id / extract._file_stem, so IDs match.
    try:
        rel = path.resolve().relative_to(root.resolve())
    except ValueError:
        return _bash_make_id(str(path))  # path outside root: hash absolute path as fallback
    return _bash_make_id(_bash_file_stem(rel))


def resolve_bash_source_edges(
    per_file: Sequence[dict | None],
    paths: Sequence[Path],
    root: Path,
    existing_edges: list[dict] | None = None,
) -> list[dict]:
    """Resolve Bash source/import edges and source-backed function calls.

    Defensive against malformed extraction fragments: non-dict ``per_file``
    entries, missing ``bash_sources``/``raw_calls`` keys, non-dict items in
    those lists, and missing/empty ``id`` / ``target_path`` / ``caller_nid``
    fields all yield silent skips rather than ``KeyError``.

    ``bash_sources[].target_path`` contract (Graphify static-analysis policy):
        - Absolute paths: resolved as-is.
        - Relative paths: resolved against the *source file's* directory
          (i.e. ``Path(path).parent / target_path``).
          NOTE: this is a deterministic static-analysis policy chosen by
          Graphify, NOT bash runtime semantics. At runtime, ``source ./X``
          is resolved against the shell's current working directory. We
          prefer source-file-relative because static analysis cannot know
          the future CWD; resolving against the file being analyzed gives
          deterministic, reproducible edges across runs.
        - Inputs of type ``str`` and ``pathlib.Path`` are processed.
          Anything else is silently skipped.
    """
    path_by_index = [Path(p).resolve() for p in paths]
    file_nid_by_path = {p: _file_node_id_for_path(p, root) for p in path_by_index}  # resolved paths only

    functions_by_file: dict[str, dict[str, str]] = {}
    for result, path in zip(per_file, path_by_index):
        if not isinstance(result, dict):
            continue
        file_nid = file_nid_by_path[path]
        nodes = result.get("nodes", [])
        if not isinstance(nodes, list):
            continue
        for node in nodes:
            if not isinstance(node, dict):
                continue
            metadata = node.get("metadata", {})
            if not isinstance(metadata, dict):
                continue
            if metadata.get("kind") != "bash_function":
                continue
            name = str(node.get("label", "")).removesuffix("()").strip()
            node_id = node.get("id")
            if not name or not node_id:
                continue
            functions_by_file.setdefault(file_nid, {})[name] = str(node_id)

    sourced_files: dict[str, set[str]] = {}
    resolved_edges: list[dict] = []
    existing = existing_edge_pairs(existing_edges or [])

    for result, path in zip(per_file, path_by_index):
        if not isinstance(result, dict):
            continue
        src_file_nid = file_nid_by_path[path]
        bash_sources = result.get("bash_sources", [])
        if not isinstance(bash_sources, list):
            continue
        for source in bash_sources:
            if not isinstance(source, dict):
                continue
            raw_target = source.get("target_path")
            if not isinstance(raw_target, (str, Path)) or not str(raw_target).strip():
                continue
            # Relative paths resolve against the source file's directory —
            # Graphify static-analysis policy (NOT bash runtime semantics;
            # at runtime `source ./X` is CWD-relative, but static analysis
            # can't know the future CWD, so we resolve relative to the
            # file being analyzed for deterministic, reproducible edges).
            candidate = Path(raw_target)
            if not candidate.is_absolute():
                candidate = path.parent / candidate
            try:
                target_path = candidate.resolve()
            except (OSError, RuntimeError):
                continue
            target_file_nid = file_nid_by_path.get(target_path)
            if target_file_nid is None:
                continue
            sourced_files.setdefault(src_file_nid, set()).add(target_file_nid)
            key = (src_file_nid, target_file_nid, "imports_from")
            if key in existing:
                continue
            existing.add(key)
            resolved_edges.append(
                {
                    "source": src_file_nid,
                    "target": target_file_nid,
                    "relation": "imports_from",
                    "context": "import",
                    "confidence": "EXTRACTED",
                    "confidence_score": 1.0,
                    "source_file": source.get("source_file", str(path)),
                    "source_location": source.get("source_location", ""),
                    "weight": 1.0,
                }
            )

    for result, path in zip(per_file, path_by_index):
        if not isinstance(result, dict):
            continue
        caller_file_nid = file_nid_by_path[path]
        imported_file_ids = sourced_files.get(caller_file_nid, set())
        if not imported_file_ids:
            continue
        raw_calls = result.get("raw_calls", [])
        if not isinstance(raw_calls, list):
            continue
        for raw_call in raw_calls:
            if not isinstance(raw_call, dict):
                continue
            if raw_call.get("language") != "bash":
                continue
            callee = raw_call.get("callee")
            caller_nid = raw_call.get("caller_nid")
            # callee must be a non-empty string — anything else (list, dict,
            # int, None, …) is silently skipped to avoid TypeError on the
            # `in functions_by_file[...]` membership check below.
            if not isinstance(callee, str) or not callee or not caller_nid:
                continue
            matches = [
                functions_by_file[file_nid][callee]
                for file_nid in imported_file_ids
                if callee in functions_by_file.get(file_nid, {})
            ]
            if len(matches) != 1:
                continue
            target = matches[0]
            key = (str(caller_nid), target, "calls")
            if key in existing:
                continue
            existing.add(key)
            resolved_edges.append(
                {
                    "source": str(caller_nid),
                    "target": target,
                    "relation": "calls",
                    "context": "call",
                    "confidence": "EXTRACTED",
                    "confidence_score": 1.0,
                    "source_file": raw_call.get("source_file", str(path)),
                    "source_location": raw_call.get("source_location", ""),
                    "weight": 1.0,
                }
            )

    return resolved_edges
