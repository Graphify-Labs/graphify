"""Portable admission/rebuild proof with narrow OS failure seams.

Real FIFO, socket, symlink and removed-CWD fixtures remain in their original
modules. These tests run on Windows too, protecting the production handling of
stat results and CWD lookup failures without claiming native POSIX object proof.
"""
from __future__ import annotations

import builtins
import errno
import io
import json
import os
import stat
from pathlib import Path

import pytest

from graphify.detect import _is_regular_file, detect
from graphify.watch import _rebuild_code


@pytest.mark.parametrize(
    "mode",
    [stat.S_IFIFO, stat.S_IFSOCK, stat.S_IFCHR, stat.S_IFBLK, stat.S_IFDIR],
    ids=["fifo", "socket", "character-device", "block-device", "directory"],
)
def test_req_core_002_ac01_detect_rejects_nonregular_stat_modes(tmp_path, monkeypatch, mode):
    """Admission rejects a special-file stat mode before any source reader runs."""
    candidate = tmp_path / "unsafe.py"
    candidate.write_text("def unsafe(): pass\n", encoding="utf-8")
    safe = tmp_path / "safe.py"
    safe.write_text("def safe(): pass\n", encoding="utf-8")
    real_stat = os.stat
    observed = []
    reads = []

    # Substitute only this source's native stat result. Discovery, admission,
    # classification and reporting still use the actual production functions.
    def special_stat(path, *args, **kwargs):
        result = real_stat(path, *args, **kwargs)
        if Path(path) == candidate:
            observed.append(path)
            fields = list(result)
            fields[0] = mode | stat.S_IRUSR
            return os.stat_result(fields)
        return result

    monkeypatch.setattr(os, "stat", special_stat)
    # Watch both builtin and pathlib readers: a caught reader error must not
    # conceal an attempted read of the source classified as nonregular.
    def guarded_reader(reader):
        def read(path, *args, **kwargs):
            if not isinstance(path, int) and Path(path) == candidate:
                reads.append(path)
                raise AssertionError("nonregular source reached a reader")
            return reader(path, *args, **kwargs)
        return read

    monkeypatch.setattr(builtins, "open", guarded_reader(builtins.open))
    monkeypatch.setattr(io, "open", guarded_reader(io.open))
    assert _is_regular_file(candidate) is False
    result = detect(tmp_path)
    assert observed
    assert str(candidate) not in result["files"]["code"]
    assert str(safe) in result["files"]["code"]
    assert str(candidate) + " [not a regular file]" in result["skipped_sensitive"]
    assert reads == []


@pytest.mark.parametrize("error_code", [errno.EACCES, errno.ENOENT, errno.ELOOP, errno.EIO])
def test_req_core_002_ac01_stat_failures_are_unreadable(tmp_path, monkeypatch, error_code):
    """Access failure, removal race, link loop and I/O failure reject the source."""
    candidate = tmp_path / "unreadable.py"
    candidate.write_text("def unreadable(): pass\n", encoding="utf-8")
    real_stat = os.stat
    calls = []

    # The source exists; only its owning stat boundary fails. Any other path,
    # including pytest's own artifacts, keeps the native filesystem behavior.
    def failed_stat(path, *args, **kwargs):
        if Path(path) == candidate:
            calls.append(path)
            raise OSError(error_code, os.strerror(error_code), str(candidate))
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(os, "stat", failed_stat)
    assert _is_regular_file(candidate) is False
    assert calls == [candidate]


def _fail_cwd_lookup(monkeypatch, unavailable):
    """Fail only cwd lookup in one real directory, preserving recovery chdir."""
    real_cwd = Path.cwd

    def lookup(cls):
        cwd = real_cwd()
        if cwd == unavailable:
            raise FileNotFoundError(errno.ENOENT, "current working directory was removed")
        return cwd

    monkeypatch.setattr(Path, "cwd", classmethod(lookup))


@pytest.mark.parametrize("root_kind", ["unset", "missing", "chdir-denied"])
def test_req_core_002_ac02_unavailable_cwd_rejects_before_artifacts(
    tmp_path, monkeypatch, capsys, root_kind
):
    """A failed CWD lookup retains prior graph bytes and creates no queue or lock."""
    unavailable = tmp_path / "unavailable"
    unavailable.mkdir()
    out = unavailable / "graphify-out"
    out.mkdir()
    graph = out / "graph.json"
    prior = b'{"nodes": [], "retained": true}\n'
    graph.write_bytes(prior)
    if root_kind == "missing":
        monkeypatch.setenv("GRAPHIFY_REPO_ROOT", str(tmp_path / "missing"))
    elif root_kind == "chdir-denied":
        denied = tmp_path / "denied"
        denied.mkdir()
        monkeypatch.setenv("GRAPHIFY_REPO_ROOT", str(denied))
        real_chdir = os.chdir

        def failed_chdir(path):
            if Path(path) == denied:
                raise PermissionError(errno.EACCES, "repository root cannot be entered")
            real_chdir(path)

        monkeypatch.setattr(os, "chdir", failed_chdir)
    else:
        monkeypatch.delenv("GRAPHIFY_REPO_ROOT", raising=False)
    monkeypatch.chdir(unavailable)
    _fail_cwd_lookup(monkeypatch, unavailable)

    assert _rebuild_code(Path("."), changed_paths=[Path("lib.py")]) is False
    assert graph.read_bytes() == prior
    assert {path.name for path in out.iterdir()} == {"graph.json"}
    assert "current working directory no longer exists" in capsys.readouterr().out


def test_req_core_002_ac02_repo_root_recovers_cwd_and_publishes_graph(tmp_path, monkeypatch):
    """Real chdir recovery reaches extraction, persistence and lock/queue cleanup."""
    unavailable = tmp_path / "unavailable"
    unavailable.mkdir()
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "lib.py").write_text("def recovered(): pass\n", encoding="utf-8")
    monkeypatch.setenv("GRAPHIFY_REPO_ROOT", str(corpus))
    monkeypatch.chdir(unavailable)
    _fail_cwd_lookup(monkeypatch, unavailable)
    with pytest.raises(FileNotFoundError):
        Path.cwd()

    assert _rebuild_code(Path("."), changed_paths=[Path("lib.py")], no_cluster=True) is True
    assert Path.cwd() == corpus
    out = corpus / "graphify-out"
    persisted = json.loads((out / "graph.json").read_text(encoding="utf-8"))
    assert any(node["label"] == "recovered()" for node in persisted["nodes"])
    assert not (out / ".pending_changes").exists()
    assert not (out / ".rebuild.lock").exists()
    assert not (unavailable / "graphify-out").exists()


@pytest.mark.parametrize(
    ("root_kind", "reason"),
    [
        ("unset", "GRAPHIFY_REPO_ROOT is not set"),
        ("missing", "GRAPHIFY_REPO_ROOT does not name an available directory"),
        ("chdir-denied", "GRAPHIFY_REPO_ROOT could not be entered"),
    ],
)
def test_req_core_002_ac03_unavailable_cwd_reports_root_reason(
    tmp_path, monkeypatch, capsys, root_kind, reason
):
    """Failure diagnostics identify root setup or entry failure without path leaks."""
    unavailable = tmp_path / "unavailable"
    unavailable.mkdir()
    supplied_root = tmp_path / "private-repository-root"
    if root_kind == "unset":
        monkeypatch.delenv("GRAPHIFY_REPO_ROOT", raising=False)
    else:
        monkeypatch.setenv("GRAPHIFY_REPO_ROOT", str(supplied_root))
    if root_kind == "chdir-denied":
        supplied_root.mkdir()
        real_chdir = os.chdir

        def denied_chdir(path):
            if Path(path) == supplied_root:
                raise PermissionError(errno.EACCES, "private failure detail", str(supplied_root))
            real_chdir(path)

        monkeypatch.setattr(os, "chdir", denied_chdir)
    monkeypatch.chdir(unavailable)
    _fail_cwd_lookup(monkeypatch, unavailable)

    assert _rebuild_code(Path("."), changed_paths=[Path("lib.py")]) is False
    output = capsys.readouterr().out
    assert "current working directory no longer exists" in output
    assert reason in output
    assert str(supplied_root) not in output
    assert "private failure detail" not in output
    assert not (unavailable / "graphify-out").exists()
