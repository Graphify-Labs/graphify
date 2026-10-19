"""D32: owned replacement may consume readonly copies without weakening rollback."""
from __future__ import annotations

import os
from pathlib import Path
import stat

import pytest

from graphify.paths import os_replace_with_fallback


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Actual Windows read-only attributes")


def writable_cleanup(*paths):
    """Release only this fixture's existing owned files for temporary-directory cleanup."""
    for path in paths:
        if path.exists():
            path.chmod(stat.S_IWRITE)


@pytest.mark.parametrize("readonly_source", [False, True])
def test_req_core001_ac03_owned_readonly_destination_replaces_without_orphans(tmp_path, readonly_source):
    """An actual readonly destination forces the OS fallback; the owned move consumes its source."""
    source, destination = tmp_path / "source.tmp", tmp_path / "SKILL.md"
    source.write_bytes(b"NEW")
    destination.write_bytes(b"ORIGINAL")
    destination.chmod(stat.S_IREAD)
    if readonly_source:
        source.chmod(stat.S_IREAD)
    source_mode = source.stat().st_mode
    try:
        os_replace_with_fallback(source, destination)
        assert destination.read_bytes() == b"NEW" and not source.exists()
        assert destination.stat().st_mode == source_mode
        assert {path.name for path in tmp_path.iterdir()} == {"SKILL.md"}
    finally:
        writable_cleanup(source, destination)


@pytest.mark.parametrize("phase", ["source", "backup"])
def test_req_qml018_ac06_cleanup_after_readonly_clear_restores_bytes_and_modes(tmp_path, monkeypatch, phase):
    """A failure after the real write-bit change restores both original files, then retries safely."""
    source, destination = tmp_path / "source.tmp", tmp_path / "SKILL.md"
    source.write_bytes(b"NEW")
    destination.write_bytes(b"ORIGINAL")
    source.chmod(stat.S_IREAD)
    if phase == "backup":
        destination.chmod(stat.S_IREAD)
    modes = source.stat().st_mode, destination.stat().st_mode
    real_unlink, failed = os.unlink, False

    def unavailable(*_args):
        raise PermissionError("known Windows replace fallback")

    def unlink(path, *args, **kwargs):
        nonlocal failed
        candidate = Path(path)
        selected = candidate == source if phase == "source" else (
            candidate.name.startswith(".gfy-replace-bak-") and candidate.read_bytes() == b"ORIGINAL")
        if selected and not failed and candidate.stat().st_mode & stat.S_IWRITE:
            failed = True
            raise OSError("cleanup after readonly clear")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(os, "replace", unavailable)
    monkeypatch.setattr(os, "unlink", unlink)
    try:
        with pytest.raises(OSError, match="cleanup after readonly clear"):
            os_replace_with_fallback(source, destination)
        assert failed
        assert source.read_bytes() == b"NEW" and destination.read_bytes() == b"ORIGINAL"
        assert (source.stat().st_mode, destination.stat().st_mode) == modes
        assert {path.name for path in tmp_path.iterdir()} == {"source.tmp", "SKILL.md"}
        os_replace_with_fallback(source, destination)
        assert destination.read_bytes() == b"NEW" and not source.exists()
        assert destination.stat().st_mode == modes[0]
        assert {path.name for path in tmp_path.iterdir()} == {"SKILL.md"}
    finally:
        writable_cleanup(source, destination)


def test_req_qml018_ac06_mode_restore_failure_retains_recovery_backup(tmp_path, monkeypatch):
    """A second genuine metadata failure is explicit integrity loss, with original bytes recoverable."""
    source, destination = tmp_path / "source.tmp", tmp_path / "SKILL.md"
    source.write_bytes(b"NEW")
    source.chmod(stat.S_IREAD)
    destination.write_bytes(b"ORIGINAL")
    real_unlink, real_chmod = os.unlink, os.chmod
    failed = False

    def unavailable(*_args):
        raise PermissionError("known Windows replace fallback")

    def unlink(path, *args, **kwargs):
        nonlocal failed
        if Path(path) == source and not failed and source.stat().st_mode & stat.S_IWRITE:
            failed = True
            raise OSError("cleanup after readonly clear")
        return real_unlink(path, *args, **kwargs)

    def chmod(path, mode, *args, **kwargs):
        if failed and Path(path) == source and not mode & stat.S_IWRITE:
            raise OSError("source mode restoration unavailable")
        return real_chmod(path, mode, *args, **kwargs)

    try:
        with monkeypatch.context() as fault:
            fault.setattr(os, "replace", unavailable)
            fault.setattr(os, "unlink", unlink)
            fault.setattr(os, "chmod", chmod)
            with pytest.raises(OSError, match="rollback failed; recovery backup retained"):
                os_replace_with_fallback(source, destination)
        backups = list(tmp_path.glob(".gfy-replace-bak-*.tmp"))
        assert failed and len(backups) == 1 and backups[0].read_bytes() == b"ORIGINAL"
        assert source.read_bytes() == b"NEW"
        assert not destination.exists()
        os.rename(backups[0], destination)
        source.chmod(stat.S_IREAD)
        os_replace_with_fallback(source, destination)
        assert destination.read_bytes() == b"NEW" and not source.exists()
        assert {path.name for path in tmp_path.iterdir()} == {"SKILL.md"}
    finally:
        writable_cleanup(source, destination, *tmp_path.glob(".gfy-replace-bak-*.tmp"))
