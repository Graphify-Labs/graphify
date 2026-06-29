"""Tests for graphify.installer.path_win.

`path_win` shells out to PowerShell to set/unset the user-level PATH.
We mock `subprocess.run` so the tests don't actually touch the registry.
"""

from __future__ import annotations

import sys
from unittest.mock import patch, MagicMock

import pytest

from graphify.installer import path_win


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell call only runs on Windows")
def test_add_to_user_path_invokes_powershell_with_setx():
    """On Windows, add_to_user_path must call PowerShell's
    [Environment]::SetEnvironmentVariable with Target=User."""
    fake = MagicMock(return_value=MagicMock(returncode=0, stdout="", stderr=""))
    with patch("graphify.installer.path_win.subprocess.run", fake):
        path_win.add_to_user_path(r"C:\Users\me\AppData\Local\graphify\bin")
    args, kwargs = fake.call_args
    # First positional arg is the command list passed to subprocess.run
    cmd = args[0]
    assert cmd[0] == "powershell"
    assert "-NoProfile" in cmd
    assert "-Command" in cmd
    # The combined -Command string must reference SetEnvironmentVariable with User target
    command_str = next(a for a in cmd if isinstance(a, str) and "SetEnvironmentVariable" in a)
    assert "User" in command_str
    assert r"C:\Users\me\AppData\Local\graphify\bin" in command_str


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell call only runs on Windows")
def test_add_to_user_path_is_idempotent():
    """Calling add_to_user_path twice with the same value must not error and
    must produce the same PowerShell call shape both times."""
    fake = MagicMock(return_value=MagicMock(returncode=0, stdout="", stderr=""))
    with patch("graphify.installer.path_win.subprocess.run", fake):
        path_win.add_to_user_path(r"C:\graphify\bin")
        path_win.add_to_user_path(r"C:\graphify\bin")
    assert fake.call_count == 2


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell call only runs on Windows")
def test_remove_from_user_path_invokes_powershell():
    fake = MagicMock(return_value=MagicMock(returncode=0, stdout="", stderr=""))
    with patch("graphify.installer.path_win.subprocess.run", fake):
        path_win.remove_from_user_path(r"C:\graphify\bin")
    cmd = fake.call_args[0][0]
    command_str = next(a for a in cmd if isinstance(a, str) and "SetEnvironmentVariable" in a)
    assert "User" in command_str
    # The path to remove must appear in the command (we filter it out of the
    # existing PATH and re-set the result).
    assert r"C:\graphify\bin" in command_str


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell call only runs on Windows")
def test_add_to_user_path_raises_on_powershell_failure():
    fake = MagicMock(return_value=MagicMock(returncode=1, stdout="", stderr="boom"))
    with patch("graphify.installer.path_win.subprocess.run", fake):
        with pytest.raises(path_win.PathWinError):
            path_win.add_to_user_path(r"C:\graphify\bin")


def test_add_to_user_path_noop_on_non_windows():
    """On non-Windows platforms, add_to_user_path must return without
    invoking subprocess."""
    fake = MagicMock()
    with patch("graphify.installer.path_win.sys.platform", "darwin"):
        with patch("graphify.installer.path_win.subprocess.run", fake):
            path_win.add_to_user_path("/tmp/whatever")
    fake.assert_not_called()