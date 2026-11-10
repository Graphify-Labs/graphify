"""`query` prefers source code over tests and docs, and answers file-first.

A test named after a bug repeats the question's words in its own name, so on the
name tiers it ties with (or beats) the source it tests and takes the seed slots.
`query` now weights test, doc, config and source-less nodes down unless the
question asks about tests or docs. `path`, `explain` and `_score_nodes` are not
affected. The answer lists nodes file by file, best-scoring file first.
"""
from __future__ import annotations

import networkx as nx

from graphify.serve import (
    _QUERY_DEMOTE_WEIGHT,
    _query_graph_text,
    _query_path_weight,
    _query_terms,
    _score_nodes,
    _score_query,
    _subgraph_to_text,
)


def _graph():
    G = nx.Graph()
    G.add_node("src", label="validate_username()", source_file="pkg/auth/validators.py", source_location="L10")
    G.add_node("tst", label="validate_username()", source_file="tests/auth/test_validators.py", source_location="L5")
    G.add_node("doc", label="validate_username", source_file="docs/auth.md", source_location="L1")
    G.add_node("cfg", label="username", source_file="pkg/settings.yml", source_location="L1")
    G.add_node("ext", label="username")  # external symbol: no source file
    G.add_edge("tst", "src", relation="calls", confidence="EXTRACTED")
    return G


def _nodes_in_order(text: str) -> list[str]:
    return [line.split(" [src=")[1].split(" ")[0] for line in text.splitlines() if line.startswith("NODE ")]


def test_source_node_outranks_its_namesake_test():
    G = _graph()
    terms = _query_terms("validate_username allows a trailing newline")
    plain = dict((nid, sc) for sc, nid in _score_query(G, terms, collect_per_term_seeds=False).ranked)
    assert plain["src"] == plain["tst"]  # names alone cannot tell them apart
    weighted = _score_query(G, terms, collect_per_term_seeds=True, path_weight=_query_path_weight(terms))
    order = [nid for _, nid in weighted.ranked]
    assert order.index("src") < order.index("tst")
    assert dict((n, s) for s, n in weighted.ranked)["tst"] == plain["tst"] * _QUERY_DEMOTE_WEIGHT


def test_query_answer_leads_with_source_not_test():
    text = _query_graph_text(_graph(), "validate_username allows a trailing newline", depth=1)
    assert _nodes_in_order(text)[0] == "pkg/auth/validators.py"


def test_question_about_tests_keeps_test_nodes_at_full_weight():
    G = _graph()
    weight = _query_path_weight(_query_terms("validate_username tests fail on newline"))
    assert weight(G.nodes["tst"]) == 1.0
    assert weight(G.nodes["src"]) == 1.0


def test_docs_config_and_sourceless_nodes_are_weighted_down():
    G = _graph()
    weight = _query_path_weight(_query_terms("username validation"))
    assert weight(G.nodes["doc"]) == _QUERY_DEMOTE_WEIGHT
    assert weight(G.nodes["cfg"]) == _QUERY_DEMOTE_WEIGHT
    assert weight(G.nodes["ext"]) == _QUERY_DEMOTE_WEIGHT
    assert weight(G.nodes["src"]) == 1.0
    # a question that names the docs keeps doc nodes at full weight
    assert _query_path_weight(_query_terms("username docs"))(G.nodes["doc"]) == 1.0


def test_pytest_style_testing_dir_and_conftest_count_as_tests():
    weight = _query_path_weight(_query_terms("collect only shortcut"))
    assert weight({"source_file": "testing/test_session.py"}) == _QUERY_DEMOTE_WEIGHT
    assert weight({"source_file": "testing/python/fixtures.py"}) == _QUERY_DEMOTE_WEIGHT
    assert weight({"source_file": "src/conftest.py"}) == _QUERY_DEMOTE_WEIGHT
    assert weight({"source_file": "src/_pytest/main.py"}) == 1.0


def test_path_and_explain_scoring_is_unchanged():
    # _score_nodes (used by path/explain endpoint resolution) applies no weight.
    G = _graph()
    terms = _query_terms("validate_username")
    assert _score_nodes(G, terms) == _score_query(G, terms, collect_per_term_seeds=False).ranked
    assert dict((n, s) for s, n in _score_nodes(G, terms))["tst"] == dict((n, s) for s, n in _score_nodes(G, terms))["src"]


def test_per_term_seed_guarantee_still_seeds_a_term_only_tests_match():
    # "fixture_loader" exists only in a test file: the term still gets its seed.
    G = _graph()
    G.add_node("fx", label="fixture_loader()", source_file="tests/helpers.py", source_location="L3")
    text = _query_graph_text(G, "validate_username fixture_loader", depth=1)
    start = text.split("Start: ")[1].split("|")[0]
    assert "fixture_loader()" in start and "validate_username()" in start


def test_answer_is_file_first():
    # The hub has the highest degree but the question does not match it; the
    # matched files come first, best file first, each file's nodes together.
    G = nx.Graph()
    G.add_node("hub", label="registry", source_file="pkg/registry.py", source_location="L1")
    G.add_node("a1", label="parse_header()", source_file="pkg/http.py", source_location="L1")
    G.add_node("a2", label="header_value()", source_file="pkg/http.py", source_location="L9")
    G.add_node("b1", label="parse()", source_file="pkg/util.py", source_location="L1")
    for n in ("a1", "a2", "b1"):
        G.add_edge("hub", n, relation="calls")
    for i in range(5):
        G.add_node(f"x{i}", label=f"other{i}", source_file="pkg/other.py", source_location=f"L{i}")
        G.add_edge("hub", f"x{i}", relation="calls")
    nodes = set(G.nodes)
    scores = {"a1": 10.0, "a2": 4.0, "b1": 6.0}
    order = _nodes_in_order(_subgraph_to_text(G, nodes, [], 2000, seeds=["b1"], scores=scores))
    assert order[:3] == ["pkg/util.py", "pkg/http.py", "pkg/http.py"]  # seed first, then best file's nodes
    # without scores (path/explain/other callers) the old hop-then-degree order is kept
    old = _nodes_in_order(_subgraph_to_text(G, nodes, [], 2000, seeds=["b1"]))
    assert old[:2] == ["pkg/util.py", "pkg/registry.py"]


def test_seed_block_is_ordered_file_first():
    G = nx.Graph()
    G.add_node("s1", label="weak()", source_file="pkg/a.py", source_location="L1")
    G.add_node("s2", label="strong()", source_file="pkg/b.py", source_location="L1")
    text = _subgraph_to_text(G, {"s1", "s2"}, [], 2000, seeds=["s1", "s2"], scores={"s1": 1.0, "s2": 9.0})
    assert _nodes_in_order(text) == ["pkg/b.py", "pkg/a.py"]
