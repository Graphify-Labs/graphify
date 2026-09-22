from __future__ import annotations

import json

import pytest

from graphify import change_completeness as cc
from graphify import missing_impact as mi


def _graph():
    paths = ["pkg/a.py", "pkg/consumer.py", "tests/test_a.py", "docs/a.md", "docs/guide.md", "config/app.yaml", "migrations/001_a.py"]
    nodes = [{"id": str(index), "label": path, "source_file": path, "community": 1} for index, path in enumerate(paths)]
    return {"nodes": nodes, "links": [{"source": "1", "target": "0", "relation": "calls"}]}


def _write(tmp_path):
    root = tmp_path / "repo"
    (root / "graphify-out").mkdir(parents=True)
    (root / "graphify-out" / "graph.json").write_text(json.dumps(_graph()))
    return root


def test_file_classification_is_conservative_and_multi_role():
    assert cc.file_dimensions("tests/test_api.py", test_like=True) == {"tests"}
    assert cc.file_dimensions("docs/guide.md") == {"documentation"}
    assert cc.file_dimensions("docs/schema.md") == {"documentation", "migration_or_schema"}
    assert cc.file_dimensions("data.json") == set()
    assert cc.file_dimensions("config/settings.yaml") == {"configuration"}
    assert cc.file_dimensions("migrations/001_a.py") == {"migration_or_schema"}
    assert cc.file_dimensions("pkg/worker.py") == {"implementation"}


def test_plan_classifies_structural_consumers_and_candidate_evidence(tmp_path, monkeypatch, capsys):
    root = _write(tmp_path)
    monkeypatch.setattr(mi, "call_typesafe", lambda *_: pytest.fail("network called"))
    cc.run(["--task", "fix", "--repo", str(root), "--changed", "pkg/a.py", "--json"])
    plan = json.loads(capsys.readouterr().out)
    assert plan["status"] == "NEEDS_SOURCE_VERIFICATION"
    assert plan["dimensions"]["implementation"]["state"] == "CHANGED_EVIDENCE"
    assert plan["dimensions"]["consumers"]["state"] == "VERIFY_CANDIDATE"
    assert plan["dimensions"]["tests"]["verify_candidates"] == ["tests/test_a.py"]
    assert plan["dimensions"]["documentation"]["state"] == "VERIFY_CANDIDATE"
    assert plan["dimensions"]["configuration"]["state"] == "VERIFY_CANDIDATE"
    assert plan["dimensions"]["migration_or_schema"]["state"] == "VERIFY_CANDIDATE"
    assert "COMPLETE" not in json.dumps(plan)


def test_changed_evidence_wins_and_no_candidate_is_not_a_verdict(tmp_path, capsys):
    root = _write(tmp_path)
    cc.run(["--task", "docs", "--repo", str(root), "--changed", "docs/a.md", "--json"])
    plan = json.loads(capsys.readouterr().out)
    assert plan["dimensions"]["documentation"]["state"] == "CHANGED_EVIDENCE"
    assert plan["dimensions"]["documentation"]["verify_candidates"]
    assert all(item["state"] in {"CHANGED_EVIDENCE", "VERIFY_CANDIDATE", "NO_STRUCTURAL_EVIDENCE"} for item in plan["dimensions"].values())


def test_live_uses_shared_single_jev_request_and_semantic_order(tmp_path, monkeypatch, capsys):
    root, calls = _write(tmp_path), []
    def fake(payload, _key):
        calls.append(payload)
        return {"model": "jev-test", "usage": {"input_tokens": 1}, "answers": {key: {"noul": float(index)} for index, key in enumerate(payload["questions"], 1)}}
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    monkeypatch.setattr(mi, "call_typesafe", fake)
    cc.run(["--task", "fix", "--repo", str(root), "--changed", "pkg/a.py", "--live", "--json"])
    plan = json.loads(capsys.readouterr().out)
    assert len(calls) == 1
    assert plan["candidates"][0]["semantic_rank"] == 1
    assert all(row["provenance"] == "JEV_INFERRED" for row in plan["candidates"])


def test_both_commands_use_shared_prepare_path(tmp_path, monkeypatch, capsys):
    root, calls = _write(tmp_path), []
    original = mi.prepare_analysis
    def wrapped(**kwargs):
        calls.append(kwargs)
        return original(**kwargs)
    monkeypatch.setattr(mi, "prepare_analysis", wrapped)
    mi.run(["--task", "fix", "--repo", str(root), "--changed", "pkg/a.py", "--json"])
    capsys.readouterr()
    cc.run(["--task", "fix", "--repo", str(root), "--changed", "pkg/a.py", "--json"])
    assert len(calls) == 2
