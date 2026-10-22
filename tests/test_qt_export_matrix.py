"""Qt semantic exports versus explicit presentation-only format boundaries."""
from __future__ import annotations

import json
import re
import sys
from types import SimpleNamespace

import networkx as nx
import pytest

from graphify.build import build_from_json
from graphify.export import to_canvas, to_cypher, to_obsidian, to_svg
from graphify.exporters.graphdb import push_to_falkordb, push_to_neo4j
from graphify.qt_export import qt_cypher_lines
from tests.test_qt_qml_integration import corpus


def actual_graph(root):
    result = corpus(root)
    return result, build_from_json(result, root=root)


def test_actual_cypher_file_retains_metadata_sources_and_native_call_direction(tmp_path):
    result, graph = actual_graph(tmp_path)
    output = tmp_path / "native.cypher"
    to_cypher(graph, str(output))
    text = output.read_text(encoding="utf-8")
    serialized = re.findall(r'`metadata_json`:("(?:[^"\\]|\\.)*")', text)
    restored = [json.loads(json.loads(value)) for value in serialized]
    expected = [data["metadata"] for _, data in graph.nodes(data=True) if data.get("metadata")]
    expected += [data["metadata"] for _, _, data in graph.edges(data=True) if data.get("metadata")]
    assert sorted(map(lambda value: json.dumps(value, sort_keys=True), restored)) == sorted(
        map(lambda value: json.dumps(value, sort_keys=True), expected))
    call = next(edge for edge in result["edges"] if edge.get("context") == "qml_js_call")
    match = f'MATCH (a {{id:{json.dumps(call["source"])}}}), (b {{id:{json.dumps(call["target"])}}})'
    assert match in text
    assert "`source_location`:" in text and "`context`:" in text and "`confidence`:" in text
    assert "metadata_json" in text and "graphify_fact_key" in text


@pytest.mark.parametrize("backend", ["neo4j", "falkordb"])
def test_actual_push_driver_boundary_keeps_native_metadata_and_logical_direction(tmp_path, monkeypatch, backend):
    result, graph = actual_graph(tmp_path)
    calls = []

    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def run(self, query, **params):
            calls.append((query, params))

        def query(self, query, params=None):
            calls.append((query, params or {}))

    if backend == "neo4j":
        driver = SimpleNamespace(session=Session, close=lambda: None)
        module = SimpleNamespace(GraphDatabase=SimpleNamespace(driver=lambda *_, **__: driver))
        monkeypatch.setitem(sys.modules, "neo4j", module)
        pushed = push_to_neo4j(graph, "unused", "", "")
    else:
        client = SimpleNamespace(select_graph=lambda _: Session())
        monkeypatch.setitem(sys.modules, "falkordb", SimpleNamespace(FalkorDB=lambda **_: client))
        pushed = push_to_falkordb(graph, "unused")
    assert pushed == {"nodes": len(graph), "edges": graph.number_of_edges()}
    node_props = {params["id"]: params["props"] for query, params in calls if query.startswith("MERGE (n:")}
    for node_id, data in graph.nodes(data=True):
        assert node_props[node_id].get("source_file") == data.get("source_file")
        if data.get("metadata"):
            assert json.loads(node_props[node_id]["metadata_json"]) == data["metadata"]
    exported = {(params["src"], params["tgt"]): params["props"]
                for query, params in calls if query.startswith("MATCH")}
    call = next(edge for edge in result["edges"] if edge.get("context") == "qml_js_call")
    props = exported[(call["source"], call["target"])]
    assert props["context"] == "qml_js_call" and props["confidence"] == "INFERRED"
    assert json.loads(props["metadata_json"]) == graph.edges[call["source"], call["target"]]["metadata"]
    assert props["graphify_source"] == call["source"] and props["graphify_target"] == call["target"]
    assert all("fact_key" in params for query, params in calls if query.startswith("MATCH"))


def test_cypher_keeps_parallel_mechanisms_and_escapes_literal_data(tmp_path):
    _, base = actual_graph(tmp_path)
    graph = nx.MultiDiGraph(base)
    graph.add_edge("extra", "second", relation="references", context="qt_connect_signal", confidence="INFERRED")
    graph.add_edge("extra", "second", relation="references", context="qt_disconnect_signal", confidence="INFERRED")
    graph.nodes["extra"].update(label='quote"\\\n<script>', **{"odd`key": "literal"})
    lines = qt_cypher_lines(graph)
    assert lines is not None
    endpoints = [line for line in lines if 'MATCH (a {id:"extra"}), (b {id:"second"})' in line]
    assert len(endpoints) == 2 and endpoints[0] != endpoints[1]
    assert '`odd``key`:"literal"' in "\n".join(lines)
    assert 'quote\\"\\\\\\n<script>' in "\n".join(lines)
    assert graph.nodes["extra"]["label"] == 'quote"\\\n<script>'


def test_non_qt_cypher_uses_legacy_export_without_extra_json_properties(tmp_path):
    graph = nx.Graph()
    graph.add_node("normal", label="normal()", file_type="code", metadata={"ordinary": "kept"})
    graph.add_edge("normal", "other", relation="calls")
    assert qt_cypher_lines(graph) is None
    path = tmp_path / "ordinary.cypher"
    to_cypher(graph, str(path))
    assert "MERGE" in path.read_text() and "metadata_json" not in path.read_text()


@pytest.mark.parametrize("field", ["metadata_json", "attributes_json", "graphify_source", "graphify_target", "graphify_fact_key"])
def test_reserved_transport_collisions_fail_before_file_or_driver_boundary(tmp_path, monkeypatch, field):
    _, graph = actual_graph(tmp_path)
    if field.endswith("_json"):
        graph.nodes[next(iter(graph))][field] = "original public value"
    else:
        next(iter(graph.edges(data=True)))[2][field] = "original public value"
    output = tmp_path / "preserved.cypher"
    output.write_text("previous valid export", encoding="utf-8")
    with pytest.raises(ValueError, match="QT_EXPORT_PROPERTY_COLLISION"):
        to_cypher(graph, str(output))
    assert output.read_text(encoding="utf-8") == "previous valid export"
    def forbidden(*_, **__):
        pytest.fail("Collision preflight must precede database creation or connection")
    monkeypatch.setitem(sys.modules, "neo4j", SimpleNamespace(GraphDatabase=SimpleNamespace(driver=forbidden)))
    monkeypatch.setitem(sys.modules, "falkordb", SimpleNamespace(FalkorDB=forbidden))
    with pytest.raises(ValueError, match="QT_EXPORT_PROPERTY_COLLISION"):
        push_to_neo4j(graph, "unused", "", "")
    with pytest.raises(ValueError, match="QT_EXPORT_PROPERTY_COLLISION"):
        push_to_falkordb(graph, "unused")


def test_canvas_and_obsidian_are_documented_presentation_views_not_fact_backups(tmp_path):
    _, graph = actual_graph(tmp_path)
    output = tmp_path / "visual.canvas"
    to_canvas(graph, {}, str(output))
    canvas = json.loads(output.read_text())
    assert len([node for node in canvas["nodes"] if node["type"] == "file"]) == len(graph)
    assert all("metadata" not in node for node in canvas["nodes"])
    assert all("context" not in edge and "source_location" not in edge for edge in canvas["edges"])
    vault = tmp_path / "notes"
    assert to_obsidian(graph, {}, str(vault)) >= len(graph)
    notes = "\n".join(path.read_text(encoding="utf-8") for path in vault.glob("*.md"))
    assert 'source_file: "Main.qml"' in notes and 'location: "L' in notes
    assert "INFERRED" in notes and "native_endpoint" not in notes


def test_svg_is_an_optional_visualization_without_semantic_roundtrip(tmp_path):
    pytest.importorskip("matplotlib", reason="Presentation SVG requires the optional svg extra")
    _, graph = actual_graph(tmp_path)
    output = tmp_path / "visual.svg"
    to_svg(graph, {}, str(output))
    text = output.read_text(encoding="utf-8")
    assert "<svg" in text and "native_endpoint" not in text and "raw_values" not in text
