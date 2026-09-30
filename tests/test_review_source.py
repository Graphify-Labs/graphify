"""Fixed Git objects, source boundaries, and failure behavior for human reviews."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from graphify import review_source as source


def git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                            encoding="utf-8", check=True)
    return result.stdout.strip()


@pytest.fixture
def repository(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.name", "Review tests")
    git(tmp_path, "config", "user.email", "review@example.invalid")
    git(tmp_path, "config", "core.autocrlf", "false")
    hooks = tmp_path / "empty-hooks"
    hooks.mkdir()
    git(tmp_path, "config", "core.hooksPath", str(hooks))
    (tmp_path / "auth.py").write_text("def authenticate(credentials):\n    return create_session(credentials)\n\ndef create_session(credentials):\n    return credentials\n", encoding="utf-8")
    (tmp_path / "app.py").write_text("from auth import authenticate\n\ndef login(credentials):\n    return authenticate(credentials)\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "base")
    base = git(tmp_path, "rev-parse", "HEAD")
    (tmp_path / "auth.py").write_text("def authenticate(credentials):\n    if credentials.get('mfa'):\n        return challenge(credentials)\n    return create_session(credentials)\n\ndef challenge(credentials):\n    return 'challenge'\n\ndef create_session(credentials):\n    return credentials\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "head")
    return tmp_path, base, git(tmp_path, "rev-parse", "HEAD")


def test_snapshots_read_committed_source_not_dirty_index_or_worktree(repository, tmp_path):
    root, base, head = repository
    (root / "auth.py").write_text("DIRTY SECRET", encoding="utf-8")
    git(root, "add", "auth.py")
    (root / "auth.py").write_text("MORE DIRTY", encoding="utf-8")
    snapshot = source.materialize_snapshot(root, head, tmp_path / "snapshot")
    assert "challenge" in snapshot["sources"]["auth.py"]
    assert "DIRTY" not in snapshot["sources"]["auth.py"]
    assert (root / "auth.py").read_text() == "MORE DIRTY"
    assert source.git_target(root, base, head)["head"] == head


def test_merge_base_excludes_changes_only_on_base_branch(repository):
    root, base, head = repository
    git(root, "checkout", "-qb", "other", base)
    (root / "only-base.py").write_text("BASE_ONLY = True\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-qm", "base tip")
    tip = git(root, "rev-parse", "HEAD")
    target = source.git_target(root, tip, head)
    assert target["base_tip"] == tip
    assert target["comparison_base"] == base
    assert [c["head_file"] for c in source.changed_files(root, base, head)] == ["auth.py"]


def test_sensitive_ignore_binary_size_and_tracked_gitignore(repository, monkeypatch, tmp_path):
    root, _, _ = repository
    for name, data in {".env": b"SECRET=yes", "binary.py": b"\x00binary", "huge.py": b"x" * 300,
                       "ignored.py": b"SECRET=True", "tracked.py": b"SAFE=True", "space ü.py": b"SAFE=True"}.items():
        (root / name).write_bytes(data)
    (root / ".graphifyignore").write_text("ignored.py\n", encoding="utf-8")
    (root / ".gitignore").write_text("tracked.py\n", encoding="utf-8")
    git(root, "add", "-f", ".")
    git(root, "commit", "-qm", "boundaries")
    monkeypatch.setattr(source, "MAX_FILE_BYTES", 250)
    snapshot = source.materialize_snapshot(root, git(root, "rev-parse", "HEAD"), tmp_path / "snapshot")
    assert "tracked.py" in snapshot["sources"]
    assert "space ü.py" in snapshot["sources"]
    assert not {".env", "binary.py", "huge.py", "ignored.py"} & snapshot["sources"].keys()
    assert len(snapshot["omitted"]) >= 4
    assert not (snapshot["root"] / ".env").exists()


def test_symlinks_are_not_materialized(repository, requires_symlinks, tmp_path):
    root, _, _ = repository
    (root / "link.py").symlink_to("auth.py")
    git(root, "add", "link.py")
    git(root, "commit", "-qm", "link")
    snapshot = source.materialize_snapshot(root, git(root, "rev-parse", "HEAD"), tmp_path / "snapshot")
    assert not (snapshot["root"] / "link.py").exists()
    assert {"file": "link.py", "reason": "symlink_or_gitlink"} in snapshot["omitted"]


@pytest.mark.parametrize("name", ["../outside", "/absolute", "C:/outside.py", "a\\b.py", "NUL.py", "a/.git/config", "a/.Git/config", "a\nb.py", "a//b.py"])
def test_unsafe_portable_paths(name):
    assert not source._safe_path(name)


def test_manifest_preserves_rename_add_delete_and_newline_paths(monkeypatch, tmp_path):
    raw = b"R100\0old name.py\0new name.py\0A\0a\nb.py\0D\0gone.py\0"
    monkeypatch.setattr(source, "_run", lambda *args, **kwargs: raw)
    changes = source.changed_files(tmp_path, "base", "head")
    assert {"status": "R100", "base_file": "old name.py", "head_file": "new name.py"} in changes
    assert {"status": "A", "base_file": None, "head_file": "a\nb.py"} in changes
    assert {"status": "D", "base_file": "gone.py", "head_file": None} in changes


def test_diff_disables_external_execution(monkeypatch, tmp_path):
    calls = []
    def run(root, args, **kwargs):
        calls.append(args)
        return b""
    monkeypatch.setattr(source, "_run", run)
    source.changed_files(tmp_path, "a" * 40, "b" * 40)
    assert "--no-ext-diff" in calls[0] and "--no-textconv" in calls[0]


def test_missing_revision_fails(repository):
    root, _, _ = repository
    with pytest.raises(source.ReviewError):
        source.resolve_commit(root, "missing-revision")
    with pytest.raises(source.ReviewError):
        source.resolve_commit(root, "--help")


def test_requested_pr_is_fetched_directly_and_repo_mismatch_rejected(monkeypatch, tmp_path):
    calls = []
    def run(root, args, **kwargs):
        calls.append(args)
        if args[1:3] == ["repo", "view"]:
            return json.dumps({"nameWithOwner": "owner/repo"}).encode()
        return json.dumps({"number": 999, "title": "Title", "body": "Body", "url": "https://github.com/owner/repo/pull/999",
                           "baseRefOid": "a" * 40, "headRefOid": "b" * 40}).encode()
    monkeypatch.setattr(source, "_run", run)
    monkeypatch.setattr(source, "resolve_commit", lambda root, ref: ref)
    monkeypatch.setattr(source, "git_target", lambda *args: {"comparison_base": "a" * 40, "head": "b" * 40})
    target = source.pr_target(tmp_path, 999)
    assert target["number"] == 999
    assert ["gh", "pr", "view", "999"] == calls[1][:4]
    with pytest.raises(source.ReviewError, match="checkout"):
        source.pr_target(tmp_path, 999, "other/repo")


def test_excluded_source_is_never_in_patch():
    snapshots = {"base": {"sources": {}}, "head": {"sources": {"private.py": "SECRET\n"}}}
    evidence, coverage = source.file_evidence({"base_file": "private.py", "head_file": "private.py"}, snapshots,
                                             {"comparison_base": "a" * 40, "head": "b" * 40}, "change-1")
    assert not evidence
    assert not coverage["patch"]
    assert coverage["sides"]["base"] == "unavailable"
