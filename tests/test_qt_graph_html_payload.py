"""QML-013-AC03 ordinary graph HTML retains source facts and readable semantics."""
import copy
import json
import re
import subprocess

import pytest

from graphify.build import build_from_json
from graphify.export import to_html
from graphify.qt_qml_search import SEARCH_NAMESPACE
from tests.qt_analysis_helpers import analysis, sites
from tests.test_export import _run_node_info_harness
from tests.test_qt_signals_slots import SOURCE


def payload(content, name):
    match = re.search(r"const " + name + r" = (\[.*?\]);", content, re.DOTALL)
    assert match
    return json.loads(match[1])


def runtime_info(content, node_id, monkeypatch):
    """Run the existing viewer harness via stdin, avoiding Windows argv limits."""
    original = subprocess.run

    def via_stdin(command, **kwargs):
        assert command[1] == "-e"
        return original([command[0], "-"], input=command[2], **kwargs)

    with monkeypatch.context() as context:
        context.setattr(subprocess, "run", via_stdin)
        return _run_node_info_harness(content, node_id)


@pytest.mark.parametrize("directed", [False, True])
def test_qml013_ac03_graph_html_payload_preserves_contracts_source_and_user_attributes(tmp_path, directed):
    """Actual export keeps metadata, status and logical direction without mutating G."""
    result = analysis(tmp_path, {"events.cpp": SOURCE, "Main.qml": 'import QtQml\nQtObject { property int x: absent }'})
    graph = build_from_json(result, root=tmp_path, directed=directed)
    connection = sites(result, "connect")[0]
    graph.nodes[connection["id"]]["attributes"] = {"custom": {"value": "retain"}}
    before = copy.deepcopy((dict(graph.nodes(data=True)), list(graph.edges(data=True))))
    path = tmp_path / "graph.html"
    to_html(graph, {0: list(graph)}, str(path))
    content = path.read_text(encoding="utf-8")
    nodes = {node["id"]: node for node in payload(content, "RAW_NODES")}
    node = nodes[connection["id"]]
    assert node["metadata"] == graph.nodes[connection["id"]]["metadata"]
    assert node["attributes"]["custom"] == {"value": "retain"}
    assert node["attributes"][SEARCH_NAMESPACE]["qt"]["declared_type"] == "QueuedConnection"
    assert node["qt_qml"] == node["attributes"][SEARCH_NAMESPACE]
    assert node["source_file"] == "events.cpp" and node["source_location"] == connection["source_location"]
    for original in result["edges"]:
        if original.get("context") != "qt_connect_signal":
            continue
        edge = next(edge for edge in payload(content, "RAW_EDGES") if edge["from"] == original["source"] and edge["to"] == original["target"])
        assert edge["metadata"] == original["metadata"]
        assert edge["context"] == original["context"] and edge["confidence"] == "INFERRED"
        assert edge["source_file"] == "events.cpp" and edge["source_location"] == original["source_location"]
        assert "connection signal" in edge["title"]
    assert (dict(graph.nodes(data=True)), list(graph.edges(data=True))) == before


def test_qml013_ac03_html_runtime_shows_projected_fields_and_escapes_original_literal_values(tmp_path, monkeypatch):
    """Execute the written viewer script, including the live node-info projection."""
    result = analysis(tmp_path, {"events.cpp": SOURCE})
    graph = build_from_json(result, root=tmp_path)
    connection = sites(result, "connect")[0]
    path = tmp_path / "graph.html"
    to_html(graph, {0: list(graph)}, str(path))
    info = runtime_info(path.read_text(encoding="utf-8"), connection["id"], monkeypatch)
    assert "QT declared type: QueuedConnection" in info
    assert "QT status: resolved" in info and "Location: L" in info
    assert "raw_values" not in info and "owner_scope_key" not in info
    # Producer facts may contain arbitrary source names. The projection is text,
    # and JSON script escaping retains literal metadata without tag breakout.
    poisoned = copy.deepcopy(graph)
    from graphify.extractors.qt_cpp_facts import update_qt
    update_qt(poisoned.nodes[connection["id"]], raw_name='</script><script>alert(1)</script>')
    to_html(poisoned, {0: list(poisoned)}, str(path))
    content = path.read_text(encoding="utf-8")
    assert '</script><script>alert(1)</script>' not in content
    info2 = runtime_info(content, connection["id"], monkeypatch)
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in info2 and "<script>alert(1)</script>" not in info2


def test_qml013_ac03_existing_search_namespace_and_generic_payload_are_preserved(tmp_path):
    """Public user attributes win; ordinary HTML nodes retain their prior schema."""
    result = analysis(tmp_path, {"events.cpp": SOURCE, "plain.py": 'def ordinary():\n    return 1\n'})
    graph = build_from_json(result, root=tmp_path)
    connection = sites(result, "connect")[0]
    graph.nodes[connection["id"]]["attributes"] = {SEARCH_NAMESPACE: {"custom": "owned"}, "keep": 1}
    path = tmp_path / "graph.html"
    to_html(graph, {0: list(graph)}, str(path))
    nodes = {node["id"]: node for node in payload(path.read_text(encoding="utf-8"), "RAW_NODES")}
    assert nodes[connection["id"]]["attributes"] == {SEARCH_NAMESPACE: {"custom": "owned"}, "keep": 1}
    assert "qt_qml" not in nodes[connection["id"]]
    generic = next(node for node in nodes.values() if node.get("source_file") == "plain.py")
    assert "metadata" not in generic and "attributes" not in generic and "source_location" not in generic


def test_qml013_ac03_aggregated_html_explicitly_states_source_fact_omission(tmp_path):
    """An aggregate artifact cannot imply that its two communities retain facts."""
    result = analysis(tmp_path, {"events.cpp": SOURCE})
    graph = build_from_json(result, root=tmp_path)
    nodes = list(graph)
    communities = {0: nodes[:len(nodes) // 2], 1: nodes[len(nodes) // 2:]}
    before = copy.deepcopy(graph.graph)
    path = tmp_path / "aggregate.html"
    assert to_html(graph, communities, str(path), node_limit=2)
    content = path.read_text(encoding="utf-8")
    assert len(payload(content, "RAW_NODES")) == 2
    assert "Qt/QML source details are omitted in this community view" in content
    assert graph.graph == before
