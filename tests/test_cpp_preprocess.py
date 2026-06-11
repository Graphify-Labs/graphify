"""The Fortran C-preprocessor path is hardened against argument injection (F5).

A corpus file is attacker-named; cpp does not accept a "--" end-of-options
terminator, so _cpp_preprocess passes an absolute path which can never be parsed
as a cpp option.
"""
from graphify import extract


def test_cpp_preprocess_passes_absolute_path(tmp_path, monkeypatch):
    f = tmp_path / "weird.F90"
    f.write_text("program x\nend program x\n")

    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv

        class _Result:
            returncode = 0
            stdout = b"preprocessed"

        return _Result()

    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/cpp")
    monkeypatch.setattr("subprocess.run", fake_run)

    out = extract._cpp_preprocess(f)
    assert out == b"preprocessed"
    last_arg = captured["argv"][-1]
    assert last_arg.startswith("/"), f"path arg must be absolute, got {last_arg!r}"
    assert not last_arg.startswith("-"), "path arg must never look like an option"
