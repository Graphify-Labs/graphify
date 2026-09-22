import json

from tools import jev_shadow_m3 as m3


def graph():
    return {"nodes": [
        {"id": "a", "source_file": "src/a.py", "community": 1},
        {"id": "b", "source_file": "src/b.py", "community": 1},
        {"id": "c", "source_file": "tests/c_test.py", "community": 2},
        {"id": "d", "source_file": "src/d.py", "community": 1},
    ], "links": [
        {"source": "a", "target": "b", "relation": "imports"},
        {"source": "b", "target": "c", "relation": "tests"},
        {"source": "a", "target": "a", "relation": "contains"},
    ]}


def case():
    return {"case_id": "opaque-case", "pr": 9, "url": "https://example.test/9", "title": "Improve sample",
            "head_sha": "a" * 40, "merge_base_sha": "b" * 40, "changed_files": ["src/a.py", "src/b.py", "new.py"],
            "github_changed_files": [{"path": "src/a.py", "status": "modified"}, {"path": "src/b.py", "status": "modified"}, {"path": "new.py", "status": "added"}]}


def test_projection_is_deterministic_and_excludes_within_file_edges():
    first = m3.project(graph()); second = m3.project(graph())
    assert first == second
    assert first["relations"] == [{"source": "src/a.py", "target": "src/b.py", "relation": "imports", "provenance": "EXTRACTED", "direction": "forward", "count": 1}, {"source": "src/b.py", "target": "tests/c_test.py", "relation": "tests", "provenance": "EXTRACTED", "direction": "forward", "count": 1}]


def test_added_file_is_not_prechange_referenceable_and_fold_hides_target():
    projection = m3.project(graph()); result, absent = m3.folds(case(), projection)
    assert absent == ["new.py"] and result
    assert all(fold["hidden_target"] not in fold["seed_files"] for fold in result)


def test_max_three_folds_uses_content_independent_stable_order():
    value = case(); value["changed_files"] = [f"src/{name}.py" for name in "abcdef"]
    value["github_changed_files"] = [{"path": path, "status": "modified"} for path in value["changed_files"]]
    projection = {"files": [{"path": path} for path in value["changed_files"]], "relations": []}
    first, _ = m3.folds(value, projection); second, _ = m3.folds(value, projection)
    assert len(first) == 3 and first == second


def test_candidates_do_not_need_target_truth_and_ranking_is_stable():
    projection = m3.project(graph())
    first = m3.candidates(projection, ["src/a.py"], 8)
    assert first == m3.candidates(projection, ["src/a.py"], 8)
    assert m3._rank(first, "src/b.py") == m3._rank(first, "src/b.py")


def test_payload_has_no_hidden_label_or_historical_metadata():
    projection = m3.project(graph()); fold, _ = m3.folds(case(), projection); fold = fold[0]
    files = {row["path"]: row for row in projection["files"]}
    fold["seed_metadata"] = [{key: files[path][key] for key in ("path", "basename", "parent", "node_count", "community_count", "test_like")} for path in fold["seed_files"]]
    encoded = json.dumps(m3.payload(fold, "Improve sample", m3.candidates(projection, fold["seed_files"], 8)))
    assert "hidden_target" not in encoded and "changed_files" not in encoded and "head_sha" not in encoded and "opaque-case" not in encoded


def test_same_fold_has_same_payload_fingerprint():
    projection = m3.project(graph()); fold, _ = m3.folds(case(), projection); fold = fold[0]
    files = {row["path"]: row for row in projection["files"]}
    fold["seed_metadata"] = [{key: files[path][key] for key in ("path", "basename", "parent", "node_count", "community_count", "test_like")} for path in fold["seed_files"]]
    rows = m3.candidates(projection, fold["seed_files"], 8)
    assert m3._sha(m3.payload(fold, "Improve sample", rows)) == m3._sha(m3.payload(fold, "Improve sample", rows))


def test_offline_evaluation_never_calls_typesafe(monkeypatch):
    monkeypatch.setattr(m3.m1, "_read_record", lambda _case: None)
    monkeypatch.setattr(m3, "call_typesafe", lambda *_args: (_ for _ in ()).throw(AssertionError("network called")))
    result = m3.evaluate([case()])
    assert result["live_calls"] == 0 and result["conclusion"] == "M3_EVIDENCE_INSUFFICIENT"


def test_metrics_topk_and_reciprocal_rank():
    result = m3.metrics([{"rank": 1}, {"rank": 4}], "rank")
    assert result == {"top1": 0.5, "top3": 0.5, "mrr": 0.625, "median_rank": 2.5}
