from __future__ import annotations

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
