"""#4199 regression — AMBIGUOUS questions tagged ``low_confidence`` and
split out of top-N so a flood of noise cannot push real bridges off the
Suggested Questions list.
"""
from __future__ import annotations
import networkx as nx
from graphify.analyze import suggest_questions


def _graph_with_noise(num_ambiguous: int = 20) -> tuple[nx.Graph, dict, dict]:
    """A graph with ``num_ambiguous`` AMBIGUOUS edges and one real
    bridge-like structure (a central node connecting two communities)."""
    G = nx.Graph()
    # Community A: 5-node clique (community 0)
    for i in range(5):
        G.add_node(f"A{i}", label=f"A{i}")
    for i in range(5):
        for j in range(i + 1, 5):
            G.add_edge(f"A{i}", f"A{j}", confidence="EXTRACTED", weight=1.0)
    # Community B: 5-node clique (community 1)
    for i in range(5):
        G.add_node(f"B{i}", label=f"B{i}")
    for i in range(5):
        for j in range(i + 1, 5):
            G.add_edge(f"B{i}", f"B{j}", confidence="EXTRACTED", weight=1.0)
    # Flood AMBIGUOUS edges between A and B — raw noise.
    for k in range(num_ambiguous):
        G.add_node(f"amb_{k}", label=f"amb_{k}")
        G.add_edge(f"A0", f"amb_{k}", confidence="AMBIGUOUS", weight=0.3, relation="conceptually_related_to")
        G.add_edge(f"B0", f"amb_{k}", confidence="AMBIGUOUS", weight=0.3, relation="conceptually_related_to")

    communities = {
        0: [f"A{i}" for i in range(5)],
        1: [f"B{i}" for i in range(5)],
        2: [f"amb_{k}" for k in range(num_ambiguous)],
    }
    labels = {0: "A clique", 1: "B clique", 2: "Noise"}
    return G, communities, labels


def test_ambiguous_questions_carry_low_confidence_flag():
    """Every AMBIGUOUS-type question must be tagged so renderers can route
    it to the low-confidence section."""
    G, c, l = _graph_with_noise(num_ambiguous=5)
    qs = suggest_questions(G, c, l, top_n=50)
    ambiguous = [q for q in qs if q["type"] == "ambiguous_edge"]
    assert ambiguous, "fixture must produce ambiguous questions"
    assert all(q.get("low_confidence") is True for q in ambiguous)


def test_high_confidence_questions_never_tagged():
    """Non-AMBIGUOUS types must not accidentally pick up low_confidence."""
    G, c, l = _graph_with_noise(num_ambiguous=3)
    qs = suggest_questions(G, c, l, top_n=50)
    for q in qs:
        if q["type"] != "ambiguous_edge":
            assert not q.get("low_confidence"), f"{q['type']} wrongly tagged low_confidence"


def test_ambiguous_tagged_regardless_of_rank():
    """`low_confidence=True` must appear on every ambiguous_edge entry even
    when top_n includes multiple of them. The downstream renderer uses the
    tag — not position — to split sections."""
    G, c, l = _graph_with_noise(num_ambiguous=20)
    qs = suggest_questions(G, c, l, top_n=10)
    tagged_count = sum(1 for q in qs if q.get("low_confidence"))
    ambiguous_count = sum(1 for q in qs if q["type"] == "ambiguous_edge")
    assert tagged_count == ambiguous_count
    assert ambiguous_count > 0  # fixture produces at least one
