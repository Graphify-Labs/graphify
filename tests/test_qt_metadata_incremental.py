"""Real QML-011 provider-only updates must equal accepted-corpus clean rebuilds."""
import json

import pytest

import graphify.extract as ex
from graphify.build import build_from_json
from graphify.extractors.qml_facts import qml_metadata
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.paths import load_node_link_graph
from graphify.watch import _rebuild_code


def project(root):
    files = {
        "Main.qml": 'import Public.Tools 1.0\nService { property int displayed: status }\n',
        "Other.qml": 'Item { property int other: 2 }\n',
        "backend.h": '#include <QObject>\nclass Backend : public QObject { Q_OBJECT '
                     'QML_NAMED_ELEMENT(Service) Q_PROPERTY(int status READ status) '
                     'public: int status() const { return 1; } };\n',
        "loader.cpp": '#include <QQmlApplicationEngine>\nvoid load() { '
                      'QQmlApplicationEngine engine; engine.load(QUrl("qrc:/ui/Main.qml")); }\n',
        "CMakeLists.txt": 'qt_add_qml_module(app URI Public.Tools VERSION 1.0 '
                         'RESOURCE_PREFIX /ui QML_FILES Main.qml Other.qml SOURCES backend.h loader.cpp)\n',
        "resources.qrc": '<RCC><qresource prefix="/ui"><file alias="Main.qml">Main.qml</file></qresource></RCC>',
    }
    for name, source in files.items():
        (root / name).write_bytes(source.encode())
    return root / "CMakeLists.txt", root / "backend.h", root / "resources.qrc"


def normalized(graph):
    nodes = {nid: (data.get("source_file"), qml_metadata(data), qt_metadata(data))
             for nid, data in graph.nodes(data=True)
             if qml_metadata(data) or qt_metadata(data)}
    edges = {(data.get("_src", source), data.get("_tgt", target), data.get("relation"),
              data.get("context"), data.get("confidence"),
              json.dumps(qml_metadata(data), sort_keys=True), json.dumps(qt_metadata(data), sort_keys=True))
             for source, target, data in graph.edges(data=True)
             if qml_metadata(data) or qt_metadata(data)}
    return nodes, edges


def published(root):
    return load_node_link_graph(json.loads((root / "graphify-out/graph.json").read_text(encoding="utf-8")))


def compare_clean(root):
    paths = ex.collect_files(root, root=root)
    fresh = ex.extract(paths, root=root, cache_root=root / "clean-cache", parallel=False)
    assert not fresh.get("qml_failures")
    assert normalized(published(root)) == normalized(build_from_json(fresh, root=root))


def test_native_cpp_provider_only_edit_refreshes_unchanged_qml_and_warm_overlay(tmp_path, monkeypatch):
    _, header, _ = project(tmp_path)
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    initial = published(tmp_path)
    # Native role views are read-only adapters; canonical C++ nodes are untouched.
    native_reads = [(source, target, data) for source, target, data in initial.edges(data=True)
                    if data.get("context") == "qml_binding_read" and qt_metadata(data).get("native_endpoint")]
    assert len(native_reads) == 1
    source, target, data = native_reads[0]
    proof = qt_metadata(data)["native_endpoint"]
    assert proof["canonical_target_id"] == data.get("_tgt", target)
    assert proof["member_fact_id"] == proof["canonical_target_id"]
    assert qt_metadata(initial.nodes[proof["member_fact_id"]])["raw_name"] == "status"
    assert initial.nodes[proof["class_id"]]["source_file"] == "backend.h"
    assert qt_metadata(initial.nodes[proof["provider_id"]])["raw_name"] == "Service"
    assert any(qml_metadata(initial.nodes[item]).get("kind") == "qt_module" for item in proof["evidence"])
    assert qml_metadata(initial.nodes[data.get("_src", source)])["status"] == "resolved"
    header.write_bytes(header.read_bytes().replace(b"Service", b"RenamedService"))
    observed, real_extract = [], ex.extract
    def observe(paths, **kwargs):
        observed.extend(paths)
        return real_extract(paths, **kwargs)
    monkeypatch.setattr(ex, "extract", observe)
    assert _rebuild_code(tmp_path, changed_paths=[header], no_cluster=True, acquire_lock=False)
    assert tmp_path / "Main.qml" in observed
    compare_clean(tmp_path)
    warm = normalized(published(tmp_path))
    assert _rebuild_code(tmp_path, changed_paths=[header], no_cluster=True, acquire_lock=False)
    assert normalized(published(tmp_path)) == warm


@pytest.mark.parametrize("mutation", ["uri", "delete", "rename", "duplicate", "ignore"])
def test_build_provider_only_mutations_equal_clean_accepted_corpus(tmp_path, mutation):
    build, _, _ = project(tmp_path)
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    assert any(qml_metadata(node).get("kind") == "qt_module" for _, node in published(tmp_path).nodes(data=True))
    changed = [build]
    if mutation == "uri":
        build.write_bytes(build.read_bytes().replace(b"Public.Tools", b"Other.Tools"))
    elif mutation == "delete":
        build.unlink()
    elif mutation == "rename":
        renamed = tmp_path / "renamed.cmake"
        build.rename(renamed)
        changed.append(renamed)
    elif mutation == "duplicate":
        duplicate = tmp_path / "duplicate.cmake"
        duplicate.write_bytes(build.read_bytes().replace(b"app ", b"other "))
        changed.append(duplicate)
    elif mutation == "ignore":
        ignore = tmp_path / ".graphifyignore"
        ignore.write_bytes(b"CMakeLists.txt\n")
        changed = [ignore]
    assert _rebuild_code(tmp_path, changed_paths=changed, no_cluster=True, acquire_lock=False)
    compare_clean(tmp_path)


@pytest.mark.parametrize("mutation", ["retarget", "delete", "rename", "ignore"])
def test_resource_only_mutations_refresh_unchanged_cpp_loaders(tmp_path, mutation, monkeypatch):
    _, _, qrc = project(tmp_path)
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    assert any(qml_metadata(node).get("kind") == "resource_alias" for _, node in published(tmp_path).nodes(data=True))
    changed = [qrc]
    if mutation == "retarget":
        qrc.write_bytes(qrc.read_bytes().replace(b">Main.qml<", b">Other.qml<"))
    elif mutation == "delete":
        qrc.unlink()
    elif mutation == "rename":
        renamed = tmp_path / "renamed.qrc"
        qrc.rename(renamed)
        changed.append(renamed)
    elif mutation == "ignore":
        ignore = tmp_path / ".graphifyignore"
        ignore.write_bytes(b"resources.qrc\n")
        changed = [ignore]
    observed, real_extract = [], ex.extract
    def observe(paths, **kwargs):
        observed.extend(paths)
        return real_extract(paths, **kwargs)
    monkeypatch.setattr(ex, "extract", observe)
    assert _rebuild_code(tmp_path, changed_paths=changed, no_cluster=True, acquire_lock=False)
    assert tmp_path / "loader.cpp" in observed
    compare_clean(tmp_path)


@pytest.mark.parametrize("name,invalid", [
    ("CMakeLists.txt", b"if(WIN32)\nqt_add_qml_module(app URI Hidden VERSION 1.0)\nendif()"),
    ("resources.qrc", b'<!DOCTYPE RCC [<!ENTITY x SYSTEM "file:///host/private">]><RCC/>'),
])
def test_failed_metadata_update_preserves_prior_graph_manifest_and_report(tmp_path, name, invalid):
    project(tmp_path)
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    out = tmp_path / "graphify-out"
    prior = {p.name: p.read_bytes() for p in out.iterdir() if p.is_file() and p.name in {
        "graph.json", "manifest.json", "report.md"}}
    path = tmp_path / name
    path.write_bytes(invalid)
    assert not _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False, force=True)
    assert {name: (out / name).read_bytes() for name in prior} == prior
