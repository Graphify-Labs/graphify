"""MCP tool annotations and server instructions (issue #5208)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("mcp")
pytest.importorskip("starlette")

from starlette.testclient import TestClient  # noqa: E402

from graphify import serve as serve_mod  # noqa: E402

_GRAPH = {
    "directed": True,
    "nodes": [{"id": "a", "label": "Alpha", "community": 0}],
    "edges": [],
}
_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}
_INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "0"},
    },
}
_GH_TOOLS = {"list_prs", "get_pr_impact", "triage_prs"}


@pytest.fixture()
def session(tmp_path: Path):
    graph = tmp_path / "graph.json"
    graph.write_text(json.dumps(_GRAPH), encoding="utf-8")
    app = serve_mod._build_http_app(str(graph), json_response=True)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        init = client.post("/mcp", headers=_HEADERS, json=_INIT)
        headers = {**_HEADERS, "mcp-session-id": init.headers["mcp-session-id"]}
        client.post("/mcp", headers=headers,
                    json={"jsonrpc": "2.0", "method": "notifications/initialized"})
        tools = client.post(
            "/mcp", headers=headers,
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        ).json()["result"]["tools"]
        yield init.json()["result"], tools


def test_initialize_returns_instructions(session):
    init, _ = session
    assert "query_graph" in init["instructions"]
    assert "read-only" in init["instructions"]


def test_every_tool_is_read_only_with_a_title(session):
    _, tools = session
    assert tools
    for tool in tools:
        ann = tool["annotations"]
        assert ann["readOnlyHint"] is True, tool["name"]
        assert ann["title"], tool["name"]


def test_only_github_tools_are_open_world(session):
    _, tools = session
    open_world = {t["name"] for t in tools if t["annotations"]["openWorldHint"]}
    assert open_world == _GH_TOOLS


def test_annotation_table_matches_the_tool_list(session):
    _, tools = session
    assert {t["name"] for t in tools} == set(serve_mod._TOOL_ANNOTATIONS)
