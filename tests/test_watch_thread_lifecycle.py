"""REQ-QML-014-AC03: real watcher acceptance leaves no live watch-loop owner."""
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from graphify import watch as watch_mod
from tests.watch_thread_lifecycle import running_watch


# Execute each original acceptance in a disposable process. The audit observes
# its real watch frames immediately after the body, before pytest restores its
# monkeypatches; the old daemon leak is therefore an ordinary failing assertion.
_AUDITED_ACCEPTANCE = '''
import sys
import pytest
import graphify.watch as watch_mod

def watchers():
    found = set()
    for identity, frame in sys._current_frames().items():
        while frame is not None:
            if frame.f_code is watch_mod.watch.__code__:
                found.add(identity)
                break
            frame = frame.f_back
    return found

class LifecycleAudit:
    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_call(self, item):
        before = watchers()
        yield
        escaped = watchers() - before
        assert not escaped, "watch loop survived acceptance and patch ownership"

raise SystemExit(pytest.main([
    sys.argv[1], "-q", "--tb=short", "-p", "no:cacheprovider"
], plugins=[LifecycleAudit()]))
'''


@pytest.mark.parametrize("name", [
    "test_watch_handler_honors_graphifyignore",
    "test_watch_loads_graphifyignore_once",
])
def test_req_qml014_ac03_original_real_watch_acceptance_joins_before_teardown(name):
    """Unchanged event/debounce assertions must finish without escaped loops."""
    pytest.importorskip("watchdog.observers")
    result = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", _AUDITED_ACCEPTANCE,
         f"tests/test_watch.py::{name}"],
        cwd=Path(__file__).resolve().parents[1],
        env=dict(os.environ, GRAPHIFY_NO_AUTO_REFRESH="1", GRAPHIFY_NO_TIPS="1"),
        capture_output=True, text=True, encoding="utf-8", timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("body_failure", [False, True])
def test_req_qml014_ac03_scoped_watch_shutdown_restores_clocks_on_every_exit(
        tmp_path, monkeypatch, body_failure):
    """Real observer cleanup precedes clock restoration on success and assertion."""
    pytest.importorskip("watchdog.observers")
    original_clock = watch_mod.time
    original_sleep, original_monotonic = time.sleep, time.monotonic
    threads = []

    def body():
        with running_watch(tmp_path, monkeypatch) as worker:
            threads.append(worker)
            assert worker.is_alive()
            assert watch_mod.time.monotonic is original_monotonic
            assert time.sleep is original_sleep
            assert time.monotonic is original_monotonic
            if body_failure:
                raise AssertionError("injected watcher body failure")

    if body_failure:
        with pytest.raises(AssertionError, match="injected watcher body failure"):
            body()
    else:
        body()
    assert len(threads) == 1 and not threads[0].is_alive()
    assert watch_mod.time is original_clock
    assert time.sleep is original_sleep
    assert time.monotonic is original_monotonic
