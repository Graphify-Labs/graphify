"""Edge confidence must survive the reverse walk into `affected` output (#2352).

An affected list mixes EXTRACTED facts with INFERRED/AMBIGUOUS guesses. Before
this, both rendered identically, so a blast radius could not be triaged without
re-reading graph.json by hand.
"""
from __future__ import annotations

import json

import networkx as nx

from graphify.affected import (
    AffectedHit,
    affected_nodes,
    affected_records,
    format_affected,
)


def _graph() -> nx.DiGraph:
    g = nx.DiGraph()
    g.add_node("t", label="applyToolsAction()", source_file="cli/app.go", source_location="L10")
    g.add_node("c1", label="run()", source_file="cli/run.go", source_location="L2")
    g.add_node("c2", label="maybe()", source_file="cli/maybe.go", source_location="L7")
    # An extracted call, recorded at its call SITE (L165), not the caller def line.
    g.add_edge("c1", "t", relation="calls", confidence="EXTRACTED",
               source_file="cli/run.go", source_location="L165")
    # An inferred use carrying a numeric score and no site of its own.
    g.add_edge("c2", "t", relation="uses", confidence="INFERRED", confidence_score=0.42)
    return g


def test_text_output_tags_each_hit_with_its_edge_confidence():
    out = format_affected(_graph(), "applyToolsAction")
    assert "- run() [calls, EXTRACTED] cli/run.go:L165" in out
    assert "- maybe() [uses, INFERRED] cli/maybe.go:L7" in out


def test_edge_without_confidence_renders_exactly_as_before():
    """No placeholder for an unknown confidence - the tag always means something."""
    g = nx.DiGraph()
    g.add_node("t", label="Foo", source_file="pkg/foo.py", source_location="L1")
    g.add_node("c", label="X()", source_file="app.py", source_location="L4")
    g.add_edge("c", "t", relation="calls")  # no confidence recorded

    assert "- X() [calls] app.py:L4" in format_affected(g, "Foo")


def test_confidence_comes_from_the_edge_actually_traversed():
    """A node joined by several parallel edges must report the confidence of the
    edge whose relation passed the filter, not whichever edge came first."""
    g = nx.MultiDiGraph()
    g.add_node("t", label="T", source_file="t.py", source_location="L1")
    g.add_node("c", label="C()", source_file="c.py", source_location="L3")
    g.add_edge("c", "t", relation="references", confidence="EXTRACTED")
    g.add_edge("c", "t", relation="uses", confidence="AMBIGUOUS")

    assert "[uses, AMBIGUOUS]" in format_affected(g, "T", relations=("uses",))
    assert "[references, EXTRACTED]" in format_affected(g, "T", relations=("references",))


def test_affected_nodes_carries_confidence_onto_the_hit():
    hits = {hit.node_id: hit for hit in affected_nodes(_graph(), "t")}

    assert hits["c1"].via_confidence == "EXTRACTED"
    assert hits["c1"].via_confidence_score is None
    assert hits["c2"].via_confidence == "INFERRED"
    assert hits["c2"].via_confidence_score == 0.42


def test_affected_hit_confidence_fields_are_optional():
    """Positional construction keeps working for existing callers/tests."""
    hit = AffectedHit("n", 1, "calls")

    assert hit.via_confidence is None
    assert hit.via_confidence_score is None


def test_records_expose_confidence_and_are_json_serializable():
    records = affected_records(_graph(), "applyToolsAction")
    by_id = {record["id"]: record for record in records}

    assert set(by_id) == {"c1", "c2"}
    assert by_id["c1"] == {
        "id": "c1",
        "label": "run()",
        "depth": 1,
        "relation": "calls",
        "confidence": "EXTRACTED",
        "confidence_score": None,
        # The call SITE, matching the text view field-for-field.
        "source_file": "cli/run.go",
        "source_location": "L165",
    }
    assert by_id["c2"]["confidence"] == "INFERRED"
    assert by_id["c2"]["confidence_score"] == 0.42
    # Falls back to the node's own def line when the edge stored no site.
    assert by_id["c2"]["source_file"] == "cli/maybe.go"
    assert by_id["c2"]["source_location"] == "L7"

    assert json.loads(json.dumps(records)) == records


def test_records_are_empty_when_the_seed_does_not_resolve():
    assert affected_records(_graph(), "no_such_symbol_anywhere") == []


def test_records_honour_relation_and_depth_filters():
    g = nx.DiGraph()
    g.add_node("t", label="T", source_file="t.py", source_location="L1")
    g.add_node("mid", label="Mid()", source_file="mid.py", source_location="L2")
    g.add_node("far", label="Far()", source_file="far.py", source_location="L3")
    g.add_edge("mid", "t", relation="calls", confidence="EXTRACTED")
    g.add_edge("far", "mid", relation="calls", confidence="INFERRED")

    assert [r["id"] for r in affected_records(g, "T", depth=1)] == ["mid"]
    assert [r["id"] for r in affected_records(g, "T", depth=2)] == ["mid", "far"]
    assert affected_records(g, "T", relations=("imports",)) == []


def test_unparseable_confidence_score_degrades_to_none():
    """A malformed score must not crash the walk or leak a bogus float.

    `True` is the interesting case: bools are ints in Python, so a naive
    float() would turn a mis-typed flag into a 1.0 score.
    """
    g = nx.DiGraph()
    g.add_node("t", label="T", source_file="t.py", source_location="L1")
    g.add_node("a", label="A()", source_file="a.py", source_location="L2")
    g.add_node("b", label="B()", source_file="b.py", source_location="L3")
    g.add_node("c", label="C()", source_file="c.py", source_location="L4")
    g.add_edge("a", "t", relation="calls", confidence="EXTRACTED", confidence_score="high")
    g.add_edge("b", "t", relation="calls", confidence="EXTRACTED", confidence_score=True)
    # A numeric string is a legitimate value and must still be read.
    g.add_edge("c", "t", relation="calls", confidence="EXTRACTED", confidence_score="0.75")

    scores = {r["id"]: r["confidence_score"] for r in affected_records(g, "T")}

    assert scores == {"a": None, "b": None, "c": 0.75}
