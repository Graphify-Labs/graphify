"""Own a real watcher thread until its observer and loop have both stopped."""
from contextlib import contextmanager
import sys
import threading
from types import SimpleNamespace

from graphify import watch as watch_mod


@contextmanager
def running_watch(root, monkeypatch, *, debounce=0.2):
    """Join shutdown before restoring the test's clock or callback patches.

    Only this owner's direct watch-loop wait is interruptible. Dependency waits,
    other threads and the shared standard-library clock retain their behavior.
    Readiness means the real observer started and the loop reached its first wait.
    """
    stop, ready = threading.Event(), threading.Event()
    failures = []
    clock, watch = watch_mod.time, watch_mod.watch
    worker = None

    def sleep(seconds):
        if (threading.current_thread() is worker
                and sys._getframe(1).f_code is watch.__code__):
            ready.set()
            if stop.wait(seconds):
                raise KeyboardInterrupt
            return None
        return clock.sleep(seconds)

    def run():
        try:
            watch(root, debounce=debounce)
        except BaseException as error:
            failures.append(error)
        finally:
            ready.set()

    # Keep this scope active through stop/join, including a failing test body.
    # watch() owns observer.stop()/join() in its own finally block.
    with monkeypatch.context() as scoped:
        scoped.setattr(watch_mod, "time", SimpleNamespace(
            monotonic=clock.monotonic, sleep=sleep,
        ))
        worker = threading.Thread(target=run, name="graphify-watch-test", daemon=True)
        worker.start()
        try:
            assert ready.wait(5), "watch thread did not reach its polling loop"
            assert not failures, failures
            assert worker.is_alive(), "watch thread stopped before the test body"
            yield worker
        finally:
            stop.set()
            worker.join(timeout=5)
            assert not worker.is_alive(), "watch thread did not stop before patch teardown"
        assert not failures, failures
