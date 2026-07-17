"""Native Leiden and community-state behavior."""

from graphify.cluster import (
    cluster,
    cohesion_score,
    community_member_sigs,
    label_communities_by_hub,
    remap_communities_to_previous,
    score_all,
)
from tests.native_helpers import graph_from_payload


def _dense_groups():
    nodes = [{"id": name, "label": name.upper()} for name in "abcdef"]
    edges = [
        {"source": left, "target": right, "relation": "related", "weight": 1.0}
        for group in ("abc", "def")
        for index, left in enumerate(group)
        for right in group[index + 1:]
    ]
    return graph_from_payload(nodes, edges)


def test_native_leiden_clusters_dense_groups():
    communities = cluster(_dense_groups())
    assert {frozenset(group) for group in communities.values()} == {
        frozenset("abc"), frozenset("def")
    }


def test_isolates_cohesion_and_score_keys():
    graph = graph_from_payload([{"id": "a"}, {"id": "b"}])
    communities = cluster(graph)
    assert communities == {0: ["a"], 1: ["b"]}
    assert cohesion_score(graph, ["a"]) == 1.0
    assert cohesion_score(graph, ["a", "b"]) == 0.0
    assert set(score_all(graph, communities)) == set(communities)


def test_hub_labels_are_deterministic():
    graph = graph_from_payload(
        [{"id": "hub", "label": "Hub()"}, {"id": "leaf", "label": "Leaf"}],
        [{"source": "hub", "target": "leaf", "relation": "calls"}],
    )
    assert label_communities_by_hub(graph, {3: ["leaf", "hub"]}) == {3: "Hub"}


def test_remap_and_signatures_are_stable():
    communities = {10: ["a", "b", "c"], 11: ["d", "e"]}
    previous = {"a": 5, "b": 5, "c": 5, "d": 1, "e": 1}
    remapped = remap_communities_to_previous(communities, previous)
    assert remapped == {5: ["a", "b", "c"], 1: ["d", "e"]}
    assert community_member_sigs({0: ["a", "b"]}) == community_member_sigs({0: ["b", "a"]})


def test_hub_exclusion_preserves_every_node():
    nodes = [{"id": "hub"}] + [{"id": f"n{i}"} for i in range(12)]
    edges = [
        {"source": "hub", "target": f"n{i}", "relation": "uses"}
        for i in range(12)
    ]
    graph = graph_from_payload(nodes, edges)
    communities = cluster(graph, exclude_hubs_percentile=80)
    assert {node for members in communities.values() for node in members} == {
        node["id"] for node in nodes
    }
