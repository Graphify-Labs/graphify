"""Temporal questions get a session-memory hand-off note; structural ones never do.

The graph is deterministic AST structure and stores no session history, so
"why was this added" / "what changed last week" questions cannot be answered
from it. `_query_graph_text` appends a one-line capability note on those
questions (including the no-match path, where a temporal question is most
likely to land), and GRAPH_REPORT.md carries a one-line pairing footer.
"""
import json
from pathlib import Path

import networkx as nx

from graphify.serve import (
    _TEMPORAL_HANDOFF_NOTE,
    _query_graph_text,
    _temporal_handoff_note,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _make_graph() -> nx.Graph:
    G = nx.Graph()
    G.add_node("n1", label="extract", source_file="extract.py", source_location="L10", community=0)
    G.add_node("n2", label="cluster", source_file="cluster.py", source_location="L5", community=0)
    G.add_edge("n1", "n2", relation="calls", confidence="INFERRED", context="call")
    return G


# --- _temporal_handoff_note ---

def test_note_fires_on_temporal_questions():
    for q in [
        "why was this retry added",
        "what changed last week in the auth flow",
        "who added extract",
        "when was cluster introduced",
        "what did we decide about caching",
        "history of the extract module",
    ]:
        assert _temporal_handoff_note(q) == _TEMPORAL_HANDOFF_NOTE, q


def test_note_silent_on_structural_questions():
    for q in [
        "how does extract relate to cluster",
        "where is cluster defined",
        "what does extract do",
        "show the auth flow",
        "explain the architecture",
        "what connects extract to cluster",
    ]:
        assert _temporal_handoff_note(q) == "", q


def test_note_is_case_insensitive():
    assert _temporal_handoff_note("WHY WAS this added") == _TEMPORAL_HANDOFF_NOTE


# --- _query_graph_text integration ---

def test_query_appends_note_for_temporal_question():
    G = _make_graph()
    out = _query_graph_text(G, "why was extract added")
    assert out.endswith(_TEMPORAL_HANDOFF_NOTE)
    # the structural answer is still present, the note is appended not replacing
    assert "extract" in out


def test_query_no_note_for_structural_question():
    G = _make_graph()
    out = _query_graph_text(G, "how does extract relate to cluster")
    assert _TEMPORAL_HANDOFF_NOTE not in out


def test_no_match_path_carries_note_for_temporal_question():
    G = _make_graph()
    out = _query_graph_text(G, "why was the zzzznonexistent thing decided")
    assert out.startswith("No matching nodes found.")
    assert out.endswith(_TEMPORAL_HANDOFF_NOTE)


def test_no_match_path_clean_for_structural_question():
    G = _make_graph()
    out = _query_graph_text(G, "zzzznonexistent")
    assert out == "No matching nodes found."


# --- report footer ---

def test_report_carries_pairing_footer():
    from graphify.build import build_from_json
    from graphify.cluster import cluster, score_all
    from graphify.analyze import god_nodes, surprising_connections
    from graphify.report import generate

    extraction = json.loads((FIXTURES / "extraction.json").read_text())
    G = build_from_json(extraction)
    communities = cluster(G)
    cohesion = score_all(G, communities)
    labels = {cid: f"Community {cid}" for cid in communities}
    detection = {"total_files": 4, "total_words": 62400, "needs_graph": True, "warning": None}
    tokens = {"input": extraction["input_tokens"], "output": extraction["output_tokens"]}
    report = generate(
        G, communities, cohesion, labels,
        god_nodes(G), surprising_connections(G), detection, tokens, "./project",
    )
    assert "session memory layer" in report
    assert report.rstrip().endswith("sessions._")
