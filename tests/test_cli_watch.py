"""#3061: graphify watch must parse --debounce and forward it to watch()."""
from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from graphify.cli import dispatch_command

PYTHON = sys.executable


def _run_watch(argv_tail: list[str], cwd: str) -> object:
    """Invoke dispatch_command('watch') with a patched watch(); cwd must exist."""
    with patch("graphify.watch.watch") as mock_watch:
        old_argv = sys.argv
        sys.argv = ["graphify", "watch"] + argv_tail
        try:
            dispatch_command("watch")
        finally:
            sys.argv = old_argv
        return mock_watch


def test_watch_debounce_space_form(tmp_path):
    mock = _run_watch(["--debounce", "60", str(tmp_path)], str(tmp_path))
    mock.assert_called_once_with(tmp_path, debounce=60.0)


def test_watch_debounce_equals_form(tmp_path):
    mock = _run_watch(["--debounce=60", str(tmp_path)], str(tmp_path))
    mock.assert_called_once_with(tmp_path, debounce=60.0)


def test_watch_debounce_zero_allowed(tmp_path):
    mock = _run_watch(["--debounce", "0", str(tmp_path)], str(tmp_path))
    mock.assert_called_once_with(tmp_path, debounce=0.0)


def test_watch_without_debounce_uses_default_kwarg(tmp_path):
    mock = _run_watch([str(tmp_path)], str(tmp_path))
    mock.assert_called_once_with(tmp_path)


def test_watch_debounce_missing_value(tmp_path):
    with pytest.raises(SystemExit) as exc:
        _run_watch(["--debounce", str(tmp_path)], str(tmp_path))
    assert exc.value.code == 2


def test_watch_debounce_negative_rejected(tmp_path):
    with pytest.raises(SystemExit) as exc:
        _run_watch(["--debounce", "-1", str(tmp_path)], str(tmp_path))
    assert exc.value.code == 2


def test_watch_debounce_non_numeric_rejected(tmp_path):
    with pytest.raises(SystemExit) as exc:
        _run_watch(["--debounce", "foo", str(tmp_path)], str(tmp_path))
    assert exc.value.code == 2


def test_watch_unknown_option_rejected(tmp_path):
    with pytest.raises(SystemExit) as exc:
        _run_watch(["--bogus", str(tmp_path)], str(tmp_path))
    assert exc.value.code == 2


def test_watch_help_lists_debounce():
    import subprocess

    r = subprocess.run(
        [PYTHON, "-m", "graphify", "--help"],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0
    assert "--debounce" in r.stdout
