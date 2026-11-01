"""The event-delivery harness must not replace dependency or lock-retry sleeps.

Only observer delivery is simulated: original configuration assertions still
exercise real discovery, parsing and publication. The POSIX child deliberately
closes its pipes before exit so subprocess enters its real timed-wait loop.
"""
import os
import subprocess
import sys
import time

import pytest

from graphify import watch as watch_mod
from tests.test_language_override_lifecycle import drive_watch
from tests.test_pr10_watch_overrides import (
    test_ignored_root_configuration_still_rebuilds_the_graph as original_config_acceptance,
)


def test_req_qml014_ac03_watch_pump_keeps_stdlib_clock_identity(tmp_path, monkeypatch):
    """Entering the event pump changes only the watch-module clock reference."""
    events = pytest.importorskip("watchdog.events")
    original_sleep, original_monotonic = time.sleep, time.monotonic
    observed = []

    def change():
        observed.append(True)
        assert time.sleep is original_sleep
        assert time.monotonic is original_monotonic
        assert watch_mod.time is not time
        assert watch_mod.time.monotonic is original_monotonic
        return events.FileOpenedEvent(str(tmp_path / "inert.py"))

    drive_watch(tmp_path, monkeypatch, [change])
    assert observed == [True]
    assert time.sleep is original_sleep


@pytest.mark.parametrize("replacement", [False, True])
def test_req_qml014_ac03_nested_dependency_sleep_keeps_original_config_acceptance(
        tmp_path, monkeypatch, replacement):
    """A harmless dependency wait cannot exhaust events or abort a real rebuild."""
    original_git_head, original_sleep = watch_mod._git_head, time.sleep
    waited = []

    def git_head(*args, **kwargs):
        waited.append(True)
        time.sleep(0)
        return original_git_head(*args, **kwargs)

    monkeypatch.setattr(watch_mod, "_git_head", git_head)
    original_config_acceptance(tmp_path, monkeypatch, replacement)
    assert waited
    assert time.sleep is original_sleep


@pytest.mark.parametrize("delay", [0.05, 0.5])
def test_req_qml014_ac03_lock_retry_sleep_does_not_consume_event(tmp_path, monkeypatch, delay):
    """Other callers use real sleep, even when their delay matches the loop poll."""
    events = pytest.importorskip("watchdog.events")
    completed = []

    def change():
        watch_mod.time.sleep(delay)
        completed.append(True)
        return events.FileOpenedEvent(str(tmp_path / "inert.py"))

    drive_watch(tmp_path, monkeypatch, [change])
    assert completed == [True]


def test_req_qml014_ac03_changed_poll_contract_fails_without_hanging(tmp_path, monkeypatch):
    """A simulated future poll change must reject the harness contract promptly."""
    def changed_poll(_root, debounce):
        try:
            watch_mod.time.sleep(0.25)
        except KeyboardInterrupt:
            pass

    monkeypatch.setattr(watch_mod, "watch", changed_poll)
    with pytest.raises(AssertionError, match="watch harness polling contract changed"):
        drive_watch(tmp_path, monkeypatch, [])


@pytest.mark.skipif(os.name != "posix", reason="Actual CPython POSIX timed child-wait boundary")
def test_req_qml014_ac03_posix_timed_child_wait_keeps_event_pump_scoped(tmp_path, monkeypatch):
    """A real timed subprocess wait completes before the unchanged acceptance case."""
    original_git_head = watch_mod._git_head
    original_sleep = time.sleep
    children = []
    waits = []
    gate = tmp_path / "child-release"

    def git_head(*args, **kwargs):
        # Release the bounded child only after observing a real POSIX wait sleep.
        # Profiling preserves the stdlib callable and is restored on every exit.
        previous_profile = sys.getprofile()

        def observe_wait(frame, event, arg):
            if (event == "c_call" and arg is original_sleep
                    and frame.f_globals.get("__name__") == "subprocess"):
                waits.append(True)
                gate.touch()
            if previous_profile is not None:
                previous_profile(frame, event, arg)

        script = (
            "import os,sys,time; from pathlib import Path; gate=Path(sys.argv[1]); "
            "os.close(1); os.close(2); deadline=time.monotonic()+2\n"
            "while not gate.exists() and time.monotonic()<deadline: time.sleep(0.001)\n"
            "raise SystemExit(0 if gate.exists() else 2)\n"
        )
        sys.setprofile(observe_wait)
        try:
            child = subprocess.run(
                [sys.executable, "-c", script, str(gate)],
                capture_output=True, timeout=3, check=True,
            )
        finally:
            sys.setprofile(previous_profile)
            gate.touch()
        children.append(child.returncode)
        return original_git_head(*args, **kwargs)

    monkeypatch.setattr(watch_mod, "_git_head", git_head)
    original_config_acceptance(tmp_path, monkeypatch, False)
    assert children == [0]
    assert waits
