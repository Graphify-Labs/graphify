"""Tests for graphify.evals — relevance eval harness (P@k / recall / MRR / nDCG)."""
from __future__ import annotations

import json

import networkx as nx
import pytest

from graphify import evals
from graphify.evals import (
    METRIC_GLOSSARY,
    EvalCase,
    _node_matches,
    _score_case,
    diff_aggregates,
    load_cases,
    load_last_report,
    run_evals,
    save_report,
    scaffold_fixture,
)


def _graph() -> nx.Graph:
    G = nx.Graph()
    G.add_node("n1", label="extract()", source_file="graphify/extract.py", source_location="L10", community=0)
    G.add_node("n2", label="cluster()", source_file="graphify/cluster.py", source_location="L5", community=0)
    G.add_node("n3", label="build()", source_file="graphify/build.py", source_location="L1", community=1)
    G.add_edge("n1", "n2", relation="calls", confidence="INFERRED", context="call")
    G.add_edge("n2", "n3", relation="imports", confidence="EXTRACTED", context="import")
    return G


# --- EvalCase parsing ---

def test_evalcase_from_dict_basic():
    c = EvalCase.from_dict({"query": "q", "expect": ["a", "b"]})
    assert c.query == "q" and c.expect == ["a", "b"]
    assert c.mode == "bfs" and c.depth == 2


def test_evalcase_accepts_question_and_expected_aliases():
    c = EvalCase.from_dict({"question": "q", "expected": "solo"})
    assert c.query == "q"
    assert c.expect == ["solo"]  # string coerced to single-item list


def test_evalcase_requires_query():
    with pytest.raises(ValueError):
        EvalCase.from_dict({"expect": ["a"]})


def test_evalcase_requires_expect():
    with pytest.raises(ValueError):
        EvalCase.from_dict({"query": "q"})


# --- node matching ---

def test_node_matches_label_and_callable_variants():
    G = _graph()
    assert _node_matches(G, "n1", "extract()")
    assert _node_matches(G, "n1", "extract")  # decoration-insensitive
    assert _node_matches(G, "n1", "EXTRACT")  # case-insensitive


def test_node_matches_id_and_source_file():
    G = _graph()
    assert _node_matches(G, "n1", "n1")
    assert _node_matches(G, "n1", "graphify/extract.py")
    assert _node_matches(G, "n1", "extract.py")  # basename
    assert not _node_matches(G, "n1", "cluster.py")


# --- scoring ---

def test_score_case_perfect_hit_at_rank_one():
    G = _graph()
    matched, m = _score_case(G, ["n1", "n2", "n3"], ["extract()"], k=10)
    assert matched["extract()"] == 1
    assert m["mrr"] == 1.0
    assert m["recall_at_k"] == 1.0
    assert m["hit_at_k"] == 1.0
    assert 0.0 <= m["ndcg_at_k"] <= 1.0


def test_score_case_miss():
    G = _graph()
    matched, m = _score_case(G, ["n1", "n2"], ["nonexistent"], k=10)
    assert matched == {}
    assert m["mrr"] == 0.0
    assert m["recall_at_k"] == 0.0
    assert m["hit_at_k"] == 0.0
    assert m["ndcg_at_k"] == 0.0


def test_score_case_respects_k_cutoff():
    G = _graph()
    # Expected node is at rank 3 but k=2 excludes it.
    matched, m = _score_case(G, ["n1", "n2", "n3"], ["build()"], k=2)
    assert matched == {}
    assert m["hit_at_k"] == 0.0


def test_score_case_mrr_reflects_rank():
    G = _graph()
    _matched, m = _score_case(G, ["n1", "n2", "n3"], ["build()"], k=10)
    assert m["mrr"] == pytest.approx(1.0 / 3, abs=1e-4)  # metrics round to 4 places


def test_ndcg_never_exceeds_one_with_duplicate_matches():
    # Two distinct nodes share the same label; one expected item matches both.
    G = nx.Graph()
    G.add_node("a", label="dup()", source_file="a.py", community=0)
    G.add_node("b", label="dup()", source_file="b.py", community=0)
    G.add_node("c", label="other()", source_file="c.py", community=0)
    _matched, m = _score_case(G, ["a", "b", "c"], ["dup()"], k=10)
    assert 0.0 <= m["ndcg_at_k"] <= 1.0


# --- end to end ---

def test_run_evals_end_to_end():
    G = _graph()
    cases = [
        EvalCase(query="extract", expect=["extract()"]),
        EvalCase(query="cluster", expect=["cluster()"]),
    ]
    report = run_evals(G, cases, k=5)
    assert len(report.cases) == 2
    assert set(report.aggregate) == set(METRIC_GLOSSARY)
    assert report.aggregate["hit_at_k"] == 1.0
    assert report.aggregate["recall_at_k"] == 1.0


def test_run_evals_is_deterministic():
    G = _graph()
    cases = [EvalCase(query="extract", expect=["extract()"])]
    a = run_evals(G, cases, k=5).aggregate
    b = run_evals(G, cases, k=5).aggregate
    assert a == b


# --- fixture IO ---

def test_load_cases_jsonl(tmp_path):
    p = tmp_path / "f.jsonl"
    p.write_text(
        '# a comment\n'
        '{"query": "a", "expect": ["x"]}\n'
        '\n'
        '{"query": "b", "expect": ["y", "z"]}\n',
        encoding="utf-8",
    )
    cases = load_cases(p)
    assert [c.query for c in cases] == ["a", "b"]


def test_load_cases_json_array(tmp_path):
    p = tmp_path / "f.json"
    p.write_text(json.dumps([{"query": "a", "expect": ["x"]}]), encoding="utf-8")
    cases = load_cases(p)
    assert cases[0].expect == ["x"]


def test_load_cases_empty_raises(tmp_path):
    p = tmp_path / "f.jsonl"
    p.write_text("\n# only comments\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_cases(p)


def test_save_and_load_last_report(tmp_path):
    G = _graph()
    report = run_evals(G, [EvalCase(query="extract", expect=["extract()"])], k=5)
    save_report(report, base=tmp_path, fixture="f.jsonl")
    # A second run appends; load_last_report returns the latest.
    report2 = run_evals(G, [EvalCase(query="cluster", expect=["cluster()"])], k=5)
    save_report(report2, base=tmp_path, fixture="f.jsonl")
    last = load_last_report(base=tmp_path)
    assert last is not None
    assert last["cases"][0]["query"] == "cluster"


def test_load_last_report_missing(tmp_path):
    assert load_last_report(base=tmp_path) is None


def test_diff_aggregates():
    delta = diff_aggregates({"p_at_k": 0.5, "mrr": 0.8}, {"p_at_k": 0.4, "mrr": 0.9})
    assert delta["p_at_k"] == pytest.approx(0.1)
    assert delta["mrr"] == pytest.approx(-0.1)


def test_scaffold_fixture_generates_cases():
    G = _graph()
    cases = scaffold_fixture(G, limit=5)
    assert cases
    assert all("query" in c and "expect" in c for c in cases)
    # Each scaffolded case expects the symbol it queries.
    assert all(c["expect"] for c in cases)
