"""Deterministic, LLM-free community labels — `label_communities_by_hub`.

Names each community after its highest-degree member so a report reads "log_action"
instead of "Community 70", with no backend. Ties break by node id for run-to-run
stability; a community with no members present in the graph falls back to "Community N".
"""
import networkx as nx

from graphify.cluster import label_communities_by_hub


def _g(node_labels, edges):
    g = nx.Graph()
    for nid, label in node_labels.items():
        if label is None:
            g.add_node(nid)
        else:
            g.add_node(nid, label=label)
    g.add_edges_from(edges)
    return g


def test_labels_by_highest_degree_hub():
    # 'a' is the hub (degree 3); the community is named after it, "()" stripped.
    g = _g(
        {"a": "log_action()", "b": "b()", "c": "c()", "d": "d()"},
        [("a", "b"), ("a", "c"), ("a", "d")],
    )
    labels = label_communities_by_hub(g, {0: ["a", "b", "c", "d"]})
    assert labels[0] == "log_action"


def test_not_a_placeholder_for_a_real_community():
    g = _g({"a": "handler()", "b": "b()"}, [("a", "b")])
    labels = label_communities_by_hub(g, {0: ["a", "b"]})
    assert labels[0] == "handler" and labels[0] != "Community 0"


def test_tie_breaks_deterministically_by_node_id():
    # both nodes degree 1 → the lexicographically smaller id wins, regardless of order
    g = _g({"z": "z()", "a": "a()"}, [("z", "a")])
    assert label_communities_by_hub(g, {0: ["z", "a"]})[0] == "a"
    assert label_communities_by_hub(g, {0: ["a", "z"]})[0] == "a"


def test_absent_members_fall_back_to_placeholder():
    # no member of community 5 is in the graph → keep the "Community N" placeholder
    g = _g({"a": "a()"}, [])
    assert label_communities_by_hub(g, {5: ["ghost1", "ghost2"]})[5] == "Community 5"


def test_node_without_label_attr_uses_id():
    g = nx.Graph()
    g.add_nodes_from(["hub", "x", "y"])
    g.add_edges_from([("hub", "x"), ("hub", "y")])  # hub degree 2, no label attrs
    assert label_communities_by_hub(g, {0: ["hub", "x", "y"]})[0] == "hub"


def test_multiple_communities_each_get_their_own_hub():
    g = _g(
        {"h1": "auth()", "a1": "a1()", "a2": "a2()",
         "h2": "billing()", "b1": "b1()", "b2": "b2()"},
        [("h1", "a1"), ("h1", "a2"), ("h2", "b1"), ("h2", "b2")],
    )
    labels = label_communities_by_hub(g, {0: ["h1", "a1", "a2"], 1: ["h2", "b1", "b2"]})
    assert labels[0] == "auth" and labels[1] == "billing"


# ── community membership signatures (stale-label detection, cluster-only) ──────

def test_community_member_sigs_are_deterministic_and_order_independent():
    from graphify.cluster import community_member_sigs
    a = community_member_sigs({0: ["x", "y", "z"], 1: ["a"]})
    b = community_member_sigs({0: ["z", "x", "y"], 1: ["a"]})  # member order shuffled
    assert a == b
    assert a[0] != a[1]


def test_community_member_sigs_change_when_membership_changes():
    from graphify.cluster import community_member_sigs
    before = community_member_sigs({0: ["x", "y", "z"]})
    after = community_member_sigs({0: ["x", "y"]})  # a node left the community
    assert before[0] != after[0], "signature must change when a community's members change"
