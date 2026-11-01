"""Fixed Git objects, source boundaries, and failure behavior for human reviews."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from graphify import review_source as source


def git(root: Path, *args: str) -> str:
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
               GIT_TERMINAL_PROMPT="0")
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                            encoding="utf-8", check=True, env=env, timeout=30)
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
    raw = (b":100644 100644 a b R100\0old name.py\0new name.py\0"
           b":000000 100644 0 b A\0a\nb.py\0:100644 000000 a 0 D\0gone.py\0")
    monkeypatch.setattr(source, "_run", lambda *args, **kwargs: raw)
    changes = source.changed_files(tmp_path, "base", "head")
    names = [{k: c[k] for k in ("status", "base_file", "head_file")} for c in changes]
    assert {"status": "R100", "base_file": "old name.py", "head_file": "new name.py"} in names
    assert {"status": "A", "base_file": None, "head_file": "a\nb.py"} in names
    assert {"status": "D", "base_file": "gone.py", "head_file": None} in names


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
            return json.dumps({"nameWithOwner": "owner/repo", "url": "https://github.com/owner/repo"}).encode()
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


def test_invalid_utf8_changed_path_never_cites_a_valid_sibling(repository, tmp_path):
    root, _, _ = repository
    (root / "bad�.py").write_text("SAFE SIBLING CONTENT\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-qm", "valid sibling")
    before = git(root, "rev-parse", "HEAD")
    oid = source._run(root, ["git", "hash-object", "-w", "--stdin"], input_bytes=b"INVALID PATH CONTENT\n").strip()
    listing = source._run(root, ["git", "ls-tree", "-z", before])
    tree = source._run(root, ["git", "mktree", "-z"], input_bytes=listing + b"100644 blob " + oid + b"\tbad\xff.py\0").strip().decode()
    after = source._run(root, ["git", "commit-tree", tree, "-p", before], input_bytes=b"invalid path\n").strip().decode()
    change = source.changed_files(root, before, after)[0]
    assert change["head_path_bytes"] == b"bad\xff.py".hex()
    snapshots = {side: source.materialize_snapshot(root, revision, tmp_path / side)
                 for side, revision in (("base", before), ("head", after))}
    evidence, coverage = source.file_evidence(change, snapshots, {"comparison_base": before, "head": after}, "change-1")
    assert not evidence and not coverage["patch"]
    assert coverage["sides"]["head"] == "unavailable"


def test_grafts_and_ambient_topology_do_not_change_pinned_comparison(repository, monkeypatch):
    root, base, head = repository
    (root / ".git" / "info" / "grafts").write_text(head + "\n", encoding="utf-8")
    for key in ("GIT_COMMON_DIR", "GIT_SHALLOW_FILE", "GIT_GRAFT_FILE"):
        monkeypatch.setenv(key, str(root / "missing"))
    assert source.git_target(root, base, head)["comparison_base"] == base


def test_sensitive_files_do_not_starve_the_source_budget(repository, monkeypatch, tmp_path):
    root, _, _ = repository
    (root / ".env").write_text("SECRET=1\n", encoding="utf-8")
    git(root, "add", "-f", ".env")
    git(root, "commit", "-qm", "sensitive source")
    monkeypatch.setattr(source, "MAX_FILES", 1)
    snapshot = source.materialize_snapshot(root, git(root, "rev-parse", "HEAD"), tmp_path / "snapshot")
    assert "app.py" in snapshot["sources"] and ".env" not in snapshot["sources"]


def test_casefold_prefix_collision_is_omitted_before_writing(repository, tmp_path):
    root, _, _ = repository
    oid = source._run(root, ["git", "hash-object", "-w", "--stdin"], input_bytes=b"VALUE = 1\n").strip()
    child = source._run(root, ["git", "mktree", "-z"], input_bytes=b"100644 blob " + oid + b"\tb.py\0").strip()
    tree = source._run(root, ["git", "mktree", "-z"], input_bytes=b"100644 blob " + oid + b"\tA\0" + b"040000 tree " + child + b"\ta\0").strip().decode()
    snapshot = source.materialize_snapshot(root, tree, tmp_path / "snapshot")
    assert {"file": "a/b.py", "reason": "case_colliding_path"} in snapshot["omitted"]
    assert "a/b.py" not in snapshot["sources"]
    assert not source._safe_path("a" * 300)


def test_metadata_and_command_output_budgets_fail_closed(repository, monkeypatch, tmp_path):
    root, _, head = repository
    with pytest.raises(source.ReviewError, match="output exceeded"):
        source._run(root, ["git", "rev-parse", "HEAD"], max_output_bytes=1)
    monkeypatch.setattr(source, "MAX_METADATA_FILES", 1)
    with pytest.raises(source.ReviewError, match="metadata exceeded"):
        source.materialize_snapshot(root, head, tmp_path / "snapshot")


@pytest.mark.parametrize("before,after", [("x\n", "x"), ("x\r\n", "x\n"),
                                         ('x = "a\u2028b"\ny = 1\n', 'x = "a\u2028b"\ny = 2\n')])
def test_physical_line_and_terminator_changes_have_faithful_evidence(before, after):
    snapshots = {"base": {"sources": {"a.py": before}}, "head": {"sources": {"a.py": after}}}
    evidence, coverage = source.file_evidence({"base_file": "a.py", "head_file": "a.py"}, snapshots,
                                             {"comparison_base": "a" * 40, "head": "b" * 40}, "change-1")
    assert evidence and coverage["patch"] and coverage["changed_ranges"]["head"]
    assert all(e["line_end"] <= 2 for e in evidence)
    if "\u2028" in before:
        assert "\u2028" in evidence[0]["snippet"]
        assert coverage["changed_ranges"]["head"] == [(2, 2)]
    if not after.endswith("\n"):
        assert "No newline at end of file" in coverage["patch"]


def test_repetitive_diff_uses_bounded_linear_fallback(monkeypatch):
    monkeypatch.setattr(source, "MAX_DIFF_WORK", 4)
    monkeypatch.setattr(source.difflib, "SequenceMatcher", lambda *args, **kwargs: pytest.fail("unbounded matcher entered"))
    before = "x\n" * 8000
    after = "x\n" * 7999 + "changed\n"
    snapshots = {"base": {"sources": {"a.py": before}}, "head": {"sources": {"a.py": after}}}
    evidence, coverage = source.file_evidence({"base_file": "a.py", "head_file": "a.py"}, snapshots,
                                             {"comparison_base": "a" * 40, "head": "b" * 40}, "change-1")
    assert coverage["diff_limited"] and coverage["changed_ranges"]["head"] == [(8000, 8000)]
    assert evidence[-1]["line_end"] == 8000 and "changed" in evidence[-1]["snippet"]


def test_executable_bit_change_is_visible_in_committed_metadata(repository, tmp_path):
    root, _, before = repository
    git(root, "update-index", "--chmod=+x", "auth.py")
    git(root, "commit", "-qm", "make executable")
    after = git(root, "rev-parse", "HEAD")
    change = source.changed_files(root, before, after)[0]
    assert (change["base_mode"], change["head_mode"]) == ("100644", "100755")
    snapshots = {side: source.materialize_snapshot(root, rev, tmp_path / side)
                 for side, rev in (("base", before), ("head", after))}
    _, coverage = source.file_evidence(change, snapshots, {"comparison_base": before, "head": after}, "change-1")
    assert "100644 → 100755" in coverage["patch"]


def test_missing_pr_objects_fetch_repository_url_without_origin(monkeypatch, tmp_path):
    calls, available = [], set()
    def run(root, args, **kwargs):
        calls.append(args)
        if args[0] == "git":
            available.add(args[-1])
            return b""
        if args[1:3] == ["repo", "view"]:
            return json.dumps({"nameWithOwner": "owner/repo", "url": "https://github.com/owner/repo"}).encode()
        return json.dumps({"baseRefOid": "a" * 40, "headRefOid": "b" * 40, "title": "T", "url": "https://github.com/owner/repo/pull/1"}).encode()
    def resolve(root, ref):
        if ref not in available:
            raise source.ReviewError("not local")
        return ref
    monkeypatch.setattr(source, "_run", run)
    monkeypatch.setattr(source, "resolve_commit", resolve)
    monkeypatch.setattr(source, "git_target", lambda *args: {})
    source.pr_target(tmp_path, 1)
    fetches = [c for c in calls if c[0] == "git"]
    assert len(fetches) == 2 and all(c[-2] == "https://github.com/owner/repo" for c in fetches)


@pytest.mark.parametrize("content", [b"*.py\x00", b"*.py\xff", b"*.py\n" * 20])
def test_unreadable_ignore_rules_fail_closed(repository, monkeypatch, tmp_path, content):
    root, _, _ = repository
    (root / ".graphifyignore").write_bytes(content)
    git(root, "add", ".graphifyignore")
    git(root, "commit", "-qm", "unreadable ignore rules")
    monkeypatch.setattr(source, "MAX_FILE_BYTES", 90)
    with pytest.raises(source.ReviewError, match="ignore rules"):
        source.materialize_snapshot(root, git(root, "rev-parse", "HEAD"), tmp_path / "snapshot")


def test_fixture_git_commands_ignore_ambient_repository_redirects(repository, monkeypatch):
    root, _, head = repository
    monkeypatch.setenv("GIT_DIR", str(root / "foreign"))
    monkeypatch.setenv("GIT_WORK_TREE", str(root / "foreign-worktree"))
    assert git(root, "rev-parse", "HEAD") == head


@pytest.mark.parametrize("marker", [
    "env/pyvenv.cfg", "tools_env/bin/activate", "env/Scripts/activate",
    "env/lib/python3.12/lib.py", "env/conda-meta/package.json",
    "coverage/lcov.info", "coverage/html-report/index.html",
    "out/module/app.class", "out/production/module/app.py", "out/_next/app.js",
    "snapshots/component.snap",
])
def test_metadata_markers_preserve_canonical_generated_directory_boundary(repository, tmp_path, marker):
    from graphify.detect import detect
    root, _, _ = repository
    directory = marker.split("/")[0]
    (root / marker).parent.mkdir(parents=True, exist_ok=True)
    # Binary markers still establish directory shape without entering source.
    (root / marker).write_bytes(b"\x00generated")
    (root / directory / "lib.py").write_text("def generated(): pass\n", encoding="utf-8")
    for real_source in ("domain/env", "domain/coverage", "domain/out", "domain/snapshots"):
        (root / real_source).mkdir(parents=True, exist_ok=True)
        (root / real_source / "real.py").write_text("def real(): pass\n", encoding="utf-8")
    git(root, "add", "-f", ".")
    git(root, "commit", "-qm", "generated directory markers")
    canonical = {Path(p).relative_to(root).as_posix() for paths in detect(root, gitignore=False)["files"].values() for p in paths}
    snapshot = source.materialize_snapshot(root, git(root, "rev-parse", "HEAD"), tmp_path / "snapshot")
    assert f"{directory}/lib.py" not in canonical | snapshot["sources"].keys()
    assert {f"domain/{part}/real.py" for part in ("env", "coverage", "out", "snapshots")} <= canonical & snapshot["sources"].keys()
    assert {"file": f"{directory}/lib.py", "reason": "excluded_or_sensitive"} in snapshot["omitted"]


def test_ignore_and_noise_marker_counts_are_bounded(repository, monkeypatch, tmp_path):
    root, _, _ = repository
    (root / ".graphifyignore").touch()
    (root / "nested").mkdir()
    (root / "nested/.graphifyignore").touch()
    git(root, "add", ".")
    git(root, "commit", "-qm", "many empty ignore files")
    monkeypatch.setattr(source, "MAX_IGNORE_FILES", 1)
    with pytest.raises(source.ReviewError, match="ignore rules exceeded"):
        source.materialize_snapshot(root, git(root, "rev-parse", "HEAD"), tmp_path / "snapshot")
    monkeypatch.setattr(source, "MAX_NOISE_MARKERS", 1)
    with pytest.raises(source.ReviewError, match="markers exceeded"):
        source._metadata_noise_dirs(["env/pyvenv.cfg", "coverage/lcov.info"])


def test_directory_only_ignore_rules_apply_before_source_admission(repository, monkeypatch, tmp_path):
    root, _, _ = repository
    (root / ".graphifyignore").write_text("private/\n!private/reinclude.py\n", encoding="utf-8")
    (root / "private/nested").mkdir(parents=True)
    (root / "private/nested/secret.py").write_text("SECRET = 'hidden'\n", encoding="utf-8")
    (root / "private/reinclude.py").write_text("SECRET = 'also hidden'\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-qm", "directory-only exclusions")
    # Only the ignore file and two original sources should consume slots.
    monkeypatch.setattr(source, "MAX_FILES", 3)
    snapshot = source.materialize_snapshot(root, git(root, "rev-parse", "HEAD"), tmp_path / "snapshot")
    assert snapshot["sources"].keys() == {".graphifyignore", "app.py", "auth.py"}
    assert not (snapshot["root"] / "private/nested/secret.py").exists()


@pytest.mark.parametrize("filename", ["file.py", ".graphifyignore"])
def test_snapshot_directory_structure_has_a_separate_budget(repository, monkeypatch, tmp_path, filename):
    root, _, _ = repository
    monkeypatch.setattr(source, "MAX_DIRECTORIES", 1)
    (root / "a/b").mkdir(parents=True)
    (root / "a/b" / filename).write_text("SAFE=True\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-qm", "deep structure")
    with pytest.raises(source.ReviewError, match="directory structure exceeded"):
        source.materialize_snapshot(root, git(root, "rev-parse", "HEAD"), tmp_path / "snapshot")
