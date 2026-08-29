import json
import sys
import networkx as nx
from pathlib import Path
from graphify.build import build_from_json
from graphify.cluster import cluster, cohesion_score, remap_communities_to_previous, score_all

FIXTURES = Path(__file__).parent / "fixtures"

def make_graph():
    return build_from_json(json.loads((FIXTURES / "extraction.json").read_text()))

def test_cluster_returns_dict():
    G = make_graph()
    communities = cluster(G)
    assert isinstance(communities, dict)

def test_cluster_covers_all_nodes():
    G = make_graph()
    communities = cluster(G)
    all_nodes = {n for nodes in communities.values() for n in nodes}
    assert all_nodes == set(G.nodes)

def test_cohesion_score_complete_graph():
    G = nx.complete_graph(4)
    G = nx.relabel_nodes(G, {i: str(i) for i in G.nodes})
    score = cohesion_score(G, list(G.nodes))
    assert score == 1.0

def test_cohesion_score_single_node():
    G = nx.Graph()
    G.add_node("a")
    score = cohesion_score(G, ["a"])
    assert score == 1.0

def test_cohesion_score_disconnected():
    G = nx.Graph()
    G.add_nodes_from(["a", "b", "c"])
    score = cohesion_score(G, ["a", "b", "c"])
    assert score == 0.0

def test_cohesion_score_range():
    G = make_graph()
    communities = cluster(G)
    for cid, nodes in communities.items():
        score = cohesion_score(G, nodes)
        assert 0.0 <= score <= 1.0

def test_score_all_keys_match_communities():
    G = make_graph()
    communities = cluster(G)
    scores = score_all(G, communities)
    assert set(scores.keys()) == set(communities.keys())


def test_cluster_does_not_write_to_stdout(capsys):
    """Clustering should not emit ANSI escape codes or other output.

    graspologic's leiden() can emit ANSI escape sequences that break
    PowerShell 5.1's scroll buffer on Windows (issue #19). The output
    suppression in _partition() should prevent any output from leaking.
    """
    G = make_graph()
    cluster(G)
    captured = capsys.readouterr()
    assert captured.out == "", f"cluster() wrote to stdout: {captured.out!r}"


def test_cluster_does_not_write_to_stderr(capsys):
    """Same as above but for stderr — ANSI codes can go to either stream."""
    G = make_graph()
    cluster(G)
    captured = capsys.readouterr()
    # Allow logging output (starts with [graphify]) but no raw ANSI codes
    for line in captured.err.splitlines():
        assert "\x1b" not in line, f"cluster() wrote ANSI to stderr: {line!r}"


def test_remap_communities_to_previous_reuses_old_ids():
    communities = {
        10: ["a", "b", "c"],
        11: ["d", "e"],
    }
    previous = {"a": 5, "b": 5, "c": 5, "d": 1, "e": 1}
    remapped = remap_communities_to_previous(communities, previous)
    assert set(remapped.keys()) == {1, 5}
    assert remapped[5] == ["a", "b", "c"]
    assert remapped[1] == ["d", "e"]


def test_remap_communities_to_previous_assigns_deterministic_new_ids():
    communities = {
        7: ["x", "y", "z"],
        8: ["m"],
    }
    previous = {"a": 3}
    remapped = remap_communities_to_previous(communities, previous)
    assert list(remapped.keys()) == [0, 1]
    assert remapped[0] == ["x", "y", "z"]
    assert remapped[1] == ["m"]


def _grouping(partition):
    """Canonicalize {node: community_id} into a set of frozenset node-groups,
    so two partitions compare equal regardless of the community-id labels."""
    from collections import defaultdict
    groups = defaultdict(set)
    for node, cid in partition.items():
        groups[cid].add(node)
    return {frozenset(s) for s in groups.values()}


def test_native_leiden_matches_graspologic_wrapper(monkeypatch):
    """#3104: the direct graspologic_native path must produce the SAME partition
    as the graspologic wrapper it replaces. Run _partition with the native path
    active, then with _native_leiden forced to fall through to the wrapper, and
    assert identical node groupings. Skips unless both are installed."""
    import importlib.util
    import pytest
    if not (importlib.util.find_spec("graspologic_native")
            and importlib.util.find_spec("graspologic")):
        pytest.skip("graspologic / graspologic_native not installed")
    import graphify.cluster as cl

    # Two triangles joined by a single edge: an unambiguous 2-community split.
    G = nx.Graph()
    for a, b in [("a1", "a2"), ("a1", "a3"), ("a2", "a3"),
                 ("b1", "b2"), ("b1", "b3"), ("b2", "b3"), ("a1", "b1")]:
        G.add_edge(a, b)

    native = cl._partition(G, 1.0)
    monkeypatch.setattr(cl, "_native_leiden", lambda *a, **k: None)
    wrapper = cl._partition(G, 1.0)

    assert _grouping(native) == _grouping(wrapper), (
        f"native path diverged from the wrapper: {native} vs {wrapper}"
    )


def test_native_leiden_returns_none_when_binding_absent(monkeypatch):
    """When graspologic_native cannot be imported, _native_leiden must return
    None so _partition falls through to the wrapper / Louvain, not crash."""
    import graphify.cluster as cl
    monkeypatch.setitem(sys.modules, "graspologic_native", None)  # import → ImportError
    stable = nx.Graph()
    stable.add_edge("x", "y")
    assert cl._native_leiden(stable, 1.0) is None


def test_partition_is_invariant_to_edge_endpoint_orientation():
    """#3146: for an undirected graph, (a,b) and (b,a) are the same edge, but the
    orientation networkx yields can vary across builds/machines. _partition must
    canonicalise endpoints so the ordering fed to the clusterer — and thus the
    resulting communities — is identical regardless of how edges were inserted."""
    import random
    edges = [
        ("a1", "a2"), ("a1", "a3"), ("a2", "a3"), ("a3", "a4"),
        ("b1", "b2"), ("b1", "b3"), ("b2", "b3"), ("b3", "b4"),
        ("a1", "b1"),
    ]

    def build(order, flip):
        G = nx.Graph()
        for n in order:
            G.add_node(n)
        for (u, v) in edges:
            G.add_edge(v, u) if flip else G.add_edge(u, v)
        return G

    nodes = sorted({n for e in edges for n in e})
    forward = build(nodes, flip=False)
    shuffled = list(nodes)
    random.Random(0).shuffle(shuffled)
    flipped = build(shuffled, flip=True)

    from graphify.cluster import _partition
    assert _grouping(_partition(forward, 1.0)) == _grouping(_partition(flipped, 1.0)), (
        "partition drifted with edge-endpoint orientation / insertion order"
    )
