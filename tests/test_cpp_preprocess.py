"""The Fortran C-preprocessor path is hardened against corpus-side file reads.

A capital-F Fortran source is attacker-controlled. cpp always searches the
source file's own directory for quoted `#include`s and always honours absolute
include paths, regardless of `-nostdinc`/`-I`, so `#include "/etc/passwd"` or
`#include "../../secret"` would inline arbitrary host files into the graph
(GHSA-pcc4-rvhr-2pr8). `_cpp_preprocess` now strips every `#include` directive
before preprocessing and feeds the sanitized source to cpp on stdin, so no host
file can be read and no attacker-named path is ever passed as a cpp argument.
"""
import shutil
from pathlib import Path

import pytest

from graphify import extract


def _capture_cpp_call(monkeypatch):
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["input"] = kwargs.get("input")

        class _Result:
            returncode = 0
            stdout = b"preprocessed"

        return _Result()

    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/cpp")
    monkeypatch.setattr("subprocess.run", fake_run)
    return captured


def test_cpp_preprocess_feeds_stdin_and_passes_no_file_path(tmp_path, monkeypatch):
    """cpp is invoked with only flags; the source arrives on stdin, so an
    attacker-named corpus file can never be parsed as a cpp option and cpp never
    opens the file's own directory for includes."""
    f = tmp_path / "-Ietc.F90"  # a name that would be an option if passed as argv
    f.write_text("program x\nend program x\n")
    monkeypatch.chdir(tmp_path)

    captured = _capture_cpp_call(monkeypatch)
    out = extract._cpp_preprocess(Path("-Ietc.F90"))

    assert out == b"preprocessed"
    argv = captured["argv"]
    assert argv == ["cpp", "-w", "-P", "-nostdinc", "-I", "/dev/null"]
    # No source path in argv at all — it goes through stdin.
    assert captured["input"] is not None
    assert b"program x" in captured["input"]


def _read_secret_from(source_file: Path) -> bool:
    """True if _cpp_preprocess leaked the sentinel secret into its output."""
    out = extract._cpp_preprocess(source_file)
    return b"TOP_SECRET_SENTINEL" in out


@pytest.mark.skipif(shutil.which("cpp") is None, reason="cpp not available")
def test_absolute_include_cannot_read_host_file(tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP_SECRET_SENTINEL=abc123\n")
    src = tmp_path / "corpus" / "evil_abs.F90"
    src.parent.mkdir(parents=True)
    src.write_text(f'program evil\n#include "{secret}"\nend program evil\n')

    assert not _read_secret_from(src), "absolute #include leaked a host file"


@pytest.mark.skipif(shutil.which("cpp") is None, reason="cpp not available")
def test_relative_traversal_include_cannot_escape_the_corpus(tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP_SECRET_SENTINEL=abc123\n")
    src = tmp_path / "corpus" / "evil_rel.F90"
    src.parent.mkdir(parents=True)
    # ../secret.txt escapes corpus/ up to tmp_path/secret.txt
    src.write_text('program evil\n#include "../secret.txt"\nend program evil\n')

    assert not _read_secret_from(src), "traversing #include escaped the corpus"


@pytest.mark.skipif(shutil.which("cpp") is None, reason="cpp not available")
def test_same_directory_include_also_stripped(tmp_path):
    # Even a same-directory include is stripped (blunt but safe); its contents
    # must not appear in the output.
    (tmp_path / "sensitive.inc").write_text("TOP_SECRET_SENTINEL=inline\n")
    src = tmp_path / "evil_same.F90"
    src.write_text('program evil\n#include "sensitive.inc"\nend program evil\n')

    assert not _read_secret_from(src)


@pytest.mark.skipif(shutil.which("cpp") is None, reason="cpp not available")
def test_macro_expansion_still_works(tmp_path):
    """The reason capital-F files need cpp — #define/#ifdef — must still work
    after the include hardening."""
    src = tmp_path / "macros.F90"
    src.write_text(
        "#define GREET hello_world\n"
        "#ifdef GREET\n"
        "program GREET\n"
        "end program GREET\n"
        "#endif\n"
    )
    out = extract._cpp_preprocess(src)
    if b"#define GREET" in out:
        # Host cpp is not a functional GNU-style preprocessor over this input
        # (e.g. the macOS clang `cpp` wrapper); _cpp_preprocess fell back to the
        # sanitized raw bytes. Security still holds (covered above); macro
        # fidelity is only available where cpp actually runs (Linux/CI).
        pytest.skip("host cpp did not preprocess the input")
    assert b"hello_world" in out
    assert b"GREET" not in out  # the macro was expanded, not left verbatim
