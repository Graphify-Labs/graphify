"""Search finds a symbol by words in its docstring (#985).

AST extraction stores a docstring as its own `rationale` node linked to the
symbol by a `rationale_for` edge. Search only matched a symbol's name and path,
so a function whose name shares no words with the question was unreachable
even when its docstring answers it.
"""
import networkx as nx

from graphify.serve import _attach_docstrings, _query_graph_text, _query_terms, _score_nodes

DOC = ("The callee identifier of a call-site name node. A generic_name reads its "
       "identifier child so the type-argument list never leaks into the callee name.")


def _graph(directed: bool = True) -> nx.Graph:
    G = nx.DiGraph() if directed else nx.Graph()
    G.add_node("fn", label="bare_call_name()", file_type="code",
               source_file="pkg/engine.py", source_location="L10")
    G.add_node("doc", label="The callee identifier of a call-site name node. A generic_name…",
               file_type="rationale", text=DOC, source_file="pkg/engine.py", source_location="L11")
    G.add_node("other", label="parse_arguments()", file_type="code",
               source_file="pkg/cli.py", source_location="L5")
    G.add_edge("doc", "fn", relation="rationale_for", confidence="EXTRACTED")
    return G


def test_symbol_ranks_first_by_words_only_in_its_docstring():
    G = _graph()
    ranked = _score_nodes(G, _query_terms("which function keeps the type-argument list out of the callee"))
    code_hits = [nid for _, nid in ranked if G.nodes[nid].get("file_type") == "code"]
    assert code_hits[:1] == ["fn"]


def test_query_output_reaches_the_documented_symbol():
    # Words past the 80-char label cut: nothing but the full text can match them.
    out = _query_graph_text(_graph(), "type-argument list leaks",
                            mode="bfs", depth=1, token_budget=2000)
    assert "bare_call_name()" in out


def test_attach_uses_full_text_and_label_fallback():
    G = _graph()
    _attach_docstrings(G)
    assert G.nodes["fn"]["_docstring"] == DOC
    # Graphs built before `text` existed still get the (truncated) label.
    G2 = _graph()
    del G2.nodes["doc"]["text"]
    _attach_docstrings(G2)
    assert G2.nodes["fn"]["_docstring"].startswith("The callee identifier")


def test_attach_is_idempotent_and_skips_rationale_targets():
    G = _graph()
    G.add_node("note", label="NOTE: see above", file_type="rationale")
    G.add_edge("note", "doc", relation="rationale_for")
    _attach_docstrings(G)
    _attach_docstrings(G)
    assert G.nodes["fn"]["_docstring"] == DOC  # not doubled
    assert "_docstring" not in G.nodes["doc"]


def test_attach_handles_undirected_edge_order():
    G = _graph(directed=False)
    G.remove_edge("doc", "fn")
    G.add_edge("fn", "doc", relation="rationale_for")
    _attach_docstrings(G)
    assert G.nodes["fn"]["_docstring"] == DOC
