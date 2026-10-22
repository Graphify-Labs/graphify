"""INC-QML-58: real QRC output pairs survive publication, updates and rejection."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from graphify.qt_analysis_state import QT_STATE_FILE
from graphify.qml_resolution_types import qml_metadata
from graphify.watch import _rebuild_code
from tests.test_qt_cmake_mutation_updates import compare_clean, normalized, published


def project(root):
    """Public, source-local fixture with XML-owned aliases and no generated C++."""
    sources = {
        "Main.qml": "Item { property int shown: 1 }\n",
        "Other.qml": "Item { property int other: 2 }\n",
        "icons.qrc": '<RCC><qresource prefix="/icons"><file alias="Document.qml">Main.qml</file></qresource></RCC>\n',
        "other.qrc": '<RCC><qresource prefix="/other"><file alias="Other.qml">Other.qml</file></qresource></RCC>\n',
        "CMakeLists.txt": "qt_add_qml_module(app URI Example VERSION 1.0 QML_FILES Main.qml Other.qml)\n"
                          "qt_add_resources(RESOURCE_SOURCES icons.qrc)\n"
                          "target_sources(app PRIVATE ${RESOURCE_SOURCES})\n",
    }
    for name, text in sources.items():
        (root / name).write_bytes(text.encode())
    return root / "CMakeLists.txt"


def qrc_targets(graph):
    """Read the serialized production membership direction, not a parser count."""
    return {graph.nodes[edge.get("_tgt", target)]["source_file"] for _, target, edge in graph.edges(data=True)
            if edge.get("context") == "qt_project_source"
            and graph.nodes[edge.get("_tgt", target)]["source_file"].endswith(".qrc")}


def test_req_qml009_ac03_pair_reaches_graph_export_reload_and_warm_full_parity(tmp_path):
    """A literal input joins its admitted QRC file; the generated use keeps its span."""
    build = project(tmp_path)
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    graph = published(tmp_path)
    assert qrc_targets(graph) == {"icons.qrc"}
    (use_id, use), = [(identity, node) for identity, node in graph.nodes(data=True)
                     if qml_metadata(node).get("kind") == "qt_generated_resource_use"]
    md = qml_metadata(use)
    span = md["span"]
    assert build.read_bytes()[span["start_byte"]:span["end_byte"]] == b"${RESOURCE_SOURCES}"
    assert md["output_variable"] == "RESOURCE_SOURCES" and md["module_key"]
    references = [graph.nodes[edge.get("_tgt", target)] for source, target, edge in graph.edges(data=True)
                  if edge.get("_src", source) == use_id
                  and edge.get("context") == "qt_generated_resource_input"]
    assert len(references) == 1 and qml_metadata(references[0])["value"] == "icons.qrc"
    assert all(node["source_file"].endswith(".qrc") for _, node in graph.nodes(data=True)
               if qml_metadata(node).get("kind") == "resource_alias")
    assert not any(node.get("source_file", "").endswith(".cpp") for _, node in graph.nodes(data=True))
    baseline = normalized(graph)
    assert _rebuild_code(tmp_path, changed_paths=[build], no_cluster=True, acquire_lock=False)
    assert normalized(published(tmp_path)) == baseline
    compare_clean(tmp_path)


def test_req_qml011_ac02_metadata_and_qrc_only_changes_remove_stale_pair_facts(tmp_path):
    """Metadata retarget, XML alias edit and pair removal all equal clean extraction."""
    build = project(tmp_path)
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    build.write_bytes(build.read_bytes().replace(b"icons.qrc", b"other.qrc"))
    assert _rebuild_code(tmp_path, changed_paths=[build], no_cluster=True, acquire_lock=False)
    assert qrc_targets(published(tmp_path)) == {"other.qrc"}
    compare_clean(tmp_path)
    resource = tmp_path / "other.qrc"
    resource.write_bytes(resource.read_bytes().replace(b"Other.qml", b"Changed.qml", 1))
    assert _rebuild_code(tmp_path, changed_paths=[resource], no_cluster=True, acquire_lock=False)
    graph = published(tmp_path)
    urls = {qml_metadata(node).get("logical_url") for _, node in graph.nodes(data=True)
            if node.get("source_file") == "other.qrc" and qml_metadata(node).get("kind") == "resource_alias"}
    assert urls == {"qrc:/other/Changed.qml"}
    compare_clean(tmp_path)
    build.write_bytes(build.read_bytes().split(b"qt_add_resources", 1)[0])
    assert _rebuild_code(tmp_path, changed_paths=[build], no_cluster=True, acquire_lock=False)
    assert qrc_targets(published(tmp_path)) == set()
    assert not any(qml_metadata(node).get("kind") == "qt_generated_resource_use"
                   for _, node in published(tmp_path).nodes(data=True))
    compare_clean(tmp_path)


@pytest.mark.parametrize("force", [False, True])
def test_req_qml012_ac02_rejected_mutation_retains_products_repeats_and_recovers(tmp_path, force):
    """An unsupported output mutation cannot replace graph/manifest/report/Qt state."""
    build = project(tmp_path)
    accepted = build.read_bytes()
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    baseline = normalized(published(tmp_path))
    out = tmp_path / "graphify-out"
    (out / "report.md").write_bytes(b"Previously accepted public report\n")
    names = ("graph.json", "manifest.json", "report.md", QT_STATE_FILE)
    prior = {name: (out / name).read_bytes() for name in names}
    build.write_bytes(accepted + b"set(RESOURCE_SOURCES other.cpp)\n")
    for _ in range(2):
        assert not _rebuild_code(tmp_path, changed_paths=[build], no_cluster=True, acquire_lock=False, force=force)
        assert {name: (out / name).read_bytes() for name in names} == prior
    build.write_bytes(accepted)
    for _ in range(2):
        assert _rebuild_code(tmp_path, changed_paths=[build], no_cluster=True, acquire_lock=False)
        assert normalized(published(tmp_path)) == baseline
    compare_clean(tmp_path)


def test_req_qml009_ac03_actual_app_only_extract_cli_keeps_corpus_boundary(tmp_path):
    """The reported CLI shape accepts the pair without reading a parent descriptor."""
    app = tmp_path / "app"
    app.mkdir()
    project(app)
    (tmp_path / "CMakeLists.txt").write_bytes(b"qt_add_resources(${unsupported})\n")
    repository = Path(__file__).resolve().parents[1]
    env = dict(os.environ, PYTHONPATH=str(repository), PYTHONIOENCODING="utf-8", GRAPHIFY_NO_TIPS="1")
    completed = subprocess.run(
        [sys.executable, "-m", "graphify", "extract", "app", "--code-only", "--no-cluster", "--max-workers", "1"],
        cwd=tmp_path, env=env, capture_output=True, text=True, encoding="utf-8", timeout=120,
    )
    assert completed.returncode == 0, (completed.stdout + completed.stderr)[-4000:]
    graph = published(app)
    assert qrc_targets(graph) == {"icons.qrc"}
    data = json.loads((app / "graphify-out/graph.json").read_text(encoding="utf-8"))
    assert all(not node.get("source_file", "").startswith("../") for node in data["nodes"])
    assert not (tmp_path / "graphify-out").exists()
