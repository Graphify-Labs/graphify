"""A collapsed edge must keep the specific relation, not the alphabetical one.

`build_from_json` puts one edge per node pair into a simple graph, and resolved
same-pair collisions by "last write wins" over a sort keyed on
`(source, target, relation)`. That sort exists for determinism (#1061 — an
unstable order flipped `_src`/`_tgt` run to run), but it also decided which
RELATION survived, and it decided it alphabetically:

    calls < contains < imports < ... < references < uses

So `references` always overwrote `calls`, and `uses` overwrote everything. On
graphify's own corpus that rewrote all 144 pairs where the extraction found both
`calls` and `references` into plain `references` — 144 out of 144, not a
sampling — and callflow's relation filter
(`calls, imports, imports_from, uses, method, indirect_call`) does not include
`references`, so those call sites dropped out of the call graph entirely.

Alphabetical order carries no meaning. These tests pin that a generic relation
never overwrites a specific one, in either arrival order, and that nothing else
about the collapse changed.
"""
import pytest

from graphify.build import build_from_json, edge_data

SPECIFIC = ["calls", "imports", "imports_from", "inherits", "implements",
            "method", "indirect_call", "re_exports", "contains"]
GENERIC = ["references", "uses", "mentions"]


def _extraction(edges):
    return {
        "nodes": [
            {"id": "a", "label": "a()", "file_type": "code", "source_file": "a.py"},
            {"id": "b", "label": "b()", "file_type": "code", "source_file": "b.py"},
        ],
        "edges": edges,
        "hyperedges": [],
    }


def _edge(rel, src="a", tgt="b", **kw):
    return {"source": src, "target": tgt, "relation": rel,
            "confidence": "EXTRACTED", **kw}


def _relation(G):
    return edge_data(G, "a", "b").get("relation")


# ---------------------------------------------------------------------------
# The bug
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("generic", GENERIC)
@pytest.mark.parametrize("specific", SPECIFIC)
@pytest.mark.parametrize("order", ["specific_first", "generic_first"])
def test_generic_never_overwrites_specific(specific, generic, order):
    pair = [_edge(specific), _edge(generic)]
    if order == "generic_first":
        pair.reverse()
    G = build_from_json(_extraction(pair))
    assert _relation(G) == specific, (
        f"{generic!r} overwrote {specific!r} when added {order.replace('_', ' ')}")


def test_the_reported_case_keeps_calls():
    """The exact shape seen 144 times on graphify's own graph."""
    G = build_from_json(_extraction([
        _edge("calls", source_location="L10"),
        _edge("references", source_location="L10"),
    ]))
    assert _relation(G) == "calls"


def test_calls_survives_for_callflow(monkeypatch):
    """The consequence that made this worth fixing: callflow filters on relation
    and does not list `references`, so a downgraded pair leaves the call graph."""
    callflow_relations = ("calls", "imports", "imports_from", "uses", "method",
                          "indirect_call")
    G = build_from_json(_extraction([_edge("calls"), _edge("references")]))
    assert _relation(G) in callflow_relations


# ---------------------------------------------------------------------------
# Everything else about the collapse is unchanged
# ---------------------------------------------------------------------------

def test_specific_still_overwrites_generic():
    """The fix is one-directional: a specific relation arriving later still wins,
    so the outcome no longer depends on arrival order in either direction."""
    G = build_from_json(_extraction([_edge("references"), _edge("calls")]))
    assert _relation(G) == "calls"


def test_two_generic_relations_keep_previous_behaviour():
    G = build_from_json(_extraction([_edge("references"), _edge("uses")]))
    assert _relation(G) in {"references", "uses"}


def test_two_specific_relations_keep_previous_behaviour():
    """Deliberately NOT ranked against each other — `contains` vs `calls` is a
    cross-axis judgement this collapse does not need to make."""
    G = build_from_json(_extraction([_edge("calls"), _edge("contains")]))
    assert _relation(G) in {"calls", "contains"}


def test_collapse_still_yields_exactly_one_edge():
    G = build_from_json(_extraction([
        _edge("calls"), _edge("references"), _edge("uses"), _edge("calls"),
    ]))
    assert G.number_of_edges() == 1
    assert G.number_of_nodes() == 2


def test_edge_count_is_unchanged_by_the_fix():
    """The fix chooses WHICH edge survives; it must not add or drop any."""
    edges = [_edge("calls"), _edge("references"),
             _edge("imports", src="b", tgt="a"), _edge("uses", src="b", tgt="a")]
    G = build_from_json(_extraction(edges))
    assert G.number_of_edges() == 1


def test_reverse_direction_guard_still_holds():
    """#1061: same relation, opposite directions — first-seen direction wins."""
    G = build_from_json(_extraction([
        _edge("calls", src="a", tgt="b"),
        _edge("calls", src="b", tgt="a"),
    ]))
    d = edge_data(G, "a", "b")
    assert (d.get("_src"), d.get("_tgt")) == ("a", "b")


def test_a_lone_generic_edge_is_kept():
    """Generic relations are only ever demoted against a specific one on the SAME
    pair — a pair that has nothing else must keep its edge."""
    G = build_from_json(_extraction([_edge("references")]))
    assert _relation(G) == "references"
    assert G.number_of_edges() == 1


def test_direction_metadata_survives_the_demotion():
    """The surviving edge must still carry the specific edge's own direction, not
    the demoted one's."""
    G = build_from_json(_extraction([
        _edge("calls", src="a", tgt="b", source_location="L1"),
        _edge("references", src="b", tgt="a", source_location="L2"),
    ]))
    d = edge_data(G, "a", "b")
    assert d.get("relation") == "calls"
    assert (d.get("_src"), d.get("_tgt")) == ("a", "b")
    assert d.get("source_location") == "L1"


def test_directed_graphs_get_the_same_protection():
    G = build_from_json(_extraction([_edge("calls"), _edge("references")]),
                        directed=True)
    assert G.is_directed()
    assert edge_data(G, "a", "b").get("relation") == "calls"


def test_specific_edge_numeric_metadata_survives_the_demotion():
    """When the generic edge is skipped, the surviving specific edge keeps its OWN
    weight/confidence, not the demoted generic one's."""
    G = build_from_json(_extraction([
        _edge("calls", weight=3.0, confidence="EXTRACTED", confidence_score=1.0),
        _edge("references", weight=9.0, confidence="INFERRED", confidence_score=0.2),
    ]))
    d = edge_data(G, "a", "b")
    assert d.get("relation") == "calls"
    assert d.get("weight") == 3.0
    assert d.get("confidence") == "EXTRACTED"
    assert d.get("confidence_score") == 1.0


def test_unknown_relation_is_treated_as_specific():
    """A relation not on the generic denylist counts as specific: a generic edge
    must not overwrite it, and it must not be demoted by the guard — so the
    denylist can't silently drift into an ordering (either arrival order keeps
    the unknown one)."""
    for order in ([_edge("custom_rel"), _edge("references")],
                  [_edge("references"), _edge("custom_rel")]):
        G = build_from_json(_extraction(order))
        assert _relation(G) == "custom_rel", f"order {[e['relation'] for e in order]}"
