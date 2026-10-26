"""The lock-queue contract for rebuild requests (#4769).

A rebuild request that loses the per-repo lock has to leave something behind, or
tell its caller it was not served. This file pins that contract for the request
kinds that exist today, and for the queue files they use.

    I2  a caller that WINS the lock runs the pass it asked for, never a full one
        driven by its own record
    I4  ``.pending_full`` / ``.pending_changes`` keep their meaning, and a queued
        full marker still upgrades a blocking incremental caller

Determinism: the real ``_rebuild_lock`` and the real queue files are used, with no
monkeypatching of the lock, the queue, or ``_rebuild_code``. Contention comes from
holding the lock in this process, which works because ``flock`` is per open file
description, so a second open conflicts even here. Content changes are paired with
an explicit ``os.utime`` bump, so nothing depends on filesystem timestamp
granularity and no test sleeps.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

import graphify.extract as extract_mod
from graphify.watch import (
    _drain_pending,
    _drain_pending_full,
    _queue_pending,
    _queue_pending_full,
    _rebuild_code,
    _rebuild_lock,
)

OUT = "graphify-out"


def _corpus(root: Path) -> Path:
    (root / "src").mkdir(parents=True, exist_ok=True)
    for name in ("a", "b", "c"):
        (root / "src" / f"{name}.py").write_text(f"def f{name}():\n    return 1\n")
    (root / "src" / "uses.py").write_text(
        "from src.a import fa\n\ndef use():\n    return fa()\n"
    )
    return root


@pytest.fixture()
def built(tmp_path: Path) -> Path:
    root = _corpus(tmp_path / "corpus")
    assert _rebuild_code(root, acquire_lock=False) is True
    assert (root / OUT / "manifest.json").exists()
    return root


def _spy_extract(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    calls: list[list[str]] = []
    real = extract_mod.extract

    def spy(targets, **kwargs):
        calls.append(sorted(Path(p).name for p in targets))
        return real(targets, **kwargs)

    monkeypatch.setattr(extract_mod, "extract", spy)
    return calls


def _edit(root: Path, name: str, body: str) -> Path:
    """Change one file and move its mtime past the manifest row, without sleeping."""
    path = root / "src" / name
    path.write_text(body)
    stamp = time.time() + 120
    os.utime(path, (stamp, stamp))
    return path


def _contend(root: Path, **kwargs):
    """Hold the real lock, make one request, release, and report both outcomes.

    Returns ``(outcome, artifacts)`` where ``outcome`` is the return value or the
    exception the caller got.
    """
    out = root / OUT
    with _rebuild_lock(out, blocking=False) as got:
        assert got, "the test failed to take the lock, so this is not a contention test"
        try:
            outcome = _rebuild_code(root, **kwargs)
        except BaseException as exc:  # noqa: BLE001 - the point is what the caller sees
            outcome = exc
    return outcome, _artifacts(root)


def _artifacts(root: Path) -> list[str]:
    """Pending records a drain would consume."""
    return sorted(p.name for p in (root / OUT).iterdir() if p.name.startswith(".pending"))


# --- I2 -------------------------------------------------------------------


def test_i2_incremental_caller_that_wins_the_lock_does_not_upgrade_itself(
    built: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _edit(built, "a.py", "def fa():\n    return 11\n")
    calls = _spy_extract(monkeypatch)

    assert _rebuild_code(built, incremental=True, acquire_lock=True, block_on_lock=True) is True

    assert calls == [["a.py"]], f"an incremental caller re-extracted {calls}"


# --- I4 -------------------------------------------------------------------


def test_i4_pending_full_and_pending_changes_keep_their_semantics(built: Path) -> None:
    out = built / OUT

    _queue_pending_full(out)
    assert (out / ".pending_full").exists()
    assert _drain_pending_full(out) is True
    assert not (out / ".pending_full").exists()
    assert _drain_pending_full(out) is False

    _queue_pending(out, [Path("/x/a.py"), Path("/x/a.py"), Path("/y/b.py")])
    assert [str(p) for p in _drain_pending(out)] == ["/x/a.py", "/y/b.py"]
    assert _drain_pending(out) == []


def test_i4_a_queued_full_marker_still_upgrades_a_blocking_incremental_caller(
    built: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # One change first: the no-change gate runs before the drain, so an untouched
    # tree returns there and never reaches the queue. Same reason
    # test_default_is_the_full_path carries a change.
    _edit(built, "a.py", "def fa():\n    return 13\n")
    _queue_pending_full(built / OUT)
    calls = _spy_extract(monkeypatch)

    assert _rebuild_code(built, incremental=True, acquire_lock=True, block_on_lock=True) is True

    assert calls == [["a.py", "b.py", "c.py", "uses.py"]], (
        f"a queued full marker no longer produces a full pass (extracted {calls})"
    )
