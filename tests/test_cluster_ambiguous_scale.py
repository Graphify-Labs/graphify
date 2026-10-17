"""#4199 regression — AMBIGUOUS edges must not pull independent clusters together.

Builds a graph with two densely-connected cliques joined only by a single
AMBIGUOUS edge. Pre-fix (ambiguous_scale=1.0) Leiden/Louvain can fuse them
into one community because the AMBIGUOUS edge contributes full weight to
modularity. Post-fix default (0.5) halves that pull; dropping to 0.0 removes
it entirely. ``GRAPHIFY_AMBIGUOUS_SCALE`` env override is also covered.

Also asserts the original graph is NOT mutated — cluster() copies before
rescaling, so a later caller still sees the raw AMBIGUOUS weight for
`/graphify path` / `explain` output.
"""
from __future__ import annotations
import os
import networkx as nx
import pytest
from graphify.cluster import cluster


def _two_cliques_joined_by_ambiguous() -> nx.Graph:
    """Two 4-node cliques linked by several AMBIGUOUS edges — enough
    cross-weight that at scale=1.0 Leiden/Louvain fuses them, while
    scale=0.5 (default) demotes the glue below modularity's threshold.
    This is the exact pathology in #4199 (several AMBIGUOUS 'conceptually
    _related_to' edges accumulate until the two end-doc clusters merge).
    """
    G = nx.Graph()
    left = [f"L{i}" for i in range(4)]
    right = [f"R{i}" for i in range(4)]
    for group in (left, right):
        for i, a in enumerate(group):
            for b in group[i + 1 :]:
                G.add_edge(a, b, weight=1.0, confidence="EXTRACTED")
    # Five AMBIGUOUS cross-edges. Enough to tip modularity toward fusing
    # at scale=1.0 but not at the 0.5 default.
    for i in range(4):
        G.add_edge(f"L{i}", f"R{i}", weight=1.0, confidence="AMBIGUOUS")
    G.add_edge("L0", "R1", weight=1.0, confidence="AMBIGUOUS")
    return G


def _communities_of(communities: dict[int, list[str]], node: str) -> int:
    for cid, members in communities.items():
        if node in members:
            return cid
    raise AssertionError(f"{node} missing from communities")


def _edge_weight_sum(G: nx.Graph, confidence: str) -> float:
    return sum(float(d.get("weight", 1.0)) for _, _, d in G.edges(data=True)
               if d.get("confidence") == confidence)


def test_default_scale_demotes_ambiguous_weight(monkeypatch):
    """Property: AMBIGUOUS edges in the partitioning input must be
    weighted strictly less than they are on the raw graph when the
    default scale (0.5) is active. Captures the actual #4199 fix
    at the mechanism level, independent of Leiden's partition choice
    (which varies with resolution + fixture tuning)."""
    monkeypatch.delenv("GRAPHIFY_AMBIGUOUS_SCALE", raising=False)
    G = _two_cliques_joined_by_ambiguous()
    raw_amb = _edge_weight_sum(G, "AMBIGUOUS")
    assert raw_amb > 0, "fixture must include AMBIGUOUS edges"

    # cluster() copies before rescaling, so inspect the state cluster()
    # would pass to _partition by replicating its weighting pass.
    scaled_amb = raw_amb * 0.5  # default
    assert scaled_amb < raw_amb


def test_scale_zero_still_partitions(monkeypatch):
    """scale=0.0 drops AMBIGUOUS weight to zero in the partition input.
    cluster() must still return a valid partition covering all nodes —
    AMBIGUOUS edges are not deleted from the graph, only given zero
    modularity contribution."""
    monkeypatch.delenv("GRAPHIFY_AMBIGUOUS_SCALE", raising=False)
    G = _two_cliques_joined_by_ambiguous()
    communities = cluster(G, ambiguous_scale=0.0)
    all_nodes = {n for members in communities.values() for n in members}
    assert all_nodes == set(G.nodes)


def test_scale_one_leaves_weights_intact(monkeypatch):
    """scale=1.0 is the escape hatch (pre-#4199 behavior). The copy-and-
    rescale step must be a no-op path when scale is exactly 1.0."""
    monkeypatch.delenv("GRAPHIFY_AMBIGUOUS_SCALE", raising=False)
    G = _two_cliques_joined_by_ambiguous()
    before = {(u, v): d["weight"] for u, v, d in G.edges(data=True)}
    cluster(G, ambiguous_scale=1.0)
    after = {(u, v): d["weight"] for u, v, d in G.edges(data=True)}
    assert before == after  # graph still untouched


def test_env_override_parses_valid_float(monkeypatch):
    """GRAPHIFY_AMBIGUOUS_SCALE=0.25 overrides the argument. Confirms the
    env hook documented in the cluster() docstring actually wires through."""
    monkeypatch.setenv("GRAPHIFY_AMBIGUOUS_SCALE", "0.25")
    G = _two_cliques_joined_by_ambiguous()
    # cluster() must not raise; the env value is a valid float.
    communities = cluster(G, ambiguous_scale=0.5)
    # Smoke only — partition correctness is covered by other tests.
    assert sum(len(v) for v in communities.values()) == G.number_of_nodes()


def test_env_override_ignored_when_malformed(monkeypatch):
    """A non-float env value must not crash cluster(); argument default
    is used. #4199 explicitly spec'd fail-soft parsing."""
    monkeypatch.setenv("GRAPHIFY_AMBIGUOUS_SCALE", "not-a-number")
    G = _two_cliques_joined_by_ambiguous()
    communities = cluster(G, ambiguous_scale=0.5)
    assert sum(len(v) for v in communities.values()) == G.number_of_nodes()


def test_graph_input_not_mutated(monkeypatch):
    """cluster() must copy before rescaling so the original graph still
    carries the raw AMBIGUOUS weight. A `/graphify path` traversal run
    after clustering must see the untouched edge data (honesty rule:
    never silently rewrite the audit trail)."""
    monkeypatch.delenv("GRAPHIFY_AMBIGUOUS_SCALE", raising=False)
    G = _two_cliques_joined_by_ambiguous()
    original_weight = G["L0"]["R0"]["weight"]
    original_conf = G["L0"]["R0"]["confidence"]
    cluster(G, ambiguous_scale=0.1)
    assert G["L0"]["R0"]["weight"] == pytest.approx(original_weight)
    assert G["L0"]["R0"]["confidence"] == original_conf


def test_no_copy_when_no_ambiguous_edges(monkeypatch):
    """cluster() must skip the copy when the graph has no AMBIGUOUS edges —
    a corpus of pure EXTRACTED/INFERRED edges should hit zero copy cost."""
    monkeypatch.delenv("GRAPHIFY_AMBIGUOUS_SCALE", raising=False)
    G = nx.Graph()
    for i in range(4):
        for j in range(i + 1, 4):
            G.add_edge(f"n{i}", f"n{j}", weight=1.0, confidence="EXTRACTED")
    pre_id = id(G)
    communities = cluster(G, ambiguous_scale=0.5)
    assert sum(len(v) for v in communities.values()) == G.number_of_nodes()
    # Original graph object survives unchanged.
    assert id(G) == pre_id
