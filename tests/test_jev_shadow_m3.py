import json

from tools import jev_shadow_m3 as m3


def _graph():
    return {"nodes": [
        {"id": "a", "source_file": "src/a.py", "community": 1},
        {"id": "b", "source_file": "src/b.py", "community": 1},
        {"id": "c", "source_file": "tests/c_test.py", "community": 2},
    ], "links": [{"source": "a", "target": "b", "relation": "imports"}, {"source": "b", "target": "c", "relation": "tests"}]}


def _case():
    return {"case_id": "opaque-case", "title": "Improve sample", "head_sha": "a" * 40, "merge_base_sha": "b" * 40,
            "changed_files": ["src/a.py", "src/b.py"], "github_changed_files": [{"path": "src/a.py", "status": "modified"}, {"path": "src/b.py", "status": "modified"}]}


def _fold_and_rows():
    projection = m3.project(_graph()); folds, _ = m3.folds(_case(), projection); fold = folds[0]
    files = {row["path"]: row for row in projection["files"]}
    fold["seed_metadata"] = [{key: files[path][key] for key in ("path", "basename", "parent", "node_count", "community_count", "test_like")} for path in fold["seed_files"]]
    return fold, m3.candidates(projection, fold["seed_files"], 8)


def test_each_candidate_has_one_explicitly_bound_question_and_no_score_leakage():
    fold, rows = _fold_and_rows()
    payload = m3.payload(fold, "Improve sample", rows)
    assert len(payload["questions"]) == len(rows)
    encoded = json.dumps(payload, sort_keys=True)
    assert "baseline_score" not in encoded
    for row in rows:
        matching = [question for question in payload["questions"].values() if row["path"] in question["instructions"]]
        assert len(matching) == 1
        assert all(other["path"] not in matching[0]["instructions"] for other in rows if other is not row)


def test_population_manifest_keeps_budget_instances_inspectable():
    result = {"candidate_budgets": [8, 12, 20], "selection_rule": m3.SELECTION_RULE, "population_fingerprint": "f" * 64,
              "folds": [{"fold_id": "fold", "candidate_budget": 8, "candidate_paths": ["src/b.py"], "candidate_fingerprint": "c" * 64}]}
    manifest = m3.population_manifest(result)
    assert manifest["population_fingerprint"] == "f" * 64
    assert manifest["folds"][0]["candidate_budget"] == 8


def test_missing_target_is_not_a_ranking_sample():
    result = m3.metrics([{"graphify_rank": 1}], "graphify_rank")
    assert result["mrr"] == 1.0
    assert m3.metrics([], "jev_rank")["mrr"] is None


def _evidence(budget_deltas, pr_deltas, *, top3_deltas=None):
    top3_deltas = top3_deltas or {"8": 0.0, "12": 0.0, "20": 0.0}
    baseline_budget = {key: {"mrr": 0.5, "top3": 0.5} for key in budget_deltas}
    jev_budget = {key: {"mrr": 0.5 + delta, "top3": 0.5 + top3_deltas.get(key, 0.0)}
                  for key, delta in budget_deltas.items()}
    baseline_pr = {key: {"mrr": 0.5} for key in pr_deltas}
    jev_pr = {key: {"mrr": 0.5 + delta} for key, delta in pr_deltas.items()}
    return baseline_budget, jev_budget, baseline_pr, jev_pr


def test_conclusion_all_positive_budgets_allow_neutral_prs():
    evidence = _evidence({"8": .14, "12": .22, "20": .21}, {"a": .12, "b": .11, "c": 0.0})
    assert m3.corrected_conclusion(True, True, *evidence) == "M3_JEV_ADDS_SIGNAL"


def test_conclusion_materially_negative_pr_prevents_adds_signal():
    evidence = _evidence({"8": .14, "12": .22, "20": .21}, {"a": .12, "b": .11, "c": -.10})
    assert m3.corrected_conclusion(True, True, *evidence) == "M3_JEV_NO_CLEAR_GAIN"


def test_conclusion_mixed_budget_evidence_is_unclear():
    evidence = _evidence({"8": .14, "12": -.01, "20": .21}, {"a": .12, "b": .11, "c": 0.0})
    assert m3.corrected_conclusion(True, True, *evidence) == "M3_JEV_NO_CLEAR_GAIN"


def test_conclusion_symmetric_negative_case_hurts_ranking():
    evidence = _evidence({"8": -.14, "12": -.22, "20": -.21}, {"a": -.12, "b": -.11, "c": 0.0})
    assert m3.corrected_conclusion(True, True, *evidence) == "M3_JEV_HURTS_RANKING"


def test_conclusion_insufficient_evidence_is_unchanged():
    evidence = _evidence({"8": .14, "12": .22}, {"a": .12, "b": .11})
    assert m3.corrected_conclusion(True, True, *evidence) == "M3_EVIDENCE_INSUFFICIENT"
