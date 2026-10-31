"""Platform-faithful, scoped faults at the real atomic publication boundary.

Windows rejects replacing a read-only destination. POSIX instead requires a
nonwritable parent; privileged/capable hosts must prove an actual denial before
claiming that fixture. Every changed mode and replacement hook is restored.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import errno
import os
from pathlib import Path
import stat

import pytest


@dataclass
class PublicationFault:
    """Observation of this fixture, without manufacturing publication results."""

    kind: str
    qualified: bool = False
    hits: int = 0


def _qualify_windows(parent):
    """Probe disposable siblings so unsupported attributes cannot alter products."""
    target, source = parent / ".readonly-target-probe", parent / ".readonly-source-probe"
    assert not target.exists() and not source.exists()
    target.write_bytes(b"accepted")
    source.write_bytes(b"candidate")
    original = target.stat().st_mode
    try:
        target.chmod(stat.S_IREAD)
        try:
            os.replace(source, target)
        except PermissionError:
            return
        pytest.skip("Filesystem cannot enforce actual Windows read-only replacement denial")
    finally:
        target.chmod(original)
        target.unlink()
        source.unlink(missing_ok=True)


@contextmanager
def publication_fault(destination, kind, monkeypatch):
    """Qualify a real platform denial or inject EIO only at graph replacement."""
    destination = Path(destination).resolve()
    observation = PublicationFault(kind)
    if kind == "replace":
        original_replace = os.replace

        def reject_graph(source, target, *args, **kwargs):
            if Path(target).resolve() == destination:
                observation.hits += 1
                raise OSError(errno.EIO, "Test-owned graph replacement failure")
            return original_replace(source, target, *args, **kwargs)

        observation.qualified = True
        try:
            with monkeypatch.context() as patch:
                patch.setattr(os, "replace", reject_graph)
                yield observation
        finally:
            assert os.replace is original_replace
        return
    assert kind == "readonly"
    if os.name == "nt":
        _qualify_windows(destination.parent)
        blocked = destination
        restricted = stat.S_IREAD
    else:
        if getattr(os, "geteuid", lambda: -1)() == 0:
            pytest.skip("POSIX root bypasses directory mode denial; unprivileged host required")
        blocked = destination.parent
        restricted = blocked.stat().st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)
    original_mode = blocked.stat().st_mode
    probe = blocked / ".parent-write-denial-probe" if os.name != "nt" else None
    if probe is not None:
        assert not probe.exists()
    try:
        blocked.chmod(restricted)
        if probe is not None:
            try:
                descriptor = os.open(probe, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except PermissionError:
                pass
            else:
                os.close(descriptor)
                pytest.skip("POSIX capability/filesystem bypasses actual parent write denial")
        observation.qualified = True
        yield observation
    finally:
        blocked.chmod(original_mode)
        if probe is not None:
            probe.unlink(missing_ok=True)
