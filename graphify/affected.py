from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import heapq
from pathlib import Path
from typing import Iterable, Mapping
import unicodedata

import networkx as nx


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

DEFAULT_RELATION_WEIGHTS: Mapping[str, float] = {
    "calls": 1.0,
    "references": 0.9,
    "imports": 0.85,
    "imports_from": 0.85,
    "re_exports": 0.8,
    "inherits": 0.75,
    "extends": 0.75,
    "implements": 0.75,
    "uses": 1.0,
    "mixes_in": 0.9,
    "embeds": 0.7,
}


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


@dataclass(frozen=True)
class WeightedAffectedHit:
    node_id: str
    cost: float
    via_relation: str
    path: tuple[str, ...]


@dataclass(frozen=True)
class WeightedAffectedResult:
    hits: tuple[WeightedAffectedHit, ...]
    proof_paths: dict[str, tuple[str, ...]]
    metrics: dict[str, int | float]


@dataclass(frozen=True)
class PreparedAffectedGraph:
    graph: nx.Graph
    incoming: dict[str, tuple[tuple[str, str, str], ...]]
    degree: dict[str, int]


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


def _as_repo_relative(query: str, root: Path | None = None) -> str:
    """Repo-relative form of a path query, for matching a stored `source_file`.

    The graph stores repo-relative paths, so `./src/x.py` and
    `/abs/repo/src/x.py` name the same file as `src/x.py` and yet matched
    nothing. `affected` then printed an empty list and exited 0 — a blast-radius
    tool answering "nothing depends on this" about a file with sixteen
    dependents, and indistinguishable from a genuine zero or a typo.

    An absolute path is anchored to `root` when given — the repo root derived
    from the graph's own location — so a seed resolves regardless of the caller's
    working directory (#2706: an absolute-path seed previously only matched when
    cwd happened to be the analysed repo root, which no editor or script can
    guarantee). `root` falls back to the current directory to preserve the prior
    behaviour when a caller has no graph location to derive it from.

    Non-path queries pass through unchanged: `Path("myFunc()").as_posix()` is
    `"myFunc()"`, so label resolution is untouched. An absolute path rooted
    outside `root` is left alone — no basename guessing.
    """
    path = Path(query)
    if path.is_absolute():
        anchor = root if root is not None else Path.cwd()
        try:
            return path.relative_to(anchor).as_posix()
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


def resolve_seed(graph: nx.Graph, query: str, root: Path | None = None) -> str | None:
    # A trailing path separator must not change a source-file match — serve's
    # _find_node tokenizes the path (which drops it), so strip it here for parity
    # (otherwise `affected "src/x.ts/"` returned None while `explain` resolved it).
    query = query.rstrip("/\\") or query
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
    # Compare paths in repo-relative form. Only this branch is path-shaped; the
    # label branches above keep the query verbatim.
    query_path = _normalize_label(_as_repo_relative(query, root))
    exact_source_matches = [
        str(node_id)
        for node_id, data in graph.nodes(data=True)
        if _normalize_label(str(data.get("source_file", ""))) in (query_lower, query_path)
    ]
    if len(exact_source_matches) == 1:
        return exact_source_matches[0]
    if exact_source_matches:
        preferred_file_node = _prefer_file_node(
            graph, exact_source_matches, _as_repo_relative(query, root)
        )
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


def prepare_affected_graph(graph: nx.Graph) -> PreparedAffectedGraph:
    incoming: dict[str, list[tuple[str, str, str]]] = {}
    for source, target, data in graph.edges(data=True):
        source_id = str(source)
        target_id = str(target)
        relation = str(data.get("relation", ""))
        incoming.setdefault(target_id, []).append((source_id, target_id, relation))
    ordered = {
        node_id: tuple(sorted(edges, key=lambda edge: (edge[0], edge[2])))
        for node_id, edges in incoming.items()
    }
    degree = {str(node_id): int(deg) for node_id, deg in graph.degree()}
    return PreparedAffectedGraph(graph=graph, incoming=ordered, degree=degree)


def _path_to_seed(parent: Mapping[str, tuple[str, str]], seed: str, node_id: str) -> tuple[str, ...]:
    path = [node_id]
    current = node_id
    for _ in range(500):
        if current == seed:
            return tuple(path)
        nxt = parent.get(current)
        if not nxt:
            return tuple()
        current = nxt[0]
        path.append(current)
    return tuple()


def weighted_affected_details(
    graph: nx.Graph,
    seed: str,
    *,
    relations: Iterable[str] = DEFAULT_AFFECTED_RELATIONS,
    relation_weights: Mapping[str, float] | None = None,
    max_cost: float | None = None,
    max_nodes: int = 200,
    hub_degree: int | None = None,
    hub_penalty: float = 2.0,
    expand_hubs: bool = False,
    proof_targets: Iterable[str] = (),
) -> WeightedAffectedResult:
    relation_set = set(relations)
    weights = dict(DEFAULT_RELATION_WEIGHTS)
    if relation_weights:
        weights.update({str(k): float(v) for k, v in relation_weights.items()})
    prepared = prepare_affected_graph(graph)
    limit = max(1, int(max_nodes))
    max_allowed_cost = float("inf") if max_cost is None else max(0.0, float(max_cost))
    hub_threshold = None if hub_degree is None else max(1, int(hub_degree))
    penalty = max(0.0, float(hub_penalty))

    dist: dict[str, float] = {seed: 0.0}
    parent: dict[str, tuple[str, str]] = {}
    via: dict[str, str] = {}
    queue: list[tuple[float, int, str]] = [(0.0, 0, seed)]
    counter = 1
    visited: set[str] = set()
    hits: list[WeightedAffectedHit] = []
    traversed_edges = 0
    hub_skips = 0
    max_seen_cost = 0.0

    while queue and len(hits) < limit:
        cost, _order, current = heapq.heappop(queue)
        if current in visited:
            continue
        if cost != dist.get(current):
            continue
        visited.add(current)
        max_seen_cost = max(max_seen_cost, cost)
        if current != seed:
            path = _path_to_seed(parent, seed, current)
            hits.append(
                WeightedAffectedHit(
                    node_id=current,
                    cost=round(cost, 6),
                    via_relation=via.get(current, ""),
                    path=path,
                )
            )

        is_hub = hub_threshold is not None and prepared.degree.get(current, 0) >= hub_threshold
        if current != seed and is_hub and not expand_hubs:
            hub_skips += 1
            continue

        for source, _target, relation in prepared.incoming.get(current, ()):
            if relation not in relation_set:
                continue
            traversed_edges += 1
            if source in visited:
                continue
            relation_cost = max(0.01, float(weights.get(relation, 1.0)))
            source_is_hub = hub_threshold is not None and prepared.degree.get(source, 0) >= hub_threshold
            next_cost = cost + relation_cost + (penalty if source_is_hub and source != seed else 0.0)
            if next_cost > max_allowed_cost:
                continue
            if next_cost < dist.get(source, float("inf")):
                dist[source] = next_cost
                parent[source] = (current, relation)
                via[source] = relation
                heapq.heappush(queue, (next_cost, counter, source))
                counter += 1

    proof_paths = {
        target: _path_to_seed(parent, seed, target)
        for target in proof_targets
        if target == seed or target in visited
    }
    return WeightedAffectedResult(
        hits=tuple(hits),
        proof_paths=proof_paths,
        metrics={
            "visited_nodes": len(visited),
            "traversed_edges": traversed_edges,
            "hub_skips": hub_skips,
            "max_cost": round(max_seen_cost, 6),
        },
    )


def weighted_affected_nodes(
    graph: nx.Graph,
    seed: str,
    *,
    relations: Iterable[str] = DEFAULT_AFFECTED_RELATIONS,
    relation_weights: Mapping[str, float] | None = None,
    max_cost: float | None = None,
    max_nodes: int = 200,
    hub_degree: int | None = None,
    hub_penalty: float = 2.0,
    expand_hubs: bool = False,
) -> list[WeightedAffectedHit]:
    return list(
        weighted_affected_details(
            graph,
            seed,
            relations=relations,
            relation_weights=relation_weights,
            max_cost=max_cost,
            max_nodes=max_nodes,
            hub_degree=hub_degree,
            hub_penalty=hub_penalty,
            expand_hubs=expand_hubs,
        ).hits
    )


def affected_proof_path(
    graph: nx.Graph,
    seed: str,
    target: str,
    *,
    relations: Iterable[str] = DEFAULT_AFFECTED_RELATIONS,
    relation_weights: Mapping[str, float] | None = None,
    max_cost: float | None = None,
    max_nodes: int = 200,
    hub_degree: int | None = None,
    hub_penalty: float = 2.0,
    expand_hubs: bool = False,
) -> tuple[str, ...]:
    if target == seed:
        return (seed,)
    details = weighted_affected_details(
        graph,
        seed,
        relations=relations,
        relation_weights=relation_weights,
        max_cost=max_cost,
        max_nodes=max_nodes,
        hub_degree=hub_degree,
        hub_penalty=hub_penalty,
        expand_hubs=expand_hubs,
        proof_targets=(target,),
    )
    return details.proof_paths.get(target, tuple())


def affected_nodes(
    graph: nx.Graph,
    seed: str,
    *,
    relations: Iterable[str] = DEFAULT_AFFECTED_RELATIONS,
    depth: int = 2,
) -> list[AffectedHit]:
    relation_set = set(relations)
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
    root: Path | None = None,
) -> str:
    relation_list = tuple(relations)
    seed = resolve_seed(graph, query, root)
    if seed is None:
        return f"No unique node match for {query}"

    hits = affected_nodes(graph, seed, relations=relation_list, depth=depth)
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
