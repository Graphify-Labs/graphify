"""REQ-QML-022-AC06: metadata-only type identity changes replace durable joins."""
import json
import os
import stat

import pytest

from graphify.extract import extract
from graphify.extractors.qml_facts import qml_metadata
from graphify.qt_project_index import QtProjectIndex
from tests.qml_persistence_helpers import protected_snapshot
from tests.test_qml_types_qt612_updates import run_update
from tests.test_qt_cmake_type_exports import source


def fixture(root, properties):
    """Inside is a declared module member; Outside only shares its physical directory."""
    build = root / "CMakeLists.txt"
    build.write_text(source(properties), encoding="utf-8")
    for name, text in {"Tree.qml": "Item {}", "Inside.qml": "import Example 2.3\nBinaryTree {}",
                       "Outside.qml": "import Example 2.3\nBinaryTree {}"}.items():
        (root / name).write_text(text, encoding="utf-8")
    return build


def sites(root):
    graph = json.loads((root / "graphify-out/graph.json").read_text(encoding="utf-8"))
    return graph, {n["source_file"]: n for n in graph["nodes"] if qml_metadata(n).get("kind") == "type_use"
                   and n.get("label") == "BinaryTree"}


@pytest.mark.parametrize("mutation", ["rename", "version", "internal"])
def test_req_qml022_ac06_metadata_only_export_mutation_retires_stale_joins_and_matches_full(
    tmp_path, monkeypatch, mutation,
):
    """Unchanged QML consumers lose only the authority invalidated by literal metadata."""
    initial = 'set_source_files_properties(Tree.qml PROPERTIES QT_QML_SOURCE_TYPENAME BinaryTree)\n'
    build = fixture(tmp_path, initial)
    monkeypatch.chdir(tmp_path)
    assert run_update(tmp_path, monkeypatch) == 0
    before, first = sites(tmp_path)
    assert {qml_metadata(n)["status"] for n in first.values()} == {"resolved"}
    changed = {"rename": initial.replace("BinaryTree", "OtherTree"),
               "version": initial.replace(")", ' QT_QML_SOURCE_VERSIONS "2.4")'),
               "internal": initial.replace(")", " QT_QML_INTERNAL_TYPE TRUE)")}[mutation]
    build.write_text(source(changed), encoding="utf-8")
    assert run_update(tmp_path, monkeypatch) == 0
    graph, current = sites(tmp_path)
    expected = {"Inside.qml": "resolved" if mutation == "internal" else "unavailable", "Outside.qml": "unavailable"}
    assert {file: qml_metadata(n)["status"] for file, n in current.items()} == expected
    stale = {n["id"] for file, n in current.items() if expected[file] == "unavailable"}
    assert not [e for e in graph["links"] if e["source"] in stale and e.get("context") == "qml_type_resolution"]
    paths = [tmp_path / name for name in ("CMakeLists.txt", "Tree.qml", "Inside.qml", "Outside.qml")]
    fresh = extract(paths, root=tmp_path, cache_root=tmp_path / "fresh", parallel=False)
    fresh_sites = {n["source_file"]: qml_metadata(n)["status"] for n in fresh["nodes"]
                   if qml_metadata(n).get("kind") == "type_use" and n.get("label") == "BinaryTree"}
    assert fresh_sites == expected
    index = QtProjectIndex(graph["nodes"], graph["links"], root=tmp_path)
    assert index.resolve_component("Example", "Tree", 2, 3).target_id is None
    settled = protected_snapshot(tmp_path / "graphify-out")
    assert run_update(tmp_path, monkeypatch) == 0
    assert protected_snapshot(tmp_path / "graphify-out") == settled


def test_req_qml022_ac06_invalid_export_update_preserves_output_and_recovers(tmp_path, monkeypatch, capsys):
    """A genuine malformed metadata edit leaves the previous graph/manifest retryable."""
    initial = 'set_source_files_properties(Tree.qml PROPERTIES QT_QML_SOURCE_TYPENAME BinaryTree)\n'
    build = fixture(tmp_path, initial)
    monkeypatch.chdir(tmp_path)
    assert run_update(tmp_path, monkeypatch) == 0
    accepted = protected_snapshot(tmp_path / "graphify-out")
    build.write_text(source(initial.replace("BinaryTree", "../Bad")), encoding="utf-8")
    assert run_update(tmp_path, monkeypatch) == 1
    assert protected_snapshot(tmp_path / "graphify-out") == accepted
    captured = capsys.readouterr()
    assert "QML_GRAPH_PRESERVED" in captured.out + captured.err
    build.write_text(source(initial.replace("BinaryTree", "OtherTree")), encoding="utf-8")
    assert run_update(tmp_path, monkeypatch) == 0
    assert all(qml_metadata(n)["status"] == "unavailable" for n in sites(tmp_path)[1].values())


@pytest.mark.skipif(os.name != "nt", reason="Actual Windows read-only output replacement boundary")
def test_req_qml022_ac06_valid_export_update_write_failure_retains_and_retries(tmp_path, monkeypatch):
    """A completed metadata parse cannot commit a new identity after publication fails."""
    initial = 'set_source_files_properties(Tree.qml PROPERTIES QT_QML_SOURCE_TYPENAME BinaryTree)\n'
    build = fixture(tmp_path, initial)
    monkeypatch.chdir(tmp_path)
    assert run_update(tmp_path, monkeypatch) == 0
    out = tmp_path / "graphify-out"
    accepted = protected_snapshot(out)
    build.write_text(source(initial.replace("BinaryTree", "OtherTree")), encoding="utf-8")
    graph = out / "graph.json"
    graph.chmod(stat.S_IREAD)
    try:
        assert run_update(tmp_path, monkeypatch) == 1
        assert protected_snapshot(out) == accepted
    finally:
        graph.chmod(stat.S_IWRITE)
    assert run_update(tmp_path, monkeypatch) == 0
    assert all(qml_metadata(n)["status"] == "unavailable" for n in sites(tmp_path)[1].values())
