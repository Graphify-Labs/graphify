"""Kernel-level characterization of the inotify overflow behind #5033.

These tests exercise the mechanism, not Graphify's handler. The overflow
rebuild loop is watchdog 7+ specific (watchdog 6 and older define
``IN_Q_OVERFLOW`` but never react to it, and use a different inotify API), so
the listener tests skip unless watchdog 7+ is installed. Run them manually with
``pip install 'watchdog>=7'`` when touching the watch masks.
"""

import os
import select
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    not sys.platform.startswith("linux"), reason="inotify is Linux-only"
)


class _Callback:
    def on_watch_deleted(self, wd):
        pass


def _watchdog7():
    events = pytest.importorskip("watchdog.events")
    inotify = pytest.importorskip("watchdog.observers.inotify")
    inotify_c = pytest.importorskip("watchdog.observers.inotify_c")
    if not hasattr(inotify_c, "InotifyFD") or not hasattr(
        inotify, "InotifyWatchGroup"
    ):
        pytest.skip("watchdog < 7 uses a different inotify implementation")
    if not hasattr(inotify.InotifyWatchGroup, "on_queue_overflow"):
        pytest.skip("this watchdog does not rebuild watches after an overflow")
    return events, inotify, inotify_c


def _mask_for(event_filter):
    from watchdog.observers.api import EventQueue, ObservedWatch
    from watchdog.observers.inotify import InotifyEmitter

    emitter = InotifyEmitter(
        EventQueue(), ObservedWatch("/tmp", recursive=True), event_filter=event_filter
    )
    return emitter.get_event_mask_from_filter()


def _drain(fd):
    """Read what is queued right now without blocking on an empty queue."""
    out = []
    while select.select([fd._inotify_fd], [], [], 0)[0]:
        out.extend(fd.read_events())
    return out


def test_default_mask_requests_read_events_but_change_filter_does_not():
    """#5033 root cause: the default mask asks for IN_OPEN / IN_CLOSE_NOWRITE."""
    events = pytest.importorskip("watchdog.events")
    inotify_c = pytest.importorskip("watchdog.observers.inotify_c")
    from graphify.watch import _watch_event_filter

    constants = inotify_c.InotifyConstants

    default = _mask_for(None)
    if default is None:
        # watchdog 6 returns None to mean "let the kernel default to all events"
        default = inotify_c.WATCHDOG_ALL_EVENTS
    assert default & constants.IN_OPEN
    if hasattr(events, "FileClosedNoWriteEvent"):
        # IN_CLOSE_NOWRITE appears in watchdog 5.0.0; 4.0.0 only has IN_OPEN.
        assert default & constants.IN_CLOSE_NOWRITE

    change_only = _mask_for(_watch_event_filter())
    assert not change_only & constants.IN_OPEN
    if hasattr(events, "FileClosedNoWriteEvent"):
        # watchdog 4 maps FileClosedEvent to IN_CLOSE (write + nowrite).
        assert not change_only & constants.IN_CLOSE_NOWRITE
    assert change_only & constants.IN_CLOSE_WRITE
    assert change_only & constants.IN_MODIFY
    assert change_only & constants.IN_CREATE


def test_reading_one_directory_emits_open_and_close_nowrite(tmp_path):
    """The recursive setup walk's opendir/closedir is itself event traffic."""
    _events, _inotify, inotify_c = _watchdog7()
    (tmp_path / "child").mkdir()
    root = os.fsencode(tmp_path)

    fd = inotify_c.InotifyFD()
    fd.add_callback(root, inotify_c.WATCHDOG_ALL_EVENTS, _Callback(), 1)
    os.listdir(root)
    got = _drain(fd)
    fd.close()

    assert len(got) == 2
    assert {e.is_open for e in got} == {True, False}
    assert all(e.is_open or e.is_close_nowrite for e in got)

    no_read = inotify_c.WATCHDOG_ALL_EVENTS & ~(
        inotify_c.InotifyConstants.IN_OPEN
        | inotify_c.InotifyConstants.IN_CLOSE_NOWRITE
    )
    fd = inotify_c.InotifyFD()
    fd.add_callback(root, no_read, _Callback(), 1)
    os.listdir(root)
    assert _drain(fd) == []
    fd.close()


def test_read_only_traffic_alone_overflows_the_queue(tmp_path):
    """One directory + one file: event count, not directory count, is the limit.

    Each open+close of the file is one IN_OPEN plus one IN_CLOSE_NOWRITE.
    ``limit // 2 + 1`` pairs therefore push 16,385 events through a 16,384-slot
    queue on a one-directory tree.
    """
    _events, _inotify, inotify_c = _watchdog7()
    limit = int(Path("/proc/sys/fs/inotify/max_queued_events").read_text())
    if limit > 100_000:
        pytest.skip("queue limit too large for a fast test")

    root = os.fsencode(tmp_path)
    file_path = os.path.join(root, b"f")
    Path(os.fsdecode(file_path)).write_text("x", encoding="utf-8")

    fd = inotify_c.InotifyFD()
    fd.add_callback(root, inotify_c.WATCHDOG_ALL_EVENTS, _Callback(), 1)
    for _ in range(limit // 2 + 1):
        os.close(os.open(file_path, os.O_RDONLY))
    got = _drain(fd)
    fd.close()

    overflow = [e for e in got if e.mask & inotify_c.InotifyConstants.IN_Q_OVERFLOW]
    delivered = [
        e for e in got if not (e.mask & inotify_c.InotifyConstants.IN_Q_OVERFLOW)
    ]
    assert len(overflow) == 1
    assert len(delivered) == limit


def test_overflow_makes_watchdog_rebuild_the_recursive_watch_tree(
    tmp_path, monkeypatch
):
    """#5033 feedback loop: every overflow re-walks the whole tree."""
    _events, inotify, inotify_c = _watchdog7()
    (tmp_path / "a").mkdir()

    walks = []
    real_add_all = inotify.InotifyWatchGroup._add_all_callbacks

    def counting_add_all(self, path):
        walks.append(os.fsdecode(path))
        return real_add_all(self, path)

    monkeypatch.setattr(
        inotify.InotifyWatchGroup, "_add_all_callbacks", counting_add_all
    )

    fd = inotify_c.InotifyFD()
    try:
        group = inotify.InotifyWatchGroup(
            fd,
            os.fsencode(tmp_path),
            is_recursive=True,
            event_mask=inotify_c.WATCHDOG_ALL_EVENTS,
        )
        assert len(walks) == 1, "construction should walk once"

        group.on_queue_overflow()
        group.on_queue_overflow()
        group.on_queue_overflow()
        assert len(walks) == 4, "each overflow should walk the tree again"

        group.deactivate()
    finally:
        fd.close()
