"""REQ-QML-017: construction ownership needs non-widget QObject ancestry."""
from __future__ import annotations

import copy

import pytest

from graphify.extractors.qml import extract_qml
from graphify.extractors.qt_cpp_facts import encode_qt, qt_metadata
from graphify.qml_resolution_types import qml_metadata
from graphify.qt_qml_access_index import QtQmlAccessIndex
from tests.test_qt_receiver_boundaries import persisted


QML = ('import QtQuick\nimport Public.Tools 1.0\nItem { '
       'property Owned child: Owned { objectName: "child"; property int count: 1 } }')


def native(root, declarations, *, extra=None):
    sources = {"backend.h": declarations, "CMakeLists.txt":
               'qt_add_qml_module(app URI Public.Tools VERSION 1.0 QML_FILES Main.qml SOURCES backend.h)'}
    return persisted(root, 'root->findChild<QObject*>("child");', QML,
                     extra={**sources, **(extra or {})})


@pytest.mark.parametrize("declarations", [
    'class Backend : public QWidget { Q_OBJECT QML_NAMED_ELEMENT(Owned) };',
    'class Base : public QWidget { Q_OBJECT }; '
    'class Backend : public Base { Q_OBJECT QML_NAMED_ELEMENT(Owned) };',
    'class Backend : public QQuickWidget { Q_OBJECT QML_NAMED_ELEMENT(Owned) };',
    'class Backend : public ExternalBase { Q_OBJECT QML_NAMED_ELEMENT(Owned) };',
    'namespace Other { class QObject : public QWidget { Q_OBJECT }; } '
    'class Backend : public Other::QObject { Q_OBJECT QML_NAMED_ELEMENT(Owned) };',
    'class QObject : public QWidget { Q_OBJECT }; '
    'class Backend : public QObject { Q_OBJECT QML_NAMED_ELEMENT(Owned) };',
])
def test_req_qml017_ac02_widget_and_unknown_ancestry_cannot_authorize_child_tree(tmp_path, declarations):
    result, site, links = native(tmp_path, declarations)
    reason = "find_child_type_unsupported" if declarations.startswith("class QObject :") else "native_construction_ancestry_unestablished"
    assert not links and qt_metadata(site)["reason"] == reason
    # The registration/declaration remains observed; rejecting construction
    # authority must not erase its source fact or invent a substitute endpoint.
    assert any(qt_metadata(node).get("kind") == "registration" for node in result["nodes"])
    child = next(node for node in result["nodes"] if qml_metadata(node).get("type_name") == "Owned")
    assert qml_metadata(child)["construction_parent_scope_key"]


@pytest.mark.parametrize("declarations", [
    'class Backend : public QObject { Q_OBJECT QML_NAMED_ELEMENT(Owned) };',
    'class Base : public QObject { Q_OBJECT }; '
    'class Backend : public Base { Q_OBJECT QML_NAMED_ELEMENT(Owned) };',
    'namespace Public { class Base : public QObject { Q_OBJECT }; '
    'class Backend : public Base { Q_OBJECT QML_NAMED_ELEMENT(Owned) }; }',
    'class Base : public QObject { Q_OBJECT }; '
    'namespace Public { class Backend : public ::Base { Q_OBJECT QML_NAMED_ELEMENT(Owned) }; }',
    'class Interface {}; class Backend : public QObject, public Interface { Q_OBJECT QML_NAMED_ELEMENT(Owned) };',
])
def test_req_qml017_ac04_direct_and_source_defined_qobject_chain_survives_publication(tmp_path, declarations):
    result, site, links = native(tmp_path, declarations)
    assert qt_metadata(site)["status"] == "resolved" and len(links) == 1
    child = next(node for node in result["nodes"] if node["id"] == links[0]["target"])
    assert qml_metadata(child)["type_name"] == "Owned" and child["source_file"] == "Main.qml"


def test_req_qml017_ac04_exact_namespace_ancestry_does_not_choose_other_file_basename(tmp_path):
    declarations = ('namespace Public { class Base : public QObject { Q_OBJECT }; '
                    'class Backend : public Base { Q_OBJECT QML_NAMED_ELEMENT(Owned) }; }')
    result, site, links = native(tmp_path, declarations,
                               extra={"other.h": 'class Base : public QWidget { Q_OBJECT };'})
    assert qt_metadata(site)["status"] == "resolved" and len(links) == 1
    bases = [qt_metadata(node) for node in result["nodes"] if qt_metadata(node).get("kind") == "class"
             and qt_metadata(node).get("class_name") in {"Base", "Public::Base"}]
    assert len(bases) == 2 and len({md["class_id"] for md in bases}) == 2


def test_req_qml017_ac04_distinct_same_file_qualified_bodies_supply_only_exact_ancestry(tmp_path):
    declarations = ('class Base : public QWidget { Q_OBJECT }; '
                    'namespace Public { class Base : public QObject { Q_OBJECT }; '
                    'class Backend : public Base { Q_OBJECT QML_NAMED_ELEMENT(Owned) }; }')
    result, site, links = native(tmp_path, declarations)
    assert qt_metadata(site)["status"] == "resolved" and len(links) == 1
    bases = [qt_metadata(node) for node in result["nodes"] if qt_metadata(node).get("kind") == "class"
             and qt_metadata(node).get("class_name") in {"Base", "Public::Base"}]
    assert len(bases) == 2 and len({md["class_id"] for md in bases}) == 2
    assert {md["class_name"]: md["canonical_base_names"] for md in bases} == {
        "Base": ["QWidget"], "Public::Base": ["QObject"]}
    assert not any(node.get("metadata", {}).get("cpp_class", {}).get("ambiguous") for node in result["nodes"])


@pytest.mark.parametrize("alias", ["using QObject = QWidget;", "using QObject = QQuickWidget;"])
def test_req_qml017_ac02_widget_alias_cannot_inherit_global_qobject_authority(tmp_path, alias):
    declarations = ('namespace Public { ' + alias
                    + ' class Backend : public QObject { Q_OBJECT QML_NAMED_ELEMENT(Owned) }; }')
    result, site, links = native(tmp_path, declarations)
    assert not links and qt_metadata(site)["reason"] == "native_construction_ancestry_unestablished"
    md = next(qt_metadata(node) for node in result["nodes"] if qt_metadata(node).get("kind") == "class")
    assert md["bases"] == ["QObject"] and md["canonical_base_names"] != ["QObject"]


@pytest.mark.parametrize("corruption", ["definition", "status", "origin", "identity", "base", "canonical_status", "canonical_missing"])
def test_req_qml017_ac02_native_ancestry_reads_only_accepted_complete_source_facts(tmp_path, corruption):
    result, _, _ = native(tmp_path, 'class Backend : public QObject { Q_OBJECT QML_NAMED_ELEMENT(Owned) };')
    nodes, edges = copy.deepcopy(result["nodes"]), copy.deepcopy(result["edges"])
    declaration = next(node for node in nodes if qt_metadata(node).get("kind") == "class")
    md = qt_metadata(declaration)
    md.pop("raw_values", None)
    if corruption == "origin":
        declaration["_origin"] = "llm"
    else:
        key, value = {"definition": ("is_definition", False), "status": ("status", "unavailable"),
                      "identity": ("class_id", "unaccepted"), "base": ("canonical_base_names", ["Unknown"]),
                      "canonical_status": ("canonical_base_status", "unavailable"),
                      "canonical_missing": ("canonical_base_names", None)}[corruption]
        declaration["metadata"]["qt"] = encode_qt({**md, key: value})
    before = copy.deepcopy((nodes, edges))
    index = QtQmlAccessIndex(nodes, edges, root=tmp_path)
    root = next(node for node in nodes if qml_metadata(node).get("kind") == "object"
                and not qml_metadata(node).get("parent_scope_key"))
    assert index.find_child(root["id"], "child").target_id is None
    assert (nodes, edges) == before


@pytest.mark.parametrize("count", [50, 51])
def test_req_qml017_ac04_parent_mutation_spans_are_bounded_original_bytes(tmp_path, count):
    source = ('import QtQuick\r\nItem { id: left; Item { id: right } function change() { '
              + 'left.parent = right; ' * count + '} }').encode()
    path = tmp_path / "Main.qml"
    path.write_bytes(source)
    result = extract_qml(path, root=tmp_path)
    if count == 51:
        assert result["nodes"] == [] and result["edges"] == []
        assert result["error"].startswith("QML_LIMIT")
        assert result["diagnostics"][0]["code"] == "QML_LIMIT"
    else:
        assert not result.get("error")
        objects = [qml_metadata(node) for node in result["nodes"] if qml_metadata(node).get("kind") == "object"]
        assert objects and all(md.get("construction_parent_dynamic") for md in objects)
        for md in objects:
            spans = md["construction_parent_mutation_spans"]
            assert len(spans) == 50
            for span in spans:
                assert source[span["start_byte"]:span["end_byte"]] == b"left.parent = right"
                assert span["start_row"] == source[:span["start_byte"]].count(b"\n")
