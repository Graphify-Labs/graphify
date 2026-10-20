"""REQ-QML-001/012/014: accepted corpus membership and real parser rejection."""
from __future__ import annotations

import os
from pathlib import PurePosixPath
import posixpath
import re
import subprocess
import sys

import pytest

from tests.test_graph_invariance import FIXTURES, _copy


def _assert_script_fixture_cohort(root):
    """Conservatively refuse fixture growth beyond the declared QML byte cohort.

    This is a trusted-fixture guard, not another QML resolver. Literal script
    references (including transitive JS/MJS imports) may not escape qml/ into
    ordinary files that the aggregate profile deliberately converts to CRLF.
    """
    qml = list(root.rglob("*.qml"))
    assert qml and all(path.relative_to(root).parts[0] == "qml" for path in qml)
    references_seen = 0
    for path in (root / "qml").rglob("*"):
        if not path.is_file() or (path.suffix not in {".qml", ".js", ".mjs"} and path.name != "qmldir"):
            continue
        text = path.read_text(encoding="utf-8")
        references = re.findall(r'''["']([^"'\r\n]+\.(?:js|mjs))["']''', text)
        if path.name == "qmldir":
            references.extend(line.split()[-1] for line in text.splitlines()
                              if line.split() and not line.lstrip().startswith("#")
                              and line.split()[-1].endswith((".js", ".mjs")))
        references_seen += len(references)
        for reference in references:
            if "\\" in reference or ":" in reference:
                continue
            relative = PurePosixPath(posixpath.normpath(
                (PurePosixPath(path.relative_to(root).as_posix()).parent / reference).as_posix()))
            if relative.is_absolute() or relative.parts[0] == ".." or not (root / relative).is_file():
                continue
            assert relative.parts[0] == "qml", "Review script byte ownership before growing the fixture cohort"
    # The real parser fixture deliberately imports unavailable helpers.js.
    # Inspect its nonempty references without inventing an accepted script owner;
    # the synthetic JS/MJS controls below prove both accepted and escaping paths.
    assert references_seen, "The script-cohort guard must inspect actual fixture references"


def test_req_qml014_ac03_script_byte_owners_remain_inside_declared_fixture_cohort():
    """Actual fixture imports justify the bounded cohort without graph-derived admission."""
    _assert_script_fixture_cohort(FIXTURES)


@pytest.mark.parametrize("suffix", [".js", ".mjs"])
def test_req_qml014_ac03_script_fixture_escape_requires_profile_review(tmp_path, suffix):
    """Literal or transitive script growth cannot silently become ordinary CRLF input."""
    qml = tmp_path / "qml"
    qml.mkdir()
    (qml / "Main.qml").write_text('import "helper.js" as Helpers\n', encoding="utf-8")
    (qml / "helper.js").write_text(f'import "./owned{suffix}";\n', encoding="utf-8")
    (qml / ("owned" + suffix)).write_text("export function value() { return 1; }\n", encoding="utf-8")
    _assert_script_fixture_cohort(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / ("owned" + suffix)).write_text("export function value() { return 1; }\n", encoding="utf-8")
    (qml / "helper.js").write_text(f'import "../outside/owned{suffix}";\n', encoding="utf-8")
    with pytest.raises(AssertionError, match="Review script byte ownership"):
        _assert_script_fixture_cohort(tmp_path)


def test_req_qml014_ac03_invariance_omits_only_two_rejection_fixtures(tmp_path):
    """Copy the real corpus; every admitted file retains its exact source bytes."""
    copied = _copy(FIXTURES, tmp_path / "accepted")
    source_files = {path.relative_to(FIXTURES).as_posix(): path for path in FIXTURES.rglob("*")
                    if path.is_file() and "graphify-out" not in path.relative_to(FIXTURES).parts}
    accepted_files = {path.relative_to(copied).as_posix(): path for path in copied.rglob("*")
                      if path.is_file()}
    assert source_files.keys() - accepted_files.keys() == {
        "qml/parser_probe/Incomplete.qml", "qml/parser_probe/Malformed.qml",
    }
    assert not accepted_files.keys() - source_files.keys()
    assert all(path.read_bytes() == source_files[name].read_bytes()
               for name, path in accepted_files.items())
    assert "qml/parser_probe/UnicodeCRLF.qml" in accepted_files


def test_req_qml014_ac03_newline_profile_keeps_native_bytes_and_converts_other_text(tmp_path):
    """Preserve native inputs anywhere and their owned project cohort, converting other text."""
    copied = _copy(FIXTURES, tmp_path / "accepted", crlf=True)
    native, converted = [], []
    for path in copied.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(copied)
        original = (FIXTURES / relative).read_bytes()
        expected = original
        if (relative.parts[0] == "qml" or relative.suffix.lower() in {
            ".cpp", ".cc", ".cxx", ".h", ".hpp", ".hh", ".hxx", ".qml",
            ".qmltypes", ".cmake", ".pro", ".pri", ".qrc",
        } or relative.name in {"qmldir", "CMakeLists.txt"}):
            native.append(relative)
        elif b"\0" not in original:
            try:
                original.decode("utf-8")
            except UnicodeDecodeError:
                pass
            else:
                expected = original.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
                converted.append(relative)
        assert path.read_bytes() == expected, relative
    assert native and converted
    assert {path.suffix for path in native} >= {".qml", ".h", ".pro", ".qrc"}
    assert any(path.name == "CMakeLists.txt" for path in native)
    assert any(path.name == "qmldir" for path in native)
    assert any(path.parts[0] != "qml" and path.suffix == ".cpp" for path in native)
    assert any(path.parts[0] != "qml" and path.suffix == ".h" for path in native)
    assert any(path.suffix == ".py" for path in converted)


@pytest.mark.parametrize("native_name", [
    "outside/unit.cpp", "outside/unit.cc", "outside/unit.cxx", "outside/unit.h",
    "outside/unit.hpp", "outside/unit.hh", "outside/unit.hxx", "outside/View.qml",
    "outside/types.qmltypes", "outside/module.cmake", "outside/project.pro",
    "outside/project.pri", "outside/resources.qrc", "outside/qmldir",
    "outside/CMakeLists.txt", "qml/owned-script.js",
])
def test_req_qml014_ac03_native_copy_ownership_does_not_depend_on_location(tmp_path, native_name):
    """Explicit LF bytes expose the old directory-only rule even on CRLF checkouts.

    This exercises copying, not parser admission. Every input remains present;
    ordinary Python/JavaScript controls receive exact newline conversion.
    """
    source = tmp_path / "inputs"
    native = source / native_name
    native.parent.mkdir(parents=True)
    native_bytes = "// Unicode α marker\n// second line\n".encode("utf-8")
    native.write_bytes(native_bytes)
    ordinary = {"ordinary.py": b"value = 1\n", "ordinary.js": b"function value() { return 1; }\n",
                "ordinary.mjs": b"export function value() { return 1; }\n"}
    for name, content in ordinary.items():
        (source / name).write_bytes(content)

    copied = _copy(source, tmp_path / "copied", crlf=True)

    assert {path.relative_to(copied).as_posix() for path in copied.rglob("*") if path.is_file()} == {
        native_name, *ordinary,
    }
    assert (copied / native_name).read_bytes() == native_bytes
    for name, content in ordinary.items():
        assert (copied / name).read_bytes() == content.replace(b"\n", b"\r\n")


@pytest.mark.parametrize("name", ["Incomplete.qml", "Malformed.qml"])
def test_req_qml012_ac02_force_still_rejects_invalid_invariance_input(tmp_path, name):
    """Force never converts deliberate syntax rejection into a committed product."""
    root = tmp_path / "rejected corpus"
    root.mkdir()
    (root / name).write_bytes((FIXTURES / "qml/parser_probe" / name).read_bytes())
    result = subprocess.run(
        [sys.executable, "-m", "graphify", "update", str(root), "--force", "--no-cluster"],
        cwd=root, env=dict(os.environ, PYTHONIOENCODING="utf-8", GRAPHIFY_NO_TIPS="1"),
        capture_output=True, text=True, timeout=120,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 1, output[-4000:]
    assert "QML_GRAPH_PRESERVED" in output
    assert not (root / "graphify-out/graph.json").exists()
    assert not (root / "graphify-out/manifest.json").exists()
