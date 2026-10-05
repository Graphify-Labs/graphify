"""REQ-QML-018-AC06: borrowed typed declarations retain their source authority."""
from __future__ import annotations

import copy

import pytest

from graphify.extractors.qt_cpp_facts import qt_metadata, update_qt
from graphify.qt_qml_projection import allows_qt_qml_edge
from tests.qt_adoption_fixture import NATIVE, QML, sources
from tests.qt_analysis_helpers import analysis


def serialized_subscription(result, *, notify=False):
    """Copy accepted producer output before altering one consumer-owned proof input."""
    nodes, edges = copy.deepcopy((result["nodes"], result["edges"]))
    by_id = {node["id"]: node for node in nodes}
    edge = next(item for item in edges if item.get("context") == "qt_context_subscription"
                and bool(qt_metadata(item)["endpoint_proof"].get("notify_property_id")) is notify)
    source, target = by_id[edge["source"]], by_id[edge["target"]]
    def accepted():
        return allows_qt_qml_edge(source, target, edge, source_id=source["id"], target_id=target["id"], nodes=by_id)
    assert accepted()
    return nodes, by_id, edge, accepted


@pytest.mark.parametrize("corruption", ["getter_arity", "accessor_owner", "accessor_file", "accessor_span",
    "accessor_name", "factory_callable", "factory_class", "factory_owner", "property_owner",
    "factory_file", "factory_span", "property_file", "property_span", "getter_callable"])
def test_req_qml018_ac06_typed_hop_rejects_altered_authoritative_declaration(tmp_path, corruption):
    """Canonical type IDs do not repair changed source ownership, callable roles or READ arity."""
    nodes, by_id, _, accepted = serialized_subscription(analysis(tmp_path, sources(tmp_path)))
    def chosen(kind, name):
        return next(node for node in nodes if qt_metadata(node).get("kind") == kind
                    and qt_metadata(node).get("raw_name") == name)
    prop, getter, factory = chosen("property", "service"), chosen("member", "service"), chosen("member", "makeBackend")
    accessor = next(node for node in nodes if qt_metadata(node).get("kind") == "property_accessor"
                    and qt_metadata(node).get("property_id") == prop["id"] and qt_metadata(node).get("accessor_role") == "read")
    target = accessor if corruption.startswith("accessor") else prop if corruption.startswith("property") else getter if corruption.startswith("getter") else factory
    if corruption == "getter_arity":
        update_qt(target, parameter_types=["int"])
    elif corruption.endswith("callable") or corruption == "factory_class":
        by_id[qt_metadata(target)["generic_target_id"]]["_callable_class" if corruption == "factory_class" else "_callable"] = corruption == "factory_class"
    elif corruption.endswith("owner"):
        update_qt(target, owner_id="missing")
    elif corruption.endswith("file"):
        target["source_file"] = "Main.qml"
    elif corruption.endswith("name"):
        update_qt(target, raw_name="unrelated")
    else:
        span = qt_metadata(target)["span"]
        span["start_byte"] += 1_000_000
        span["end_byte"] += 1_000_000
        update_qt(target, span=span)
    assert not accepted()


@pytest.mark.parametrize("corruption", ["owner", "file", "span", "name", "property_owner"])
def test_req_qml018_ac06_typed_notify_revalidates_property_accessor_provenance(tmp_path, corruption):
    """A property-change subscription retains the same owner/name/file/span guard as lookup."""
    native = NATIVE.replace("Q_PROPERTY(int count READ count)", "Q_PROPERTY(int count READ count NOTIFY actualCount)")
    native = native.replace("signals: void ready();", "signals: void ready(); void actualCount();")
    result = analysis(tmp_path, sources(tmp_path, native=native, qml=QML.replace("function onReady()", "function onCountChanged()")))
    nodes, by_id, edge, accepted = serialized_subscription(result, notify=True)
    prop = by_id[qt_metadata(edge)["endpoint_proof"]["notify_property_id"]]
    accessor = next(node for node in nodes if qt_metadata(node).get("kind") == "property_accessor"
                    and qt_metadata(node).get("property_id") == prop["id"] and qt_metadata(node).get("accessor_role") == "notify")
    if corruption in {"owner", "property_owner"}:
        update_qt(prop if corruption == "property_owner" else accessor, owner_id="missing")
    elif corruption == "file":
        accessor["source_file"] = "Main.qml"
    elif corruption == "name":
        update_qt(accessor, raw_name="unrelated")
    else:
        span = qt_metadata(accessor)["span"]
        span["start_byte"] += 1_000_000
        span["end_byte"] += 1_000_000
        update_qt(accessor, span=span)
    assert not accepted()


@pytest.mark.parametrize("directed", [False, True])
def test_req_qml018_ac04_ac06_reloaded_notify_proof_retains_mapping_identity(tmp_path, directed):
    """Persisted NetworkX mappings lend the same accepted NOTIFY authority as raw producer nodes."""
    import json
    from graphify.build import build_from_json
    from graphify.export import to_json
    from graphify.paths import load_node_link_graph
    native = NATIVE.replace("Q_PROPERTY(int count READ count)", "Q_PROPERTY(int count READ count NOTIFY actualCount)")
    native = native.replace("signals: void ready();", "signals: void ready(); void actualCount();")
    result = analysis(tmp_path, sources(tmp_path, native=native, qml=QML.replace("function onReady()", "function onCountChanged()")))
    graph = build_from_json(result, root=tmp_path, directed=directed)
    path = tmp_path / "graph.json"
    assert to_json(graph, {}, str(path), force=True)
    restored = load_node_link_graph(json.loads(path.read_text(encoding="utf-8")))
    for edge in result["edges"]:
        if edge.get("context") == "qt_context_subscription" and qt_metadata(edge)["endpoint_proof"].get("notify_property_id"):
            source, target = edge["source"], edge["target"]
            assert allows_qt_qml_edge(restored.nodes[source], restored.nodes[target], restored.edges[source, target],
                                      source_id=source, target_id=target, nodes=restored.nodes)
