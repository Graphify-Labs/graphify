"""Offline boundary tests for the historical Jev evaluation harness."""
import json
import subprocess
from pathlib import Path

import pytest

from tools import jev_shadow_eval as evaluation


def case(**changes):
    value = {"case_id": "graphify-pr-1", "pr": 1, "url": "https://example.test/1", "title": "A title", "category": "test", "base_sha": "a" * 40, "head_sha": "b" * 40, "merge_base_sha": "c" * 40, "changed_file_count": 1, "changed_files": ["a.py"], "github_changed_files": [{"path": "a.py", "status": "modified"}]}
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
    monkeypatch.setattr(evaluation, "_git", lambda *_args: "f" * 40 if "rev-parse" in _args else ("c" * 40 if "merge-base" in _args else "a.py"))
    monkeypatch.setattr(evaluation, "authoritative_changed_files", lambda *_args: [{"path": "a.py", "status": "M"}])
    monkeypatch.setattr(evaluation, "_ensure_object", lambda _sha: None)
    monkeypatch.setattr(evaluation, "_extract", lambda *_args: (_ for _ in ()).throw(evaluation.JevShadowError("task seeds matched no graph nodes")))
    evaluation.prepare([case()])
    assert evaluation._read_record("graphify-pr-1")["prepare_status"] == "PREPARE_UNRESOLVED"


def test_authoritative_changed_files_uses_name_status(monkeypatch):
    monkeypatch.setattr(evaluation, "_ensure_object", lambda _sha: None)
    monkeypatch.setattr(evaluation, "_git", lambda *args: "c" * 40 if args and args[0] == "merge-base" else "A\tsrc/new.py\nM\tsrc/old.py")
    assert evaluation.authoritative_changed_files("a" * 40, "b" * 40) == [
        {"path": "src/new.py", "status": "A"},
        {"path": "src/old.py", "status": "M"},
    ]


def test_manifest_requires_expected_count_and_github_evidence(tmp_path):
    bad = case(changed_file_count=2)
    with pytest.raises(ValueError, match="count"):
        evaluation.load_manifest(manifest(tmp_path, [bad]))


def test_prepare_archives_same_identity_previous_record(monkeypatch, tmp_path):
    monkeypatch.setattr(evaluation, "_root", lambda _kind: tmp_path)
    monkeypatch.setattr(evaluation, "_git", lambda *args: "c" * 40 if args and args[0] == "merge-base" else ("a" * 40 if args and args[0] == "rev-parse" else "a.py"))
    monkeypatch.setattr(evaluation, "authoritative_changed_files", lambda *_args: [{"path": "a.py", "status": "M"}])
    evaluation._write(evaluation._record_path("graphify-pr-1"), {"evaluator_sha": "a" * 40, "case_identity": evaluation._case_identity(case()), "prepare_status": "PREPARED", "collection_status": "LIVE_PASS"})
    monkeypatch.setattr(evaluation, "_extract", lambda *_args: (_ for _ in ()).throw(evaluation.JevShadowError("task seeds matched no graph nodes")))
    evaluation.prepare([case()])
    history = list((tmp_path / "history").glob("*.json"))
    assert len(history) == 1
    assert evaluation._json(history[0])["archive_reason"] == "SUPERSEDED_PREVIOUS_PREPARATION"


def test_merge_base_patch_excludes_diverged_base_changes(monkeypatch, tmp_path):
    repo = tmp_path / "git-repo"
    repo.mkdir()
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()
    git("init", "-q")
    git("config", "user.email", "test@example.invalid")
    git("config", "user.name", "test")
    (repo / "shared.txt").write_text("base\n")
    git("add", "."); git("commit", "-qm", "base")
    base_parent = git("rev-parse", "HEAD")
    git("checkout", "-qb", "pr")
    (repo / "pr.py").write_text("pr\n")
    git("add", "."); git("commit", "-qm", "pr")
    pr_head = git("rev-parse", "HEAD")
    git("checkout", "-q", "-")
    (repo / "unrelated.txt").write_text("unrelated\n")
    git("add", "."); git("commit", "-qm", "unrelated")
    reported_base = git("rev-parse", "HEAD")
    monkeypatch.setattr(evaluation, "ROOT", repo)
    assert evaluation.authoritative_changed_files(reported_base, pr_head) == [{"path": "pr.py", "status": "A"}]
    assert git("merge-base", reported_base, pr_head) == base_parent


def test_collect_stale_evaluator_makes_zero_typesafe_calls(monkeypatch, tmp_path):
    monkeypatch.setattr(evaluation, "_root", lambda _kind: tmp_path)
    record = {
        "prepare_status": "PREPARED", "evaluator_sha": "a" * 40,
        "case_identity": evaluation._case_identity(case()),
        "task": evaluation._task(case(), ["a.py"]), "task_fingerprint": evaluation._fingerprint(evaluation._task(case(), ["a.py"])),
        "graph_path": str(tmp_path / "graph.json"), "payload_path": str(tmp_path / "payload.json"),
        "graph_fingerprint": "b" * 64, "payload_fingerprint": "c" * 64,
    }
    evaluation._write(evaluation._record_path("graphify-pr-1"), record)
    monkeypatch.setattr(evaluation, "_git", lambda *_args: "d" * 40)
    monkeypatch.setattr(evaluation, "call_typesafe", lambda *_args: pytest.fail("stale evidence called TypeSafe"))
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-only")
    evaluation.collect([case()], live=True)
    assert evaluation._read_record("graphify-pr-1")["collection_status"] == "STALE"


def test_report_has_saturation_and_noul_columns(monkeypatch, tmp_path):
    monkeypatch.setattr(evaluation, "_root", lambda _kind: tmp_path)
    evaluation._write(evaluation._record_path("graphify-pr-1"), {
        "prepare_status": "PREPARED", "candidate_node_count": 40, "candidate_edge_count": 80,
        "node_cap_reached": True, "edge_cap_reached": True, "question_count": 3,
        "collection_status": "LIVE_PASS", "usage": {"input_tokens": 2, "output_tokens": 3},
        "result": {"graph_judgments": {
            "blast_radius": {"choice": "localized"},
            "consumer_discovery_needed": {"noul": 0.1},
            "test_evidence_discovery_needed": {"noul": 0.2},
        }},
    })
    path = evaluation.report([case()])
    text = path.read_text()
    assert "Node cap?" in text and "Edge cap?" in text and "Consumer Noul" in text and "Test Noul" in text
