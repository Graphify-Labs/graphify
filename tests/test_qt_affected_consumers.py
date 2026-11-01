"""QML-013-AC02 changed members reach source owners without propagation calls."""
import pytest

from graphify.affected import affected_nodes, load_graph
from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extractors.qml_facts import qml_metadata
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.qt_affected import owned_ancestors
from tests.qt_analysis_helpers import analysis, sites
from tests.test_qt_signals_slots import SOURCE


@pytest.mark.parametrize("directed", [False, True])
def test_property_change_reports_binding_and_owning_component(tmp_path, directed):
    result = analysis(tmp_path, {"Main.qml": 'import QtQml\nQtObject { property int input: 1; property int output: input }'})
    graph = build_from_json(result, directed=directed, root=tmp_path)
    path = tmp_path / "graph.json"
    assert to_json(graph, {}, str(path), force=True)
    loaded = load_graph(path)
    prop = next(node for node in result["nodes"] if qml_metadata(node).get("kind") == "property" and qml_metadata(node).get("raw_name") == "input")
    component = next(node for node in result["nodes"] if qml_metadata(node).get("kind") == "component")
    dependent = next(node for node in result["nodes"] if qml_metadata(node).get("kind") == "property" and qml_metadata(node).get("raw_name") == "output")
    hits = {hit.node_id for hit in affected_nodes(loaded, prop["id"], depth=2)}
    assert dependent["id"] in hits and component["id"] in hits


def test_native_signal_changes_report_connection_owner_with_references_filter(tmp_path):
    result = analysis(tmp_path, {"events.cpp": SOURCE})
    graph = build_from_json(result, directed=True, root=tmp_path)
    signal = qt_metadata(sites(result, "connect")[0])["signal_target_id"]
    connection = sites(result, "connect")[0]
    hits = {hit.node_id for hit in affected_nodes(graph, signal, relations=["references"], depth=2)}
    assert connection["id"] in hits and qt_metadata(connection)["owner_id"] in hits
    assert not {connection["id"]} & {hit.node_id for hit in affected_nodes(graph, signal, relations=["calls"], depth=2)}


def test_future_metadata_or_foreign_file_ownership_is_not_dependency_evidence(tmp_path):
    """Only current source-owned contains links may promote a dependency site."""
    result = analysis(tmp_path, {"Main.qml": 'import QtQml\nQtObject { property int input: 1; property int output: input }'})
    graph = build_from_json(result, directed=True, root=tmp_path)
    read = next(node for node in result["nodes"] if qml_metadata(node).get("kind") == "read")
    ancestors = list(owned_ancestors(graph, read["id"]))
    assert ancestors and len(list(owned_ancestors(graph, read["id"], limit=2))) == 1
    graph.nodes[read["id"]]["metadata"]["qml"]["contract_version"] = 2
    assert not list(owned_ancestors(graph, read["id"]))
    graph.nodes[read["id"]]["metadata"]["qml"]["contract_version"] = 1
    graph.nodes[ancestors[0][0]]["source_file"] = "Other.qml"
    assert not list(owned_ancestors(graph, read["id"]))
