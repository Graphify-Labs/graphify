"""REQ-QML-017-AC02/AC04: SDK reflection authority and persisted receiver targets.

Public synthetic inputs reach extraction, build, JSON publication and reload. No
Qt compiler, application, QML component or corpus build hook executes. The source
class controls describe accepted parser inputs, not claims of successful Qt builds.
"""
from __future__ import annotations

import json

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.paths import load_node_link_graph
from graphify.qml_resolution_types import qml_metadata
from tests.qt_analysis_helpers import analysis, sites

QML = 'import QtQml\nQtObject { property int count: 1; function refresh() {} }'
OPERATIONS = {
    "invoke": ('static void invokeMethod(QObject *, const char *) {}',
               'QMetaObject::invokeMethod(root, "refresh");', "QMetaObject"),
    "static_read": ('static QVariant read(QObject *, const char *) {}',
                    'QQmlProperty::read(root, "count");', "QQmlProperty"),
    "static_write": ('static bool write(QObject *, const char *, QVariant) {}',
                     'QQmlProperty::write(root, "count", 2);', "QQmlProperty"),
    "property_handle": ('OtherProperty(QObject *, const char *) {} QVariant read() {}',
                        'QQmlProperty handle(root, "count"); handle.read();', "QQmlProperty"),
}
TARGET_CONTEXTS = {"qt_cpp_qml_invoke", "qt_cpp_qml_property_read", "qt_cpp_qml_property_write"}


def source(root, operation, shadow, *, absolute=False):
    """A real source loader supplies the receiver; the reflection type varies."""
    member, tail, sdk_name = OPERATIONS[operation]
    definition, alias, namespace = "", "", ""
    if shadow == "local_alias":
        other = "OtherMeta" if sdk_name == "QMetaObject" else "OtherProperty"
        definition = f"struct {other} {{ {member} }};"
        alias = f"using {sdk_name} = {other};"
    elif shadow in {"global_source_class", "namespace_source_class"}:
        definition = f"struct {sdk_name} {{ {member.replace('OtherProperty(', 'QQmlProperty(')} }};"
        namespace = "Public" if shadow == "namespace_source_class" else ""
    elif shadow == "sdk_namespace_control":
        namespace = "Public"
    elif shadow == "forward_source_class":
        definition = f"class {sdk_name};"
    elif shadow == "conditional_alias":
        definition = "struct Other {};"
        alias = f"#if FEATURE\nusing {sdk_name} = Other;\n#endif\n"
    elif shadow == "sdk_alias_control":
        alias = f"using {sdk_name} = ::{sdk_name};"
    elif shadow != "sdk_control":
        raise ValueError(shadow)
    if absolute:
        tail = tail.replace(sdk_name, "::" + sdk_name, 1)
    body = f'''// Original-byte evidence: café
{definition}
void use() {{ QQuickView view;
 view.setSource(QUrl("{(root / 'Main.qml').as_uri()}"));
 auto root = view.rootObject();
 {alias}
 {tail}
}}'''
    return "\ufeff" + (("namespace " + namespace + " {\n" + body + "\n}") if namespace else body).replace("\n", "\r\n")


def persisted(root, operation, shadow, *, directed=False, absolute=False):
    """Check actual durable direction and original source evidence before rejection."""
    original = source(root, operation, shadow, absolute=absolute)
    result = analysis(root, {"access.cpp": original, "Main.qml": QML})
    graph = build_from_json(result, root=root, directed=directed)
    output = root / "proof.json"
    assert to_json(graph, {}, str(output), force=True)
    payload = json.loads(output.read_text(encoding="utf-8"))
    restored = load_node_link_graph(payload)
    accesses = sites(result, "qml_access")
    by_id = {node["id"]: node for node in accesses}
    for node in accesses:
        metadata = qt_metadata(node)
        span = metadata["span"]
        text = original.encode()[span["start_byte"]:span["end_byte"]].decode()
        assert text and text in original and "\r" not in text
        assert node["source_location"].split("-", 1)[0] == "L" + str(original.encode()[:span["start_byte"]].count(b"\n") + 1)
        assert node["source_file"] == "access.cpp"
        assert node["source_location"].startswith("L")
    links = [edge for edge in payload["links"] if edge["source"] in by_id
             and edge.get("context") in TARGET_CONTEXTS]
    for edge in links:
        site = by_id[edge["source"]]
        assert restored.has_edge(edge["source"], edge["target"])
        actual = restored.edges[edge["source"], edge["target"]]
        if directed:
            assert not restored.has_edge(edge["target"], edge["source"])
        else:
            assert (actual["_src"], actual["_tgt"]) == (edge["source"], edge["target"])
        assert actual["relation"] == ("calls" if operation == "invoke" else "uses")
        assert actual["confidence"] == "INFERRED"
        assert actual["source_file"] == "access.cpp"
        assert actual["source_location"] == site["source_location"]
        assert qt_metadata(actual)["span"] == qt_metadata(site)["span"]
    return result, accesses, links, restored, output


@pytest.mark.parametrize("operation", list(OPERATIONS))
@pytest.mark.parametrize("shadow", ["local_alias", "global_source_class", "namespace_source_class", "forward_source_class", "conditional_alias"])
@pytest.mark.parametrize("directed", [False, True])
def test_req_qml017_ac02_shadowed_reflection_type_cannot_create_qml_target(tmp_path, operation, shadow, directed):
    """A local alias or source class spelling is not the Qt reflection SDK class."""
    _, accesses, links, _, _ = persisted(tmp_path, operation, shadow, directed=directed)
    assert not links, "Unrelated reflection class persisted a false QML member target"
    rejected = [qt_metadata(node) for node in accesses if qt_metadata(node).get("reflection_supported") is False]
    assert len(rejected) == 1
    assert rejected[0]["status"] == "unsupported" and rejected[0]["reason"] == "reflection_api_type_unestablished"
    assert all(qt_metadata(node)["status"] != "resolved" and not qt_metadata(node).get("target_id") for node in accesses)


@pytest.mark.parametrize("operation", list(OPERATIONS))
@pytest.mark.parametrize("shadow, absolute", [("sdk_control", False), ("sdk_namespace_control", False),
                                            ("local_alias", True), ("sdk_alias_control", False)])
@pytest.mark.parametrize("directed", [False, True])
def test_req_qml017_ac04_unshadowed_sdk_reflection_preserves_targets_and_provenance(tmp_path, operation, shadow, absolute, directed):
    """The correction must preserve genuine SDK calls, including namespace scope."""
    result, accesses, links, _, _ = persisted(tmp_path, operation, shadow, absolute=absolute, directed=directed)
    assert len(links) == (2 if operation == "property_handle" else 1)
    assert accesses and all(qt_metadata(node)["status"] == "resolved" for node in accesses)
    nodes = {node["id"]: node for node in result["nodes"]}
    assert {qml_metadata(nodes[edge["target"]])["raw_name"] for edge in links} == {
        "refresh" if operation == "invoke" else "count"}


@pytest.mark.parametrize("operation", list(OPERATIONS))
def test_req_qml017_ac02_absolute_sdk_spelling_still_rejects_global_source_class(tmp_path, operation):
    """Absolute qualification bypasses locals, never a source declaration at ::."""
    _, accesses, links, _, _ = persisted(tmp_path, operation, "global_source_class", absolute=True)
    assert not links and all(qt_metadata(node)["status"] != "resolved" for node in accesses)


@pytest.mark.parametrize("operation", list(OPERATIONS))
def test_req_qml017_ac04_sdk_reflection_query_and_affected_use_exact_persisted_site(tmp_path, monkeypatch, capsys, operation):
    """Consumers expose the same source-owned endpoint as the serialized graph."""
    from graphify.affected import affected_nodes, load_graph
    from tests.qt_consumer_helpers import cli
    _, accesses, links, _, output = persisted(tmp_path, operation, "sdk_control", directed=True)
    site = accesses[0]["id"]
    target = links[0]["target"]
    assert "access.cpp" in cli(monkeypatch, capsys, output, "explain", site)
    assert "Main.qml" in cli(monkeypatch, capsys, output, "query", site)
    relation = "calls" if operation == "invoke" else "uses"
    assert site in {hit.node_id for hit in affected_nodes(load_graph(output), target, relations=[relation], depth=1)}


@pytest.mark.parametrize("operation", list(OPERATIONS))
def test_req_qml017_ac02_direct_collector_carries_type_rejection_and_original_span(tmp_path, operation):
    """The child collector owns authority before resolver/facade annotation."""
    import copy
    from graphify.extractors.qt_cpp_access import collect_qt_cpp_access
    original = source(tmp_path, operation, "local_alias")
    result = analysis(tmp_path, {"access.cpp": original, "Main.qml": QML})
    borrowed = copy.deepcopy(result)
    fresh = {"nodes": [], "edges": []}
    collect_qt_cpp_access([tmp_path / "access.cpp"], [fresh], root=tmp_path,
                          accepted_nodes=result["nodes"], accepted_edges=result["edges"])
    assert result == borrowed
    rejected = [node for node in fresh["nodes"] if qt_metadata(node).get("reflection_supported") is False]
    assert len(rejected) == 1
    md = qt_metadata(rejected[0])
    assert md["reflection_type"] == OPERATIONS[operation][2]
    span = md["span"]
    assert original.encode()[span["start_byte"]:span["end_byte"]].decode() in OPERATIONS[operation][1]
    assert md["owner_id"] in {node["id"] for node in result["nodes"] if node.get("_callable")}


@pytest.mark.parametrize("tail", [
    'QQmlProperty handle(root,"count"); QQmlProperty other(root,"count"); handle=other; handle.read();',
    '{ QQmlProperty handle(root,"count"); handle.read(); } handle.read();',
    'QQmlProperty handle(root,"count"); handle=makeProperty(); handle.write(4);',
])
def test_req_qml017_ac02_property_handle_reassignment_and_lifetime_cannot_borrow_old_target(tmp_path, tail):
    """A previously established property wrapper cannot authorize another value/scope."""
    original = source(tmp_path, "invoke", "sdk_control").replace(OPERATIONS["invoke"][1], tail)
    result = analysis(tmp_path, {"access.cpp": original, "Main.qml": QML})
    site = sites(result, "qml_access")[-1]
    metadata = qt_metadata(site)
    assert metadata["status"] != "resolved" and not metadata.get("target_id")
    graph = build_from_json(result, root=tmp_path)
    assert not any(data.get("_src", start) == site["id"] and data.get("context") in TARGET_CONTEXTS
                   for start, _, data in graph.edges(data=True))


@pytest.mark.parametrize("operation", list(OPERATIONS))
def test_req_qml017_ac02_sdk_identity_does_not_override_receiver_member_scope(tmp_path, operation):
    """A genuine SDK API on a child still cannot access the root's members."""
    original = source(tmp_path, operation, "sdk_control").replace(OPERATIONS[operation][1],
        'auto child = root->findChild<QObject*>("details"); ' + OPERATIONS[operation][1].replace("root,", "child,"))
    qml = 'import QtQml\nQtObject { property int count:1; function refresh(){} '
    qml += 'property QtObject child: QtObject { objectName:"details"; property int childOnly:2 } }'
    result = analysis(tmp_path, {"access.cpp": original, "Main.qml": qml})
    accesses = [node for node in sites(result, "qml_access") if qt_metadata(node).get("operation") != "findChild"]
    assert accesses and all(qt_metadata(node)["status"] != "resolved" for node in accesses)
    graph = build_from_json(result, root=tmp_path, directed=True)
    ids = {node["id"] for node in accesses}
    assert not any(start in ids and data.get("context") in TARGET_CONTEXTS for start, _, data in graph.edges(data=True))
