"""INC-QML-36: accepted source mechanisms survive every bridge consumer boundary."""
from __future__ import annotations

import copy
from pathlib import Path

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extractors.qml_facts import encode_metadata, qml_metadata
from graphify.extractors.qt_cpp_facts import qt_metadata, update_qt
from graphify.paths import load_node_link_graph
from graphify.qt_qml_projection import allows_qt_qml_edge
from tests.qt_adoption_fixture import sources
from tests.qt_analysis_helpers import analysis
from tests.test_qt_access_providers import BACKEND


def fixture(root, profile):
    """Only ordinary public source fixtures produce the bridge facts under review."""
    if profile == "context":
        inputs = sources(root)
    elif profile == "native":
        native = BACKEND.replace("changed", "ready")
        native += 'void registerTypes() { qmlRegisterType<Backend>("Demo.Tools", 1, 0, "Service"); }'
        qml = ('import QtQml\nimport Demo.Tools 1.0\nService { id: service; '
               'property int displayed: count; property alias mirrored: service.count; '
               'function run() { refresh(); ready() } onReady: {} }')
        inputs = {"backend.cpp": native, "Main.qml": qml}
    else:
        url = (root / "Main.qml").as_uri()
        native = BACKEND + f'''void use(Backend *backend) {{ QQuickView view;
 view.setSource(QUrl("{url}")); auto root = view.rootObject();
 root->property("count"); root->setProperty("count", 2);
 QMetaObject::invokeMethod(root, "refresh"); QMetaObject::invokeMethod(root, "closed");
 auto child = root->findChild<QObject*>("details"); child->property("count");
 QObject::connect(root, SIGNAL(closed()), backend, SLOT(close()));
 QObject::connect(backend, SIGNAL(changed()), root, SLOT(refresh())); }}'''
        if profile == "disconnect":
            native = native.replace("QObject::connect", "QObject::disconnect")
        qml = ('import QtQml\nQtObject { property int count: 1; function refresh() {} signal closed(); '
               'property QtObject child: QtObject { objectName: "details"; property int count: 2 } }')
        inputs = {"access.cpp": native, "Main.qml": qml}
    inputs["keep.py"] = "def helper(): return 7\ndef retained(): return helper()\n"
    return analysis(root, inputs)


def selected(result, context):
    nodes = {node["id"]: node for node in result["nodes"]}
    return next(edge for edge in result["edges"] if edge.get("context") == context
                and (Path(nodes[edge["source"]]["source_file"]).suffix == ".qml")
                != (Path(nodes[edge["target"]]["source_file"]).suffix == ".qml"))


def accepted(result, edge):
    nodes = {node["id"]: node for node in result["nodes"]}
    return allows_qt_qml_edge(nodes[edge["source"]], nodes[edge["target"]], edge,
                             source_id=edge["source"], target_id=edge["target"], nodes=nodes)


CASES = [("context", value) for value in ("qt_context_member", "qt_context_subscription")]
CASES += [("native", value) for value in ("qml_import_resolution", "qml_type_resolution",
           "qml_binding_read", "qml_alias_target", "qml_js_call", "qml_signal_emit", "qml_signal_subscription")]
CASES += [("reverse", value) for value in ("qt_cpp_qml_load", "qt_cpp_qml_property_read",
           "qt_cpp_qml_property_write", "qt_cpp_qml_find_child", "qt_cpp_qml_invoke",
           "qt_qml_connect_signal", "qt_qml_connect_receiver")]
CASES += [("disconnect", value) for value in ("qt_qml_disconnect_signal", "qt_qml_disconnect_receiver")]


@pytest.mark.parametrize("profile,context", CASES)
@pytest.mark.parametrize("directed", [False, True])
def test_source_mechanisms_survive_builder_export_and_reload(tmp_path, profile, context, directed):
    """Valid source facts retain their observed operation rather than becoming generic calls."""
    result = fixture(tmp_path, profile)
    edge = selected(result, context)
    assert accepted(result, edge)
    graph = build_from_json(result, root=tmp_path, directed=directed)
    assert graph.has_edge(edge["source"], edge["target"])
    path = tmp_path / "accepted.json"
    assert to_json(graph, {}, str(path), force=True)
    restored = load_node_link_graph(path)
    source, target = edge["source"], edge["target"]
    data = restored.edges[source, target]
    assert data["relation"] == edge["relation"] and data["context"] == context
    assert allows_qt_qml_edge(restored.nodes[source], restored.nodes[target], data,
                             source_id=source, target_id=target, nodes=restored.nodes)
    assert any(node.get("source_file") == "keep.py" for _, node in restored.nodes(data=True))


@pytest.mark.parametrize("profile,context", CASES)
@pytest.mark.parametrize("corruption", ["relation", "context", "confidence", "inverse", "status", "span"])
def test_source_mechanism_substitution_is_rejected_before_graph_assembly(tmp_path, profile, context, corruption):
    """A changed real producer edge/site cannot retain a valid-looking endpoint proof."""
    result = fixture(tmp_path, profile)
    edge = selected(result, context)
    # Disconnect projection was previously missing from the consumer's bounded
    # whitelist despite being emitted by the ordinary cross-language resolver.
    if "disconnect" not in context:
        assert accepted(result, edge)
    nodes = {node["id"]: node for node in result["nodes"]}
    source = nodes[edge["source"]]
    if corruption == "relation":
        edge["relation"] = "references" if edge["relation"] == "calls" else "calls"
    elif corruption == "confidence":
        edge["confidence"] = "EXTRACTED"
    elif corruption == "context":
        edge["context"] = "qt_cpp_qml_invoke" if profile in {"reverse", "disconnect"} else "qml_js_call"
        if context == edge["context"]:
            edge["context"] = "qt_cpp_qml_property_read" if profile == "reverse" else "qml_binding_read"
    elif corruption == "inverse":
        edge["source"], edge["target"] = edge["target"], edge["source"]
        edge["_src"], edge["_tgt"] = edge["source"], edge["target"]
    elif profile == "native":
        md = {key: value for key, value in qml_metadata(source).items() if key != "raw_values"}
        md.update(status="unavailable") if corruption == "status" else md.update(span={**md["span"], "start_byte": 999999})
        source["metadata"]["qml"] = encode_metadata(md)
    else:
        md = qt_metadata(source)
        update_qt(source, **({"status": "unavailable"} if corruption == "status"
                             else {"span": {**md["span"], "start_byte": 999999}}))
    assert not accepted(result, edge)
    graph = build_from_json(result, root=tmp_path)
    assert not graph.has_edge(edge["source"], edge["target"])
    assert any(node.get("source_file") == "keep.py" for _, node in graph.nodes(data=True))


@pytest.mark.parametrize("corruption", ["owner_kind", "owner_status", "owner_span", "owner_file", "owner_location", "lexical"])
def test_context_access_revalidates_original_read_or_call(tmp_path, corruption):
    """The derived access repeats source ownership and lexical admission after serialization."""
    result = fixture(tmp_path, "context")
    edge = selected(result, "qt_context_member")
    nodes = {node["id"]: node for node in result["nodes"]}
    source = nodes[edge["source"]]
    owner = nodes[qt_metadata(source)["owner_id"]]
    md = {key: value for key, value in qml_metadata(owner).items() if key != "raw_values"}
    if corruption == "owner_file":
        owner["source_file"] = "Other.qml"
    elif corruption == "owner_location":
        owner["source_location"] = "L999"
    else:
        fields = {"owner_kind": {"kind": "alias"}, "owner_status": {"status": "dynamic"},
                  "owner_span": {"span": {**md["span"], "start_byte": 999999}}, "lexical": {"lexical_shadowed": True}}
        owner["metadata"]["qml"] = encode_metadata({**md, **fields[corruption]})
    assert not accepted(result, edge)


@pytest.mark.parametrize("profile", ["native", "reverse"])
def test_endpoint_role_cannot_be_changed_to_repair_relation(tmp_path, profile):
    """Changing the proof's display kind cannot replace the original signal/property/function role."""
    result = fixture(tmp_path, profile)
    edge = selected(result, "qml_js_call" if profile == "native" else "qt_qml_connect_signal")
    assert accepted(result, edge)
    if profile == "native":
        md = qt_metadata(edge)
        proof = copy.deepcopy(md["native_endpoint"])
        proof["kind"] = "signal"
        update_qt(edge, native_endpoint=proof)
        edge["relation"], edge["context"] = "uses", "qml_signal_emit"
    else:
        source = next(node for node in result["nodes"] if node["id"] == edge["source"])
        update_qt(source, role="receiver")
        edge["context"] = "qt_qml_connect_receiver"
    assert not accepted(result, edge)


@pytest.mark.parametrize("profile,context", [case for case in CASES if case[0] != "native"])
def test_cross_language_flow_cannot_be_reversed_by_metadata(tmp_path, profile, context):
    """Dependency endpoints and the observed QML/C++ flow retain separate, consistent authority."""
    result = fixture(tmp_path, profile)
    edge = selected(result, context)
    assert accepted(result, edge)
    old = qt_metadata(edge)["bridge_direction"]
    update_qt(edge, bridge_direction="cpp_to_qml" if old == "qml_to_cpp" else "qml_to_cpp")
    assert not accepted(result, edge)
    assert not build_from_json(result, root=tmp_path).has_edge(edge["source"], edge["target"])


@pytest.mark.parametrize("field", ["conditional", "reflection_supported", "operation"])
def test_reverse_reflection_repeats_original_supported_operation(tmp_path, field):
    """Resolved transport cannot repair a newly conditional or rejected reflection operation."""
    result = fixture(tmp_path, "reverse")
    edge = selected(result, "qt_cpp_qml_property_read")
    source = next(node for node in result["nodes"] if node["id"] == edge["source"])
    assert accepted(result, edge)
    update_qt(source, **{field: {"conditional": True, "reflection_supported": False, "operation": "invokeMethod"}[field]})
    assert not accepted(result, edge)
    assert not build_from_json(result, root=tmp_path).has_edge(edge["source"], edge["target"])
