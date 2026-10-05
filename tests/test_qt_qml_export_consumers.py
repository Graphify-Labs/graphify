"""Actual native bridge evidence survives supported machine-readable exports."""
from __future__ import annotations

import json

import networkx as nx
import pytest

from graphify.build import build_from_json
from graphify.export import to_graphml, to_json
from graphify.extractors.qml_facts import qml_metadata
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.paths import load_node_link_graph
from graphify.serve import _shortest_path_text
from tests.test_qt_qml_integration import corpus


def bridge_edges(result):
    return [edge for edge in result["edges"] if qt_metadata(edge).get("native_endpoint")]


def test_directed_graphml_roundtrip_keeps_native_evidence_and_literal_source_fields(tmp_path):
    result = corpus(tmp_path)
    graph = build_from_json(result, root=tmp_path, directed=True)
    output = tmp_path / "native.graphml"
    to_graphml(graph, {}, str(output))
    restored = nx.read_graphml(output)
    assert restored.is_directed()
    assert set(restored) == set(graph)
    assert set(restored.edges) == set(graph.edges)
    for node_id, original in graph.nodes(data=True):
        if original.get("metadata"):
            data = dict(restored.nodes[node_id])
            data["metadata"] = json.loads(data["metadata"])
            assert qml_metadata(data) == qml_metadata(original)
            assert qt_metadata(data) == qt_metadata(original)
            assert data["source_file"] == original["source_file"]
            assert data["source_location"] == original["source_location"]
    for edge in bridge_edges(result):
        data = dict(restored.edges[edge["source"], edge["target"]])
        data["metadata"] = json.loads(data["metadata"])
        assert qt_metadata(data)["native_endpoint"] == qt_metadata(edge)["native_endpoint"]
        assert (data["relation"], data["context"], data["confidence"]) == (
            edge["relation"], edge["context"], "INFERRED")
        assert (data["source_file"], data["source_location"]) == (edge["source_file"], edge["source_location"])


@pytest.mark.parametrize("directed", [False, True])
def test_json_repeated_native_mechanisms_remain_distinct_and_directional(tmp_path, directed):
    qml = '''import Demo 1.0 as Native
Native.Backend {
 property int first: next(1)
 property int second: next(2)
 property int third: value
 property int fourth: value
 onValueChanged: { next(value); }
}'''
    result = corpus(tmp_path, qml=qml)
    expected = bridge_edges(result)
    calls = [edge for edge in expected if edge["relation"] == "calls"]
    assert len(calls) == 3
    assert len({edge["source"] for edge in calls}) == 3
    assert len({edge["target"] for edge in calls}) == 1
    graph = build_from_json(result, root=tmp_path, directed=directed)
    output = tmp_path / "native.json"
    assert to_json(graph, {}, str(output), force=True)
    restored = load_node_link_graph(json.loads(output.read_text(encoding="utf-8")))
    for edge in expected:
        data = restored.edges[edge["source"], edge["target"]]
        assert (data.get("_src", edge["source"]), data.get("_tgt", edge["target"])) == (edge["source"], edge["target"])
        assert qt_metadata(data)["native_endpoint"] == qt_metadata(edge)["native_endpoint"]
        assert data["relation"] == edge["relation"] and data["confidence"] == "INFERRED"
        assert data["source_file"] == "Main.qml" and data["source_location"].startswith("L")


def test_native_path_reports_qml_call_site_and_cpp_declaration_without_reversing_flow(tmp_path):
    result = corpus(tmp_path)
    graph = build_from_json(result, root=tmp_path, directed=True)
    call = next(edge for edge in bridge_edges(result) if edge["relation"] == "calls")
    route = _shortest_path_text(graph, {"source": call["source"], "target": call["target"]})
    assert "Shortest path (1 hops)" in route and "--calls [INFERRED]-->" in route
    assert f'Main.qml:{call["source_location"]}' in route
    target = graph.nodes[call["target"]]
    assert f'backend.hpp:{target["source_location"]}' in route
    assert "qml_js_call" in route
    assert "native_endpoint" not in route and "raw_values" not in route
    reverse = _shortest_path_text(graph, {"source": call["target"], "target": call["source"]})
    assert "No directed path found" in reverse
