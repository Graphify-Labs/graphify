"""Offline boundary tests for the historical Jev evaluation harness."""
import json
from pathlib import Path

import pytest

from tools import jev_shadow_eval as evaluation


def case(**changes):
    value = {"case_id": "graphify-pr-1", "pr": 1, "url": "https://example.test/1", "title": "A title", "category": "test", "base_sha": "a" * 40, "head_sha": "b" * 40, "changed_files": ["a.py"]}
    value.update(changes)
    return value


def manifest(tmp_path: Path, cases, version=1):
    path = tmp_path / "cases.json"; path.write_text(json.dumps({"schema_version": version, "cases": cases})); return path


def test_valid_manifest(tmp_path):
    assert evaluation.load_manifest(manifest(tmp_path, [case()]))[0]["pr"] == 1


@pytest.mark.parametrize("cases, message", [([case(), case(case_id="graphify-pr-1", pr=2)], "case ID"), ([case(), case(case_id="graphify-pr-2")], "PR"), ([case(base_sha="bad")], "SHA"), ([case(changed_files=[])], "required fields")])
def test_invalid_manifest_rejected(tmp_path, cases, message):
    with pytest.raises(ValueError, match=message): evaluation.load_manifest(manifest(tmp_path, cases))


def test_unsupported_manifest_version(tmp_path):
    with pytest.raises(ValueError, match="unsupported"):
        evaluation.load_manifest(manifest(tmp_path, [case()], version=2))


def test_cache_key_includes_evaluator_and_base():
    assert evaluation._cache_key("a" * 40, "b" * 40) != evaluation._cache_key("c" * 40, "b" * 40)
    assert evaluation._cache_key("a" * 40, "b" * 40) != evaluation._cache_key("a" * 40, "c" * 40)


def test_collect_without_live_never_reads_key(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "should-not-be-read")
    with pytest.raises(ValueError, match="--live"):
        evaluation.collect([], False)


def test_task_only_uses_base_present_files():
    assert evaluation._task(case(), ["a.py"])["changed_files"] == ["a.py"]


def test_no_graph_seed_is_an_unresolved_prepare(monkeypatch, tmp_path):
    monkeypatch.setattr(evaluation, "_root", lambda _kind: tmp_path)
    monkeypatch.setattr(evaluation, "_git", lambda *_args: "f" * 40 if "rev-parse" in _args else "a.py")
    monkeypatch.setattr(evaluation, "_ensure_object", lambda _sha: None)
    monkeypatch.setattr(evaluation, "_extract", lambda *_args: (_ for _ in ()).throw(evaluation.JevShadowError("task seeds matched no graph nodes")))
    evaluation.prepare([case()])
    assert evaluation._read_record("graphify-pr-1")["prepare_status"] == "PREPARE_UNRESOLVED"
