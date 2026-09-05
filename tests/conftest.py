from __future__ import annotations

import os
import socket
import tempfile
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture(scope="session")
def _can_symlink() -> bool:
    """Whether this machine can create symlinks at all (#2642).

    Probed rather than inferred from ``sys.platform``: Windows *can* create
    symlinks from an elevated shell or with Developer Mode enabled, and those
    runs should still get the coverage. A plain non-elevated Windows shell
    raises ``OSError: [WinError 1314] A required privilege is not held by the
    client``, which pytest reports as a FAILURE — 15 of them, drowning out real
    defects — when what it means is "unsupported here".

    One file symlink is enough to probe: Windows gates file and directory
    symlinks behind the same ``SeCreateSymbolicLinkPrivilege`` check.
    """
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "probe-src"
        src.write_text("x", encoding="utf-8")
        try:
            (Path(d) / "probe-link").symlink_to(src)
        except (OSError, NotImplementedError):
            return False
        return True


@pytest.fixture
def requires_symlinks(_can_symlink) -> None:
    """Skip a test that must create symlinks when the platform won't allow it.

    Take this as a parameter rather than wrapping each ``symlink_to()`` call in
    try/except: the guard then sits in the signature where it is visible, and
    an OSError from the code UNDER test is still a real failure instead of
    being swallowed into a skip.
    """
    if not _can_symlink:
        pytest.skip(
            "symlink creation unavailable on this machine "
            "(Windows requires an elevated shell or Developer Mode)"
        )


@pytest.fixture(scope="session")
def _can_mkfifo() -> bool:
    """Whether this machine can create a FIFO (#2919).

    Probed, not inferred from ``sys.platform``, for the same reason as
    ``_can_symlink``: ``os.mkfifo`` is absent on Windows, but it can also fail
    on a POSIX host whose temp dir sits on a filesystem that has no FIFOs
    (some network and container mounts). Either way an ``AttributeError`` or
    ``OSError`` raised while *building the fixture* says nothing about the code
    under test.
    """
    if not hasattr(os, "mkfifo"):
        return False
    with tempfile.TemporaryDirectory() as d:
        try:
            os.mkfifo(Path(d) / "probe-fifo")
        except (OSError, NotImplementedError):
            return False
        return True


@pytest.fixture
def requires_fifo(_can_mkfifo) -> None:
    """Skip a test whose fixture is a named pipe when the platform has none."""
    if not _can_mkfifo:
        pytest.skip("named pipes (os.mkfifo) unavailable on this platform")


@pytest.fixture(scope="session")
def _can_bind_unix_socket() -> bool:
    """Whether this machine can bind an ``AF_UNIX`` socket to a path (#2919).

    Windows 10+ does support ``AF_UNIX``, and CPython exposes it on some
    builds, so this cannot be decided from the platform name either — probe and
    let the hosts that can do it keep the coverage.
    """
    if not hasattr(socket, "AF_UNIX"):
        return False
    with tempfile.TemporaryDirectory() as d:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.bind(str(Path(d) / "probe.sock"))
        except (OSError, NotImplementedError):
            return False
        finally:
            sock.close()
        return True


@pytest.fixture
def requires_unix_socket(_can_bind_unix_socket) -> None:
    """Skip a test that must bind an AF_UNIX socket where that is unsupported."""
    if not _can_bind_unix_socket:
        pytest.skip("AF_UNIX sockets unavailable on this platform")


@pytest.fixture(scope="session")
def _can_delete_cwd() -> bool:
    """Whether a directory can be removed while it is a process's CWD (#2919).

    POSIX unlinks the directory entry and leaves the process sitting on an
    orphaned inode — the state a detached hook inherits, and the one
    ``_rebuild_code`` has to survive. Windows keeps an open handle on the CWD,
    so ``rmdir`` raises ``PermissionError: [WinError 32]`` and the scenario
    cannot be constructed at all. The failure is in the fixture, not the code.
    """
    old = Path.cwd()
    with tempfile.TemporaryDirectory() as d:
        probe = Path(d) / "probe-cwd"
        probe.mkdir()
        try:
            os.chdir(probe)
            probe.rmdir()
        except OSError:
            return False
        finally:
            os.chdir(old)
        return True


@pytest.fixture
def requires_deletable_cwd(_can_delete_cwd) -> None:
    """Skip a test that must delete its own CWD where the OS forbids it."""
    if not _can_delete_cwd:
        pytest.skip(
            "cannot remove a directory that is the process CWD on this platform "
            "(Windows holds an open handle: WinError 32)"
        )


@pytest.fixture(autouse=True)
def _sandbox_home(tmp_path_factory, monkeypatch):
    """Every test gets a throwaway HOME so installers/uninstallers can never
    touch the developer's real ~/.claude, ~/.gemini, ~/.codebuddy, ~/.copilot,
    ~/.config, ~/.agents (issue #2168).

    Allocated via tmp_path_factory (not inside tmp_path) so tests that assert
    the exact contents of their own tmp_path are unaffected."""
    home = tmp_path_factory.mktemp("sandbox-home")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))              # Windows ntpath.expanduser
    monkeypatch.setenv("LOCALAPPDATA", str(home / "AppData" / "Local"))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)     # escape hatch that bypasses Path.home
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    return home

_ANALYZE_WARNING_FILTERS = (
    "ignore:Tensorflow not installed; ParametricUMAP will be unavailable:ImportWarning:umap",
    "ignore:Please import `random` from the `scipy\\.sparse` namespace.*:"
    "DeprecationWarning:hyppo\\.independence\\.hhg",
    "ignore:The keyword argument 'nopython=False' was supplied.*:Warning:numba\\.core\\.decorators",
)


def pytest_collection_modifyitems(items: list[Any]) -> None:
    for item in items:
        if item.path.name != "test_analyze.py":
            continue
        for warning_filter in _ANALYZE_WARNING_FILTERS:
            item.add_marker(pytest.mark.filterwarnings(warning_filter))
