"""REQ-QML-001/012/014: accepted corpus membership and real parser rejection."""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

from tests.test_graph_invariance import FIXTURES, _copy


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
    """The profile preserves the whole native tree, including metadata and owned JS."""
    copied = _copy(FIXTURES, tmp_path / "accepted", crlf=True)
    native, converted = [], []
    for path in copied.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(copied)
        original = (FIXTURES / relative).read_bytes()
        expected = original
        if relative.parts[0] == "qml":
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
