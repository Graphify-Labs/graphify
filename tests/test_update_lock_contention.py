"""The lock-queue contract for rebuild requests (#4769).

A rebuild request that loses the per-repo lock has to leave something behind, or
tell its caller it was not served. This file pins that contract for every request
kind, and for the queue files they use.

    I1  a contended incremental request leaves a record a drain can act on, or
        tells its caller it was not served; it must not vanish
    I2  a caller that WINS the lock runs the pass it asked for, never a full one
        driven by its own record
    I3  the record drives the work through the winner's drain, with nothing
        re-asking for it
    I4  ``.pending_full`` / ``.pending_changes`` keep their meaning, and a queued
        full marker still upgrades a blocking incremental caller

An incremental request names no paths, so it can neither append to
``.pending_changes`` nor use ``.pending_full`` (which means "re-extract
everything"). It records ``.pending_incremental`` instead, and the tests below
pin that marker's lifecycle.

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
    _drain_pending_incremental,
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


def _refused(outcome) -> bool:
    """The caller was told it was not served, rather than given a plain False."""
    return isinstance(outcome, BaseException) or outcome is None


# --- I1 -------------------------------------------------------------------


def test_i1_contended_incremental_request_is_not_silently_dropped(built: Path) -> None:
    outcome, artifacts = _contend(
        built, incremental=True, acquire_lock=True, block_on_lock=False
    )

    assert artifacts or _refused(outcome), (
        "a contended incremental request was dropped: it left no pending record "
        f"and its caller got an indistinguishable result (outcome={outcome!r}, "
        f"pending={artifacts})"
    )


def test_i1_the_marker_is_written_on_contention_and_drained_exactly_once(
    built: Path,
) -> None:
    """.pending_incremental's lifecycle: written when the lock is lost, drained once."""
    out = built / OUT
    assert not (out / ".pending_incremental").exists()

    _contend(built, incremental=True, acquire_lock=True, block_on_lock=False)
    assert (out / ".pending_incremental").exists(), "the contended request left no marker"

    assert _drain_pending_incremental(out) is True
    assert not (out / ".pending_incremental").exists()
    assert _drain_pending_incremental(out) is False


# --- I2 -------------------------------------------------------------------


def test_i2_incremental_caller_that_wins_the_lock_does_not_upgrade_itself(
    built: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _edit(built, "a.py", "def fa():\n    return 11\n")
    calls = _spy_extract(monkeypatch)

    assert _rebuild_code(built, incremental=True, acquire_lock=True, block_on_lock=True) is True

    assert calls == [["a.py"]], f"an incremental caller re-extracted {calls}"


# --- I3 -------------------------------------------------------------------


def test_i3_a_queued_incremental_request_makes_the_next_winner_run_incrementally(
    built: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The record drives the work; nothing re-asks for an incremental pass.

    The call that ends up running the work asks for the DEFAULT pass, which is a
    full one, so a single re-extracted file can only come from the winner's own
    drain honouring the marker. Calling ``_rebuild_code(incremental=True)`` here
    instead would be this test re-asking, which proves nothing about the queue.
    """
    _edit(built, "a.py", "def fa():\n    return 12\n")
    _, artifacts = _contend(
        built, incremental=True, acquire_lock=True, block_on_lock=False
    )
    assert ".pending_incremental" in artifacts, "the contended request left no record"

    calls = _spy_extract(monkeypatch)
    assert _rebuild_code(built, acquire_lock=True, block_on_lock=True) is True

    assert calls == [["a.py"]], (
        "the queued incremental record did not drive the winner's pass "
        f"(extracted {calls})"
    )
    assert ".pending_incremental" not in _artifacts(built), "the marker survived the drain"


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
