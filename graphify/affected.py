from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable, cast
import unicodedata

import networkx as nx

from graphify.paths import _is_test_path


DEFAULT_AFFECTED_RELATIONS = (
    "calls",
    "indirect_call",
    "references",
    "imports",
    "imports_from",
    # `import('…')` — emitted by the Svelte/Astro/Vue rescue passes and (since
    # #2575) by plain JS/TS too. Omitting it made every dynamic import
    # invisible to blast-radius traversal even where the edge WAS in the
    # graph, and dynamic import is precisely how codebases break require
    # cycles, so the missing edges sat under the most load-bearing modules.
    "dynamic_import",
    "re_exports",
    "inherits",
    "extends",
    "implements",
    "uses",
    "mixes_in",
    "embeds",
    "requires",
)


@dataclass(frozen=True)
class AffectedHit:
    node_id: str
    depth: int
    via_relation: str
    # The traversed edge's location — the actual call/import/reference SITE in
    # this node's file, not the node's own definition line (#BUG1). Defaults keep
    # existing constructors/tests working; None falls back to the node's def line.
    via_file: "str | None" = None
    via_location: "str | None" = None


def _node_label(graph: nx.Graph, node_id: str) -> str:
    data = graph.nodes[node_id]
    return str(data.get("label") or node_id)


def _format_location(data: dict) -> str:
    source_file = data.get("source_file") or "-"
    source_location = data.get("source_location")
    if source_location:
        return f"{source_file}:{source_location}"
    return str(source_file)


def _bare_name(label: str) -> str:
    """Lowercased label with the callable decoration (trailing "()") removed."""
    label = _normalize_label(label)
    return label[:-2] if label.endswith("()") else label


def _normalize_label(label: str) -> str:
    return unicodedata.normalize("NFC", label).casefold()


def _as_repo_relative(query: str) -> str:
    """Repo-relative form of a path query, for matching a stored `source_file`.

    The graph stores repo-relative paths, so `./src/x.py` and
    `/abs/repo/src/x.py` name the same file as `src/x.py` and yet matched
    nothing. `affected` then printed an empty list and exited 0 — a blast-radius
    tool answering "nothing depends on this" about a file with sixteen
    dependents, and indistinguishable from a genuine zero or a typo.

    Non-path queries pass through unchanged: `Path("myFunc()").as_posix()` is
    `"myFunc()"`, so label resolution is untouched. An absolute path rooted
    outside the repo is left alone — no basename guessing.
    """
    path = Path(query)
    if path.is_absolute():
        try:
            return path.relative_to(Path.cwd()).as_posix()
        except ValueError:
            # Rooted outside the repo: nothing here can make it repo-relative,
            # so leave it alone rather than guess at a basename that would match
            # some unrelated file with the same name.
            return query
    return path.as_posix()


def _prefer_file_node(
    graph: nx.Graph,
    node_ids: list[str],
    query: str,
) -> str | None:
    """Return the file-level node when a source_file query matches many nodes."""
    query_basename = _normalize_label(Path(query).name)
    exact_file_nodes = [
        node_id
        for node_id in node_ids
        if str(graph.nodes[node_id].get("source_location", "")) == "L1"
        and _normalize_label(str(graph.nodes[node_id].get("label", ""))) == query_basename
    ]
    if len(exact_file_nodes) == 1:
        return exact_file_nodes[0]

    l1_nodes = [
        node_id
        for node_id in node_ids
        if str(graph.nodes[node_id].get("source_location", "")) == "L1"
    ]
    if len(l1_nodes) == 1:
        return l1_nodes[0]

    basename_nodes = [
        node_id
        for node_id in node_ids
        if _normalize_label(str(graph.nodes[node_id].get("label", ""))) == query_basename
    ]
    if len(basename_nodes) == 1:
        return basename_nodes[0]

    return None


_NON_PRODUCTION_DIR_SEGMENTS = frozenset({"docs", "eval"})
_GraphEdge = tuple[object, object, dict]


def _is_production_source(path: str) -> bool:
    """Return whether a path is production code for affected traversal.

    Tests use the shared repository classifier. Whole ``docs`` and ``eval``
    directory segments are also excluded. Segment matching is conservative:
    names such as ``contest``, ``latest``, and ``document_service`` remain
    production paths.
    """
    if not path or _is_test_path(path):
        return False
    normalized = str(path).replace("\\", "/")
    segments = (segment.casefold() for segment in PurePosixPath(normalized).parts)
    return not any(segment in _NON_PRODUCTION_DIR_SEGMENTS for segment in segments)


def _unique_or_production_match(graph: nx.Graph, node_ids: list[str]) -> str | None:
    """Resolve uniquely, preferring one proven production node."""
    if len(node_ids) == 1:
        return node_ids[0]
    production_nodes = [
        node_id
        for node_id in node_ids
        if _is_production_source(str(graph.nodes[node_id].get("source_file", "")))
    ]
    if len(production_nodes) == 1:
        return production_nodes[0]
    return None


def _label_matches(graph: nx.Graph, query: str, *, bare: bool) -> list[str]:
    normalize = _bare_name if bare else _normalize_label
    normalized_query = normalize(query)
    return [
        str(node_id)
        for node_id, data in graph.nodes(data=True)
        if normalize(str(data.get("label", ""))) == normalized_query
    ]


def _resolve_source_match(graph: nx.Graph, query: str, query_lower: str) -> str | None:
    repo_relative_query = _as_repo_relative(query)
    query_path = _normalize_label(repo_relative_query)
    matches = [
        str(node_id)
        for node_id, data in graph.nodes(data=True)
        if _normalize_label(str(data.get("source_file", ""))) in (query_lower, query_path)
    ]
    if len(matches) == 1:
        return matches[0]
    return _prefer_file_node(graph, matches, repo_relative_query) if matches else None


def resolve_seed(graph: nx.Graph, query: str) -> str | None:
    # A trailing path separator must not change a source-file match — serve's
    # _find_node tokenizes the path (which drops it), so strip it here for parity
    # (otherwise `affected "src/x.ts/"` returned None while `explain` resolved it).
    query = query.rstrip("/\\") or query
    if query in graph:
        return query
    query_lower = _normalize_label(query)
    exact_label_match = _unique_or_production_match(
        graph, _label_matches(graph, query_lower, bare=False)
    )
    if exact_label_match is not None:
        return exact_label_match
    # Callable labels are decorated ("name()"), so a bare "name" query falls
    # through exact matching and then ties with any "name*" sibling in the
    # contains pass. Match on the undecorated name before giving up.
    bare_name_match = _unique_or_production_match(
        graph, _label_matches(graph, query_lower, bare=True)
    )
    if bare_name_match is not None:
        return bare_name_match
    # Compare paths in repo-relative form. Only this branch is path-shaped; the
    # label branches above keep the query verbatim.
    source_match = _resolve_source_match(graph, query, query_lower)
    if source_match is not None:
        return source_match
    contains_matches = [
        str(node_id)
        for node_id, data in graph.nodes(data=True)
        if query_lower in _normalize_label(str(data.get("label", "")))
    ]
    if len(contains_matches) == 1:
        return contains_matches[0]
    return None


def _is_production_node(graph: nx.Graph, node_id: str) -> bool:
    source_file = str(graph.nodes[node_id].get("source_file", ""))
    return _is_production_source(source_file)


def _out_edges(graph: nx.Graph, node_id: str) -> Iterable[_GraphEdge]:
    edge_reader = getattr(graph, "out_edges", None)
    if callable(edge_reader):
        return cast(Iterable[_GraphEdge], edge_reader(node_id, data=True))
    return (
        (source, target, data)
        for source, target, data in graph.edges(data=True)
        if source == node_id
    )


def _in_edges(graph: nx.Graph, node_id: str) -> Iterable[_GraphEdge]:
    edge_reader = getattr(graph, "in_edges", None)
    if callable(edge_reader):
        return cast(Iterable[_GraphEdge], edge_reader(node_id, data=True))
    return (
        (source, target, data)
        for source, target, data in graph.edges(data=True)
        if target == node_id
    )


def _seed_members(
    graph: nx.Graph,
    seed: str,
    seen: set[str],
    queue: deque[tuple[str, int]],
    *,
    production_only: bool,
) -> None:
    """Add root members as traversal-only seeds, subject to path policy."""
    for _source, member, data in _out_edges(graph, seed):
        if str(data.get("relation", "")) not in ("method", "contains"):
            continue
        member_id = str(member)
        if member_id in seen:
            continue
        if production_only and not _is_production_node(graph, member_id):
            continue
        seen.add(member_id)
        queue.append((member_id, 0))


def affected_nodes(
    graph: nx.Graph,
    seed: str,
    *,
    relations: Iterable[str] = DEFAULT_AFFECTED_RELATIONS,
    depth: int = 2,
    production_only: bool = False,
) -> list[AffectedHit]:
    """Find reverse dependencies, optionally traversing production code only."""
    relation_set = set(relations)
    seen = {seed}
    queue: deque[tuple[str, int]] = deque([(seed, 0)])
    hits: list[AffectedHit] = []

    # Seed the reverse walk with root members (#1669); members are not reported.
    _seed_members(graph, seed, seen, queue, production_only=production_only)

    while queue:
        current, current_depth = queue.popleft()
        if current_depth >= depth:
            continue
        for source, _target, data in _in_edges(graph, current):
            relation = str(data.get("relation", ""))
            if relation not in relation_set:
                continue
            source = str(source)
            if source in seen:
                continue
            if production_only and not _is_production_node(graph, source):
                continue
            via_file = str(data.get("source_file") or "")
            if production_only and via_file and not _is_production_source(via_file):
                continue
            seen.add(source)
            # Carry the matched edge's location (taken from the SAME edge dict
            # whose relation passed the filter, so relation and location stay
            # consistent) — that is the call/import/reference site in `source`'s
            # own file, which is where the user should click (#BUG1).
            hit = AffectedHit(
                source,
                current_depth + 1,
                relation,
                via_file=via_file or None,
                via_location=str(data.get("source_location") or "") or None,
            )
            hits.append(hit)
            queue.append((source, current_depth + 1))

    return hits


def format_affected(
    graph: nx.Graph,
    query: str,
    *,
    relations: Iterable[str] = DEFAULT_AFFECTED_RELATIONS,
    depth: int = 2,
    production_only: bool = False,
) -> str:
    """Render affected nodes, optionally excluding non-production traversal."""
    relation_list = tuple(relations)
    seed = resolve_seed(graph, query)
    if seed is None:
        return f"No unique node match for {query}"

    hits = affected_nodes(
        graph,
        seed,
        relations=relation_list,
        depth=depth,
        production_only=production_only,
    )
    lines = [
        f"Affected nodes for {_node_label(graph, seed)}",
        f"Relations: {', '.join(relation_list)}",
        f"Depth: {depth}",
    ]
    if not hits:
        lines.append("No affected nodes found.")
        return "\n".join(lines)

    for hit in hits:
        data = graph.nodes[hit.node_id]
        if hit.via_location:
            # The relation SITE in this node's file (call/import/reference line),
            # labeled by [via_relation] so it's never mistaken for a def line.
            location = f"{hit.via_file or data.get('source_file') or '-'}:{hit.via_location}"
        else:
            location = _format_location(data)  # honest fallback: the node's own def line
        lines.append(
            f"- {_node_label(graph, hit.node_id)} [{hit.via_relation}] {location}"
        )
    return "\n".join(lines)


def load_graph(path: Path) -> nx.Graph:
    import json
    from networkx.readwrite import json_graph

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise RuntimeError(
            f"Cannot read graph file {path}: {exc}. "
            "Re-run 'graphify extract' to regenerate it."
        ) from exc
    # Force directed so stored caller→callee direction survives the round-trip;
    # mirrors serve.py and __main__.py (#1174).
    raw = {**raw, "directed": True}
    # Normalize the edge key: graphify's `extract` output uses "edges" while
    # networkx's node_link_data default is "links". Without this, an edges-keyed
    # graph.json raises an uncaught KeyError: 'links' here — every other loader
    # (__main__.py) already normalizes this (#738; same class as #1198).
    if "links" not in raw and "edges" in raw:
        raw = dict(raw, links=raw["edges"])
    try:
        return json_graph.node_link_graph(raw, edges="links")
    except TypeError:
        return json_graph.node_link_graph(raw)
