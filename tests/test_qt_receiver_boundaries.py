"""REQ-QML-017-AC02/AC04: persisted reflection belongs to its receiving QObject."""
from __future__ import annotations

import copy
import json

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extractors.qml_facts import encode_metadata
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.paths import load_node_link_graph
from graphify.qml_resolution_types import qml_metadata
from graphify.qt_qml_access_index import QtQmlAccessIndex
from tests.qt_analysis_helpers import analysis, sites

QML = '''import QtQuick
Item {
 id: owner
 objectName: "owner"
 property int rootOnly: 7
 function rootAction() {}
 Item { id: left; objectName: "left"; property int localValue: 1;
        Item { objectName: "deep"; property int count: 2 } }
 Item { id: right; objectName: "right"; property int localValue: 2 }
}
'''
TARGET_CONTEXTS = {"qt_cpp_qml_property_read", "qt_cpp_qml_property_write", "qt_cpp_qml_invoke", "qt_cpp_qml_find_child"}


def source(root, tail):
    return f'''// original-byte Unicode evidence: café
void use() {{ QQuickView view;
 view.setSource(QUrl("{(root / 'Main.qml').as_uri()}"));
 auto root = view.rootObject(); auto left = root->findChild<QObject*>("left");
 {tail}
}}'''


def persisted(root, tail, qml=QML, *, extra=None, directed=False):
    cpp = source(root, tail).replace("\n", "\r\n")
    result = analysis(root, {"access.cpp": cpp, "Main.qml": qml, **(extra or {})})
    graph = build_from_json(result, root=root, directed=directed)
    output = root / "proof.json"
    assert to_json(graph, {}, str(output), force=True)
    payload = json.loads(output.read_text(encoding="utf-8"))
    reloaded = load_node_link_graph(payload)
    site = sites(result, "qml_access")[-1]
    md = qt_metadata(site)
    assert (root / "access.cpp").read_bytes()[md["span"]["start_byte"]:md["span"]["end_byte"]].decode() == tail.split(";")[-2].strip()
    links = [edge for edge in payload["links"] if edge["source"] == site["id"] and edge.get("context") in TARGET_CONTEXTS]
    assert all(reloaded.has_edge(edge["source"], edge["target"]) for edge in links)
    for edge in links:
        attributes = reloaded.edges[edge["source"], edge["target"]]
        assert attributes["source_file"] == "access.cpp" and attributes["source_location"] == site["source_location"]
        assert qt_metadata(attributes)["span"] == md["span"]
        assert attributes["relation"] == edge["relation"] and attributes["confidence"] == "INFERRED"
        if not directed:
            assert (attributes["_src"], attributes["_tgt"]) == (edge["source"], edge["target"])
    return result, site, links


@pytest.mark.parametrize("directed", [False, True])
@pytest.mark.parametrize("tail", ['left->property("rootOnly");', 'left->setProperty("rootOnly", 9);',
                                  'QMetaObject::invokeMethod(left, "rootAction");'])
def test_req_qml017_ac02_child_reflection_cannot_use_lexical_root(tmp_path, directed, tail):
    _, site, links = persisted(tmp_path, tail, directed=directed)
    assert not links and qt_metadata(site)["status"] != "resolved"


@pytest.mark.parametrize("tail", ['left->findChild<QObject*>("right");',
                                  'root->findChild<QObject*>("deep", Qt::FindDirectChildrenOnly);',
                                  'root->findChild<QObject*>("owner");'])
def test_req_qml017_ac02_findchild_rejects_siblings_depth_and_receiver(tmp_path, tail):
    _, site, links = persisted(tmp_path, tail)
    assert not links and qt_metadata(site)["status"] != "resolved"


@pytest.mark.parametrize("tail, expected", [
    ('left->property("localValue");', "localValue"), ('root->property("rootOnly");', "rootOnly"),
    ('QMetaObject::invokeMethod(root, "rootAction");', "rootAction"),
    ('left->findChild<QObject*>("deep");', "Item"),
    ('root->findChild<QObject*>("left", Qt::FindDirectChildrenOnly);', "left"),
    ('root->findChild<QObject*>("deep", Qt::FindChildrenRecursively);', "Item"),
])
def test_req_qml017_ac04_owned_members_and_subtree_targets_survive_reload(tmp_path, tail, expected):
    result, site, links = persisted(tmp_path, tail)
    assert qt_metadata(site)["status"] == "resolved" and len(links) == 1
    target = next(node for node in result["nodes"] if node["id"] == links[0]["target"])
    assert qml_metadata(target)["raw_name"] == expected


def test_req_qml017_ac02_property_held_qobject_has_construction_owner(tmp_path):
    qml = 'import QtQml\nQtObject { property QtObject child: QtObject { objectName: "details"; property int count: 1 } }'
    result, site, links = persisted(tmp_path, 'auto child = root->findChild<QObject*>("details"); child->setProperty("count", 2);', qml)
    assert qt_metadata(site)["status"] == "resolved" and len(links) == 1
    child = next(node for node in result["nodes"] if qml_metadata(node).get("kind") == "object" and qml_metadata(node).get("parent_scope_key"))
    md = qml_metadata(child)
    assert md["construction_parent_kind"] == "property" and md["construction_parent_scope_key"] == md["parent_scope_key"]
    assert "static_parent_scope_key" not in md


@pytest.mark.parametrize("tail, expected", [
    ('root->property("status");', "status"),
    ('QMetaObject::invokeMethod(root, "refresh");', "refresh"),
    ('auto child = root->findChild<QObject*>("details"); child->property("count");', "count"),
])
def test_req_qml017_ac04_native_base_members_and_property_child_keep_source_proof(tmp_path, tail, expected):
    qml = ('import QtQml\nimport Public.Tools 1.0\nService { '
           'property QtObject child: QtObject { objectName: "details"; property int count: 1 } }')
    extra = {"backend.h": 'class Backend : public QObject { Q_OBJECT QML_NAMED_ELEMENT(Service) '
             'Q_PROPERTY(int status READ status) public: int status() { return 1; } '
             'Q_INVOKABLE void refresh() {} };',
             "CMakeLists.txt": 'qt_add_qml_module(app URI Public.Tools VERSION 1.0 QML_FILES Main.qml SOURCES backend.h)'}
    result, site, links = persisted(tmp_path, tail, qml, extra=extra)
    assert qt_metadata(site)["status"] == "resolved" and len(links) == 1
    target = next(node for node in result["nodes"] if node["id"] == links[0]["target"])
    if expected == "count":
        assert qml_metadata(target)["raw_name"] == expected
    elif expected == "status":
        assert qt_metadata(target)["raw_name"] == expected and target["source_file"] == "backend.h"
    else:
        member = next(node for node in result["nodes"] if qt_metadata(node).get("generic_target_id") == target["id"]
                      and qt_metadata(node).get("kind") == "member")
        assert qt_metadata(member)["raw_name"] == expected and target["source_file"] == "backend.h"
        assert links[0]["relation"] == "calls"


@pytest.mark.parametrize("annotation", ["QML_UNCREATABLE(\"source-only\")", "QML_SINGLETON", "Q_GADGET"])
def test_req_qml017_ac02_noncreatable_singleton_and_gadget_cannot_prove_qobject_creation(tmp_path, annotation):
    qml = ('import QtQml\nimport Public.Tools 1.0\nService { '
           'property QtObject child: QtObject { objectName: "details" } }')
    base = "" if annotation == "Q_GADGET" else " : public QObject"
    extra = {"backend.h": 'class Backend' + base + ' { QML_NAMED_ELEMENT(Service) '
             + (annotation if annotation == "Q_GADGET" else "Q_OBJECT " + annotation) + ' };',
             "CMakeLists.txt": 'qt_add_qml_module(app URI Public.Tools VERSION 1.0 QML_FILES Main.qml SOURCES backend.h)'}
    _, site, links = persisted(tmp_path, 'root->findChild<QObject*>("details");', qml, extra=extra)
    assert not links and qt_metadata(site)["status"] != "resolved"


@pytest.mark.parametrize("write", [False, True])
def test_req_qml017_ac02_inherited_member_is_receiver_owned_and_readonly_write_rejected(tmp_path, write):
    qml = 'import QtQuick\nItem { property int rootOnly: 9; Base { objectName: "left" } }'
    extra = {"Base.qml": 'import QtQuick\nItem { readonly property int inherited: 3; function action() {} }'}
    tail = 'left->setProperty("inherited", 4);' if write else 'left->property("inherited");'
    result, site, links = persisted(tmp_path, tail, qml, extra=extra)
    if write:
        assert not links and qt_metadata(site)["reason"] == "readonly_property"
    else:
        assert len(links) == 1 and qt_metadata(site)["status"] == "resolved"
        assert next(node for node in result["nodes"] if node["id"] == links[0]["target"])["source_file"] == "Base.qml"


def test_req_qml017_ac02_duplicate_names_are_ambiguous_only_inside_receiver(tmp_path):
    qml = QML.replace('objectName: "deep";', 'objectName: "right";')
    _, site, links = persisted(tmp_path, 'root->findChild<QObject*>("right");', qml)
    assert not links and qt_metadata(site)["status"] == "ambiguous"
    _, site, links = persisted(tmp_path, 'left->findChild<QObject*>("right");', qml)
    assert len(links) == 1 and qt_metadata(site)["status"] == "resolved"


@pytest.mark.parametrize("mutation", ['parent: right;', 'Component.onCompleted: left.parent = right;',
                                      'function move() { left.parent = right; }',
                                      'function move(key) { left[key] = right; }'])
def test_req_qml017_ac02_parent_bindings_and_js_writes_do_not_authorize_construction_tree(tmp_path, mutation):
    qml = QML.replace('objectName: "deep";', f'objectName: "deep"; {mutation}')
    result, site, links = persisted(tmp_path, 'root->findChild<QObject*>("deep");', qml)
    assert not links and qt_metadata(site)["reason"] == "component_parenting_mutated"
    evidence = [qml_metadata(node)["construction_parent_mutation_spans"] for node in result["nodes"]
                if qml_metadata(node).get("construction_parent_dynamic")]
    assert evidence and all(spans == evidence[0] for spans in evidence)
    span = evidence[0][0]
    assert "parent" in (tmp_path / "Main.qml").read_bytes()[span["start_byte"]:span["end_byte"]].decode() or "[key]" in mutation


@pytest.mark.parametrize("fragment", ['Unknown { objectName: "blocked" }',
                                      'Component { Item { objectName: "blocked" } }',
                                      'Loader { sourceComponent: Item { objectName: "blocked" } }'])
def test_req_qml017_ac02_unknown_types_and_component_templates_remain_unavailable(tmp_path, fragment):
    qml = 'import QtQuick\nItem { ' + fragment + ' }'
    _, site, links = persisted(tmp_path, 'root->findChild<QObject*>("blocked");', qml)
    assert not links and qt_metadata(site)["status"] != "resolved"


@pytest.mark.parametrize("corrupt", ["scope", "owner", "source", "confidence", "origin", "parent_origin", "owner_span"])
def test_req_qml017_ac02_construction_lookup_requires_accepted_declaration_proof(tmp_path, corrupt):
    result = analysis(tmp_path, {"Main.qml": QML})
    nodes, edges = copy.deepcopy(result["nodes"]), copy.deepcopy(result["edges"])
    child = next(node for node in nodes if qml_metadata(node).get("object_id") == "left")
    root = next(node for node in nodes if qml_metadata(node).get("object_id") == "owner")
    declaration = next(edge for edge in edges if edge["target"] == child["id"] and qml_metadata(edge).get("kind") == "declaration")
    if corrupt == "scope":
        child["metadata"]["qml"] = encode_metadata({**qml_metadata(child), "construction_parent_scope_key": "absent"})
    elif corrupt == "origin":
        child["_origin"] = "llm"
    elif corrupt == "parent_origin":
        root["_origin"] = "llm"
    elif corrupt == "owner_span":
        root["metadata"]["qml"] = encode_metadata({**qml_metadata(root), "span": qml_metadata(child)["span"]})
    else:
        declaration[{"owner": "source", "source": "source_file", "confidence": "confidence"}[corrupt]] = "unaccepted"
    before = copy.deepcopy((nodes, edges))
    index = QtQmlAccessIndex(nodes, edges, root=tmp_path)
    resolution = index.find_child(root["id"], "left")
    assert resolution.target_id is None
    assert (nodes, edges) == before


def test_req_qml017_ac02_proved_cpp_parent_mutation_keeps_source_but_no_target(tmp_path):
    _, site, links = persisted(tmp_path, 'left->setParent(other); root->findChild<QObject*>("deep");')
    assert not links and qt_metadata(site)["status"] != "resolved"


def test_req_qml017_ac02_unsupported_findchild_options_cannot_choose_target(tmp_path):
    _, site, links = persisted(tmp_path, 'root->findChild<QObject*>("left", options);')
    assert not links and qt_metadata(site)["reason"] == "find_child_options_unsupported"


@pytest.mark.parametrize("target_type", ["QQuickItem*", "Custom*", "QObject"])
def test_req_qml017_ac02_unproved_findchild_type_filter_cannot_choose_object(tmp_path, target_type):
    """A QObject construction tree does not prove an arbitrary requested cast."""
    _, site, links = persisted(tmp_path, f'root->findChild<{target_type}>("left");')
    assert not links and qt_metadata(site)["reason"] == "find_child_type_unsupported"
