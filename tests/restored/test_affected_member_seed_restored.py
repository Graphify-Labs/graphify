"""#1669 — affected <Class> must reach callers that bind to the class's method
nodes (post-#1634 method-granularity resolution), by seeding the reverse walk
with the root's member nodes (one method/contains hop). method/contains stay out
of the general relation-filtered walk, so no forward noise is added elsewhere.
"""
from __future__ import annotations

from graphify.affected import affected_nodes
from tests.native_helpers import graph_from_payload


def _g():
    return graph_from_payload(
        [
            {"id": "proc", "label": "Processor"},
            {"id": "proc_call", "label": ".call()"},
            {"id": "runner", "label": "Runner"},
            {"id": "runner_run", "label": ".run()"},
        ],
        [
            {"source": "proc", "target": "proc_call", "relation": "method"},
            {"source": "runner", "target": "runner_run", "relation": "method"},
            {"source": "runner_run", "target": "proc_call", "relation": "calls"},
        ],
        kind="digraph",
    )


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
    g = graph_from_payload(
        [{"id": nid, "label": label} for nid, label in
         [("a", "A"), ("a_m", ".m()"), ("b", "B"), ("b_m", ".n()")]],
        [
            {"source": "a", "target": "a_m", "relation": "method"},
            {"source": "a_m", "target": "b", "relation": "calls"},
            {"source": "b", "target": "b_m", "relation": "method"},
        ],
        kind="digraph",
    )
    hits = {h.node_id for h in affected_nodes(g, "a", depth=3)}
    # We seeded A's members and walk reverse; B and B's method are downstream of A
    # (A.m -> B), not reverse-callers of A, so they must not appear.
    assert hits == set() or "b_m" not in hits


def test_class_level_caller_still_works():
    # A caller bound to the class node itself (not a method) is unaffected.
    g = graph_from_payload(
        [{"id": "svc", "label": "Svc"}, {"id": "caller", "label": ".use()"}],
        [{"source": "caller", "target": "svc", "relation": "references"}],
        kind="digraph",
    )
    hits = {h.node_id for h in affected_nodes(g, "svc", depth=2)}
    assert "caller" in hits
