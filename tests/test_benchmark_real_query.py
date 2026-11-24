"""`graphify benchmark` counts the answer query_graph really returns."""
from __future__ import annotations

import json

import networkx as nx
import pytest
from networkx.readwrite import json_graph

from graphify.benchmark import _estimate_tokens, _query_subgraph_tokens, run_benchmark
from graphify.serve import _load_graph, _query_graph_text, _read_graph


def _write(G: nx.Graph, path) -> str:
    path.write_text(json.dumps(json_graph.node_link_data(G, edges="links")), encoding="utf-8")
    return str(path)


def _small_graph() -> nx.DiGraph:
    G = nx.DiGraph()
    G.add_node("auth", label="authentication()", source_file="auth.py", source_location="L1")
    G.add_node("login", label="login()", source_file="views.py", source_location="L9")
    G.add_node("user", label="get_user()", source_file="db.py", source_location="L3")
    G.add_edge("login", "auth", relation="calls", confidence="EXTRACTED")
    G.add_edge("auth", "user", relation="calls", confidence="EXTRACTED")
    return G


def _hub_graph(spokes: int = 400) -> nx.DiGraph:
    G = nx.DiGraph()
    G.add_node("auth", label="authentication()", source_file="auth.py", source_location="L1")
    for i in range(spokes):
        G.add_node(f"n{i}", label=f"helper_function_number_{i}_with_a_long_name()",
                   source_file=f"pkg/module_{i}.py", source_location=f"L{i}")
        G.add_edge("auth", f"n{i}", relation="calls", confidence="EXTRACTED")
    return G


def test_tokens_are_those_of_the_mcp_query_graph_answer(tmp_path):
    path = _write(_small_graph(), tmp_path / "graph.json")
    question = "how does authentication work"
    answer = _query_graph_text(_load_graph(path), question, mode="bfs", depth=3, token_budget=2000)
    result = run_benchmark(path, corpus_words=10_000, questions=[question])
    assert result["per_question"][0]["query_tokens"] == _estimate_tokens(answer)


def test_tokens_stop_at_the_query_budget(tmp_path):
    # 400 callees: query_graph cuts the answer at its ~2000-token budget, the
    # benchmark must count that cut answer, not every node BFS reaches.
    path = _write(_hub_graph(), tmp_path / "graph.json")
    G = _read_graph(path)
    full = _query_graph_text(G, "authentication", token_budget=10**6)
    tokens = _query_subgraph_tokens(G, "authentication")
    assert "[!] TRUNCATED" in _query_graph_text(G, "authentication")
    assert tokens <= 2000 < _estimate_tokens(full)


def test_a_larger_budget_buys_a_larger_answer(tmp_path):
    G = _read_graph(_write(_hub_graph(), tmp_path / "graph.json"))
    assert _query_subgraph_tokens(G, "authentication", token_budget=500) < _query_subgraph_tokens(G, "authentication")


def test_no_answer_counts_zero_and_is_left_out(tmp_path):
    path = _write(_small_graph(), tmp_path / "graph.json")
    assert _query_subgraph_tokens(_read_graph(path), "xyzzy plugh") == 0
    result = run_benchmark(path, corpus_words=10_000, questions=["xyzzy plugh", "authentication"])
    assert [p["question"] for p in result["per_question"]] == ["authentication"]


def test_bad_graph_path_raises_instead_of_exiting(tmp_path):
    with pytest.raises(FileNotFoundError):
        run_benchmark(str(tmp_path / "missing.json"))
    with pytest.raises(ValueError):
        run_benchmark(str(tmp_path / "graph.txt"))
