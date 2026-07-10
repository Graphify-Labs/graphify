"""Tests for graphify.ranking — Reciprocal Rank Fusion over query subgraphs."""
from __future__ import annotations

import networkx as nx

from graphify.ranking import RRF_K, RankedNode, rank_nodes, rrf_fuse


def test_rrf_fuse_sums_reciprocal_ranks():
    fused = rrf_fuse({"a": ["x", "y"], "b": ["y", "x"]}, k=RRF_K)
    # x: 1/(60+1) + 1/(60+2); y: 1/(60+2) + 1/(60+1) -> equal, both backends agree symmetrically
    assert abs(fused["x"].score - fused["y"].score) < 1e-12
    assert fused["x"].ranks == {"a": 1, "b": 2}
    assert fused["y"].ranks == {"a": 2, "b": 1}


def test_rrf_fuse_first_occurrence_wins_within_backend():
    fused = rrf_fuse({"a": ["x", "x", "y"]}, k=RRF_K)
    # duplicate x must not double-count; it keeps its best (rank 1) contribution
    assert fused["x"].ranks == {"a": 1}
    assert abs(fused["x"].contributions["a"] - 1.0 / (RRF_K + 1)) < 1e-12


def test_rrf_fuse_agreement_beats_single_backend_top():
    # y is #1 in one backend only; x is #2 in both. Consensus should win.
    fused = rrf_fuse({"a": ["y", "x"], "b": ["z", "x"]}, k=RRF_K)
    assert fused["x"].score > fused["y"].score
    assert fused["x"].score > fused["z"].score


def test_rank_nodes_pins_seeds_first():
    nodes = ["seed", "a", "b"]
    ranked = rank_nodes(
        nodes,
        ["seed"],
        lexical_scores={"a": 100.0, "b": 50.0, "seed": 1.0},
        degrees={"a": 9, "b": 9, "seed": 0},
    )
    # Even though 'a' dominates every non-seed signal, the seed renders first.
    assert ranked[0].node_id == "seed"


def test_rank_nodes_orders_rest_by_fused_score():
    nodes = ["seed", "a", "b"]
    ranked = rank_nodes(
        nodes,
        ["seed"],
        lexical_scores={"a": 100.0, "b": 1.0, "seed": 1.0},
        distances={"seed": 0, "a": 1, "b": 3},
        degrees={"a": 5, "b": 1, "seed": 0},
    )
    order = [r.node_id for r in ranked]
    assert order[0] == "seed"
    assert order.index("a") < order.index("b")


def test_rank_nodes_proximity_matters():
    # Isolate the proximity backend: the closer node must earn a strictly larger
    # proximity contribution than the far node (other backends are held equal, so
    # asserting final order would just measure the id tie-break, not proximity).
    ranked = rank_nodes(
        ["seed", "near", "far"],
        ["seed"],
        lexical_scores={"near": 5.0, "far": 5.0},
        distances={"seed": 0, "near": 1, "far": 6},
        degrees={"near": 2, "far": 2},
    )
    near = next(r for r in ranked if r.node_id == "near")
    far = next(r for r in ranked if r.node_id == "far")
    assert near.contributions["proximity"] > far.contributions["proximity"]


def test_rank_nodes_community_backend_only_with_seed_community():
    # No community info -> no 'community' backend contributes.
    ranked = rank_nodes(
        ["seed", "a"],
        ["seed"],
        lexical_scores={"a": 1.0},
    )
    a = next(r for r in ranked if r.node_id == "a")
    assert "community" not in a.contributions


def test_rank_nodes_community_boost():
    common = dict(
        lexical_scores={"same": 5.0, "other": 5.0},
        degrees={"same": 2, "other": 2},
    )
    with_comm = rank_nodes(
        ["seed", "same", "other"],
        ["seed"],
        node_community={"seed": 7, "same": 7, "other": 99},
        **common,
    )
    without = rank_nodes(["seed", "same", "other"], ["seed"], **common)
    same_with = next(r for r in with_comm if r.node_id == "same")
    same_without = next(r for r in without if r.node_id == "same")
    # Sharing the seed's community adds a backend vote the node otherwise lacks.
    assert "community" in same_with.contributions
    assert same_with.score > same_without.score


def test_rank_nodes_semantic_backend_optional_and_used():
    without = rank_nodes(["s", "a", "b"], ["s"], lexical_scores={"a": 1.0, "b": 1.0})
    assert all("semantic" not in r.contributions for r in without)
    with_sem = rank_nodes(
        ["s", "a", "b"],
        ["s"],
        lexical_scores={"a": 1.0, "b": 1.0},
        semantic_scores={"a": 0.9, "b": 0.1},
    )
    a = next(r for r in with_sem if r.node_id == "a")
    b = next(r for r in with_sem if r.node_id == "b")
    assert "semantic" in a.contributions
    assert a.score > b.score


def test_rank_nodes_is_deterministic():
    kwargs = dict(
        lexical_scores={"a": 1.0, "b": 1.0, "c": 1.0},
        degrees={"a": 1, "b": 1, "c": 1},
    )
    first = [r.node_id for r in rank_nodes(["s", "a", "b", "c"], ["s"], **kwargs)]
    second = [r.node_id for r in rank_nodes(["c", "b", "a", "s"], ["s"], **kwargs)]
    assert first == second  # ties break on node id regardless of input order


def test_ranked_node_explain_is_readable():
    rn = RankedNode("x", 0.05, {"lexical": 1, "proximity": 4}, {"lexical": 0.03, "proximity": 0.02})
    text = rn.explain()
    assert "score=0.0500" in text
    assert "lexical#1" in text
    # Sorted by contribution: lexical (0.03) before proximity (0.02).
    assert text.index("lexical") < text.index("proximity")


def test_rank_nodes_empty():
    assert rank_nodes([], []) == []
