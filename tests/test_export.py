import json
import xml.etree.ElementTree as ET

from graphify.export import to_canvas, to_cypher, to_graphml, to_html, to_obsidian
from tests.native_helpers import graph_from_payload


def _graph():
    return graph_from_payload(
        [
            {"id": "a", "label": "Auth", "file_type": "code", "source_file": "auth.py"},
            {"id": "b", "label": "API", "file_type": "code", "source_file": "api.py"},
        ],
        [{"source": "a", "target": "b", "relation": "calls", "confidence": "INFERRED", "weight": 0.5}],
        kind="digraph",
    )


def test_native_presentation_exports(tmp_path):
    graph = _graph()
    communities = {0: ["a"], 1: ["b"]}
    labels = {0: "Security", 1: "Interface"}
    html = tmp_path / "graph.html"
    graphml = tmp_path / "graph.graphml"
    cypher = tmp_path / "graph.cypher"
    canvas = tmp_path / "graph.canvas"
    vault = tmp_path / "vault"
    to_html(graph, communities, str(html), community_labels=labels)
    to_graphml(graph, communities, str(graphml))
    to_cypher(graph, str(cypher))
    to_canvas(graph, communities, str(canvas), community_labels=labels)
    assert to_obsidian(graph, communities, str(vault), community_labels=labels) == 4
    assert "Auth" in html.read_text() and "calls" in html.read_text()
    ET.parse(graphml)
    assert "INFERRED" in graphml.read_text()
    assert "MERGE" in cypher.read_text() and "CALLS" in cypher.read_text()
    canvas_nodes = json.loads(canvas.read_text())["nodes"]
    assert len([node for node in canvas_nodes if node["type"] == "file"]) == 2
    assert (vault / "Auth.md").is_file() and (vault / "API.md").is_file()


def test_typed_ids_export_without_collision(tmp_path):
    graph = graph_from_payload(
        [{"id": 1, "label": "Integer"}, {"id": "1", "label": "String"}],
        [{"source": 1, "target": "1", "relation": "links"}],
    )
    output = tmp_path / "typed.graphml"
    to_graphml(graph, {0: [1, "1"]}, str(output))
    root = ET.parse(output).getroot()
    ids = [element.attrib["id"] for element in root.findall(".//{*}node")]
    assert len(ids) == len(set(ids)) == 2


def test_export_escapes_hostile_labels(tmp_path):
    graph = graph_from_payload(
        [{"id": "a", "label": "</script><script>alert(1)</script>", "source_file": "a.py"}]
    )
    output = tmp_path / "safe.html"
    to_html(graph, {0: ["a"]}, str(output))
    text = output.read_text()
    assert "</script><script>alert(1)" not in text
