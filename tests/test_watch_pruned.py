import sys
from pathlib import Path

import pytest

pytest.importorskip("watchdog")


@pytest.mark.skipif(
    not sys.platform.startswith("linux"),
    reason="the pruned watch tree is Linux-only",
)
def test_watch_schedules_only_kept_directories(tmp_path, monkeypatch):
    """#5033: ignored directories must not get an inotify watch.

    Smallest case: root + one kept dir + one .graphifyignore'd dir. The
    watcher should schedule root and keep/ only, non-recursively.
    """
    from graphify import watch as watch_mod
    from watchdog import observers
    from watchdog.observers import polling

    (tmp_path / "keep").mkdir()
    (tmp_path / "ignored").mkdir()
    (tmp_path / "keep" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "ignored" / "b.py").write_text("x = 2\n", encoding="utf-8")
    (tmp_path / ".graphifyignore").write_text("ignored/\n", encoding="utf-8")

    calls = []

    class StopWatch(Exception):
        pass

    class FakeObserver:
        def schedule(self, handler, path, *, recursive=False, event_filter=None):
            calls.append((Path(path).resolve(), recursive))

        def start(self):
            raise StopWatch

    fake = FakeObserver()
    monkeypatch.setattr(observers, "Observer", lambda: fake)
    monkeypatch.setattr(polling, "PollingObserver", lambda: fake)
    monkeypatch.setattr(watch_mod, "_rebuild_code", lambda p, **kw: True)
    monkeypatch.setattr(watch_mod, "_notify_only", lambda p: None)

    with pytest.raises(StopWatch):
        watch_mod.watch(tmp_path, debounce=0.1)

    scheduled = {path for path, _ in calls}
    assert scheduled == {tmp_path.resolve(), (tmp_path / "keep").resolve()}
    assert all(recursive is False for _, recursive in calls)


def _inotify_watch_count():
    import os

    total = 0
    for fd in os.listdir("/proc/self/fd"):
        try:
            target = os.readlink(f"/proc/self/fd/{fd}")
        except OSError:
            continue
        if "inotify" not in target:
            continue
        try:
            with open(f"/proc/self/fdinfo/{fd}") as f:
                total += sum(1 for line in f if line.startswith("inotify wd:"))
        except OSError:
            pass
    return total


@pytest.mark.skipif(
    not __import__("sys").platform.startswith("linux"),
    reason="inotify is Linux-only",
)
def test_watch_does_not_watch_ignored_directories(tmp_path, monkeypatch):
    """The kernel should see watches for root and keep/ only, not ignored/."""
    import threading
    import time

    from graphify import watch as watch_mod

    (tmp_path / "keep").mkdir()
    (tmp_path / "ignored").mkdir()
    (tmp_path / "keep" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "ignored" / "b.py").write_text("x = 2\n", encoding="utf-8")
    (tmp_path / ".graphifyignore").write_text("ignored/\n", encoding="utf-8")

    monkeypatch.setattr(watch_mod, "_rebuild_code", lambda p, **kw: True)
    monkeypatch.setattr(watch_mod, "_notify_only", lambda p: None)

    before = _inotify_watch_count()
    thread = threading.Thread(
        target=watch_mod.watch,
        args=(tmp_path,),
        kwargs={"debounce": 0.1},
        daemon=True,
    )
    thread.start()

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if _inotify_watch_count() > before:
            break
        time.sleep(0.05)
    time.sleep(0.2)

    assert _inotify_watch_count() - before == 2
