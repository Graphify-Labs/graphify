"""REQ-QML-017-AC01/AC03: component loaders retain exact engine providers."""
from __future__ import annotations

import json

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.paths import load_node_link_graph
from tests.qt_analysis_helpers import analysis, sites
from tests.test_qt_loader_updates import assert_context

BACKEND = '''class Backend : public QObject { Q_OBJECT Q_PROPERTY(int count READ count)
public: int count() { return 1; } };
'''
LOAD = 'component.loadUrl(QUrl("qrc:/ui/Main.qml")); auto root = component.create();'


def published(root, source, *, bare=False, directed=False):
    """The producer, resolver, strict build guard and actual JSON writer all run."""
    result = analysis(root, {
        "backend.h": BACKEND,
        "access.cpp": '#include "backend.h"\n' + source,
        "Main.qml": 'import QtQml\nQtObject { property int value: ' + ("count" if bare else "backend.count") + ' }',
        "ui.qrc": '<RCC><qresource prefix="/ui"><file>Main.qml</file></qresource></RCC>',
        "CMakeLists.txt": 'qt_add_qml_module(app URI Public.Tools VERSION 1.0 QML_FILES Main.qml SOURCES backend.h access.cpp)\n',
    })
    graph = build_from_json(result, root=root, directed=directed)
    output = root / "proof.json"
    assert to_json(graph, {}, str(output), force=True)
    return result, load_node_link_graph(json.loads(output.read_text(encoding="utf-8")))


@pytest.mark.parametrize("engine_type", ["QQmlEngine", "QQmlApplicationEngine"])
@pytest.mark.parametrize("context_object", [False, True])
@pytest.mark.parametrize("directed", [False, True])
def test_req_qml017_ac03_component_load_url_uses_its_exact_engine_provider(tmp_path, engine_type, context_object, directed):
    """Engine-only construction associates one later URL load with its provider."""
    exposure = 'setContextObject(backend)' if context_object else 'setContextProperty("backend", backend)'
    source = f'''void use(Backend *backend) {{ {engine_type} engine;
 engine.rootContext()->{exposure}; QQmlComponent component(&engine); {LOAD} }}'''
    result, graph = published(tmp_path, source, bare=context_object, directed=directed)
    loads = sites(result, "qml_load")
    assert len(loads) == 1 and qt_metadata(loads[0])["operation"] == "loadUrl"
    loader = qt_metadata(loads[0])
    expose = qt_metadata(sites(result, "context_exposure")[0])
    binding = sites(result, "context_binding")[0]
    bound = qt_metadata(binding)
    assert loader["status"] == bound["status"] == "resolved"
    assert loader["engine_declaration_id"] == expose["engine_declaration_id"] == bound["engine_declaration_id"]
    assert len(bound["engine_declaration_id"]) == 64
    assert bound["provider_declaration_id"] == expose["provider_declaration_id"]
    assert bound["component_target_id"] == loader["target_id"]
    assert_context(graph, loads[0]["id"], loader["target_id"], "qt_cpp_qml_load")
    assert_context(graph, binding["id"], bound["component_target_id"], "qt_context_exposure")
    access = sites(result, "context_access")[0]
    target = qt_metadata(access)["target_id"]
    assert graph.nodes[target]["source_file"] == "backend.h"
    assert_context(graph, access["id"], target, "qt_context_member")
    if directed:
        assert not graph.has_edge(target, access["id"])


@pytest.mark.parametrize("body", [
    '{ QQmlEngine engine; engine.rootContext()->setContextProperty("backend", backend); } '
    '{ QQmlEngine engine; QQmlComponent component(&engine); ' + LOAD + ' }',
    'QQmlEngine engine; engine.rootContext()->setContextProperty("backend", backend); '
    '{ QQmlEngine engine; QQmlComponent component(&engine); ' + LOAD + ' }',
])
def test_req_qml017_ac03_component_engine_shadow_cannot_borrow_another_provider(tmp_path, body):
    """A valid component load must not select an exposure by engine spelling."""
    result, graph = published(tmp_path, 'void use(Backend *backend) { ' + body + ' }')
    loads = sites(result, "qml_load")
    assert len(loads) == 1 and qt_metadata(loads[0])["status"] == "resolved"
    assert not sites(result, "context_binding") and not sites(result, "context_access")
    assert not [edge for _, _, edge in graph.edges(data=True)
                if edge.get("context") in {"qt_context_exposure", "qt_context_member"}]


@pytest.mark.parametrize("body", [
    'QQmlEngine *engine = new QQmlEngine; engine->rootContext()->setContextProperty("backend", backend); '
    'engine = replacement; QQmlComponent component(engine); ' + LOAD,
    'QQmlEngine engine; engine.rootContext()->setContextProperty("backend", backend); '
    'if (enabled) { QQmlComponent component(&engine); ' + LOAD + ' }',
    'QQmlEngine engine; engine.rootContext()->setContextProperty("backend", backend); '
    'QQmlComponent component(factory()); ' + LOAD,
])
def test_req_qml017_ac03_component_engine_assignment_condition_and_factory_reject(tmp_path, body):
    """Unproved constructor engine associations publish no component/provider targets."""
    source = 'void use(Backend *backend, QQmlEngine *replacement) { ' + body + ' }'
    result, graph = published(tmp_path, source)
    assert not sites(result, "context_binding") and not sites(result, "context_access")
    assert not [md for node in sites(result, "qml_load") if (md := qt_metadata(node))["status"] == "resolved"]
    assert not [edge for _, _, edge in graph.edges(data=True)
                if edge.get("context") in {"qt_cpp_qml_load", "qt_context_exposure", "qt_context_member"}]
