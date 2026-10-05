"""QML-013-AC01 exact scope and metadata through actual query/explain/path CLI."""
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.serve import _load_graph, _node_attributes_text, _shortest_path_text
from graphify.qt_qml_search import search_attributes
from tests.qt_analysis_helpers import analysis, sites
from tests.qt_consumer_helpers import cli, saved_graph
from tests.test_qt_signals_slots import SOURCE


def test_cli_query_explain_and_path_use_source_scoped_nodes(tmp_path, monkeypatch, capsys):
    path, result, component, prop, read = saved_graph(tmp_path)
    query = cli(monkeypatch, capsys, path, "query", read["id"])
    assert "Main.qml" in query and "INFERRED" in query
    explanation = cli(monkeypatch, capsys, path, "explain", prop["id"])
    assert "Main.qml" in explanation and prop["id"] in explanation
    route = cli(monkeypatch, capsys, path, "path", component["id"], prop["id"])
    assert "No path" not in route and "input" in route
    loaded = _load_graph(str(path))
    text = _shortest_path_text(loaded, {"source": component["id"], "target": prop["id"]})
    assert "input" in text and "Main.qml" in text
    other_ids = {node["id"] for node in result["nodes"] if node["source_file"] == "Other.qml"}
    assert not other_ids & {target for _, target in loaded.out_edges(read["id"])}


def test_public_connection_type_is_searchable_without_opaque_transport(tmp_path):
    result = analysis(tmp_path, {"events.cpp": SOURCE})
    connection = sites(result, "connect")[0]
    assert qt_metadata(connection)["declared_type"] == "QueuedConnection"
    text, _ = _node_attributes_text(connection)
    assert "queuedconnection" in text
    attributes = search_attributes(connection)
    assert "raw_values" not in str(attributes) and "owner_scope_key" not in str(attributes)
