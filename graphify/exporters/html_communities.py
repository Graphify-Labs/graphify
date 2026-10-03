"""Prepare offline HTML grouping and names without changing accepted graph facts.

Large aggregate views need a complete partition so every source node is counted.
Small full-node views retain their supplied membership rather than initiating an
unexpected clustering pass. Hub names use the existing deterministic labeler.
"""
from __future__ import annotations

import networkx as nx

from graphify.cluster import cluster, label_communities_by_hub


def _complete_partition(graph: nx.Graph, groups: dict[int, list[str]]) -> bool:
    """Reject stale, duplicate and malformed membership before aggregation."""
    if not isinstance(groups, dict):
        return False
    seen: set[str] = set()
    for cid, members in groups.items():
        if isinstance(cid, bool) or not isinstance(cid, int):
            return False
        if not isinstance(members, list) or not members:
            return False
        for node in members:
            try:
                if node not in graph or node in seen:
                    return False
                seen.add(node)
            except TypeError:
                return False
    return seen == set(graph)


def prepare_html_communities(
    graph: nx.Graph,
    communities: dict[int, list[str]],
    community_labels: dict[int, str] | None,
    *,
    recover_missing: bool,
) -> tuple[dict[int, list[str]], dict[int, str]]:
    """Return export-local membership and complete names for accepted groups.

    Recovered partitions must pass the same complete-membership check as saved
    partitions. Failure raises a bounded diagnostic before the exporter writes.
    Names from an invalid partition are stale even if numeric IDs get reused.
    """
    if not graph:
        return {}, {}

    rebuilt = recover_missing and not _complete_partition(graph, communities)
    if rebuilt:
        try:
            recovered = cluster(graph.copy())
        except Exception:
            raise ValueError(
                "HTML_GROUPING_INVALID: unable to compute HTML communities; retry export."
            ) from None
        if not _complete_partition(graph, recovered):
            raise ValueError(
                "HTML_GROUPING_INVALID: computed communities do not cover every graph node once."
            )
        groups = {cid: list(members) for cid, members in recovered.items()}
        supplied: dict[int, str] = {}
    else:
        groups = {cid: list(members) for cid, members in communities.items()}
        supplied = community_labels or {}

    # Full-node exports may intentionally have partial membership. Only groups
    # with accepted members belong in their legend; stale label-only IDs do not.
    named_groups = {
        cid: members for cid, members in groups.items()
        if members and any(node in graph for node in members)
    }
    fallbacks = label_communities_by_hub(graph, named_groups)
    labels: dict[int, str] = {}
    for cid in named_groups:
        label = supplied.get(cid)
        labels[cid] = label if isinstance(label, str) and label.strip() else fallbacks[cid]
    return groups, labels
