from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
import unicodedata


DEFAULT_AFFECTED_RELATIONS = (
    "calls",
    "indirect_call",
    "references",
    "imports",
    "imports_from",
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


def _normalize_label(label: str) -> str:
    return unicodedata.normalize("NFC", label).casefold()


def _bare_name(label: str) -> str:
    """Normalized label with the callable decoration (trailing "()") removed."""
    label = _normalize_label(label)
    return label[:-2] if label.endswith("()") else label


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


def resolve_seed(graph, query: str) -> str | None:
    # A trailing path separator must not change a source-file match — serve's
    # _find_node tokenizes the path (which drops it), so strip it here for parity
    # (otherwise `affected "src/x.ts/"` returned None while `explain` resolved it).
    query = query.rstrip("/\\") or query
    # FalkorDB-native: resolve via scoped queries (no full-graph load).
    if hasattr(graph, "find_node_ids"):
        if graph.has_node(query):
            return query
        # Mirror the in-memory tier order: exact label -> bare callable name ->
        # exact source_file -> substring (#1353). Without the bare-name tier a
        # query like "foo" failed to resolve to "foo()" on the native path.
        for kwargs in ({"label": query}, {"label_bare": _bare_name(query)}):
            matches = graph.find_node_ids(limit=2, **kwargs)
            if len(matches) == 1:
                return str(matches[0])
        # source_file tier: when several nodes share the file, prefer the
        # file-level node, exactly as the in-memory path does — otherwise a
        # path query is ambiguous natively but resolves in memory.
        src_matches = [str(m) for m in graph.find_node_ids(source_file=query, limit=50)]
        if len(src_matches) == 1:
            return src_matches[0]
        if src_matches:
            preferred = _prefer_file_node(graph, src_matches, query)
            if preferred is not None:
                return preferred
        matches = graph.find_node_ids(limit=2, label_contains=query)
        if len(matches) == 1:
            return str(matches[0])
        return None
    # In-memory fallback (nx / MemGraph) — normalized + bare-name matching (#1353).
    if query in graph:
        return query
    query_lower = _normalize_label(query)
    exact_label_matches = [
        str(node_id)
        for node_id, data in graph.nodes(data=True)
        if _normalize_label(str(data.get("label", ""))) == query_lower
    ]
    if len(exact_label_matches) == 1:
        return exact_label_matches[0]
    # Callable labels are decorated ("name()"), so a bare "name" query falls
    # through exact matching and then ties with any "name*" sibling in the
    # contains pass. Match on the undecorated name before giving up.
    query_bare = _bare_name(query_lower)
    bare_name_matches = [
        str(node_id)
        for node_id, data in graph.nodes(data=True)
        if _bare_name(str(data.get("label", ""))) == query_bare
    ]
    if len(bare_name_matches) == 1:
        return bare_name_matches[0]
    exact_source_matches = [
        str(node_id)
        for node_id, data in graph.nodes(data=True)
        if _normalize_label(str(data.get("source_file", ""))) == query_lower
    ]
    if len(exact_source_matches) == 1:
        return exact_source_matches[0]
    if exact_source_matches:
        preferred_file_node = _prefer_file_node(graph, exact_source_matches, query)
        if preferred_file_node is not None:
            return preferred_file_node
    contains_matches = [
        str(node_id)
        for node_id, data in graph.nodes(data=True)
        if query_lower in _normalize_label(str(data.get("label", "")))
    ]
    if len(contains_matches) == 1:
        return contains_matches[0]
    return None


def affected_nodes(
    graph: nx.Graph,
    seed: str,
    *,
    relations: Iterable[str] = DEFAULT_AFFECTED_RELATIONS,
    depth: int = 2,
) -> list[AffectedHit]:
    relation_set = set(relations)

    # FalkorDB-native: one batched reverse-edge query per BFS level (depth queries
    # total) instead of a per-node loop over an in-memory copy of the graph.
    if hasattr(graph, "incoming_edges"):
        seen = {seed}
        hits: list[AffectedHit] = []
        frontier = [seed]
        # #1669: seed the reverse walk with the root's own member nodes (one
        # outward `method`/`contains` hop), mirroring the in-memory path. A caller
        # can bind to a class's method node rather than the class node itself, so
        # those callers are otherwise unreachable. Seeds only — not reported as
        # hits, and `method`/`contains` stay out of the relation-filtered walk.
        if hasattr(graph, "member_nodes"):
            for member in sorted(str(m) for m in graph.member_nodes(seed)):
                if member not in seen:
                    seen.add(member)
                    frontier.append(member)
        for d in range(depth):
            if not frontier:
                break
            rows = graph.incoming_edges(frontier, relation_set)
            nxt: list[str] = []
            for _fid, src, relation, via_file, via_loc in sorted(
                rows, key=lambda r: (str(r[0]), str(r[1]), str(r[2]))
            ):
                src = str(src)
                if src in seen:
                    continue
                seen.add(src)
                # Location comes from the SAME edge whose relation passed the
                # filter, so relation and site stay consistent (#BUG1).
                hits.append(AffectedHit(
                    src, d + 1, str(relation),
                    via_file=str(via_file or "") or None,
                    via_location=str(via_loc or "") or None,
                ))
                nxt.append(src)
            frontier = nxt
        return hits

    # In-memory fallback (nx / MemGraph)
    seen = {seed}
    queue: deque[tuple[str, int]] = deque([(seed, 0)])
    hits: list[AffectedHit] = []

    # #1669: seed the reverse walk with the root's own member nodes (one outward
    # `method`/`contains` hop). A caller can bind to a class's method node rather
    # than the class node itself (e.g. `Service.call` resolves to the `def
    # self.call` node, #1634), so those callers are unreachable from the class
    # otherwise. The member nodes are seeds only (not reported as hits), and
    # `method`/`contains` stay out of the general relation-filtered walk, so this
    # adds no forward noise anywhere else.
    if hasattr(graph, "out_edges"):
        member_edges = graph.out_edges(seed, data=True)
    else:
        member_edges = (
            (s, t, d) for s, t, d in graph.edges(data=True) if s == seed
        )
    for _s, member, data in member_edges:
        if str(data.get("relation", "")) not in ("method", "contains"):
            continue
        member = str(member)
        if member not in seen:
            seen.add(member)
            queue.append((member, 0))

    while queue:
        current, current_depth = queue.popleft()
        if current_depth >= depth:
            continue
        if hasattr(graph, "in_edges"):
            incoming = graph.in_edges(current, data=True)
        else:
            incoming = (
                (source, target, data)
                for source, target, data in graph.edges(data=True)
                if target == current
            )
        for source, _target, data in incoming:
            relation = str(data.get("relation", ""))
            if relation not in relation_set:
                continue
            source = str(source)
            if source in seen:
                continue
            seen.add(source)
            # Carry the matched edge's location (taken from the SAME edge dict
            # whose relation passed the filter, so relation and location stay
            # consistent) — that is the call/import/reference site in `source`'s
            # own file, which is where the user should click (#BUG1).
            hit = AffectedHit(
                source, current_depth + 1, relation,
                via_file=str(data.get("source_file") or "") or None,
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
) -> str:
    relation_list = tuple(relations)
    seed = resolve_seed(graph, query)
    if seed is None:
        return f"No unique node match for {query}"

    hits = affected_nodes(graph, seed, relations=relation_list, depth=depth)

    # Fetch attrs for seed + all hits in one batched query (native) or per-node (fallback).
    ids = [seed] + [h.node_id for h in hits]
    if hasattr(graph, "node_attrs_batch"):
        attrs = graph.node_attrs_batch(ids)
    else:
        attrs = {nid: dict(graph.nodes[nid]) for nid in ids if nid in graph}

    def _label(nid):
        return str(attrs.get(nid, {}).get("label") or nid)

    lines = [
        f"Affected nodes for {_label(seed)}",
        f"Relations: {', '.join(relation_list)}",
        f"Depth: {depth}",
    ]
    if not hits:
        lines.append("No affected nodes found.")
        return "\n".join(lines)

    for hit in hits:
        data = attrs.get(hit.node_id, {})
        if hit.via_location:
            # The relation SITE in this node's file (call/import/reference line),
            # labeled by [via_relation] so it's never mistaken for a def line.
            location = f"{hit.via_file or data.get('source_file') or '-'}:{hit.via_location}"
        else:
            location = _format_location(data)  # honest fallback: the node's own def line
        lines.append(
            f"- {_label(hit.node_id)} [{hit.via_relation}] {location}"
        )
    return "\n".join(lines)


def connect_graph(path: Path):
    """Open a connection to the FalkorDB-backed graph for the output dir containing
    `path`. Cache-free: returns a store handle (a connection), it does NOT load the
    graph into memory.

    `path` is the legacy graph.json location (e.g. graphify-out/graph.json); we
    use its parent directory to locate the FalkorDB pointer and open the store.
    """
    from .store import open_store

    resolved = Path(path)
    out_dir = resolved.parent if resolved.suffix else resolved
    store = open_store(out_dir, create=False)
    if store.number_of_nodes() == 0:
        # Back-compat: the store is empty but a node-link graph.json may still
        # hold the graph (a pre-FalkorDB project, or a `--no-cluster` run that
        # only wrote JSON). Import it on first use, exactly as serve._connect_graph
        # does, so `affected`/`god-nodes` stay usable on the same graphs `query`
        # and `explain` can already read.
        from .serve import _import_graph_json_into_store

        gj = resolved if resolved.suffix == ".json" else (out_dir / "graph.json")
        _import_graph_json_into_store(gj, store)
    # open_store(create=False) hands back a store even when no graph was built
    # (it derives a name from the pointer/root rather than erroring), so guard the
    # empty case here — matching serve._connect_graph — so `graphify affected`
    # tells the user to build instead of silently reporting nothing.
    if store.number_of_nodes() == 0:
        raise FileNotFoundError(
            f"No graph found for {out_dir} (FalkorDB graph empty). Re-run /graphify to build."
        )
    return store
