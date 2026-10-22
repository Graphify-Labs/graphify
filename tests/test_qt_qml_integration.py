"""Actual facade-to-graph native Qt/QML bridges and scoped rejection cases."""
from __future__ import annotations

import json

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extract import extract
from graphify.extractors.qml_facts import qml_metadata
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.paths import load_node_link_graph
from tests.qt_cpp_test_helpers import HEADER, write


SOURCE = '''import Demo 1.0 as Native
Native.Backend {
    id: root
    property int doubled: value * 2
    property int called: next(1)
    onValueChanged: { doubled = value; }
}
'''


def corpus(root, qml=SOURCE, header=HEADER, calls=None):
    calls = calls or 'void install(){ qmlRegisterType<Backend>("Demo",1,0,"Backend"); }'
    paths = [write(root, "backend.hpp", header), write(root, "register.cpp", calls), write(root, "Main.qml", qml)]
    return extract(paths, root=root, cache_root=root / "cache", parallel=False)


def sites(result, kind):
    return [node for node in result["nodes"] if qml_metadata(node).get("kind") == kind]


@pytest.mark.parametrize("directed", [False, True])
def test_actual_native_import_property_call_and_subscription_survive_roundtrip(tmp_path, directed):
    result = corpus(tmp_path)
    assert not result.get("qml_failures")
    assert all(qml_metadata(node)["status"] == "resolved" for kind in ("import_resolution", "type_use", "handler", "call")
               for node in sites(result, kind))
    reads = sites(result, "read")
    assert len(reads) == 2
    assert {qml_metadata(node)["status"] for node in reads} == {"resolved", "dynamic"}
    shadow = next(qml_metadata(node) for node in reads if qml_metadata(node)["status"] == "dynamic")
    assert shadow["reference"] == "value" and shadow["reason"] == "javascript_lexical_binding"
    edges = [edge for edge in result["edges"] if qt_metadata(edge).get("native_endpoint")]
    assert {(edge["relation"], edge["context"]) for edge in edges} == {
        ("imports", "qml_import_resolution"), ("uses", "qml_type_resolution"),
        ("uses", "qml_binding_read"), ("calls", "qml_js_call"), ("references", "qml_signal_subscription")}
    for edge in edges:
        assert edge["confidence"] == "INFERRED"
        proof = qt_metadata(edge)["native_endpoint"]
        assert proof["canonical_target_id"] == edge["target"]
        assert proof["provider_id"] in proof["evidence"]
    graph = build_from_json(result, root=tmp_path, directed=directed)
    output = tmp_path / "graph.json"
    assert to_json(graph, {}, str(output))
    restored = load_node_link_graph(json.loads(output.read_text(encoding="utf-8")))
    assert restored.is_directed() == directed
    for edge in edges:
        assert graph.has_edge(edge["source"], edge["target"])
        assert restored.has_edge(edge["source"], edge["target"])
        data = restored.edges[edge["source"], edge["target"]]
        assert (data["relation"], data["context"], data["confidence"]) == (edge["relation"], edge["context"], "INFERRED")
        assert (data.get("_src", edge["source"]), data.get("_tgt", edge["target"])) == (edge["source"], edge["target"])
        assert qt_metadata(data)["native_endpoint"] == qt_metadata(edge)["native_endpoint"]


def test_duplicate_registration_has_no_arbitrary_type_or_member_bridge(tmp_path):
    calls = 'void install(){ qmlRegisterType<Backend>("Demo",1,0,"Backend"); qmlRegisterType<Backend>("Demo",1,0,"Backend"); }'
    result = corpus(tmp_path, calls=calls)
    assert qml_metadata(sites(result, "type_use")[0])["status"] == "ambiguous"
    assert all(qml_metadata(node)["status"] != "resolved" for kind in ("call", "handler") for node in sites(result, kind))
    assert not any(qt_metadata(edge).get("native_endpoint", {}).get("member_fact_id") for edge in result["edges"])


def test_ambiguous_overload_and_version_revised_member_are_explicit(tmp_path):
    header = HEADER.replace("Q_INVOKABLE int next(int amount);", "Q_INVOKABLE int next(int amount); Q_INVOKABLE int next(QString value);")
    result = corpus(tmp_path, header=header)
    assert qml_metadata(sites(result, "call")[0])["status"] == "ambiguous"
    header = HEADER.replace("Q_INVOKABLE int next(int amount);", "Q_REVISION(1, 2) Q_INVOKABLE int next(int amount);")
    result = corpus(tmp_path, header=header)
    call = qml_metadata(sites(result, "call")[0])
    assert call["status"] == "unsupported" and call["reason"] == "native_member_revision_requires_supported_version"
    header = HEADER.replace("NOTIFY valueChanged)", "NOTIFY valueChanged REVISION 2)")
    result = corpus(tmp_path, header=header)
    assert any(qml_metadata(node)["status"] == "unsupported" for node in sites(result, "read"))


@pytest.mark.parametrize("registration", [
    'qmlRegisterUncreatableType<Backend>("Demo",1,0,"Backend","reason")',
    'qmlRegisterSingletonType<Backend>("Demo",1,0,"Backend",factory)',
])
def test_noncreatable_native_object_declaration_does_not_get_type_edge(tmp_path, registration):
    result = corpus(tmp_path, calls=f"void install(){{ {registration}; }}")
    site = sites(result, "type_use")[0]
    assert qml_metadata(site)["status"] == "unsupported" and qml_metadata(site)["reason"] == "native_type_not_creatable"
    assert not any(edge["source"] == site["id"] and edge["relation"] == "uses" for edge in result["edges"])


def test_registered_singleton_qualifier_member_uses_exact_source_type(tmp_path):
    qml = 'import Demo 1.0 as Native\nQtObject { property int result: Native.State.next(1) }'
    calls = 'void install(){ qmlRegisterSingletonType<Backend>("Demo",1,0,"State",factory); }'
    result = corpus(tmp_path, qml=qml, calls=calls)
    call = sites(result, "call")[0]
    assert qml_metadata(call)["status"] == "resolved"
    target = qml_metadata(call)["resolved_target_id"]
    assert next(node for node in result["nodes"] if node["id"] == target)["_callable"]
    assert any(edge["source"] == call["id"] and edge["target"] == target and qt_metadata(edge).get("native_endpoint") for edge in result["edges"])


def test_native_property_does_not_invent_automatic_qml_notify_signal(tmp_path):
    header = HEADER.replace("NOTIFY valueChanged", "").replace("void valueChanged(int value);", "")
    result = corpus(tmp_path, header=header)
    handler = qml_metadata(sites(result, "handler")[0])
    assert handler["status"] != "resolved"
    assert sites(result, "property_change_signal") == []
