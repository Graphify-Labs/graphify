"""Real normal-edit and no-change Qt/QML parity across production entry points."""
from __future__ import annotations

from collections import Counter
import json

import pytest

import graphify.__main__ as entrypoint
import graphify.extract as extraction
from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extractors.qml_facts import qml_metadata
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.paths import load_node_link_graph
from graphify.watch import _rebuild_code


def project(root):
    files = {
        "Main.qml": 'import Public.Tools 1.0\nService { property int adjustment: 1; '
                    'property int displayed: status + adjustment; function refresh() { fetch() } }\n',
        "backend.h": 'class Backend : public QObject { Q_OBJECT QML_NAMED_ELEMENT(Service) '
                     'Q_PROPERTY(int status READ status) public: int status() { return 1; } '
                     'Q_INVOKABLE int fetch() { return 2; } };\n',
        "loader.cpp": 'void load() { QQmlApplicationEngine engine; '
                      'engine.load(QUrl("qrc:/ui/Main.qml")); }\n',
        "CMakeLists.txt": 'qt_add_qml_module(app URI Public.Tools VERSION 1.0 '
                         'QML_FILES Main.qml SOURCES backend.h loader.cpp)\n',
        "resources.qrc": '<RCC><qresource prefix="/ui"><file alias="Main.qml">'
                         'Main.qml</file></qresource></RCC>',
        "keep.py": 'def helper():\n    return 7\n\ndef retained():\n    return helper()\n',
    }
    for name, source in files.items():
        (root / name).write_text(source, encoding="utf-8", newline="")
    return root / "Main.qml"


def published(root):
    return load_node_link_graph(json.loads((root / "graphify-out/graph.json").read_text(encoding="utf-8")))


def semantic(data):
    # The builder adds norm_label and numeric confidence_score to raw no-cluster
    # output. They duplicate label/confidence; source metadata is never dropped.
    return {key: value for key, value in data.items()
            if not key.startswith("_") and key not in {"community", "id", "norm_label", "confidence_score"}}


def normalized(graph):
    nodes = {identity: json.dumps(semantic(data), sort_keys=True, ensure_ascii=False)
             for identity, data in graph.nodes(data=True)}
    edges = Counter((*endpoints(graph, source, target, data),
                     json.dumps(semantic(data), sort_keys=True, ensure_ascii=False))
                    for source, target, data in graph.edges(data=True))
    return nodes, edges


def endpoints(graph, source, target, data):
    if graph.is_directed() or qml_metadata(data) or qt_metadata(data):
        return data.get("_src", source), data.get("_tgt", target)
    # Untyped baseline undirected edges have no logical-direction reload promise.
    # Qt/QML facts above always retain exact source direction and metadata.
    return tuple(sorted((source, target)))


def unrelated(graph):
    nodes, edges = normalized(graph)
    identities = {identity for identity, data in graph.nodes(data=True) if data.get("source_file") == "keep.py"}
    return ({identity: nodes[identity] for identity in identities},
            Counter({edge: count for edge, count in edges.items()
                     if edge[0] in identities and edge[1] in identities}))


def clean(root, cache):
    paths = extraction.collect_files(root, root=root)
    result = extraction.extract(paths, root=root, cache_root=cache, parallel=False)
    assert not result["failed_sources"] and not result["qml_failures"]
    graph = build_from_json(result, root=root)
    output = root / "graphify-out/clean-comparison.json"
    assert to_json(graph, {}, str(output), force=True)
    return load_node_link_graph(json.loads(output.read_text(encoding="utf-8")))


def manual_update(root, monkeypatch):
    # Suppress only unrelated installed-skill maintenance. The actual CLI,
    # locking, extraction, resolution, persistence and update driver all run.
    monkeypatch.setattr(entrypoint, "_check_skill_version", lambda *_: None)
    monkeypatch.setattr(entrypoint, "_refresh_stale_skills", lambda: None)
    monkeypatch.setattr(entrypoint.sys, "argv", ["graphify", "update", str(root), "--no-cluster"])
    entrypoint.main()


def run(root, monkeypatch, operation, changes=None):
    if operation == "manual":
        manual_update(root, monkeypatch)
    else:
        assert _rebuild_code(root, changed_paths=changes, no_cluster=True)
    return published(root)


def named_declarations(graph):
    return {(md["kind"], md["raw_name"]): identity
            for identity, data in graph.nodes(data=True)
            if data.get("source_file") == "Main.qml" and (md := qml_metadata(data)).get("kind")
            in {"component", "property", "function"}}


def assert_native_fixture(graph):
    native_calls = [data for _, _, data in graph.edges(data=True)
                    if data.get("context") == "qml_js_call" and qt_metadata(data).get("native_endpoint")]
    assert len(native_calls) == 1
    proof = qt_metadata(native_calls[0])["native_endpoint"]
    assert graph.nodes[proof["canonical_target_id"]]["source_file"] == "backend.h"
    assert any(qml_metadata(graph.nodes[item]).get("kind") == "qt_module" for item in proof["evidence"])
    assert any(qt_metadata(data).get("kind") == "qml_load" and qt_metadata(data).get("status") == "resolved"
               for _, data in graph.nodes(data=True))
    assert unrelated(graph)[0] and unrelated(graph)[1]


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_qml011_ac01_real_normal_qml_edit_matches_cold_warm_manual_and_watch(tmp_path, monkeypatch, operation):
    source = project(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    cache = tmp_path / ".clean-cache"
    cold = clean(tmp_path, cache)
    warm = clean(tmp_path, cache)
    assert normalized(cold) == normalized(warm)
    initial = run(tmp_path, monkeypatch, operation)
    assert normalized(initial) == normalized(cold)
    assert_native_fixture(initial)
    declarations, untouched = named_declarations(initial), unrelated(initial)
    source.write_text(source.read_text(encoding="utf-8").replace("adjustment: 1", "adjustment: 5")
                      .replace("status + adjustment", "status * adjustment")
                      .replace("function refresh()", "property int incremented: displayed + 1; function refresh()"),
                      encoding="utf-8", newline="")
    edited = run(tmp_path, monkeypatch, operation, [source])
    assert_native_fixture(edited)
    edited_cold = clean(tmp_path, tmp_path / ".after-edit-cache")
    edited_warm = clean(tmp_path, tmp_path / ".after-edit-cache")
    assert normalized(edited) == normalized(edited_cold) == normalized(edited_warm)
    assert normalized(edited) != normalized(initial)
    assert all(named_declarations(edited)[name] == identity for name, identity in declarations.items())
    assert ("property", "incremented") in named_declarations(edited)
    assert unrelated(edited) == untouched


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_qml011_ac04_real_no_change_updates_preserve_every_fact_and_unrelated_python(tmp_path, monkeypatch, operation):
    source = project(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(tmp_path, monkeypatch, operation)
    assert_native_fixture(initial)
    accepted, declarations, untouched = normalized(initial), named_declarations(initial), unrelated(initial)
    for _ in range(2):
        # Duplicate watcher events still take the real supported full Qt refresh;
        # the manual command runs its normal production rebuild each time.
        repeated = run(tmp_path, monkeypatch, operation, [source])
        assert normalized(repeated) == accepted
        assert named_declarations(repeated) == declarations
        assert unrelated(repeated) == untouched
    assert normalized(clean(tmp_path, tmp_path / ".no-change-cache")) == accepted
    before = (tmp_path / "graphify-out/graph.json").read_bytes()
    assert normalized(run(tmp_path, monkeypatch, operation, [])) == accepted
    assert (tmp_path / "graphify-out/graph.json").read_bytes() == before


def access_facts(graph):
    return {identity: qt_metadata(data) for identity, data in graph.nodes(data=True)
            if qt_metadata(data).get("kind") == "qml_access"}


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_qml017_ac04_qml_member_edit_refreshes_unchanged_reverse_cpp_access(tmp_path, monkeypatch, operation):
    source = project(tmp_path)
    source.write_text('import Public.Tools 1.0\nService { property string title: "hello"; '
        'function refresh() { fetch() } property int observed: backend.status; '
        'property QtObject child: QtObject { objectName: "details"; property int count: 1 } }\n', encoding="utf-8")
    access = tmp_path / "access.cpp"
    access.write_text('void reverse(Backend *backend) { QQmlApplicationEngine engine; '
        'engine.rootContext()->setContextProperty("backend", backend); engine.load(QUrl("qrc:/ui/Main.qml")); '
        'auto root = engine.rootObjects().first(); root->property("title"); root->property("acquired"); '
        'QMetaObject::invokeMethod(root, "refresh"); QMetaObject::invokeMethod(root, "future"); '
        'auto child = root->findChild<QObject*>("details"); child->property("count"); '
        'auto replacement = root->findChild<QObject*>("renamed"); replacement->property("count"); }\n',
        encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    original_cpp = access.read_bytes()
    initial = run(tmp_path, monkeypatch, operation)
    before = access_facts(initial)
    assert len(before) == 8
    assert sum(md["status"] == "resolved" for md in before.values()) == 4
    assert any(qt_metadata(data).get("kind") == "context_access" for _, data in initial.nodes(data=True))
    source.write_text(source.read_text(encoding="utf-8").replace('title:', 'renamedTitle:')
        .replace('function refresh()', 'function updatedRefresh()').replace('"details"', '"renamed"')
        .replace('property int observed:', 'property var backend; property int acquired: 2; function future() {} property int observed:'),
        encoding="utf-8")
    edited = run(tmp_path, monkeypatch, operation, [source])
    after = access_facts(edited)
    assert set(after) == set(before) and access.read_bytes() == original_cpp
    lost = {identity for identity, md in before.items() if md["status"] == "resolved" and after[identity]["status"] != "resolved"}
    gained = {identity for identity, md in before.items() if md["status"] != "resolved" and after[identity]["status"] == "resolved"}
    assert len(lost) == 4 and len(gained) == 4
    def selector(md):
        return md["operation"], md["lookup_name"], md["receiver_reference"]
    assert {selector(before[identity]) for identity in lost} == {
        ("property", "title", "root"), ("invokeMethod", "refresh", "root"),
        ("findChild", "details", "root"), ("property", "count", "child")}
    assert {selector(after[identity]) for identity in gained} == {
        ("property", "acquired", "root"), ("invokeMethod", "future", "root"),
        ("findChild", "renamed", "root"), ("property", "count", "replacement")}
    assert all(after[identity]["span"] == before[identity]["span"] for identity in before)
    for identity in gained:
        target = after[identity]["target_id"]
        assert edited.nodes[target]["source_file"] == "Main.qml"
        assert any(data.get("_src", source_id) == identity and data.get("_tgt", target_id) == target
                   for source_id, target_id, data in edited.edges(data=True))
    assert not any(qt_metadata(data).get("kind") == "context_access" for _, data in edited.nodes(data=True))
    for identity in lost:
        assert not after[identity].get("target_id")
        assert not any(data.get("_src", source_id) == identity and data.get("relation") != "contains"
                       for source_id, _, data in edited.edges(data=True))
    assert normalized(edited) == normalized(clean(tmp_path, tmp_path / ".reverse-cold"))
    assert normalized(edited) == normalized(clean(tmp_path, tmp_path / ".reverse-cold"))
    assert unrelated(edited) == unrelated(initial)
