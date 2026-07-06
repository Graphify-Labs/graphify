"""#1669 — affected <Class> must reach callers that bind to the class's method
nodes (post-#1634 method-granularity resolution), by seeding the reverse walk
with the root's member nodes (one method/contains hop). method/contains stay out
of the general relation-filtered walk, so no forward noise is added elsewhere.
"""
from __future__ import annotations

import networkx as nx

from graphify.affected import affected_nodes


def _g():
    g = nx.DiGraph()
    for nid, label in [
        ("proc", "Processor"), ("proc_call", ".call()"),
        ("runner", "Runner"), ("runner_run", ".run()"),
    ]:
        g.add_node(nid, label=label)
    g.add_edge("proc", "proc_call", relation="method")       # class owns method
    g.add_edge("runner", "runner_run", relation="method")
    g.add_edge("runner_run", "proc_call", relation="calls")  # caller binds to method node (#1634)
    return g


def test_class_affected_reaches_method_bound_caller():
    g = _g()
    hits = {h.node_id for h in affected_nodes(g, "proc", depth=2)}
    assert "runner_run" in hits, "caller of Processor.call must be reachable from Processor"


def test_member_method_node_not_reported_as_hit():
    g = _g()
    hits = {h.node_id for h in affected_nodes(g, "proc", depth=2)}
    # the class's own method node is a seed, not an affected node
    assert "proc_call" not in hits


def test_method_contains_still_excluded_from_general_walk():
    # A node two method-hops away (method of a DIFFERENT class discovered during
    # the walk) must NOT be pulled in: only the root's own members are seeded.
    g = nx.DiGraph()
    for nid, label in [("a", "A"), ("a_m", ".m()"), ("b", "B"), ("b_m", ".n()")]:
        g.add_node(nid, label=label)
    g.add_edge("a", "a_m", relation="method")
    g.add_edge("a_m", "b", relation="calls")   # A.m calls class B
    g.add_edge("b", "b_m", relation="method")  # B's own method
    hits = {h.node_id for h in affected_nodes(g, "a", depth=3)}
    # We seeded A's members and walk reverse; B and B's method are downstream of A
    # (A.m -> B), not reverse-callers of A, so they must not appear.
    assert hits == set() or "b_m" not in hits


def test_class_level_caller_still_works():
    # A caller bound to the class node itself (not a method) is unaffected.
    g = nx.DiGraph()
    g.add_node("svc", label="Svc")
    g.add_node("caller", label=".use()")
    g.add_edge("caller", "svc", relation="references")
    hits = {h.node_id for h in affected_nodes(g, "svc", depth=2)}
    assert "caller" in hits
