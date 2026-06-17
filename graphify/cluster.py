"""Community detection on the FalkorDB-backed GraphStore. Runs Louvain via a
server-side JS UDF (graphify_algos.louvain), splits oversized/low-cohesion
communities, and returns stable community IDs with cohesion scores."""
from __future__ import annotations


def _partition(G, resolution: float = 1.0) -> dict[str, int]:
    """Run Louvain community detection. Returns {node_id: community_id}.

    Delegates to the server-side `graphify_algos.louvain` UDF (deterministic:
    sorted node order, no RNG). `G` is a GraphStore or a subgraph view, both of
    which expose `louvain_partition(resolution)`.

    resolution > 1.0 → more, smaller communities; < 1.0 → fewer, larger.
    """
    return G.louvain_partition(resolution=resolution)


_MAX_COMMUNITY_FRACTION = 0.25   # communities larger than 25% of graph get split
_MIN_SPLIT_SIZE = 10             # only split if community has at least this many nodes
_COHESION_SPLIT_THRESHOLD = 0.05 # re-split communities with cohesion below this
_COHESION_SPLIT_MIN_SIZE = 50    # only cohesion-split if community has at least this many nodes


def cluster(
    G: nx.Graph,
    resolution: float = 1.0,
    exclude_hubs_percentile: float | None = None,
) -> dict[int, list[str]]:
    """Run Leiden community detection. Returns {community_id: [node_ids]}.

    Community IDs are stable across runs: 0 = largest community after splitting.
    Oversized communities (> 25% of graph nodes, min 10) are split by running
    a second Leiden pass on the subgraph.

    Accepts directed or undirected graphs. DiGraphs are converted to undirected
    internally since Louvain/Leiden require undirected input.

    resolution: passed to Leiden/Louvain. >1.0 = more smaller communities,
        <1.0 = fewer larger communities. Default 1.0.
    exclude_hubs_percentile: if set (0-100), nodes whose degree exceeds this
        percentile are excluded from partitioning and reattached to their
        majority-vote neighbour community afterwards. Useful for staging/utility
        super-hubs that inflate god-node rankings (#919).
    """
    if G.number_of_nodes() == 0:
        return {}
    if G.is_directed():
        G = G.to_undirected()
    if G.number_of_edges() == 0:
        return {i: [n] for i, n in enumerate(sorted(G.nodes))}

    # Compute hub exclusion set before removing anything so degree is based on full graph
    hub_nodes: set[str] = set()
    if exclude_hubs_percentile is not None:
        degrees = sorted(d for _, d in G.degree())
        if degrees:
            idx = max(0, int(len(degrees) * exclude_hubs_percentile / 100) - 1)
            threshold = degrees[idx]
            hub_nodes = {n for n, d in G.degree() if d > threshold}

    # Leiden warns and drops isolates - handle them separately
    # Also exclude hub nodes from partitioning so they don't pull unrelated
    # subsystems into the same community
    excluded = hub_nodes
    isolates = [n for n in G.nodes() if G.degree(n) == 0 and n not in excluded]
    connected_nodes = [n for n in G.nodes() if G.degree(n) > 0 and n not in excluded]
    connected = G.subgraph(connected_nodes)

    raw: dict[int, list[str]] = {}
    if connected.number_of_nodes() > 0:
        partition = _partition(connected, resolution=resolution)
        for node, cid in partition.items():
            raw.setdefault(cid, []).append(node)

    # Each isolate becomes its own single-node community
    next_cid = max(raw.keys(), default=-1) + 1
    for node in isolates:
        raw[next_cid] = [node]
        next_cid += 1

    # Reattach excluded hubs by majority-vote neighbour community
    if hub_nodes:
        node_community: dict[str, int] = {n: cid for cid, nodes in raw.items() for n in nodes}
        for hub in sorted(hub_nodes):
            votes: dict[int, int] = {}
            for nb in G.neighbors(hub):
                cid = node_community.get(nb)
                if cid is not None:
                    votes[cid] = votes.get(cid, 0) + 1
            if votes:
                best = min(votes, key=lambda c: (-votes[c], c))
                raw.setdefault(best, []).append(hub)
                node_community[hub] = best
            else:
                raw[next_cid] = [hub]
                node_community[hub] = next_cid
                next_cid += 1

    # Split oversized communities
    max_size = max(_MIN_SPLIT_SIZE, int(G.number_of_nodes() * _MAX_COMMUNITY_FRACTION))
    final_communities: list[list[str]] = []
    for nodes in raw.values():
        if len(nodes) > max_size:
            final_communities.extend(_split_community(G, nodes))
        else:
            final_communities.append(nodes)

    # Second pass: re-split low-cohesion communities caused by doc-hub nodes
    # that bridge otherwise-unrelated subsystems (e.g. CLAUDE.md connected to everything).
    second_pass: list[list[str]] = []
    for nodes in final_communities:
        if len(nodes) >= _COHESION_SPLIT_MIN_SIZE and cohesion_score(G, nodes) < _COHESION_SPLIT_THRESHOLD:
            splits = _split_community(G, nodes)
            second_pass.extend(splits if len(splits) > 1 else [nodes])
        else:
            second_pass.append(nodes)
    final_communities = second_pass

    # Re-index by size descending. The tuple(sorted(nodes)) tiebreak makes this a
    # TOTAL order, so an identical grouping always gets identical community IDs.
    # Without it, the hundreds of equal-sized small communities are ordered by the
    # partitioner's (not seed-stable) enumeration order, so their integer IDs
    # permute run-to-run - which reads as massive "community churn" in a per-node
    # cid diff even though the actual grouping is reproducible (#1090 follow-up).
    final_communities.sort(key=lambda nodes: (-len(nodes), tuple(sorted(map(str, nodes)))))
    return {i: sorted(nodes) for i, nodes in enumerate(final_communities)}


def _split_community(G: nx.Graph, nodes: list[str]) -> list[list[str]]:
    """Run a second Leiden pass on a community subgraph to split it further."""
    subgraph = G.subgraph(nodes)
    if subgraph.number_of_edges() == 0:
        # No edges - split into individual nodes
        return [[n] for n in sorted(nodes)]
    try:
        sub_partition = _partition(subgraph)
        sub_communities: dict[int, list[str]] = {}
        for node, cid in sub_partition.items():
            sub_communities.setdefault(cid, []).append(node)
        if len(sub_communities) <= 1:
            return [sorted(nodes)]
        return [sorted(v) for v in sub_communities.values()]
    except Exception:
        return [sorted(nodes)]


def cohesion_score(G: nx.Graph, community_nodes: list[str]) -> float:
    """Ratio of actual intra-community edges to maximum possible."""
    n = len(community_nodes)
    if n <= 1:
        return 1.0
    subgraph = G.subgraph(community_nodes)
    actual = subgraph.number_of_edges()
    possible = n * (n - 1) / 2
    return actual / possible if possible > 0 else 0.0


def score_all(G: nx.Graph, communities: dict[int, list[str]]) -> dict[int, float]:
    return {cid: cohesion_score(G, nodes) for cid, nodes in communities.items()}


def remap_communities_to_previous(
    communities: dict[int, list[str]],
    previous_node_community: dict[str, int],
) -> dict[int, list[str]]:
    """Remap community IDs to maximize overlap with a previous assignment.

    Uses greedy one-to-one matching by intersection size, then assigns fresh IDs
    to unmatched communities in deterministic order (size desc, lexical tie-break).
    """
    if not communities:
        return {}

    new_sets = {cid: set(nodes) for cid, nodes in communities.items()}
    old_sets: dict[int, set[str]] = {}
    for node, old_cid in previous_node_community.items():
        old_sets.setdefault(old_cid, set()).add(node)

    overlaps: list[tuple[int, int, int]] = []
    for old_cid, old_nodes in old_sets.items():
        for new_cid, new_nodes in new_sets.items():
            overlap = len(old_nodes & new_nodes)
            if overlap > 0:
                overlaps.append((overlap, old_cid, new_cid))
    overlaps.sort(key=lambda x: (-x[0], x[1], x[2]))

    new_to_final: dict[int, int] = {}
    used_old_ids: set[int] = set()
    matched_new_ids: set[int] = set()
    for _overlap, old_cid, new_cid in overlaps:
        if old_cid in used_old_ids or new_cid in matched_new_ids:
            continue
        new_to_final[new_cid] = old_cid
        used_old_ids.add(old_cid)
        matched_new_ids.add(new_cid)

    unmatched = [cid for cid in communities if cid not in matched_new_ids]
    unmatched.sort(key=lambda cid: (-len(communities[cid]), tuple(sorted(communities[cid]))))
    next_id = 0
    for new_cid in unmatched:
        while next_id in used_old_ids:
            next_id += 1
        new_to_final[new_cid] = next_id
        used_old_ids.add(next_id)
        next_id += 1

    remapped: dict[int, list[str]] = {}
    for new_cid, nodes in communities.items():
        remapped[new_to_final[new_cid]] = sorted(nodes)
    return dict(sorted(remapped.items(), key=lambda kv: kv[0]))
