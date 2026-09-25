"""Tests for the LLM semantic judgment layer (graphify/semantic_judge.py).

All backend calls are mocked — no network. The contract under test:
- fail-open: any error / missing backend returns the input unchanged (or the
  same truncation the heuristic path applied);
- re-ranking and filtering happen only through the model verdicts;
- metadata only: prompts never contain file contents.
"""
from __future__ import annotations

import pytest

from graphify.semantic_judge import (
    reorder_surprises,
    refine_questions,
    validate_community_labels,
    _safe_json_load,
    _parse_surprise_verdicts,
    _parse_question_refinements,
    _parse_label_verdicts,
    _model_score,
)


# ── verdict parsers ───────────────────────────────────────────────────────────

def test_model_score_variants():
    assert _model_score(True) == 1.0
    assert _model_score(False) == 0.0
    assert _model_score("yes") == 1.0
    assert _model_score("Y") == 1.0
    assert _model_score("weak") == 0.5
    assert _model_score("maybe") == 0.5
    assert _model_score("no") == 0.0
    assert _model_score(0.7) == 0.7
    assert _model_score("0.3") == 0.3
    assert _model_score("garbage") is None


def test_safe_json_load_handles_fences_and_prose():
    assert _safe_json_load('{"1": 1.0}') == {"1": 1.0}
    assert _safe_json_load('```json\n{"1": 1.0}\n```') == {"1": 1.0}
    assert _safe_json_load('Here you go:\n{"1": 0.0}\nThanks!') == {"1": 0.0}
    assert _safe_json_load("not json at all") is None
    assert _safe_json_load(None) is None


def test_parse_surprise_verdicts_accepts_yes_no_strings():
    text = '{"1": "yes", "2": "no", "3": "weak"}'
    parsed = _parse_surprise_verdicts(text)
    assert parsed == {"1": 1.0, "2": 0.0, "3": 0.5}


def test_parse_surprise_verdicts_tolerates_noise():
    text = "sure, here:\n```json\n{\"1\": 1.0, \"bad\": 0.9, \"2\": 0.0}\n```"
    parsed = _parse_surprise_verdicts(text)
    assert parsed == {"1": 1.0, "2": 0.0}


def test_parse_question_refinements_mixed():
    text = (
        '{"1": {"keep": false}, '
        '"2": {"keep": true, "question": "Why does the auth bridge exist?"}, '
        '"3": {"keep": "maybe"}}'
    )
    parsed = _parse_question_refinements(text)
    by_idx = {p["index"]: p for p in parsed}
    assert by_idx[1]["keep"] == 0.0
    assert by_idx[2]["keep"] == 1.0
    assert by_idx[2]["question"] == "Why does the auth bridge exist?"
    assert by_idx[3]["keep"] == 0.5


def test_parse_label_verdicts():
    parsed = _parse_label_verdicts('{"0": "yes", "1": "no"}')
    assert parsed == {"0": 1.0, "1": 0.0}


# ── reorder_surprises ─────────────────────────────────────────────────────────

def _surprise_candidates():
    return [
        {"source": "Alpha", "target": "Beta", "relation": "calls",
         "confidence": "AMBIGUOUS", "why": "cross-repo"},
        {"source": "Gamma", "target": "Delta", "relation": "uses",
         "confidence": "INFERRED", "why": "cross-language"},
        {"source": "Epsilon", "target": "Zeta", "relation": "references",
         "confidence": "EXTRACTED", "why": "cross-file"},
    ]


def test_reorder_surprises_fail_open_on_missing_backend(monkeypatch):
    monkeypatch.setattr("graphify.semantic_judge.detect_backend", lambda: None)
    cands = _surprise_candidates()
    result = reorder_surprises(cands, top_n=5)
    assert [c["source"] for c in result] == ["Alpha", "Gamma", "Epsilon"]


def test_reorder_surprises_reorders_by_verdict(monkeypatch):
    def fake_call(prompt, *, backend, max_tokens=1024, model=None):
        # Model says candidate 2 is the only truly surprising one.
        return '{"1": "no", "2": "yes", "3": "weak"}'

    monkeypatch.setattr("graphify.semantic_judge._call_llm", fake_call)
    cands = _surprise_candidates()
    result = reorder_surprises(cands, top_n=3, backend="gemini")
    # kept: #2 (score 1.0), #3 (0.5); dropped: #1
    assert result[0]["source"] == "Gamma"
    assert result[1]["source"] == "Epsilon"
    assert result[2]["source"] == "Alpha"
    assert len(result) == 3


def test_reorder_surprises_preserves_all_on_parse_failure(monkeypatch):
    monkeypatch.setattr(
        "graphify.semantic_judge._call_llm",
        lambda p, *, backend, max_tokens=1024, model=None: "sorry, no json",
    )
    cands = _surprise_candidates()
    result = reorder_surprises(cands, top_n=3, backend="gemini")
    assert [c["source"] for c in result] == ["Alpha", "Gamma", "Epsilon"]


def test_reorder_surprises_empty():
    assert reorder_surprises([]) == []


def test_reorder_surprises_keeps_unjudged_candidates_at_tail(monkeypatch):
    def fake_call(prompt, *, backend, max_tokens=1024, model=None):
        return '{"1": "yes"}'

    monkeypatch.setattr("graphify.semantic_judge._call_llm", fake_call)
    cands = _surprise_candidates()
    result = reorder_surprises(cands, top_n=5, backend="gemini")
    # #1 judged surprising -> first; #2/#3 unjudged -> tail in original order
    assert [c["source"] for c in result] == ["Alpha", "Gamma", "Epsilon"]


# ── refine_questions ──────────────────────────────────────────────────────────

def _questions():
    return [
        {"type": "ambiguous_edge",
         "question": "What is the exact relationship between `A` and `B`?",
         "why": "Edge tagged AMBIGUOUS."},
        {"type": "bridge_node",
         "question": "Why does `connector` connect the pieces?",
         "why": "High betweenness."},
        {"type": "isolated_nodes",
         "question": "What connects `orphan` to the rest of the system?",
         "why": "Weakly-connected nodes found."},
    ]


def test_refine_questions_fail_open_on_missing_backend(monkeypatch):
    monkeypatch.setattr("graphify.semantic_judge.detect_backend", lambda: None)
    qs = _questions()
    result = refine_questions(qs, top_n=2)
    assert result == qs[:2]


def test_refine_questions_filters_and_rewrites(monkeypatch):
    def fake_call(prompt, *, backend, max_tokens=2048, model=None):
        return (
            '{"1": {"keep": false}, '
            '"2": {"keep": true, "question": "Why does the connector bridge them?"}, '
            '"3": {"keep": true}}'
        )

    monkeypatch.setattr("graphify.semantic_judge._call_llm", fake_call)
    result = refine_questions(_questions(), top_n=3, backend="gemini")
    # #1 dropped; #2 (rewritten) then #3
    assert len(result) == 2
    assert result[0]["question"] == "Why does the connector bridge them?"
    assert "semantic refinement" in result[0]["why"]
    assert result[1]["question"] == _questions()[2]["question"]


def test_refine_questions_no_signal_never_touched():
    ns = [{"type": "no_signal", "question": None, "why": "No signal."}]
    assert refine_questions(ns, top_n=7) == ns


def test_refine_questions_parse_failure_keeps_pool(monkeypatch):
    monkeypatch.setattr(
        "graphify.semantic_judge._call_llm",
        lambda p, *, backend, max_tokens=2048, model=None: "nothing useful",
    )
    qs = _questions()
    result = refine_questions(qs, top_n=3, backend="gemini")
    assert [q["question"] for q in result] == [q["question"] for q in qs]


def test_refine_questions_truncates_to_top_n(monkeypatch):
    def fake_call(prompt, *, backend, max_tokens=2048, model=None):
        return '{"1": {"keep": true}, "2": {"keep": true}, "3": {"keep": true}}'

    monkeypatch.setattr("graphify.semantic_judge._call_llm", fake_call)
    result = refine_questions(_questions(), top_n=2, backend="gemini")
    assert len(result) == 2


# ── validate_community_labels ─────────────────────────────────────────────────

def _label_graph():
    import networkx as nx
    G = nx.Graph()
    G.add_node("place_order", label="place_order")
    G.add_node("order_repo", label="OrderRepository")
    G.add_node("pay_charge", label="charge_card")
    G.add_node("pay_stripe", label="StripeClient")
    communities = {0: ["place_order", "order_repo"], 1: ["pay_charge", "pay_stripe"]}
    return G, communities


def test_validate_labels_fail_open_on_missing_backend(monkeypatch):
    monkeypatch.setattr("graphify.semantic_judge.detect_backend", lambda: None)
    G, communities = _label_graph()
    names = {0: "Order Management", 1: "Payment Flow"}
    assert validate_community_labels(names, communities, G) == names


def test_validate_labels_rejects_fall_back_to_hub(monkeypatch):
    def fake_call(prompt, *, backend, max_tokens=1024, model=None, usage_out=None):
        return '{"0": "yes", "1": "no"}'

    monkeypatch.setattr("graphify.semantic_judge._call_llm", fake_call)
    G, communities = _label_graph()
    names = {0: "Order Management", 1: "Totally Wrong"}
    result = validate_community_labels(names, communities, G, backend="gemini")
    assert result[0] == "Order Management"       # confirmed
    assert result[1] == "charge_card"            # hub label for community 1
    assert result[1] != "Totally Wrong"


def test_validate_labels_keeps_placeholders_unjudged(monkeypatch):
    def fake_call(prompt, *, backend, max_tokens=1024, model=None, usage_out=None):
        return '{"0": "yes"}'

    monkeypatch.setattr("graphify.semantic_judge._call_llm", fake_call)
    G, communities = _label_graph()
    names = {0: "Order Management", 1: "Community 1"}  # placeholder not judged
    result = validate_community_labels(names, communities, G, backend="gemini")
    assert result == names


def test_validate_labels_parse_failure_keeps_all(monkeypatch):
    monkeypatch.setattr(
        "graphify.semantic_judge._call_llm",
        lambda p, *, backend, max_tokens=1024, model=None, usage_out=None: "garbage",
    )
    G, communities = _label_graph()
    names = {0: "Order Management", 1: "Payment Flow"}
    assert validate_community_labels(names, communities, G, backend="gemini") == names


# ── prompt hygiene: metadata only ─────────────────────────────────────────────

def test_surprise_prompt_contains_only_metadata(monkeypatch):
    captured = {}

    def fake_call(prompt, *, backend, max_tokens=1024, model=None):
        captured["prompt"] = prompt
        return '{"1": "yes"}'

    monkeypatch.setattr("graphify.semantic_judge._call_llm", fake_call)
    reorder_surprises(_surprise_candidates(), top_n=3, backend="gemini")
    prompt = captured["prompt"]
    assert "def " not in prompt          # no source code
    assert "source_file" not in prompt   # no file contents
    assert "Alpha" in prompt and "calls" in prompt


def test_label_prompt_contains_member_labels_not_contents(monkeypatch):
    import graphify.semantic_judge as sj
    captured = {}

    def fake_call(prompt, *, backend, max_tokens=1024, model=None, usage_out=None):
        captured["prompt"] = prompt
        return '{"0": "yes"}'

    monkeypatch.setattr(sj, "_call_llm", fake_call)
    G, communities = _label_graph()
    validate_community_labels({0: "Orders"}, {0: communities[0]}, G, backend="gemini")
    prompt = captured["prompt"]
    assert "place_order" in prompt
    assert "OrderRepository" in prompt
    assert "def " not in prompt