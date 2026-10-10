r"""The read hook's out-of-project guard must not treat a rooted-but-driveless
path as cwd-relative.

`_run_hook_guard` short-circuits on `not Path(v).is_absolute()` with the comment
"relative -> anchored at cwd == in project". On Windows that premise is false for
a path like `/somewhere/else/x.py`: it has no drive, so `is_absolute()` is False,
but Windows anchors it at the current DRIVE root, not at cwd —
`Path("/somewhere/else/x.py").resolve()` is `C:\somewhere\else\x.py`. The guard
therefore declared out-of-project files in-project and emitted the read nudge,
and in strict mode the once-per-session deny, for files the graph never indexed.
`tests/test_hook_strict.py::test_out_of_project_read_silenced` has been failing
on Windows for exactly this reason.

`C:x.py` is the mirror case: drive-relative, anchored at that drive's current
directory rather than cwd.

The classification tests below drive `_is_cwd_relative` with `os.name` forced, so
the Windows semantics are exercised on POSIX CI too (`PureWindowsPath` works on
any host). The end-to-end tests need a real Windows `Path` flavour to show the
difference, so those are gated.
"""
import io
import json
import os
import sys
import time

import pytest

import graphify.cli as cli
from graphify.cli import _is_cwd_relative


def _fake_os_name(monkeypatch, name):
    """Force the flavour `_is_cwd_relative` selects, so both platforms' rules can
    be checked from either host."""
    monkeypatch.setattr(cli.os, "name", name)


# ---------------------------------------------------------------------------
# Classification — real teeth on POSIX CI as well as Windows
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "value",
    [
        "/somewhere/else/x.py",     # the reported case: rooted, no drive
        "/tmp/scratch.py",          # what a WSL / Git Bash / POSIX-shaped host sends
        "\\somewhere\\else\\x.py",  # same path, backslashes
        "C:x.py",                   # drive-relative: anchored at C:'s cwd, not ours
        "C:/proj/a.py",             # fully qualified
        "C:\\proj\\a.py",
        "\\\\server\\share\\a.py",  # UNC
    ],
)
def test_windows_non_cwd_relative_forms(monkeypatch, value):
    _fake_os_name(monkeypatch, "nt")
    assert _is_cwd_relative(value) is False, value


@pytest.mark.parametrize(
    "value",
    ["src/a.py", "a.py", "./rel.py", "..\\up.py", "sub\\dir\\a.py", "dir/../a.py"],
)
def test_windows_cwd_relative_forms(monkeypatch, value):
    _fake_os_name(monkeypatch, "nt")
    assert _is_cwd_relative(value) is True, value


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("/somewhere/else/x.py", False),
        ("/tmp/scratch.py", False),
        ("src/a.py", True),
        ("a.py", True),
        ("./rel.py", True),
        # No drives on POSIX: "C:x.py" is an ordinary relative filename there, and
        # a backslash is a legal character in a POSIX filename, not a separator.
        ("C:x.py", True),
        ("C:/proj/a.py", True),
        ("\\somewhere\\else\\x.py", True),
    ],
)
def test_posix_rules_are_unchanged(monkeypatch, value, expected):
    """On POSIX `root` is set exactly when the path is absolute and `drive` is
    always empty, so the guard's behaviour there is identical to the old
    `not is_absolute()` test. Pinned so the fix stays Windows-only."""
    _fake_os_name(monkeypatch, "posix")
    assert _is_cwd_relative(value) is expected, value


def test_matches_is_absolute_on_every_posix_input(monkeypatch):
    """The property the above table samples: on POSIX, `_is_cwd_relative` is
    exactly `not Path(v).is_absolute()`."""
    from pathlib import PurePosixPath
    _fake_os_name(monkeypatch, "posix")
    for v in ["/a/b", "a/b", "", ".", "..", "/", "//x", "C:x", "\\x", "/a/../b"]:
        assert _is_cwd_relative(v) is (not PurePosixPath(v).is_absolute()), v


def test_empty_path_is_treated_as_cwd_relative(monkeypatch):
    # Callers filter empties out before the loop; pinned so the helper cannot
    # raise if that ever changes.
    for name in ("nt", "posix"):
        _fake_os_name(monkeypatch, name)
        assert _is_cwd_relative("") is True


# ---------------------------------------------------------------------------
# End-to-end through the guard
# ---------------------------------------------------------------------------

def _project(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    f = src / "mod.py"
    f.write_text("def x():\n    return 1\n", encoding="utf-8")
    out = tmp_path / "graphify-out"
    out.mkdir()
    (out / "manifest.json").write_text(
        json.dumps({"src/mod.py": {"mtime": 1}}), encoding="utf-8")
    time.sleep(0.02)
    (out / "graph.json").write_text('{"nodes":[],"links":[]}', encoding="utf-8")
    return f


def _invoke(tmp_path, monkeypatch, file_path, *, strict=False):
    monkeypatch.chdir(tmp_path)
    payload = {"session_id": "s1", "tool_name": "Read",
               "tool_input": {"file_path": str(file_path)}}

    class _Stdin:
        buffer = io.BytesIO(json.dumps(payload).encode())
    monkeypatch.setattr(sys, "stdin", _Stdin())
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    cli._run_hook_guard("read", strict=strict)
    return buf.getvalue()


@pytest.mark.skipif(os.name != "nt",
                    reason="needs a Windows Path flavour: on POSIX these strings are "
                           "already absolute, so the guard was never wrong about them")
@pytest.mark.parametrize("outside", ["/somewhere/else/x.py", "\\somewhere\\else\\x.py"])
@pytest.mark.parametrize("strict", [False, True])
def test_driveless_rooted_path_outside_the_project_is_silent(tmp_path, monkeypatch, outside, strict):
    _project(tmp_path)
    assert _invoke(tmp_path, monkeypatch, outside, strict=strict).strip() == ""


def test_in_project_relative_path_still_nudges(tmp_path, monkeypatch):
    """The guard must keep firing for the paths it exists to catch."""
    _project(tmp_path)
    assert "MANDATORY" in _invoke(tmp_path, monkeypatch, "src/mod.py")


def test_in_project_absolute_path_still_nudges(tmp_path, monkeypatch):
    f = _project(tmp_path)
    assert "MANDATORY" in _invoke(tmp_path, monkeypatch, f)


def test_absolute_path_outside_the_project_is_still_silent(tmp_path, monkeypatch):
    """Unchanged behaviour, kept as the control for the cases above."""
    _project(tmp_path)
    other = tmp_path.parent / "elsewhere_project" / "z.py"
    other.parent.mkdir(parents=True, exist_ok=True)
    other.write_text("x = 1\n", encoding="utf-8")
    assert _invoke(tmp_path, monkeypatch, other).strip() == ""
