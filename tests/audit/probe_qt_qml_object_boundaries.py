"""Opt-in public audit of receiver identity; expected rejection assertions stay strict.

Invoke this probe explicitly with pytest. Its name excludes normal ``test_*.py``
discovery. Synthetic sources pass through production extraction, graph assembly
and JSON reload; neither QML nor a Qt application/build hook executes.
"""
from __future__ import annotations

import json

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.paths import load_node_link_graph
from tests.qt_analysis_helpers import analysis, sites

BACKEND = '''class Backend : public QObject {
 Q_OBJECT
 Q_PROPERTY(int count READ count)
public:
 int count() { return 1; }
};
'''
QML = '''import QtQuick
Item {
 property int rootOnly: 7
 function rootAction() {}
 Item { objectName: "left"; property int localValue: 1; Item { objectName: "deep" } }
 Item { objectName: "right"; property int localValue: 2 }
}
'''


def persisted(root, sources):
    """Read only synthetic inputs and inspect the actual completed JSON output."""
    result = analysis(root, sources)
    graph = build_from_json(result, root=root)
    output = root / "proof.json"
    assert to_json(graph, {}, str(output), force=True)
    return result, load_node_link_graph(json.loads(output.read_text(encoding="utf-8")))


def access_source(root, tail):
    """The literal file URL establishes a receiver without runtime execution."""
    return f'''void use() {{
 QQuickView view;
 view.setSource(QUrl("{(root / 'Main.qml').as_uri()}"));
 auto root = view.rootObject();
 auto left = root->findChild<QObject*>("left");
 {tail}
}}'''


def target_edges(graph, site, contexts):
    """Select semantic target links by their serialized logical source direction."""
    return [(data.get("_tgt", target), data.get("relation"), data.get("context"))
            for source, target, data in graph.edges(site["id"], data=True)
            if data.get("_src", source) == site["id"] and data.get("context") in contexts]


@pytest.mark.parametrize("tail", ['left->property("rootOnly");', 'left->setProperty("rootOnly", 9);',
                                  'QMetaObject::invokeMethod(left, "rootAction");'])
def test_cpp_reflective_child_property_does_not_inherit_qml_lexical_root(tmp_path, tail):
    """REQ-QML-017-AC02/AC04: a child must not acquire its QML root's reflected API."""
    result, graph = persisted(tmp_path, {"access.cpp": access_source(tmp_path, tail), "Main.qml": QML})
    access = sites(result, "qml_access")[-1]
    span = qt_metadata(access)["span"]
    assert (tmp_path / "access.cpp").read_bytes()[span["start_byte"]:span["end_byte"]].decode() == tail[:-1]
    assert not target_edges(graph, access, {"qt_cpp_qml_property_read", "qt_cpp_qml_property_write", "qt_cpp_qml_invoke"}), (
        "The child's read/write/invoke site persisted an enclosing-root member edge")
    assert qt_metadata(access)["status"] != "resolved"


def test_cpp_findchild_does_not_search_sibling_outside_receiver_subtree(tmp_path):
    """REQ-QML-017-AC02/AC04: left has no right child; a sibling is not its target."""
    result, graph = persisted(tmp_path, {"access.cpp": access_source(tmp_path, 'left->findChild<QObject*>("right");'),
                                         "Main.qml": QML})
    access = sites(result, "qml_access")[-1]
    assert not target_edges(graph, access, {"qt_cpp_qml_find_child"}), "A sibling target edge survived build/JSON reload"
    assert qt_metadata(access)["status"] != "resolved"


def test_cpp_findchild_direct_search_cannot_select_grandchild(tmp_path):
    """REQ-QML-017-AC02/AC04: direct-child search must not choose nested deep."""
    result, graph = persisted(tmp_path, {"access.cpp": access_source(tmp_path,
                                         'root->findChild<QObject*>("deep", Qt::FindDirectChildrenOnly);'),
                                         "Main.qml": QML})
    access = sites(result, "qml_access")[-1]
    assert not target_edges(graph, access, {"qt_cpp_qml_find_child"}), "Direct-child search persisted a grandchild edge"
    assert qt_metadata(access)["status"] != "resolved"


def test_disjoint_engine_scopes_cannot_supply_context_provider(tmp_path):
    """REQ-QML-017-AC03/AC04: a destroyed engine cannot inject into a new engine."""
    source = BACKEND + f'''void use(Backend *backend) {{
 {{ QQmlApplicationEngine engine;
   engine.rootContext()->setContextProperty("backend", backend);
 }}
 QQmlApplicationEngine engine;
 engine.load(QUrl("{(tmp_path / 'Main.qml').as_uri()}"));
}}'''
    result, graph = persisted(tmp_path, {"access.cpp": source,
                                         "Main.qml": 'import QtQml\nQtObject { property int value: backend.count }'})
    joins = sites(result, "context_access")
    assert not [(node["id"], edge) for node in joins for edge in target_edges(graph, node, {"qt_context_member"})], (
        "A block-local engine's provider edge reached another engine's loaded component")
    assert not joins


def test_public_receiver_and_engine_positive_controls(tmp_path):
    """Valid own-receiver lookups and same-engine context joins remain resolvable."""
    source = access_source(tmp_path, 'left->property("localValue"); root->property("rootOnly"); root->findChild<QObject*>("right");')
    result, graph = persisted(tmp_path, {"access.cpp": source, "Main.qml": QML})
    accesses = sites(result, "qml_access")
    assert len(accesses) == 4 and all(qt_metadata(node)["status"] == "resolved" for node in accesses)
    assert all(graph.has_edge(node["id"], qt_metadata(node)["target_id"]) for node in accesses)
    folder = tmp_path / "context"
    folder.mkdir()
    source = BACKEND + f'''void use(Backend *backend) {{ QQmlApplicationEngine engine;
 engine.rootContext()->setContextProperty("backend", backend);
 engine.load(QUrl("{(folder / 'Main.qml').as_uri()}")); }}'''
    result, graph = persisted(folder, {"access.cpp": source,
                                      "Main.qml": 'import QtQml\nQtObject { property int value: backend.count }'})
    joins = sites(result, "context_access")
    assert len(joins) == 1 and graph.has_edge(joins[0]["id"], qt_metadata(joins[0])["target_id"])


def test_pending_typed_factory_provider_remains_unresolved(tmp_path):
    """REQ-QML-018-AC03 remains a planned gap; unavailable factory types are not guessed."""
    source = BACKEND + f'''class Factory {{ public: Backend *makeBackend(); }};
void use(Factory *factory) {{ QQmlApplicationEngine engine;
 engine.rootContext()->setContextProperty("backend", factory->makeBackend());
 engine.load(QUrl("{(tmp_path / 'Main.qml').as_uri()}")); }}'''
    result, _ = persisted(tmp_path, {"access.cpp": source,
                                    "Main.qml": 'import QtQml\nQtObject { property int value: backend.count }'})
    assert not sites(result, "context_binding") and not sites(result, "context_access")
    assert qt_metadata(sites(result, "context_exposure")[0])["status"] == "unavailable"
