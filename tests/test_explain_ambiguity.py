import networkx as nx
from graphify.serve import _score_nodes


def test_explain_ambiguity_tied_top_scores():
    # Two nodes that tie for the simple query "dup"
    G = nx.DiGraph()
    G.add_node("a", label="dup", norm_label="dup", source_file="pkg/a.py")
    G.add_node("b", label="dup", norm_label="dup", source_file="pkg/b.py")

    scored = _score_nodes(G, ["dup"])
    assert len(scored) >= 2
    # top two scores should be equal (tie)
    assert abs(scored[0][0] - scored[1][0]) < 1e-12
