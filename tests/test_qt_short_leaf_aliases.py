"""REQ-QML-020: Windows native file spellings preserve accepted source identities."""
from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path

import pytest

import graphify.extract as extraction
from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extractors.qml_facts import qml_metadata
from graphify.paths import load_node_link_graph
from tests.test_qt_final_incremental_parity import normalized, project
from tests.test_source_alias_provenance import directory_alias


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Actual Windows native short-file spelling")
HEADER = "LongCanonicalBackendDeclaration.h"
NAMES = (HEADER, "Main.qml", "loader.cpp", "CMakeLists.txt", "resources.qrc", "keep.py")
PYTHON = b"def helper():\n    return 7\n\ndef caller():\n    return helper()\n"


def short_leaf(path):
    """Shorten the real leaf alone, retaining its walked parent-directory owner."""
    api = ctypes.windll.kernel32.GetShortPathNameW
    api.argtypes = (ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32)
    api.restype = ctypes.c_uint32
    buffer = ctypes.create_unicode_buffer(32768)
    length = api(str(path), buffer, len(buffer))
    if not length or length >= len(buffer):
        pytest.skip("Filesystem does not expose a native short-file spelling")
    alias = path.parent / Path(buffer.value).name
    if alias == path:
        pytest.skip("Filesystem has no distinct short spelling for this leaf")
    assert alias.resolve() == path.resolve()
    return alias


def fixture(root):
    """Retain public Qt membership declarations and original BOM/CRLF source bytes."""
    project(root)
    old, header = root / "backend.h", root / HEADER
    header.write_bytes(b"\xef\xbb\xbf// Unicode \xcf\x80\r\n" + old.read_bytes().replace(b"\n", b"\r\n"))
    old.unlink()
    cmake = root / "CMakeLists.txt"
    cmake.write_bytes(cmake.read_bytes().replace(b"backend.h", HEADER.encode()))
    return [root / name for name in NAMES]


def graph(paths, root, cache):
    result = extraction.extract(paths, root=root, cache_root=cache, parallel=False)
    assert not result["failed_sources"] and not result["qml_failures"]
    return build_from_json(result, root=root, directed=True), result


@pytest.mark.parametrize("selection", ["header", "build_metadata", "both"])
def test_req_qml020_ac01_short_native_leaf_preserves_membership_facts_and_reload(
        tmp_path, selection, monkeypatch):
    """One NTFS entry has identical IDs, spans, memberships and cold/warm products."""
    root = tmp_path.resolve()
    paths = fixture(root)
    spellings = {"header": {HEADER}, "build_metadata": {"CMakeLists.txt"},
                 "both": {HEADER, "CMakeLists.txt"}}[selection]
    aliased = [short_leaf(path) if path.name in spellings else path for path in paths]
    before = {name: (root / name).read_bytes() for name in NAMES}
    expected, expected_result = graph(paths, root, root / "canonical-cache")
    actual, result = graph(aliased, root, root / "alias-cache")
    memberships = [qml_metadata(data) for _, data in actual.nodes(data=True)
                   if qml_metadata(data).get("kind") == "membership_resolution"]
    assert memberships and all(item["status"] == "resolved" for item in memberships)
    assert normalized(actual) == normalized(expected)
    assert result["nodes"] == expected_result["nodes"] and result["edges"] == expected_result["edges"]
    observed, real = [], extraction._safe_extract_with_xaml_root

    def record(extractor, path, anchor):
        observed.append(path.name)
        return real(extractor, path, anchor)

    monkeypatch.setattr(extraction, "_safe_extract_with_xaml_root", record)
    warm, _ = graph(aliased, root, root / "alias-cache")
    assert "keep.py" not in observed and normalized(warm) == normalized(expected)
    output = root / "reloaded.json"
    assert to_json(warm, {}, str(output), force=True)
    reloaded = load_node_link_graph(json.loads(output.read_text(encoding="utf-8")))
    assert normalized(reloaded) == normalized(expected)
    assert before == {name: (root / name).read_bytes() for name in NAMES}


def test_req_qml020_ac02_short_spelling_preserves_two_discovered_junction_owners(
        tmp_path, directory_alias):
    """Native spelling expansion preserves separate source owners and actual calls."""
    root = tmp_path.resolve()
    paths = fixture(root)
    real = root / "CanonicalRealDirectory"
    real.mkdir()
    source = real / "LongCanonicalFunctionSource.py"
    source.write_bytes(PYTHON)
    link = directory_alias(root / "DiscoveredJunctionDirectory", real)
    walked = [source, link / source.name]
    expected, _ = graph([*paths, *walked], root, root / "canonical-cache")
    actual, result = graph([*paths, *(short_leaf(path) for path in walked)], root, root / "alias-cache")
    identities = {
        path.relative_to(root).as_posix(): {node["id"] for node in result["nodes"]
                                          if node.get("source_file") == path.relative_to(root).as_posix()}
        for path in walked
    }
    first, second = identities.values()
    assert len(first) == len(second) == 3 and first.isdisjoint(second)
    for source_file, owned in identities.items():
        calls = [edge for edge in result["edges"] if edge.get("source_file") == source_file
                 and edge.get("context") == "call"]
        assert calls and all(edge["source"] in owned and edge["target"] in owned for edge in calls)
    assert normalized(actual) == normalized(expected)
    warm, _ = graph([*paths, *(short_leaf(path) for path in walked)], root, root / "alias-cache")
    assert normalized(warm) == normalized(expected)
    assert source.read_bytes() == PYTHON


def test_req_qml020_ac02_short_foreign_native_leaf_keeps_existing_root_rejection(
        tmp_path, directory_alias):
    """A local spelling of a foreign QObject still gains no Qt endpoint authority."""
    root, foreign = tmp_path / "repo", tmp_path / "foreign"
    root.mkdir()
    foreign.mkdir()
    paths = fixture(root)
    target = foreign / "LongForeignBackendDeclaration.h"
    target.write_bytes(b"class Foreign : public QObject { Q_OBJECT public: Q_INVOKABLE void run(); };\n")
    link = directory_alias(root / "ForeignJunctionDirectory", foreign)
    alias = short_leaf(link / target.name)
    before = target.read_bytes()
    assert extraction.collect_files(link, follow_symlinks=True, root=root) == []
    result = extraction.extract([*paths, alias], root=root, cache_root=root / "cache", parallel=False)
    assert result["failed_sources"] and {item["code"] for item in result["qml_failures"]} == {"QT_CPP_ROOT"}
    assert not [node for node in result["nodes"] if node.get("label") == "Qt class: Foreign"]
    assert target.read_bytes() == before


def test_req_qml020_ac01_native_utf16_lengths_preserve_astral_source_names(tmp_path):
    """Actual Win32 WCHAR lengths accept supplementary characters in owners and leaves."""
    root = tmp_path.resolve()
    parent = root / "PublicAstralDirectory\U0001f680"
    parent.mkdir()
    source = parent / "LongAstralFunctionSource\U0001f680.py"
    source.write_bytes(PYTHON)
    canonical, _ = graph([source], root, root / "canonical-cache")
    actual, _ = graph([short_leaf(source)], root, root / "alias-cache")
    assert normalized(actual) == normalized(canonical)
    assert source.read_bytes() == PYTHON
