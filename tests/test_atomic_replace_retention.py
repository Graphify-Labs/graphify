"""REQ-QML-018-AC06: replacement failure never masquerades as committed data."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import stat

import pytest

from graphify.paths import os_replace_with_fallback, write_json_atomic, write_text_atomic


def fallback(monkeypatch):
    """Only the OS replace boundary is forced; real copy/rename/unlink still run."""
    def unavailable(*_):
        raise PermissionError("replace temporarily unavailable")
    monkeypatch.setattr(os, "replace", unavailable)


@pytest.mark.skipif(os.name != "nt", reason="Actual Windows read-only attribute")
@pytest.mark.parametrize("writer", ["text", "json", "replace"])
def test_req_qml018_ac06_readonly_rejects_without_displacing_destination(tmp_path, writer):
    """The actual OS rejection keeps bytes/permissions; repair then succeeds."""
    target, source = tmp_path / "graph.json", tmp_path / "source.tmp"
    target.write_bytes(b'{"original":true}')
    original = target.read_bytes()
    source.write_bytes(b'{"new":true}')
    target.chmod(stat.S_IREAD)
    try:
        with pytest.raises(PermissionError):
            if writer == "text":
                write_text_atomic(target, '{"new":true}')
            elif writer == "json":
                write_json_atomic(target, {"new": True})
            else:
                os_replace_with_fallback(source, target)
        assert target.read_bytes() == original
        assert not target.stat().st_mode & stat.S_IWRITE
        assert source.read_bytes() == b'{"new":true}'
        assert {p.name for p in tmp_path.iterdir()} == {"graph.json", "source.tmp"}
    finally:
        target.chmod(stat.S_IWRITE)
    write_text_atomic(target, '{"new":true}')
    accepted = target.read_bytes()
    write_text_atomic(target, '{"new":true}')
    assert target.read_bytes() == accepted


def test_req_qml018_ac06_directory_is_not_a_replace_fallback_target(tmp_path, monkeypatch):
    """A destination directory must not be renamed away to land a plain file."""
    source, target = tmp_path / "source.tmp", tmp_path / "directory"
    source.write_bytes(b"NEW")
    target.mkdir()
    (target / "keep").write_bytes(b"KEEP")
    fallback(monkeypatch)
    with pytest.raises(PermissionError):
        os_replace_with_fallback(source, target)
    assert (target / "keep").read_bytes() == b"KEEP"
    assert source.read_bytes() == b"NEW"
    assert {p.name for p in tmp_path.iterdir()} == {"source.tmp", "directory"}


@pytest.mark.parametrize("phase,existing", [
    ("copy", True), ("backup", True), ("land", True),
    ("source_cleanup", True), ("backup_cleanup", True),
    ("copy", False), ("land", False), ("source_cleanup", False),
])
def test_req_qml018_ac06_fallback_failure_restores_prior_state(tmp_path, monkeypatch, phase, existing):
    """Each actual fallback phase can fail without publishing a false success."""
    source, target = tmp_path / "source.tmp", tmp_path / "graph.json"
    source.write_bytes(b"NEW")
    if existing:
        target.write_bytes(b"ORIGINAL")
    fallback(monkeypatch)
    real_copy, real_rename, real_unlink = shutil.copy2, os.rename, os.unlink
    raised = False

    def reject():
        nonlocal raised
        raised = True
        raise OSError("injected " + phase)

    def copy(start, destination, *args, **kwargs):
        if phase == "copy" and not raised:
            reject()
        return real_copy(start, destination, *args, **kwargs)

    def rename(start, destination, *args, **kwargs):
        if not raised and ((phase == "backup" and Path(start) == target)
                           or (phase == "land" and Path(start).name.startswith(".gfy-replace-")
                               and Path(destination) == target)):
            reject()
        return real_rename(start, destination, *args, **kwargs)

    def unlink(path, *args, **kwargs):
        candidate = Path(path)
        if not raised and ((phase == "source_cleanup" and candidate == source)
                           or (phase == "backup_cleanup" and candidate.name.startswith(".gfy-replace-bak-")
                               and candidate.read_bytes() == b"ORIGINAL")):
            reject()
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(shutil, "copy2", copy)
    monkeypatch.setattr(os, "rename", rename)
    monkeypatch.setattr(os, "unlink", unlink)
    with pytest.raises(OSError, match="injected " + phase):
        os_replace_with_fallback(source, target)
    assert raised and source.read_bytes() == b"NEW"
    assert target.read_bytes() == b"ORIGINAL" if existing else not target.exists()
    assert {p.name for p in tmp_path.iterdir()} == ({"source.tmp", "graph.json"} if existing else {"source.tmp"})
    os_replace_with_fallback(source, target)
    assert target.read_bytes() == b"NEW" and not source.exists()
    assert {p.name for p in tmp_path.iterdir()} == {"graph.json"}


@pytest.mark.skipif(os.name != "nt", reason="Actual Windows read-only attribute")
def test_req_qml018_ac06_readonly_source_is_consumed_on_successful_fallback(tmp_path, monkeypatch):
    """The move contract consumes an authorized source, including its read-only bit."""
    source, target = tmp_path / "source.tmp", tmp_path / "graph.json"
    source.write_bytes(b"NEW")
    target.write_bytes(b"ORIGINAL")
    source.chmod(stat.S_IREAD)
    fallback(monkeypatch)
    try:
        os_replace_with_fallback(source, target)
        assert target.read_bytes() == b"NEW" and not source.exists()
        assert not target.stat().st_mode & stat.S_IWRITE
        assert {p.name for p in tmp_path.iterdir()} == {"graph.json"}
    finally:
        for path in (source, target):
            if path.exists():
                path.chmod(stat.S_IWRITE)


def test_req_qml018_ac06_restore_failure_keeps_recovery_backup(tmp_path, monkeypatch):
    """A second OS failure must expose integrity failure and retain original bytes."""
    source, target = tmp_path / "source.tmp", tmp_path / "graph.json"
    source.write_bytes(b"NEW")
    target.write_bytes(b"ORIGINAL")
    fallback(monkeypatch)
    real_rename = os.rename

    def fail_landing_and_restore(start, destination):
        if Path(destination) == target:
            raise OSError("landing/restore unavailable")
        return real_rename(start, destination)

    monkeypatch.setattr(os, "rename", fail_landing_and_restore)
    with pytest.raises(OSError, match="rollback failed"):
        os_replace_with_fallback(source, target)
    backups = list(tmp_path.glob(".gfy-replace-bak-*.tmp"))
    assert len(backups) == 1 and backups[0].read_bytes() == b"ORIGINAL"
    assert source.read_bytes() == b"NEW" and not target.exists()
    assert list(tmp_path.glob(".gfy-replace-*.tmp")) == backups
    monkeypatch.setattr(os, "rename", real_rename)
    real_rename(backups[0], target)
    os_replace_with_fallback(source, target)
    assert target.read_bytes() == b"NEW"
    assert {p.name for p in tmp_path.iterdir()} == {"graph.json"}


def test_req_qml018_ac06_absent_destination_restore_failure_has_no_fake_backup(tmp_path, monkeypatch):
    """An unavoidable second OS failure reports recovery without inventing a backup."""
    source, target = tmp_path / "source.tmp", tmp_path / "graph.json"
    source.write_bytes(b"NEW")
    fallback(monkeypatch)
    real_rename, real_unlink = os.rename, os.unlink

    def unlink(path, *args, **kwargs):
        if Path(path) == source:
            raise OSError("source cleanup unavailable")
        return real_unlink(path, *args, **kwargs)

    def rename(start, destination):
        if Path(start) == target:
            raise OSError("candidate rollback unavailable")
        return real_rename(start, destination)

    monkeypatch.setattr(os, "unlink", unlink)
    monkeypatch.setattr(os, "rename", rename)
    with pytest.raises(OSError, match="rollback failed; manual recovery required"):
        os_replace_with_fallback(source, target)
    assert source.read_bytes() == target.read_bytes() == b"NEW"
    assert not list(tmp_path.glob(".gfy-*.tmp"))
    monkeypatch.setattr(os, "unlink", real_unlink)
    monkeypatch.setattr(os, "rename", real_rename)
    target.unlink()
    os_replace_with_fallback(source, target)
    assert target.read_bytes() == b"NEW" and not source.exists()


@pytest.mark.skipif(os.name != "nt", reason="Actual Windows read-only attribute")
def test_req_qml018_ac06_readonly_source_cleanup_rollback_retains_attributes(tmp_path, monkeypatch):
    """A consumed source is reconstructed before restoring a failed cleanup transaction."""
    source, target = tmp_path / "source.tmp", tmp_path / "graph.json"
    source.write_bytes(b"NEW")
    source.chmod(stat.S_IREAD)
    target.write_bytes(b"ORIGINAL")
    fallback(monkeypatch)
    real_unlink = os.unlink
    rejected = False

    def unlink(path, *args, **kwargs):
        nonlocal rejected
        if not rejected and Path(path).name.startswith(".gfy-replace-bak-") and Path(path).read_bytes() == b"ORIGINAL":
            rejected = True
            raise OSError("backup cleanup unavailable")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(os, "unlink", unlink)
    try:
        with pytest.raises(OSError, match="backup cleanup unavailable"):
            os_replace_with_fallback(source, target)
        assert target.read_bytes() == b"ORIGINAL" and target.stat().st_mode & stat.S_IWRITE
        assert source.read_bytes() == b"NEW" and not source.stat().st_mode & stat.S_IWRITE
        assert {p.name for p in tmp_path.iterdir()} == {"source.tmp", "graph.json"}
    finally:
        if source.exists():
            source.chmod(stat.S_IWRITE)
