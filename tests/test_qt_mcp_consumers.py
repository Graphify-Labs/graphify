"""QML-013-AC04 actual in-process MCP HTTP calls agree with saved-graph CLI."""
import pytest

pytest.importorskip("mcp", reason="QML-013-AC04 requires the MCP extra")
pytest.importorskip("starlette", reason="QML-013-AC04 requires the MCP HTTP dependency")

from starlette.testclient import TestClient  # noqa: E402
from graphify.build import build_from_json  # noqa: E402
from graphify.export import to_json  # noqa: E402
from graphify.serve import _build_http_app  # noqa: E402
from tests.qt_analysis_helpers import analysis  # noqa: E402
from tests.qt_consumer_helpers import cli, saved_graph  # noqa: E402
from tests.test_qt_signals_slots import SOURCE  # noqa: E402

HEADERS = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}


def initialize(client):
    response = client.post("/mcp", headers=HEADERS, json={"jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "qt-acceptance", "version": "1"}}})
    assert response.status_code == 200
    headers = {**HEADERS, "mcp-session-id": response.headers.get("mcp-session-id")}
    client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "method": "notifications/initialized"})
    return headers


def tool(client, headers, name, arguments, rid):
    response = client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": rid, "method": "tools/call",
        "params": {"name": name, "arguments": arguments}})
    assert response.status_code == 200
    result = response.json()["result"]
    assert not result.get("isError"), result
    return result["content"][0]["text"].strip()


def test_mcp_query_node_and_neighbors_match_cli_source_confidence(tmp_path, monkeypatch, capsys):
    """An initialized HTTP session queries persisted scoped facts and evidence."""
    path, _, _, prop, read = saved_graph(tmp_path)
    query = cli(monkeypatch, capsys, path, "query", read["id"])
    app = _build_http_app(str(path), json_response=True)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        headers = initialize(client)
        # The CLI defaults to depth two; protocol defaults stay independent.
        mcp_query = tool(client, headers, "query_graph", {"question": read["id"], "depth": 2}, 2)
        assert mcp_query == query
        node = tool(client, headers, "get_node", {"node_id": prop["id"]}, 4)
        assert "Main.qml" in node and prop["id"] in node
        neighbors = tool(client, headers, "get_neighbors", {"node_id": read["id"]}, 5)
        assert "INFERRED" in neighbors and "Main.qml:L" in neighbors


def test_mcp_exact_id_path_matches_cli_and_retains_source_evidence(tmp_path, monkeypatch, capsys):
    """Opaque canonical IDs select the intended endpoints in both interfaces."""
    path, _, component, prop, _ = saved_graph(tmp_path)
    route = cli(monkeypatch, capsys, path, "path", component["id"], prop["id"])
    with TestClient(_build_http_app(str(path), json_response=True), base_url="http://127.0.0.1") as client:
        headers = initialize(client)
        mcp_path = tool(client, headers, "shortest_path", {"source": component["id"], "target": prop["id"]}, 2)
    assert mcp_path == route
    assert "Main.qml:L" in mcp_path and "EXTRACTED" in mcp_path


def test_qml016_ac04_http_metadata_search_keeps_connection_reference_semantics(tmp_path, monkeypatch, capsys):
    """Native Qt facts stay searchable and references cannot become delivery calls."""
    result = analysis(tmp_path, {"events.cpp": SOURCE})
    graph = build_from_json(result, root=tmp_path)
    path = tmp_path / "graph.json"
    assert to_json(graph, {}, str(path), force=True)
    query = cli(monkeypatch, capsys, path, "query", "QueuedConnection")
    endpoint = next(edge["source"] for edge in result["edges"] if edge.get("context") == "qt_connect_signal")
    with TestClient(_build_http_app(str(path), json_response=True), base_url="http://127.0.0.1") as client:
        headers = initialize(client)
        mcp_query = tool(client, headers, "query_graph", {"question": "QueuedConnection", "depth": 2}, 2)
        assert mcp_query == query and "Qt connect:" in mcp_query and "events.cpp:L" in mcp_query
        references = tool(client, headers, "get_neighbors", {"node_id": endpoint, "relation_filter": "references"}, 3)
        assert "[references] [INFERRED]" in references and "events.cpp:L" in references
        calls = tool(client, headers, "get_neighbors", {"node_id": endpoint, "relation_filter": "calls"}, 4)
        assert "-->" not in calls and "<--" not in calls
