"""Regression test for affected_nodes() on undirected graphs.

Guards two invariants:
1. Incident edge lookup for undirected graphs must use O(deg) incident edges
   (graph.edges(node, data=True)) rather than scanning the entire graph
   (graph.edges(data=True)), which was O(|E|) on every BFS iteration.
2. Undirected endpoint traversal must respect stored _src/_tgt direction when
   present, and must not drop edges due to NetworkX endpoint ordering (where
   (u, v) is stored with u < v).
"""
from __future__ import annotations

import networkx as nx
import pytest

from graphify.affected import affected_nodes


def test_affected_undirected_plain_both_lexical_orders():
    """On a plain undirected nx.Graph(), affected_nodes must discover the
    affected caller regardless of whether seed < caller or seed > caller."""
    # Case 1: seed "a.py" < caller "b.py"
    g1 = nx.Graph()
    g1.add_node("a.py", label="a.py")
    g1.add_node("b.py", label="b.py")
    g1.add_edge("a.py", "b.py", relation="imports")

    hits1 = affected_nodes(g1, "a.py", relations={"imports"}, depth=1)
    hit_ids1 = {h.node_id for h in hits1}
    assert "b.py" in hit_ids1, (
        "seed a.py must discover caller b.py even when seed < caller in undirected graph"
    )

    # Case 2: seed "z.py" > caller "y.py"
    g2 = nx.Graph()
    g2.add_node("z.py", label="z.py")
    g2.add_node("y.py", label="y.py")
    g2.add_edge("y.py", "z.py", relation="imports")

    hits2 = affected_nodes(g2, "z.py", relations={"imports"}, depth=1)
    hit_ids2 = {h.node_id for h in hits2}
    assert "y.py" in hit_ids2, (
        "seed z.py must discover caller y.py when seed > caller in undirected graph"
    )


def test_affected_undirected_built_graph_src_tgt_direction():
    """build.build() creates an undirected graph with _src and _tgt annotations.
    affected_nodes must follow the true _src -> _tgt direction regardless of
    how NetworkX orders the endpoints in the undirected representation."""
    g = nx.Graph()
    g.add_node("a.py", label="a.py")
    g.add_node("b.py", label="b.py")
    # b.py imports a.py (so caller is b.py, callee is a.py)
    # NetworkX undirected graph stores the edge tuple as ("a.py", "b.py", ...)
    g.add_edge("a.py", "b.py", relation="imports", _src="b.py", _tgt="a.py")

    # Modifying a.py should affect b.py
    hits = affected_nodes(g, "a.py", relations={"imports"}, depth=1)
    hit_ids = {h.node_id for h in hits}
    assert "b.py" in hit_ids, (
        "b.py imports a.py: seed a.py must discover caller b.py using _src/_tgt"
    )

    # Modifying b.py should NOT affect a.py (a.py does not import b.py)
    hits_reverse = affected_nodes(g, "b.py", relations={"imports"}, depth=1)
    hit_ids_reverse = {h.node_id for h in hits_reverse}
    assert "a.py" not in hit_ids_reverse, (
        "b.py imports a.py: seed b.py must not report callee a.py as affected"
    )


def test_affected_undirected_member_seed_ordering():
    """Member seeding on an undirected graph must discover members even when
    member node id < parent class node id."""
    g = nx.Graph()
    # ZClass > a_method lexicographically
    g.add_node("ZClass", label="ZClass")
    g.add_node("a_method", label="a_method")
    g.add_node("caller.py", label="caller.py")

    # ZClass defines a_method; caller calls a_method
    g.add_edge("ZClass", "a_method", relation="method", _src="ZClass", _tgt="a_method")
    g.add_edge("caller.py", "a_method", relation="calls", _src="caller.py", _tgt="a_method")

    hits = affected_nodes(g, "ZClass", relations={"calls"}, depth=2)
    hit_ids = {h.node_id for h in hits}
    assert "caller.py" in hit_ids, (
        "caller of ZClass.a_method must be reachable when member < parent in undirected graph"
    )
