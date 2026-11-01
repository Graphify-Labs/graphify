"""REQ-QML-018-AC01/AC06: accepted qmake metadata through production consumers."""
from __future__ import annotations

import json
import stat

import pytest

import graphify.extract as extraction
from graphify.build import build_from_json
from graphify.cache import cache_dir
from graphify.export import to_json
from graphify.extractors.qml_facts import qml_metadata
from graphify.extractors.qml_qmake import extract_qmake
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.paths import load_node_link_graph
from graphify.qt_project_index import QtProjectIndex
from graphify.watch import _rebuild_code
from tests.test_qt_final_incremental_parity import clean, normalized, run, unrelated


BUILD = """QT += qml quick
CONFIG += c++17
win32: LIBS += $$PWD/optional.lib
QML_IMPORT_NAME = Public.Tools
QML_IMPORT_VERSION = 1.0
HEADERS += $$PWD/backend.hpp
QML_FILES += $$PWD/Main.qml
QML_IMPORT_PATH += $$PWD/imports/Public/Hidden
QMLPATHS += $$PWD/imports
"""
HEADER = """class Backend : public QObject { Q_OBJECT QML_NAMED_ELEMENT(Service)
 public: Q_INVOKABLE int fetch() { return 2; }
};
"""
QML = "import Public.Tools 1.0\nService { property int result: fetch() }\n"
PRODUCTS = ("graph.json", "manifest.json", ".qt_analysis.json", ".graphify_root")


def corpus(root):
    """A nested public application owns membership; hint-only module stays separate."""
    sources = {"app/tools.pro": BUILD, "app/backend.hpp": HEADER, "app/Main.qml": QML,
               "app/imports/Public/Hidden/qmldir": "module Public.Hidden\nHidden 1.0 Hidden.qml\n",
               "app/imports/Public/Hidden/Hidden.qml": "import QtQml\nQtObject {}\n",
               "app/Consumer.qml": "import Public.Hidden 1.0\nHidden {}\n",
               "keep.py": "def helper(): return 7\n\ndef retained(): return helper()\n"}
    paths = []
    for name, text in sources.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode())
        paths.append(path)
    return paths


def source_facts(graph, kind):
    return {identity: qml_metadata(node) for identity, node in graph.nodes(data=True)
            if qml_metadata(node).get("kind") == kind}


def test_req_qml018_ac01_direct_facade_project_index_and_reload_preserve_pwd_roles(tmp_path):
    """Membership reaches accepted endpoints; tooling/build hints supply no lookup root."""
    paths = corpus(tmp_path)
    direct = extract_qmake(tmp_path / "app/tools.pro", root=tmp_path)
    result = extraction.extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    assert not result["qml_failures"] and not result["failed_sources"]
    qmake = {node["id"]: qml_metadata(node) for node in result["nodes"]
             if node.get("source_file") == "app/tools.pro"}
    direct_facts = {node["id"]: qml_metadata(node) for node in direct["nodes"]}
    assert {identity: qmake[identity] for identity in direct_facts} == direct_facts
    index = QtProjectIndex(result["nodes"], result["edges"], root=tmp_path)
    assert index.module_context("app/backend.hpp").status == "resolved"
    assert index.resolve_component("Public.Tools", "Main").status == "resolved"
    assert index.resolve_component("Public.Hidden", "Hidden").status == "unavailable"
    explicit = QtProjectIndex(result["nodes"], result["edges"], root=tmp_path,
                              import_roots=("app/imports",))
    assert explicit.resolve_component("Public.Hidden", "Hidden").status == "resolved"
    native = [edge for edge in result["edges"] if qt_metadata(edge).get("native_endpoint")]
    assert len([edge for edge in native if edge["relation"] == "calls"]) == 1
    graph = build_from_json(result, root=tmp_path)
    output = tmp_path / "accepted.json"
    assert to_json(graph, {}, str(output), force=True)
    restored = load_node_link_graph(json.loads(output.read_text(encoding="utf-8")))
    assert source_facts(graph, "qt_import_path") == source_facts(restored, "qt_import_path")
    for md in source_facts(restored, "qt_import_path").values():
        assert md["visibility"] in {"tooling", "build"}
        assert md["path_origin"] == "current_file_pwd"
    from graphify.serve import _query_graph_text
    answer = _query_graph_text(restored, "app/Main.qml", token_budget=8000)
    assert "app/Main.qml" in answer and "app/tools.pro" in answer and "references" in answer


def test_req_qml018_ac01_build_pwd_paths_do_not_admit_disk_only_sources(tmp_path):
    """A correct literal path cannot enlarge the explicitly accepted corpus."""
    paths = corpus(tmp_path)
    accepted = [path for path in paths if path.name != "backend.hpp"]
    result = extraction.extract(accepted, root=tmp_path, cache_root=tmp_path, parallel=False)
    assert not result["qml_failures"]
    assert not any(qt_metadata(edge).get("native_endpoint") for edge in result["edges"])
    index = QtProjectIndex(result["nodes"], result["edges"], root=tmp_path)
    assert index.module_context("app/backend.hpp").status == "unavailable"


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml018_ac01_metadata_only_pwd_edit_removal_matches_clean_updates(tmp_path, monkeypatch, operation):
    """Only qmake bytes change; old membership and native edges retire faithfully."""
    corpus(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    cold = clean(tmp_path, tmp_path / ".cold")
    assert normalized(clean(tmp_path, tmp_path / ".cold")) == normalized(cold)
    initial = run(tmp_path, monkeypatch, operation)
    assert normalized(initial) == normalized(cold)
    prior = unrelated(initial)
    path = tmp_path / "app/tools.pro"
    path.write_bytes(BUILD.replace("QML_IMPORT_VERSION = 1.0", "QML_IMPORT_VERSION = 2.0").encode())
    edited = run(tmp_path, monkeypatch, operation, [path])
    assert unrelated(edited) == prior
    assert normalized(edited) == normalized(clean(tmp_path, tmp_path / ".edited"))
    assert not any(qt_metadata(data).get("native_endpoint") for _, _, data in edited.edges(data=True))
    path.write_bytes(BUILD.replace("HEADERS += $$PWD/backend.hpp\n", "").encode())
    removed = run(tmp_path, monkeypatch, operation, [path])
    assert unrelated(removed) == prior
    assert normalized(removed) == normalized(clean(tmp_path, tmp_path / ".removed"))
    assert not any(qt_metadata(data).get("native_endpoint") for _, _, data in removed.edges(data=True))
    path.write_bytes(BUILD.encode())
    recovered = run(tmp_path, monkeypatch, operation, [path])
    assert normalized(recovered) == normalized(initial)
    assert normalized(run(tmp_path, monkeypatch, operation, [])) == normalized(initial)


@pytest.mark.parametrize("operation", ["manual", "watch"])
@pytest.mark.parametrize("mutation", [
    "unix: QML_FILES += $$PWD/Hidden.qml\n", "include(unaccepted.pri)\n",
    "QML_FILES += $$PWD/../../Outside.qml\n", "QMLPATHS += $$factory()\n",
])
def test_req_qml018_ac06_rejected_metadata_preserves_products_and_existing_cache(tmp_path, monkeypatch, capsys, operation, mutation):
    """Actual metadata rejection leaves accepted disk products and cache entries intact."""
    corpus(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(tmp_path, monkeypatch, operation)
    output = tmp_path / "graphify-out"
    prior = {name: (output / name).read_bytes() for name in PRODUCTS}
    cache = {path: path.read_bytes() for path in cache_dir(tmp_path).rglob("*") if path.is_file()}
    assert cache
    path = tmp_path / "app/tools.pro"
    path.write_bytes((BUILD + mutation).encode())
    if operation == "manual":
        with pytest.raises(SystemExit) as failure:
            run(tmp_path, monkeypatch, operation, [path])
        assert failure.value.code == 1
    else:
        assert not _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True)
    assert prior == {name: (output / name).read_bytes() for name in PRODUCTS}
    assert all(path.exists() and path.read_bytes() == data for path, data in cache.items())
    assert "QML_GRAPH_PRESERVED" in capsys.readouterr().out
    assert extract_qmake(path, root=tmp_path)["diagnostics"][0]["code"] == "QML_PROJECT_UNSUPPORTED"
    path.write_bytes(BUILD.encode())
    repaired = run(tmp_path, monkeypatch, operation, [path])
    assert normalized(repaired) == normalized(initial)
    assert normalized(run(tmp_path, monkeypatch, operation, [])) == normalized(initial)


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml018_ac06_readonly_publication_after_metadata_edit_retains_and_retries(tmp_path, monkeypatch, operation):
    """A real read-only graph destination rejects changed metadata publication."""
    import os
    if os.name != "nt":
        pytest.skip("Actual Windows read-only destination attribute")
    corpus(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(tmp_path, monkeypatch, operation)
    output = tmp_path / "graphify-out"
    prior = {name: (output / name).read_bytes() for name in PRODUCTS}
    path = tmp_path / "app/tools.pro"
    path.write_bytes(BUILD.replace("QML_IMPORT_VERSION = 1.0", "QML_IMPORT_VERSION = 2.0").encode())
    target = output / "graph.json"
    target.chmod(stat.S_IREAD)
    try:
        if operation == "manual":
            with pytest.raises(SystemExit) as failure:
                run(tmp_path, monkeypatch, operation, [path])
            assert failure.value.code == 1
        else:
            assert not _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True)
        assert prior == {name: (output / name).read_bytes() for name in PRODUCTS}
    finally:
        target.chmod(stat.S_IWRITE)
    repaired = run(tmp_path, monkeypatch, operation, [path])
    assert normalized(repaired) != normalized(initial)
    assert normalized(repaired) == normalized(clean(tmp_path, tmp_path / ".readonly-retry"))
