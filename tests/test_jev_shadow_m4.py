import json

import pytest

from tools import jev_shadow_m4 as m4


def _row(group, fold, target=True, base=(10, 5, 1), jev=(.1, .9, .2)):
    paths = [f"{fold}/{i}" for i in range(len(base))]
    return {"fold_id": fold, "case_group": group, "candidate_paths": paths, "candidate_fingerprint": fold, "target_present": target, "hidden_target": paths[1], "baseline_scores": dict(zip(paths, base)), "graphify_rank": 2 if target else None, "candidate_noul": dict(zip(paths, jev)), "jev_rank": 1 if target else None}


def test_rank_scores_and_all_predeclared_fusions_are_deterministic():
    scores = {"a": 3, "b": 2, "c": 1}
    assert m4._rank_scores(scores) == {"a": 1, "b": .5, "c": 0}
    assert set(m4.hybrid_scores(scores, {"a": .1, "b": .9, "c": .2}, .5)) == set(scores)
    assert m4.FUSION_WEIGHTS == (.75, .50, .25)


def test_m4_budget_is_frozen_to_twelve():
    assert m4.BUDGET == 12


def test_rank_scores_handle_one_candidate_without_division_by_zero():
    assert m4._rank_scores({"only": 9}) == {"only": 1.0}


def test_margin_is_target_free_and_single_candidate_is_decisive():
    assert m4.uncertainty_margin({"a": 10, "b": 5}) == .5
    assert m4.uncertainty_margin({"a": 10}) is None
    assert not m4.should_call({"a": 10}, .30)


def test_gate_grid_is_frozen_and_always_call_fallback():
    assert m4.GATE_THRESHOLDS == (.02, .05, .10, .20, .30)
    assert m4.should_call({"a": 4}, m4.ALWAYS_CALL)
    assert m4._choose_gate([_row("a", "a")], [_row("a", "a")]) == m4.ALWAYS_CALL


def test_gate_decision_does_not_accept_target_or_pr_identity():
    baseline = {"a": 10, "b": 9}
    assert m4.should_call(baseline, .20) == m4.should_call(dict(reversed(list(baseline.items()))), .20)


def test_payload_has_no_target_or_baseline_information():
    row = _row("a", "a"); row.update({"objective": "Improve", "seed_metadata": [], "candidate_rows": [{"path": path, "baseline_score": score} for path, score in row["baseline_scores"].items()]})
    encoded = json.dumps(m4.payload_for(row), sort_keys=True)
    for forbidden in ("hidden_target", "target_present", "baseline_score", "case_group"):
        assert forbidden not in encoded


def test_collection_calls_target_missing_fold_too(monkeypatch):
    rows = [_row("a", "a", True), _row("a", "b", False)]
    for row in rows:
        row.update({"objective": "Improve", "seed_metadata": [], "candidate_rows": [{"path": path, "baseline_score": score} for path, score in row["baseline_scores"].items()]})
    seen = []
    def fake(payload, key):
        seen.append(payload); return {"answers": {question: {"noul": .5} for question in payload["questions"]}, "model": "fake", "usage": {"input_tokens": 1, "output_tokens": 1}}
    monkeypatch.setattr(m4, "call_typesafe", fake)
    result = m4.collect_live({"population_fingerprint": "p", "folds": rows}, "key")
    assert len(result["collections"]) == 2
    assert all(len(item["candidate_noul"]) == 3 for item in result["collections"])


def test_collection_rejects_mismatched_population_vectors():
    population = {"population_fingerprint": "one", "folds": [_row("a", "a")]}
    collection = {"population_fingerprint": "two", "collections": []}
    with pytest.raises(ValueError, match="frozen population"):
        m4._join(population, collection)


def test_collection_rejects_candidate_fingerprint_drift():
    row = _row("a", "a")
    population = {"population_fingerprint": "one", "folds": [row]}
    collection = {"population_fingerprint": "one", "collections": [{"fold_id": "a", "candidate_fingerprint": "different", "candidate_noul": row["candidate_noul"]}]}
    with pytest.raises(ValueError, match="candidate fingerprint"):
        m4._join(population, collection)


def test_lopo_never_uses_held_out_pr_for_fusion_choice():
    rows = [_row("a", "a"), _row("b", "b")]
    present, choices = m4.lopo_hybrid(rows)
    assert set(choices) == {"a", "b"}
    assert all("hybrid_strategy" in row for row in present)


def test_hybrid_result_requires_improvement_over_both_baselines():
    rows = [_row("a", "a"), _row("b", "b"), _row("c", "c"), _row("d", "d")]
    m4.lopo_hybrid(rows)
    assert m4._hybrid_result(rows) != "M4_HYBRID_ADDS_GAIN"


def test_lopo_gate_includes_missing_in_call_rate_and_excludes_it_from_mrr():
    rows = [_row("a", "a", True), _row("a", "missing", False), _row("b", "b", True)]
    m4.lopo_hybrid(rows)
    all_rows, policies = m4.lopo_selective(rows)
    assert len(all_rows) == 3 and set(policies) == {"a", "b"}
    assert m4._metrics([row for row in all_rows if row["target_present"]], "jev_rank")["mrr"] == 1


def test_selective_skip_uses_graphify_rank_not_jev_rank():
    row = _row("a", "a")
    row["graphify_rank"], row["jev_rank"] = 3, 1
    assert m4._selective_rank(row, .02, "jev_rank") == 3


def test_gain_retention_and_no_network_offline(monkeypatch):
    assert m4._retention(.8, .5, .9) == pytest.approx(.75)
    monkeypatch.setattr(m4, "call_typesafe", lambda *_: (_ for _ in ()).throw(AssertionError("network")))
    population = {"population_fingerprint": "p", "folds": [_row("a", "a"), _row("b", "b")]}
    collection = {"population_fingerprint": "p", "collections": [{"fold_id": row["fold_id"], "candidate_fingerprint": row["candidate_fingerprint"], "candidate_noul": row["candidate_noul"], "returned_model": "fake", "usage": {}} for row in population["folds"]]}
    first, second = m4.analyze(population, collection), m4.analyze(population, collection)
    assert first == second
