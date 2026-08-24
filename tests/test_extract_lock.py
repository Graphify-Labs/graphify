"""Tests for extract holding the per-repo rebuild lock.

`graphify extract` takes the same advisory flock that ``_rebuild_code`` takes
so two extracts (or an extract and a watcher/hook rebuild) racing on one
graphify-out/ cannot interleave cache saves or clobber graph.json. These
tests cover the new bounded-wait mode of ``_rebuild_lock`` plus the CLI
behaviour under contention (run as a subprocess, like the other CLI tests).
"""
from __future__ import annotations
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from graphify.watch import _rebuild_lock

PYTHON = sys.executable
REPO_ROOT = Path(__file__).parent.parent


def _run_extract(args: list[str], cwd: Path, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    # Import THIS checkout in the subprocess, not an installed graphify.
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [PYTHON, "-m", "graphify", "extract"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env,
    )


# --- _rebuild_lock bounded wait ---


@pytest.mark.skipif(sys.platform == "win32", reason="fcntl-only (POSIX)")
def test_rebuild_lock_timeout_expires_yields_false(tmp_path):
    """A blocking caller with a timeout must give up once the deadline passes
    instead of waiting on the kernel forever, and must not disturb the
    holder's lock file on the way out."""
    out = tmp_path / "graphify-out"
    with _rebuild_lock(out) as outer:
        assert outer is True
        held_contents = (out / ".rebuild.lock").read_text(encoding="utf-8")
        t0 = time.monotonic()
        with _rebuild_lock(out, blocking=True, timeout=0.5) as inner:
            assert inner is False
        waited = time.monotonic() - t0
        assert waited >= 0.5, waited
        assert waited < 5.0, waited
        # The holder's PID payload must survive the failed bounded wait.
        assert (out / ".rebuild.lock").read_text(encoding="utf-8") == held_contents


@pytest.mark.skipif(sys.platform == "win32", reason="fcntl-only (POSIX)")
def test_rebuild_lock_timeout_acquires_when_free(tmp_path):
    """The bounded-wait path must keep the PID-payload and unlink-on-release
    contracts of the plain acquisition paths."""
    out = tmp_path / "graphify-out"
    lock_path = out / ".rebuild.lock"
    with _rebuild_lock(out, blocking=True, timeout=5.0) as got:
        assert got is True
        assert lock_path.read_text(encoding="utf-8") == f"{os.getpid()}\n"
    assert not lock_path.exists(), "lock file should be unlinked after release"


@pytest.mark.skipif(sys.platform == "win32", reason="fcntl-only (POSIX)")
def test_rebuild_lock_timeout_waits_for_release(tmp_path):
    """A bounded waiter must acquire promptly once the holder releases, not
    only when the deadline expires."""
    out = tmp_path / "graphify-out"
    held = threading.Event()
    release = threading.Event()

    def _holder():
        with _rebuild_lock(out) as got:
            assert got is True
            held.set()
            release.wait(timeout=10)

    t = threading.Thread(target=_holder)
    t.start()
    try:
        assert held.wait(timeout=10)
        threading.Timer(0.5, release.set).start()
        t0 = time.monotonic()
        with _rebuild_lock(out, blocking=True, timeout=30.0) as got:
            assert got is True
        assert time.monotonic() - t0 < 10.0
    finally:
        release.set()
        t.join(timeout=10)


# --- graphify extract under contention (CLI, subprocess) ---


@pytest.mark.skipif(sys.platform == "win32", reason="fcntl-only (POSIX)")
def test_extract_times_out_when_lock_is_held(tmp_path):
    """extract must wait behind a held rebuild lock, name the holder's PID,
    and exit 1 once GRAPHIFY_LOCK_TIMEOUT expires — not race the holder."""
    fcntl = pytest.importorskip("fcntl")
    (tmp_path / "app.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    out = tmp_path / "graphify-out"
    out.mkdir()
    lock_path = out / ".rebuild.lock"
    with open(lock_path, "a+", encoding="utf-8") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        fh.seek(0)
        fh.truncate()
        fh.write("12345\n")
        fh.flush()
        proc = _run_extract(
            [str(tmp_path), "--code-only", "--no-cluster"],
            cwd=tmp_path,
            extra_env={"GRAPHIFY_LOCK_TIMEOUT": "1"},
        )
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "waiting for another rebuild (pid 12345)" in proc.stdout
    assert "gave up waiting for the rebuild lock" in proc.stderr
    # A timed-out waiter must not have clobbered the holder's payload.
    assert lock_path.read_text(encoding="utf-8") == "12345\n"


@pytest.mark.skipif(sys.platform == "win32", reason="fcntl-only (POSIX)")
def test_extract_releases_lock_when_free(tmp_path):
    """An uncontended extract must run to completion and leave no lock file
    behind (the unlink-on-release contract downstream pollers rely on)."""
    (tmp_path / "app.py").write_text(
        "def f():\n    return 1\n\ndef g():\n    return f()\n", encoding="utf-8"
    )
    proc = _run_extract([str(tmp_path), "--code-only", "--no-cluster"], cwd=tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert (tmp_path / "graphify-out" / "graph.json").exists()
    assert not (tmp_path / "graphify-out" / ".rebuild.lock").exists()
