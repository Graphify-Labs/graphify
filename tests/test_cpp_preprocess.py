"""The Fortran C-preprocessor path is hardened against argument injection (F5).

A corpus file is attacker-named; cpp does not accept a "--" end-of-options
terminator, so _cpp_preprocess passes an absolute path which can never be parsed
as a cpp option.
"""
import os
from pathlib import Path

import pytest

from graphify import extract


def _capture_cpp_argv(monkeypatch):
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv

        class _Result:
            returncode = 0
            stdout = b"preprocessed"

        return _Result()

    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/cpp")
    monkeypatch.setattr("subprocess.run", fake_run)
    return captured


def test_cpp_preprocess_passes_absolute_path(tmp_path, monkeypatch):
    f = tmp_path / "weird.F90"
    f.write_text("program x\nend program x\n")

    captured = _capture_cpp_argv(monkeypatch)

    out = extract._cpp_preprocess(f)
    assert out == b"preprocessed"
    last_arg = captured["argv"][-1]
    # Test the property, not the spelling: a leading "/" is only what "absolute"
    # looks like on POSIX, so the literal check failed on a perfectly correct
    # Windows path (C:\...\weird.F90). os.path.isabs answers for the host.
    assert os.path.isabs(last_arg), f"path arg must be absolute, got {last_arg!r}"
    assert not last_arg.startswith("-"), "path arg must never look like an option"


@pytest.mark.parametrize("hostile_name", ["-Ietc.F90", "-include.F90"])
def test_cpp_preprocess_absolutises_a_relative_attacker_named_file(
    tmp_path, monkeypatch, hostile_name
):
    """The guard only does work when the incoming path is RELATIVE.

    The test above hands in an already-absolute path, so it passes whether or
    not `_cpp_preprocess` resolves anything — removing the `.resolve()` does not
    make it fail. This is the case the hardening actually exists for: a corpus
    file whose own name is a cpp option, reached by a relative path.
    """
    (tmp_path / hostile_name).write_text("program x\nend program x\n")
    monkeypatch.chdir(tmp_path)

    captured = _capture_cpp_argv(monkeypatch)

    assert extract._cpp_preprocess(Path(hostile_name)) == b"preprocessed"
    last_arg = captured["argv"][-1]
    assert os.path.isabs(last_arg), (
        f"relative path was passed through unresolved: {last_arg!r}"
    )
    assert not last_arg.startswith("-"), (
        f"cpp would parse {last_arg!r} as an option, not a filename"
    )
