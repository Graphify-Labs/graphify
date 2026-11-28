from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from graphify import watch as watch_mod


@pytest.mark.parametrize("event_type", ["deleted", "moved"])
@pytest.mark.parametrize("ignored", [False, True])
def test_linux_watch_reconciles_removed_subtree(tmp_path, monkeypatch, event_type, ignored):
    events = pytest.importorskip("watchdog.events")
    observers = pytest.importorskip("watchdog.observers")
    root = tmp_path / "corpus"
    package = root / "pkg"
    package.mkdir(parents=True)
    if ignored:
        (root / ".graphifyignore").write_text("pkg/\n", encoding="utf-8")
    calls = []

    class FakeObserver:
        def schedule(self, handler, path, *, recursive=False, event_filter=None):
            self.handler = handler
            return path

        def unschedule(self, path):
            pass

        def start(self):
            destination = tmp_path / "removed"
            package.rename(destination)
            event = (events.DirDeletedEvent(str(package)) if event_type == "deleted"
                     else events.DirMovedEvent(str(package), str(destination)))
            self.handler.on_any_event(event)

        def stop(self):
            pass

        def join(self):
            pass

    def dispatch_once(_interval):
        if dispatch_once.called:
            raise KeyboardInterrupt
        dispatch_once.called = True

    dispatch_once.called = False
    monkeypatch.setattr(observers, "Observer", FakeObserver)
    monkeypatch.setattr(watch_mod.sys, "platform", "linux")
    monkeypatch.setattr(watch_mod, "time", SimpleNamespace(
        sleep=dispatch_once, monotonic=lambda: 1.0))
    monkeypatch.setattr(watch_mod, "_rebuild_timeout", nullcontext)
    monkeypatch.setattr(watch_mod, "_rebuild_code", lambda path: calls.append(path))
    monkeypatch.setattr(watch_mod, "_notify_only", lambda _: pytest.fail(
        "removing a source should not require semantic extraction"))
    watch_mod.watch(root, debounce=0)
    assert calls == ([] if ignored else [root])
