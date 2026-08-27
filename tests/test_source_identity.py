from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from graphify.detect import detect
from graphify.source_identity import (
    FreshnessReason,
    PENDING_FILENAME,
    SOURCE_MANIFEST_FILENAME,
    begin_reconciliation,
    freshness_status,
    publish_source_identity,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Graphify test",
        "GIT_AUTHOR_EMAIL": "graphify@example.com",
        "GIT_COMMITTER_NAME": "Graphify test",
        "GIT_COMMITTER_EMAIL": "graphify@example.com",
    }
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )


def _repo(tmp_path: Path, name: str = "repo") -> Path:
    repo = tmp_path / name
    repo.mkdir()
    (repo / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
    (repo / "app.py").write_text("def answer():\n    return 42\n", encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "initial")
    return repo


def _artifact(repo: Path) -> Path:
    out = repo / "graphify-out"
    out.mkdir()
    graph = {
        "directed": False,
        "multigraph": False,
        "graph": {},
        "nodes": [
            {
                "id": "answer",
                "label": "answer",
                "source_file": "app.py",
                "source_location": "L1",
                "community": 0,
            }
        ],
        "links": [],
    }
    graph_path = out / "graph.json"
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    publish_source_identity(graph_path, repo, detection=detect(repo))
    return graph_path


def _cli(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}
    return subprocess.run(
        [sys.executable, "-m", "graphify", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env,
    )


def _status(repo: Path, graph_path: Path | None = None) -> tuple[subprocess.CompletedProcess[str], dict]:
    args = ["status", str(repo), "--json"]
    if graph_path is not None:
        args.extend(["--graph", str(graph_path)])
    result = _cli(repo, *args)
    return result, json.loads(result.stdout)


def test_status_accepts_current_real_repository_artifact(tmp_path):
    repo = _repo(tmp_path)
    graph_path = _artifact(repo)

    result, payload = _status(repo, graph_path)

    assert result.returncode == 0
    assert payload["eligible"] is True
    assert payload["reason_codes"] == []
    assert payload["source_identity"]["root"] == str(repo.resolve())
    assert len(payload["source_identity"]["revision"]) == 40
    assert len(payload["source_identity"]["manifest_digest"]) == 64
    assert payload["source_identity"]["detector"] == {
        "name": "graphify.detect",
        "version": "1",
    }


def test_status_accepts_a_current_source_tree_without_git(tmp_path):
    source = tmp_path / "plain-source"
    source.mkdir()
    (source / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    graph_path = _artifact(source)

    result, payload = _status(source, graph_path)

    assert result.returncode == 0
    assert payload["eligible"] is True
    assert payload["source_identity"]["revision"] is None


def test_status_rejects_legacy_graph_without_identity(tmp_path):
    repo = _repo(tmp_path)
    out = repo / "graphify-out"
    out.mkdir()
    graph_path = out / "graph.json"
    graph_path.write_text('{"nodes": [], "links": []}', encoding="utf-8")

    result, payload = _status(repo, graph_path)

    assert result.returncode == 1
    assert payload["eligible"] is False
    assert payload["reason_codes"] == ["missing_identity"]


def test_status_rejects_artifact_copied_from_another_root(tmp_path):
    source = _repo(tmp_path, "source")
    source_graph = _artifact(source)
    target = _repo(tmp_path, "target")
    target_out = target / "graphify-out"
    shutil.copytree(source_graph.parent, target_out)

    result, payload = _status(target, target_out / "graph.json")

    assert result.returncode == 1
    assert "wrong_root" in payload["reason_codes"]


def test_status_rejects_a_new_commit_even_when_files_do_not_change(tmp_path):
    repo = _repo(tmp_path)
    graph_path = _artifact(repo)
    _git(repo, "commit", "--allow-empty", "-qm", "advance")

    result, payload = _status(repo, graph_path)

    assert result.returncode == 1
    assert "revision_mismatch" in payload["reason_codes"]


def test_status_rejects_a_dirty_supported_file(tmp_path):
    repo = _repo(tmp_path)
    graph_path = _artifact(repo)
    (repo / "app.py").write_text("def answer():\n    return 43\n", encoding="utf-8")

    result, payload = _status(repo, graph_path)

    assert result.returncode == 1
    assert "changed_supported_files" in payload["reason_codes"]


def test_status_ignores_files_excluded_by_graphify_detection(tmp_path):
    repo = _repo(tmp_path)
    graph_path = _artifact(repo)
    (repo / "ignored.txt").write_text("not part of the corpus\n", encoding="utf-8")

    result, payload = _status(repo, graph_path)

    assert result.returncode == 0
    assert payload["eligible"] is True
    assert payload["reason_codes"] == []


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("missing", "missing_manifest"),
        ("mismatched", "manifest_mismatch"),
    ],
)
def test_status_rejects_a_missing_or_mismatched_source_manifest(
    tmp_path, mutation: str, reason: str
):
    repo = _repo(tmp_path)
    graph_path = _artifact(repo)
    manifest_path = graph_path.parent / SOURCE_MANIFEST_FILENAME
    if mutation == "missing":
        manifest_path.unlink()
    else:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["files"].append({"path": "forged.py", "sha256": "0" * 64, "type": "code"})
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result, payload = _status(repo, graph_path)

    assert result.returncode == 1
    assert reason in payload["reason_codes"]


def test_status_rejects_pending_reconciliation(tmp_path):
    repo = _repo(tmp_path)
    graph_path = _artifact(repo)
    (graph_path.parent / PENDING_FILENAME).write_text("1", encoding="utf-8")

    result, payload = _status(repo, graph_path)

    assert result.returncode == 1
    assert "pending_reconciliation" in payload["reason_codes"]


def test_query_rechecks_after_an_external_status_call(tmp_path):
    repo = _repo(tmp_path)
    graph_path = _artifact(repo)
    first, payload = _status(repo, graph_path)
    assert first.returncode == 0
    assert payload["eligible"] is True
    (repo / "app.py").write_text("def answer():\n    return 0\n", encoding="utf-8")

    query = _cli(repo, "query", "answer", "--graph", str(graph_path))

    assert query.returncode == 1
    assert "changed_supported_files" in query.stderr
    assert "Subgraph" not in query.stdout


def test_query_prints_the_bound_source_identity(tmp_path):
    repo = _repo(tmp_path)
    graph_path = _artifact(repo)

    query = _cli(repo, "query", "answer", "--graph", str(graph_path))

    assert query.returncode == 0, query.stderr
    assert f"source root={repo.resolve()}" in query.stderr
    assert " revision=" in query.stderr
    assert " manifest=" in query.stderr
    assert " detector=graphify.detect/1" in query.stderr


def test_query_discards_a_result_when_source_changes_during_traversal(
    tmp_path, monkeypatch, capsys
):
    import graphify.__main__ as mainmod
    import graphify.serve as serve

    repo = _repo(tmp_path)
    graph_path = _artifact(repo)
    monkeypatch.chdir(repo)
    original_query = serve._query_graph_text

    def mutate_during_query(*args, **kwargs):
        result = original_query(*args, **kwargs)
        (repo / "app.py").write_text("def answer():\n    return -1\n", encoding="utf-8")
        return result

    monkeypatch.setattr(serve, "_query_graph_text", mutate_during_query)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "query", "answer", "--graph", str(graph_path)],
    )

    with pytest.raises(SystemExit) as exited:
        mainmod.main()

    captured = capsys.readouterr()
    assert exited.value.code == 1
    assert "changed during query" in captured.err
    assert captured.out == ""


def test_full_extract_and_zero_change_update_publish_current_identity(tmp_path):
    repo = _repo(tmp_path)

    extract = _cli(repo, "extract", str(repo), "--code-only", "--no-cluster")
    assert extract.returncode == 0, extract.stderr
    graph_path = repo / "graphify-out" / "graph.json"
    first_identity = json.loads(graph_path.read_text(encoding="utf-8"))["source_identity"]
    first_status, first_payload = _status(repo, graph_path)
    assert first_status.returncode == 0
    assert first_payload["eligible"] is True

    update = _cli(repo, "update", str(repo), "--no-cluster")
    assert update.returncode == 0, update.stderr
    second_identity = json.loads(graph_path.read_text(encoding="utf-8"))["source_identity"]
    second_status, second_payload = _status(repo, graph_path)
    assert second_status.returncode == 0
    assert second_payload["eligible"] is True
    assert second_identity == first_identity


def test_code_update_cannot_upgrade_a_legacy_graph_with_unproven_documents(tmp_path):
    repo = _repo(tmp_path)
    (repo / "README.md").write_text("# Existing semantic content\n", encoding="utf-8")
    out = repo / "graphify-out"
    out.mkdir()
    graph_path = out / "graph.json"
    graph_path.write_text(
        json.dumps(
            {
                "nodes": [
                    {
                        "id": "legacy-doc",
                        "label": "Existing semantic content",
                        "source_file": "README.md",
                        "file_type": "document",
                    }
                ],
                "links": [],
            }
        ),
        encoding="utf-8",
    )

    update = _cli(repo, "update", str(repo), "--no-cluster")

    assert update.returncode == 0
    payload = json.loads(graph_path.read_text(encoding="utf-8"))
    assert "source_identity" not in payload
    assert (out / PENDING_FILENAME).is_file()


def test_cluster_only_preserves_source_identity(tmp_path):
    repo = _repo(tmp_path)
    extract = _cli(repo, "extract", str(repo), "--code-only", "--no-cluster")
    assert extract.returncode == 0, extract.stderr
    graph_path = repo / "graphify-out" / "graph.json"
    before = json.loads(graph_path.read_text(encoding="utf-8"))["source_identity"]

    cluster = _cli(repo, "cluster-only", str(repo), "--no-label", "--no-viz")

    assert cluster.returncode == 0, cluster.stderr
    after = json.loads(graph_path.read_text(encoding="utf-8"))["source_identity"]
    assert after == before
    assert freshness_status(repo, graph_path).eligible is True


def test_watch_rebuild_reconciles_identity_after_a_code_change(tmp_path):
    from graphify.watch import _rebuild_code

    repo = _repo(tmp_path)
    assert _rebuild_code(repo, acquire_lock=False, no_cluster=True) is True
    graph_path = repo / "graphify-out" / "graph.json"
    (repo / "app.py").write_text("def answer():\n    return 84\n", encoding="utf-8")
    assert freshness_status(repo, graph_path).eligible is False

    assert _rebuild_code(
        repo,
        changed_paths=[repo / "app.py"],
        acquire_lock=False,
        no_cluster=True,
    ) is True

    assert freshness_status(repo, graph_path).eligible is True
    assert not (graph_path.parent / PENDING_FILENAME).exists()


def test_failed_atomic_publication_leaves_the_artifact_pending(tmp_path, monkeypatch):
    import graphify.source_identity as source_identity

    repo = _repo(tmp_path)
    graph_path = _artifact(repo)
    old_graph = graph_path.read_bytes()
    (repo / "app.py").write_text("def answer():\n    return 7\n", encoding="utf-8")
    begin_reconciliation(graph_path)
    real_write = source_identity.write_json_atomic
    calls = 0

    def fail_graph_write(path, value, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated graph publication failure")
        return real_write(path, value, **kwargs)

    monkeypatch.setattr(source_identity, "write_json_atomic", fail_graph_write)

    with pytest.raises(OSError, match="simulated graph publication failure"):
        publish_source_identity(graph_path, repo, detection=detect(repo))

    assert graph_path.read_bytes() == old_graph
    assert (graph_path.parent / PENDING_FILENAME).is_file()
    status = freshness_status(repo, graph_path)
    assert FreshnessReason.PENDING_RECONCILIATION in status.reasons


def test_external_symlink_target_is_not_part_of_the_source_manifest(
    tmp_path, requires_symlinks
):
    repo = _repo(tmp_path)
    external = tmp_path / "outside.py"
    external.write_text("VALUE = 1\n", encoding="utf-8")
    (repo / "outside-link.py").symlink_to(external)
    graph_path = _artifact(repo)
    manifest = json.loads(
        (graph_path.parent / SOURCE_MANIFEST_FILENAME).read_text(encoding="utf-8")
    )

    assert "outside-link.py" not in {entry["path"] for entry in manifest["files"]}
    external.write_text("VALUE = 2\n", encoding="utf-8")
    assert freshness_status(repo, graph_path).eligible is True


def test_generated_full_build_runbooks_publish_source_identity():
    runbooks = sorted((REPO_ROOT / "graphify").glob("skill*.md"))
    assert runbooks
    for runbook in runbooks:
        text = runbook.read_text(encoding="utf-8")
        assert "begin_reconciliation(Path('graphify-out/graph.json'))" in text, runbook
        assert "publish_source_identity(Path('graphify-out/graph.json')" in text, runbook


def test_generated_update_runbooks_reconcile_zero_change_updates():
    references = sorted((REPO_ROOT / "graphify" / "skills").glob("*/references/update.md"))
    assert references
    for reference in references:
        text = reference.read_text(encoding="utf-8")
        assert "begin_reconciliation(Path('graphify-out/graph.json'))" in text, reference
        assert "if new_total == 0 and not deleted:" in text, reference
        zero_change = text.split("if new_total == 0 and not deleted:", 1)[1]
        assert "publish_source_identity(Path('graphify-out/graph.json')" in zero_change, reference
