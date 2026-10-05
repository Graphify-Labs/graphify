"""REQ-QML-017-AC04: engine identity through real refresh, failure and consumers."""
from __future__ import annotations

import json

import pytest

from graphify.affected import affected_nodes, load_graph
from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.paths import load_node_link_graph
from tests.qt_consumer_helpers import cli as consumer_cli
from tests.test_qt_final_incremental_parity import clean, normalized, run, unrelated

HEADER = '''class Backend : public QObject { Q_OBJECT Q_PROPERTY(int count READ count)
public: int count() { return 1; } };
class OtherBackend : public QObject { Q_OBJECT Q_PROPERTY(int count READ count)
public: int count() { return 2; } };
'''


def loader(state="same", target="Main.qml"):
    """Only lexical source placement changes; URLs refer to accepted resources."""
    expose = 'engine.rootContext()->setContextProperty("backend", backend);'
    load = f'engine.load(QUrl("qrc:/ui/{target}"));'
    if state == "disjoint":
        body = f'{{ QQmlApplicationEngine engine; {expose} }} {{ QQmlApplicationEngine engine; {load} }}'
    elif state == "nested":
        body = ('QQmlApplicationEngine engine; ' + expose +
                ' { QQmlApplicationEngine engine; engine.rootContext()->setContextProperty("backend", other); '
                'engine.load(QUrl("qrc:/ui/Main.qml")); } engine.load(QUrl("qrc:/ui/Alt.qml"));')
    else:
        body = 'QQmlApplicationEngine engine; ' + (expose if state != "removed" else "") + load
    return '#include "backend.h"\nvoid use(Backend *backend, OtherBackend *other) { ' + body + ' }\n'


def fixture(root, state="same"):
    sources = {
        "backend.h": HEADER,
        "loader.cpp": loader(state),
        "Main.qml": 'import QtQml\nQtObject { property int observed: backend.count }\n',
        "Alt.qml": 'import QtQml\nQtObject { property int alternative: backend.count }\n',
        "CMakeLists.txt": 'qt_add_qml_module(app URI Public.Tools VERSION 1.0 QML_FILES Main.qml Alt.qml SOURCES backend.h loader.cpp)\n',
        "ui.qrc": '<RCC><qresource prefix="/ui"><file alias="Main.qml">Main.qml</file><file alias="Alt.qml">Alt.qml</file></qresource></RCC>',
        "keep.py": 'def helper(): return 7\n\ndef retained(): return helper()\n',
    }
    for name, source in sources.items():
        (root / name).write_bytes(source.encode())
    return root / "loader.cpp"


def facts(graph, kind):
    return {identity: qt_metadata(node) for identity, node in graph.nodes(data=True)
            if qt_metadata(node).get("kind") == kind}


def assert_binding(graph, filename, provider="Backend"):
    """A resolved provider must retain its exact engine and class evidence."""
    bindings = [md for md in facts(graph, "context_binding").values()
                if graph.nodes[md["component_target_id"]]["source_file"] == filename]
    assert len(bindings) == 1 and bindings[0]["status"] == "resolved"
    assert bindings[0]["provider_class_name"] == provider
    assert len(bindings[0]["engine_declaration_id"]) == len(bindings[0]["provider_declaration_id"]) == 64
    accesses = [(identity, md) for identity, md in facts(graph, "context_access").items()
                if graph.nodes[identity]["source_file"] == filename]
    assert len(accesses) == 1
    assert graph.has_edge(accesses[0][0], accesses[0][1]["target_id"])


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml017_ac04_engine_scope_changes_remove_stale_provider_links(tmp_path, monkeypatch, operation):
    """Cold/warm and real manual/watch agree across scope, provider and load edits."""
    source = fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    cold = clean(tmp_path, tmp_path / ".cold-cache")
    assert normalized(clean(tmp_path, tmp_path / ".cold-cache")) == normalized(cold)
    initial = run(tmp_path, monkeypatch, operation)
    assert normalized(initial) == normalized(cold)
    assert_binding(initial, "Main.qml")
    retired = set(facts(initial, "context_access")) | set(facts(initial, "context_binding"))
    kept = unrelated(initial)

    source.write_bytes(loader("disjoint").encode())
    rejected = run(tmp_path, monkeypatch, operation, [source])
    assert not facts(rejected, "context_binding") and not facts(rejected, "context_access")
    assert not retired.intersection(rejected)
    assert normalized(rejected) == normalized(clean(tmp_path, tmp_path / ".disjoint-cache"))

    # Nested shadow engines retain their own exact provider and document;
    # neither the spelling nor source ordering may select the other provider.
    source.write_bytes(loader("nested").encode())
    nested = run(tmp_path, monkeypatch, operation, [source])
    assert_binding(nested, "Main.qml", "OtherBackend")
    assert_binding(nested, "Alt.qml", "Backend")
    assert normalized(nested) == normalized(clean(tmp_path, tmp_path / ".nested-cache"))

    source.write_bytes(loader("removed").encode())
    removed = run(tmp_path, monkeypatch, operation, [source])
    assert not facts(removed, "context_binding") and not facts(removed, "context_access")
    assert normalized(removed) == normalized(clean(tmp_path, tmp_path / ".removed-cache"))
    source.write_bytes(loader("same", "Alt.qml").encode())
    moved = run(tmp_path, monkeypatch, operation, [source])
    assert_binding(moved, "Alt.qml")
    assert not [identity for identity in facts(moved, "context_access")
                if moved.nodes[identity]["source_file"] == "Main.qml"]
    assert normalized(moved) == normalized(clean(tmp_path, tmp_path / ".moved-cache"))

    # Resource-only changes must invalidate the unchanged C++ loader/provider,
    # without preserving the previous component binding from graph context.
    resource = tmp_path / "ui.qrc"
    valid_resource = resource.read_bytes()
    resource.write_bytes(valid_resource.replace(b'alias="Alt.qml"', b'alias="changed.qml"'))
    missing = run(tmp_path, monkeypatch, operation, [resource])
    assert not facts(missing, "context_binding") and not facts(missing, "context_access")
    assert normalized(missing) == normalized(clean(tmp_path, tmp_path / ".metadata-cache"))
    resource.write_bytes(valid_resource)
    assert normalized(run(tmp_path, monkeypatch, operation, [resource])) == normalized(moved)

    # An unchanged C++ exposure cannot override a newly declared QML property.
    qml = tmp_path / "Alt.qml"
    qml.write_bytes(qml.read_bytes().replace(b"property int alternative", b"property var backend; property int alternative"))
    shadowed = run(tmp_path, monkeypatch, operation, [qml])
    assert len(facts(shadowed, "context_binding")) == 1 and not facts(shadowed, "context_access")
    assert normalized(shadowed) == normalized(clean(tmp_path, tmp_path / ".qml-shadow-cache"))
    assert unrelated(shadowed) == kept
    before = (tmp_path / "graphify-out/graph.json").read_bytes()
    assert normalized(run(tmp_path, monkeypatch, operation, [])) == normalized(shadowed)
    assert (tmp_path / "graphify-out/graph.json").read_bytes() == before


@pytest.mark.parametrize("operation", ["manual", "force", "watch"])
def test_req_qml017_ac04_malformed_identity_source_retains_products_and_retries(tmp_path, monkeypatch, operation):
    """Actual parser rejection preserves all durable products, including forced CLI."""
    source = fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    mode = "manual" if operation == "force" else operation
    initial = run(tmp_path, monkeypatch, mode)
    assert_binding(initial, "Main.qml")
    output = tmp_path / "graphify-out"
    products = ("graph.json", "manifest.json", ".qt_analysis.json", ".graphify_root")
    before = {name: (output / name).read_bytes() for name in products}
    valid = source.read_bytes()
    source.write_bytes(valid + b"\nvoid broken({")
    if operation == "watch":
        from graphify.watch import _rebuild_code
        assert not _rebuild_code(tmp_path, changed_paths=[source], no_cluster=True)
    else:
        with pytest.raises(SystemExit) as rejected:
            if operation == "force":
                from tests.test_qt_cpp_upgrade_invalidation import cli
                cli(tmp_path, monkeypatch, "update", force=True)
            else:
                run(tmp_path, monkeypatch, mode, [source])
        assert rejected.value.code == 1
    assert before == {name: (output / name).read_bytes() for name in products}
    source.write_bytes(valid)
    repaired = run(tmp_path, monkeypatch, mode, [source])
    assert normalized(repaired) == normalized(initial)
    assert_binding(repaired, "Main.qml")
    assert normalized(run(tmp_path, monkeypatch, mode, [])) == normalized(initial)


def test_req_qml017_ac04_directed_query_affected_and_reload_keep_scoped_provider(tmp_path, monkeypatch, capsys):
    """The real directed consumer graph distinguishes the two nested providers."""
    fixture(tmp_path, "nested")
    paths = [tmp_path / name for name in ("backend.h", "loader.cpp", "Main.qml", "Alt.qml", "CMakeLists.txt", "ui.qrc", "keep.py")]
    from graphify.extract import extract
    result = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    assert not result["failed_sources"] and not result["qml_failures"]
    graph = build_from_json(result, root=tmp_path, directed=True)
    path = tmp_path / "directed.json"
    assert to_json(graph, {}, str(path), force=True)
    loaded = load_node_link_graph(json.loads(path.read_text(encoding="utf-8")))
    assert_binding(loaded, "Main.qml", "OtherBackend")
    assert_binding(loaded, "Alt.qml", "Backend")
    access, metadata = next((identity, md) for identity, md in facts(loaded, "context_access").items()
                            if loaded.nodes[identity]["source_file"] == "Main.qml")
    assert loaded.has_edge(access, metadata["target_id"])
    assert not loaded.has_edge(metadata["target_id"], access)
    text = consumer_cli(monkeypatch, capsys, path, "query", access)
    assert "Qt context access: backend.count" in text and "Main.qml" in text
    assert "Main.qml" in consumer_cli(monkeypatch, capsys, path, "explain", access)
    hits = {hit.node_id for hit in affected_nodes(load_graph(path), metadata["target_id"], relations=["uses"], depth=1)}
    assert access in hits
    assert not {identity for identity in facts(loaded, "context_access")
                if loaded.nodes[identity]["source_file"] == "Alt.qml"}.intersection(hits)
