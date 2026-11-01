"""Typed bridge evidence survives the production builder and fails closed."""
import copy

import pytest

from graphify.build import build_from_json
from graphify.extract import extract
from graphify.extractors.qt_cpp_facts import encode_qt, qt_metadata
from graphify.paths import load_node_link_graph
from graphify.export import to_json


def bridge(tmp_path):
    cpp = tmp_path / "backend.cpp"
    cpp.write_text('''class Backend : public QObject {
    Q_OBJECT
    public: Q_INVOKABLE int refresh() { return 1; }
    signals: void ready(int value);
    };
    void registerTypes() { qmlRegisterType<Backend>("Demo.Tools", 1, 0, "Service"); }
    ''', encoding="utf-8")
    qml = tmp_path / "Main.qml"
    qml.write_text('import Demo.Tools 1.0\nService { property int count: refresh(); onReady: count = 1 }', encoding="utf-8")
    result = extract([cpp, qml], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert not result["qml_failures"] and not result["failed_sources"]
    return result


def test_native_import_call_and_subscription_survive_default_graph_reload(tmp_path):
    result = bridge(tmp_path)
    graph = build_from_json(result, root=tmp_path)
    calls = [edge for edge in result["edges"] if edge.get("relation") == "calls" and qt_metadata(edge).get("native_endpoint")]
    assert len(calls) == 1
    endpoint = calls[0]
    assert graph.has_edge(endpoint["source"], endpoint["target"])
    assert graph.edges[endpoint["source"], endpoint["target"]]["relation"] == "calls"
    exported = tmp_path / "graph.json"
    assert to_json(graph, {}, str(exported))
    loaded = load_node_link_graph(exported)
    assert loaded.edges[endpoint["source"], endpoint["target"]]["_src"] == endpoint["source"]
    assert loaded.edges[endpoint["source"], endpoint["target"]]["_tgt"] == endpoint["target"]
    contexts = {data.get("context") for _, _, data in loaded.edges(data=True)}
    assert {"qml_import_resolution", "qml_type_resolution", "qml_signal_subscription"} <= contexts


@pytest.mark.parametrize("damage", ["missing", "target", "class", "member", "provider"])
def test_bridge_context_and_label_cannot_replace_exact_endpoint_proof(tmp_path, damage):
    result = bridge(tmp_path)
    edge = next(edge for edge in result["edges"] if edge.get("relation") == "calls" and qt_metadata(edge).get("native_endpoint"))
    source, target = edge["source"], edge["target"]
    values = qt_metadata(edge)
    proof = copy.deepcopy(values["native_endpoint"])
    if damage == "missing":
        edge["metadata"].pop("qt")
    else:
        field = {"target": "canonical_target_id", "class": "class_id", "member": "member_fact_id", "provider": "provider_id"}[damage]
        proof[field] = source
        edge["metadata"]["qt"] = encode_qt({**values, "native_endpoint": proof})
    graph = build_from_json(result, root=tmp_path)
    assert not graph.has_edge(source, target)
