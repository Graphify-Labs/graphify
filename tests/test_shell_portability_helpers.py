"""Characterize exact file identity at the shell/native fixture boundary."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

import pytest

from tests.shell_portability import resolve_shell_path


def test_native_path_keeps_full_identity_with_spaces(tmp_path):
    """A full native path identifies the created file, including spaced parents."""
    target = tmp_path / "tool with spaces" / "python"
    target.parent.mkdir()
    target.touch()
    assert resolve_shell_path(str(target)) == target.resolve()


def test_same_named_sibling_is_not_the_requested_file(tmp_path):
    """Canonicalization must preserve parent identity rather than just basename."""
    requested = tmp_path / "requested" / "python"
    rejected = tmp_path / "rejected" / "python"
    for target in (requested, rejected):
        target.parent.mkdir()
        target.touch()
    assert resolve_shell_path(str(rejected)) != requested.resolve()


def test_relative_identity_is_rejected(tmp_path, monkeypatch):
    """An existing relative file cannot accidentally bind to the test runner cwd."""
    (tmp_path / "python").touch()
    monkeypatch.chdir(tmp_path)
    with pytest.raises(AssertionError, match="relative file identity"):
        resolve_shell_path("python")


def test_missing_absolute_identity_is_rejected(tmp_path):
    """A nonexistent interpreter candidate cannot satisfy a path-only comparison."""
    with pytest.raises(FileNotFoundError):
        resolve_shell_path(str(tmp_path / "missing-python"))


@pytest.mark.skipif(os.name != "nt" or shutil.which("sh") is None,
                    reason="native Windows and an MSYS shell required")
def test_msys_mount_mapping_preserves_full_sibling_identity(tmp_path):
    """Real cygpath maps /tmp and spaced parents while keeping decoys distinct."""
    executable = shutil.which("sh")
    assert executable is not None
    system = subprocess.check_output([executable, "-c", "uname -s"], text=True).strip()
    if not system.startswith(("MSYS_", "MINGW", "CYGWIN_")):
        pytest.skip("the available Windows shell uses a different path namespace")
    mapper = Path(executable).with_name("cygpath.exe")
    paths = []
    for directory in ("requested with spaces", "rejected with spaces"):
        target = tmp_path / directory / "python"
        target.parent.mkdir()
        target.touch()
        reported = subprocess.check_output(
            [str(mapper), "-u", "--", str(target)], text=True,
        ).strip()
        assert reported.startswith("/"), reported
        paths.append((target, reported))
    requested, rejected = paths
    assert resolve_shell_path(requested[1]) == requested[0].resolve()
    assert resolve_shell_path(rejected[1]) == rejected[0].resolve()
    assert resolve_shell_path(rejected[1]) != requested[0].resolve()
