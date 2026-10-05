"""REQ-QML-007-AC03: handler formals own their names across production boundaries."""
from __future__ import annotations

import json

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extract import extract
from graphify.extractors.qml import extract_qml
from graphify.paths import load_node_link_graph
from graphify.qml_resolution_types import qml_metadata
from tests.qt_analysis_helpers import analysis


def qml(style, parameters="int count"):
    """Legacy injection and renamed explicit formals observe different dependencies."""
    handler = {
        "legacy": "onReady: { count; }",
        "arrow": "onReady: (renamed) => { count; renamed; }",
        "anonymous": "onReady: function(renamed) { count; renamed; }",
        "connections": "property Connections observer: Connections { target: root; "
                       "function onReady(renamed) { count; renamed; } }",
    }[style]
    return "\ufeff// café\r\nimport QtQml\r\nQtObject { id: root; property int count: 1; " + \
        f"signal ready({parameters}); {handler} }}\r\n"


@pytest.mark.parametrize("style", ["legacy", "arrow", "anonymous", "connections"])
@pytest.mark.parametrize("directed", [False, True])
def test_req_qml007_ac03_source_handler_formals_preserve_property_dependency(tmp_path, style, directed):
    """Direct facts carry authority; facade, build and reload retain exact bindings."""
    source = qml(style)
    result = analysis(tmp_path, {"Main.qml": source})
    direct = extract_qml(tmp_path / "Main.qml", root=tmp_path)
    handler = next(node for node in direct["nodes"] if qml_metadata(node).get("kind") == "handler")
    md = qml_metadata(handler)
    assert md["implicit_parameters"] is (style == "legacy")
    span = md["span"]
    original = source.encode()[span["start_byte"]:span["end_byte"]]
    assert original.startswith(b"function onReady" if style == "connections" else b"onReady")
    assert handler["source_file"] == "Main.qml" and handler["source_location"].startswith("L3")
    direct_reads = {qml_metadata(node)["reference"]: qml_metadata(node) for node in direct["nodes"]
                    if qml_metadata(node).get("kind") == "read"}
    assert direct_reads["count"]["lexical_shadowed"] is (style == "legacy")
    if style != "legacy":
        assert direct_reads["renamed"]["lexical_shadowed"] is True
    graph = build_from_json(result, root=tmp_path, directed=directed)
    output = tmp_path / "handler.json"
    assert to_json(graph, {}, str(output), force=True)
    restored = load_node_link_graph(json.loads(output.read_text(encoding="utf-8")))
    reads = {qml_metadata(node)["reference"]: (identity, qml_metadata(node))
             for identity, node in restored.nodes(data=True) if qml_metadata(node).get("kind") == "read"}
    identity, count = reads["count"]
    assert count["status"] == ("dynamic" if style == "legacy" else "resolved")
    read_edges = [(a, b, data) for a, b, data in restored.edges(data=True)
                  if data.get("context") == "qml_binding_read" and data.get("_src", a) == identity]
    assert len(read_edges) == (0 if style == "legacy" else 1)
    if style != "legacy":
        assert reads["renamed"][1]["status"] == "dynamic"
        assert qml_metadata(restored.nodes[count["resolved_target_id"]])["raw_name"] == "count"
        assert restored.has_edge(identity, count["resolved_target_id"])
    subscriptions = [data for _, _, data in restored.edges(data=True) if data.get("context") == "qml_signal_subscription"]
    assert len(subscriptions) == 1


@pytest.mark.parametrize("style", ["legacy", "arrow"])
def test_req_qml007_ac03_handler_authority_survives_parameter_display_limit(tmp_path, style):
    """The last supported signal parameter retains exact lexical authority."""
    names = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVW"
    parameters = ", ".join([f"int {name}" for name in names] + ["int count"])
    result = analysis(tmp_path, {"Main.qml": qml(style, parameters)})
    read = next(qml_metadata(node) for node in result["nodes"]
                if qml_metadata(node).get("kind") == "read" and qml_metadata(node).get("reference") == "count")
    assert read["status"] == ("dynamic" if style == "legacy" else "resolved")
    assert read["lexical_shadowed"] is (style == "legacy")


@pytest.mark.parametrize("style", ["legacy", "arrow"])
def test_req_qml007_ac03_signal_parameter_overflow_rejects_without_truncation(tmp_path, style):
    """Unsupported signatures fail closed before a hidden binder can resolve."""
    names = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWX"
    parameters = ", ".join([f"int {name}" for name in names] + ["int count"])
    path = tmp_path / "Main.qml"
    path.write_text(qml(style, parameters), encoding="utf-8", newline="")
    direct = extract_qml(path, root=tmp_path)
    facade = extract([path], root=tmp_path, parallel=False)
    assert direct["qml_failures"][0]["code"] == "QML_LIMIT"
    assert facade["qml_failures"][0]["code"] == "QML_LIMIT"
    assert not direct["nodes"] and not facade["nodes"]


def test_req_qml007_ac03_handler_change_does_not_reclassify_unrelated_javascript(tmp_path):
    """Ordinary JavaScript retains its generic callable IDs and source metadata."""
    script = tmp_path / "keep.js"
    script.write_text("function helper(count) { return count; }\n", encoding="utf-8")
    before = extract([script], root=tmp_path, cache_root=tmp_path / ".before", parallel=False)
    after = analysis(tmp_path, {"Main.qml": qml("arrow"), "keep.js": script.read_text(encoding="utf-8")})
    def selected(result):
        return ([node for node in result["nodes"] if node.get("source_file") == "keep.js"],
                [edge for edge in result["edges"] if edge.get("source_file") == "keep.js"])
    assert selected(after) == selected(before)
    assert not any(qml_metadata(node) for node in selected(after)[0])
