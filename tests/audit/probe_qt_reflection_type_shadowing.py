"""Opt-in INC-QML-22 reflection identity audit; rejection assertions stay strict.

Explicit pytest invocation is required: ``probe_*.py`` is outside normal discovery.
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


def source(root, operation, shadow):
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
    elif shadow != "sdk_control":
        raise ValueError(shadow)
    body = f'''// Original-byte evidence: café
{definition}
void use() {{ QQuickView view;
 view.setSource(QUrl("{(root / 'Main.qml').as_uri()}"));
 auto root = view.rootObject();
 {alias}
 {tail}
}}'''
    return (("namespace " + namespace + " {\n" + body + "\n}") if namespace else body).replace("\n", "\r\n")


def persisted(root, operation, shadow):
    """Check actual durable direction and original source evidence before rejection."""
    original = source(root, operation, shadow)
    result = analysis(root, {"access.cpp": original, "Main.qml": QML})
    graph = build_from_json(result, root=root)
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
        assert text and text in OPERATIONS[operation][1]
        assert node["source_file"] == "access.cpp"
        assert node["source_location"].startswith("L")
    links = [edge for edge in payload["links"] if edge["source"] in by_id
             and edge.get("context") in TARGET_CONTEXTS]
    for edge in links:
        site = by_id[edge["source"]]
        assert restored.has_edge(edge["source"], edge["target"])
        actual = restored.edges[edge["source"], edge["target"]]
        assert (actual["_src"], actual["_tgt"]) == (edge["source"], edge["target"])
        assert actual["relation"] == ("calls" if operation == "invoke" else "uses")
        assert actual["confidence"] == "INFERRED"
        assert actual["source_file"] == "access.cpp"
        assert actual["source_location"] == site["source_location"]
        assert qt_metadata(actual)["span"] == qt_metadata(site)["span"]
    return result, accesses, links


@pytest.mark.parametrize("operation", list(OPERATIONS))
@pytest.mark.parametrize("shadow", ["local_alias", "global_source_class", "namespace_source_class"])
def test_req_qml017_ac02_shadowed_reflection_type_cannot_create_qml_target(tmp_path, operation, shadow):
    """A local alias or source class spelling is not the Qt reflection SDK class."""
    _, _, links = persisted(tmp_path, operation, shadow)
    assert not links, "Unrelated reflection class persisted a false QML member target"


@pytest.mark.parametrize("operation, shadow", [
    ("invoke", "sdk_namespace_control"), ("property_handle", "sdk_control"),
])
def test_req_qml017_ac04_unshadowed_sdk_reflection_preserves_targets_and_provenance(tmp_path, operation, shadow):
    """The correction must preserve genuine SDK calls, including namespace scope."""
    result, accesses, links = persisted(tmp_path, operation, shadow)
    assert len(links) == (1 if operation == "invoke" else 2)
    assert accesses and all(qt_metadata(node)["status"] == "resolved" for node in accesses)
    nodes = {node["id"]: node for node in result["nodes"]}
    assert {qml_metadata(nodes[edge["target"]])["raw_name"] for edge in links} == {
        "refresh" if operation == "invoke" else "count"}
