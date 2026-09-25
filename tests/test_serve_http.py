"""Tests for the Streamable HTTP transport on the MCP server (issue #1143).

These exercise the ASGI wiring in-process (no uvicorn, no real socket) via
Starlette's TestClient, so they stay fast and offline. The stdio path is
unchanged and covered elsewhere.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("mcp")
pytest.importorskip("starlette")

from starlette.testclient import TestClient  # noqa: E402

from graphify import serve as serve_mod  # noqa: E402

SAMPLE_GRAPH = {
    "directed": True,
    "nodes": [
        {"id": "a", "label": "Alpha", "community": 0},
        {"id": "b", "label": "Beta", "community": 0},
    ],
    "edges": [
        {"source": "a", "target": "b", "relation": "calls", "confidence": "EXTRACTED"},
    ],
}

_INIT_BODY = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "0"},
    },
}

_MCP_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}


def _graph_file(tmp_path: Path) -> str:
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(SAMPLE_GRAPH), encoding="utf-8")
    return str(p)


def _client(app) -> TestClient:
    # Default host is 127.0.0.1, so the DNS-rebinding guard only accepts that
    # Host header (TestClient otherwise sends the disallowed "testserver").
    return TestClient(app, base_url="http://127.0.0.1")


def test_app_builds_and_initialize_succeeds(tmp_path):
    app = serve_mod._build_http_app(_graph_file(tmp_path), json_response=True)
    with _client(app) as client:
        resp = client.post("/mcp", headers=_MCP_HEADERS, json=_INIT_BODY)
        assert resp.status_code == 200
        # json_response=True returns a single JSON-RPC envelope.
        payload = resp.json()
        assert payload["jsonrpc"] == "2.0"
        assert payload["result"]["serverInfo"]["name"] == "graphify"


def test_unknown_path_is_404(tmp_path):
    app = serve_mod._build_http_app(_graph_file(tmp_path), json_response=True)
    with _client(app) as client:
        resp = client.post("/nope", headers=_MCP_HEADERS, json=_INIT_BODY)
        assert resp.status_code == 404


def test_api_key_missing_is_401(tmp_path):
    app = serve_mod._build_http_app(_graph_file(tmp_path), api_key="s3cret", json_response=True)
    with _client(app) as client:
        resp = client.post("/mcp", headers=_MCP_HEADERS, json=_INIT_BODY)
        assert resp.status_code == 401
        assert resp.json()["error"] == "unauthorized"


def test_api_key_wrong_is_401(tmp_path):
    app = serve_mod._build_http_app(_graph_file(tmp_path), api_key="s3cret", json_response=True)
    with _client(app) as client:
        resp = client.post(
            "/mcp",
            headers={**_MCP_HEADERS, "Authorization": "Bearer nope"},
            json=_INIT_BODY,
        )
        assert resp.status_code == 401


def test_api_key_bearer_ok(tmp_path):
    app = serve_mod._build_http_app(_graph_file(tmp_path), api_key="s3cret", json_response=True)
    with _client(app) as client:
        resp = client.post(
            "/mcp",
            headers={**_MCP_HEADERS, "Authorization": "Bearer s3cret"},
            json=_INIT_BODY,
        )
        assert resp.status_code == 200
        assert resp.json()["result"]["serverInfo"]["name"] == "graphify"


def test_api_key_x_api_key_header_ok(tmp_path):
    app = serve_mod._build_http_app(_graph_file(tmp_path), api_key="s3cret", json_response=True)
    with _client(app) as client:
        resp = client.post(
            "/mcp",
            headers={**_MCP_HEADERS, "X-API-Key": "s3cret"},
            json=_INIT_BODY,
        )
        assert resp.status_code == 200


def test_blank_api_key_means_no_auth(tmp_path):
    # An empty/whitespace key must normalize to "no auth", not a key of "".
    app = serve_mod._build_http_app(_graph_file(tmp_path), api_key="   ", json_response=True)
    with _client(app) as client:
        resp = client.post("/mcp", headers=_MCP_HEADERS, json=_INIT_BODY)
        assert resp.status_code == 200


def test_api_key_bearer_scheme_case_insensitive(tmp_path):
    app = serve_mod._build_http_app(_graph_file(tmp_path), api_key="s3cret", json_response=True)
    with _client(app) as client:
        resp = client.post(
            "/mcp",
            headers={**_MCP_HEADERS, "Authorization": "bearer s3cret"},
            json=_INIT_BODY,
        )
        assert resp.status_code == 200


def test_custom_mount_path(tmp_path):
    app = serve_mod._build_http_app(_graph_file(tmp_path), path="/graph", json_response=True)
    with _client(app) as client:
        ok = client.post("/graph", headers=_MCP_HEADERS, json=_INIT_BODY)
        assert ok.status_code == 200
        missing = client.post("/mcp", headers=_MCP_HEADERS, json=_INIT_BODY)
        assert missing.status_code == 404


def test_tools_list_over_http(tmp_path):
    """A full initialize -> tools/list round trip works over the HTTP transport."""
    app = serve_mod._build_http_app(_graph_file(tmp_path), json_response=True)
    with _client(app) as client:
        init = client.post("/mcp", headers=_MCP_HEADERS, json=_INIT_BODY)
        assert init.status_code == 200
        session_id = init.headers.get("mcp-session-id")
        assert session_id, "stateful transport should return a session id"
        notify_headers = {**_MCP_HEADERS, "mcp-session-id": session_id}
        client.post(
            "/mcp",
            headers=notify_headers,
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        )
        resp = client.post(
            "/mcp",
            headers=notify_headers,
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        )
        assert resp.status_code == 200
        names = {t["name"] for t in resp.json()["result"]["tools"]}
        assert {"query_graph", "get_node", "graph_stats"} <= names


def _project_with_graph(tmp_path, node_count: int, name: str = "proj") -> str:
    """Create ``<proj>/graphify-out/graph.json`` and return the project dir."""
    proj = tmp_path / name
    (proj / "graphify-out").mkdir(parents=True)
    graph = {
        "directed": True,
        "nodes": [{"id": f"n{i}", "label": f"N{i}", "community": 0} for i in range(node_count)],
        "edges": [],
    }
    (proj / "graphify-out" / "graph.json").write_text(json.dumps(graph), encoding="utf-8")
    return str(proj)


def _init_session(client) -> dict:
    init = client.post("/mcp", headers=_MCP_HEADERS, json=_INIT_BODY)
    assert init.status_code == 200
    headers = {**_MCP_HEADERS, "mcp-session-id": init.headers.get("mcp-session-id")}
    client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "method": "notifications/initialized"})
    return headers


def _call_tool(client, headers, name, arguments, rid) -> str:
    resp = client.post("/mcp", headers=headers, json={
        "jsonrpc": "2.0", "id": rid, "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    })
    assert resp.status_code == 200
    return resp.json()["result"]["content"][0]["text"]


def _call_tool_result(client, headers, name, arguments, rid) -> dict:
    """Like _call_tool, but returns the full tools/call result object (so a
    caller can inspect isError, not just the text) instead of just the text.
    """
    resp = client.post("/mcp", headers=headers, json={
        "jsonrpc": "2.0", "id": rid, "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    })
    assert resp.status_code == 200
    return resp.json()["result"]


def test_project_path_is_optional_on_every_tool(tmp_path):
    """Multi-project support is additive: every tool gains an optional
    project_path, and none of them makes it required."""
    app = serve_mod._build_http_app(_graph_file(tmp_path), json_response=True)
    with _client(app) as client:
        headers = _init_session(client)
        resp = client.post("/mcp", headers=headers,
                            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        for tool in resp.json()["result"]["tools"]:
            props = tool["inputSchema"].get("properties", {})
            assert "project_path" in props, f"{tool['name']} missing project_path"
            assert "project_path" not in tool["inputSchema"].get("required", [])


def test_project_path_routes_to_that_projects_graph(tmp_path):
    """One running server answers against the default graph when project_path is
    omitted, and against a project's own graph when it is supplied."""
    proj = _project_with_graph(tmp_path, node_count=3)  # default graph has 2 nodes
    app = serve_mod._build_http_app(_graph_file(tmp_path), json_response=True)
    with _client(app) as client:
        headers = _init_session(client)
        assert "Nodes: 2" in _call_tool(client, headers, "graph_stats", {}, rid=2)
        assert "Nodes: 3" in _call_tool(client, headers, "graph_stats", {"project_path": proj}, rid=3)
        # Falling back to the default afterwards still works (no state leak).
        assert "Nodes: 2" in _call_tool(client, headers, "graph_stats", {}, rid=4)


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, 8), ("", 8), ("bad", 8), ("0", 1), ("-4", 1), ("3", 3)],
)
def test_max_server_contexts_parsing(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv("GRAPHIFY_MAX_CONTEXTS", raising=False)
    else:
        monkeypatch.setenv("GRAPHIFY_MAX_CONTEXTS", value)
    assert serve_mod._max_server_contexts() == expected


def test_project_context_cache_is_lru_and_pins_default_graph(tmp_path, monkeypatch):
    """Project contexts hit, promote, and evict without evicting the default."""
    monkeypatch.setenv("GRAPHIFY_MAX_CONTEXTS", "2")
    original_load = serve_mod._load_graph
    loads: dict[str, int] = {}

    def counting_load(path: str):
        resolved = str(Path(path).resolve())
        loads[resolved] = loads.get(resolved, 0) + 1
        return original_load(path)

    monkeypatch.setattr(serve_mod, "_load_graph", counting_load)
    projects = [
        _project_with_graph(tmp_path, node_count=i + 3, name=f"project-{i}")
        for i in range(3)
    ]
    default_graph = _graph_file(tmp_path)
    app = serve_mod._build_http_app(default_graph, json_response=True)
    with _client(app) as client:
        headers = _init_session(client)
        assert "Nodes: 3" in _call_tool(client, headers, "graph_stats", {"project_path": projects[0]}, rid=2)
        assert "Nodes: 4" in _call_tool(client, headers, "graph_stats", {"project_path": projects[1]}, rid=3)
        # A cache hit promotes project-0 above project-1 in LRU recency.
        assert "Nodes: 3" in _call_tool(client, headers, "graph_stats", {"project_path": projects[0]}, rid=4)
        assert "Nodes: 5" in _call_tool(client, headers, "graph_stats", {"project_path": projects[2]}, rid=5)
        # project-1, not the re-touched project-0, was evicted.
        assert "Nodes: 4" in _call_tool(client, headers, "graph_stats", {"project_path": projects[1]}, rid=6)
        # The configured default graph stays warm even when project capacity is full.
        assert "Nodes: 2" in _call_tool(client, headers, "graph_stats", {}, rid=7)

    first_graph = str((Path(projects[0]) / "graphify-out" / "graph.json").resolve())
    second_graph = str((Path(projects[1]) / "graphify-out" / "graph.json").resolve())
    default_graph = str(Path(default_graph).resolve())
    assert loads[first_graph] == 1
    assert loads[second_graph] == 2
    assert loads[default_graph] == 1


def test_bad_project_path_errors_without_killing_server(tmp_path):
    """A missing project graph is a tool error, not a process exit — the server
    keeps serving the default graph."""
    app = serve_mod._build_http_app(_graph_file(tmp_path), json_response=True)
    with _client(app) as client:
        headers = _init_session(client)
        bad = _call_tool(client, headers, "graph_stats",
                         {"project_path": str(tmp_path / "does-not-exist")}, rid=2)
        assert "not found" in bad.lower()
        assert "Nodes: 2" in _call_tool(client, headers, "graph_stats", {}, rid=3)


def test_bad_project_path_sets_is_error(tmp_path):
    """#2714: a missing project_path graph is a TOOL failure, so the result's
    isError flag must be set — not just the same text a success reply would
    also carry. isError is what a programmatic caller (health check, CI gate,
    rollout script) branches on; an LLM reads the text either way, but a
    script reading isError=False on a "not found" error can't tell the
    call failed."""
    app = serve_mod._build_http_app(_graph_file(tmp_path), json_response=True)
    with _client(app) as client:
        headers = _init_session(client)
        result = _call_tool_result(client, headers, "graph_stats",
                                    {"project_path": str(tmp_path / "does-not-exist")}, rid=2)
        assert result.get("isError") is True, f"expected isError=True, got {result}"


def test_corrupt_project_graph_is_a_tool_error_without_killing_server(tmp_path):
    """A CLI-style SystemExit from a client graph cannot stop the MCP server."""
    project = Path(_project_with_graph(tmp_path, node_count=3))
    (project / "graphify-out" / "graph.json").write_text("{not json", encoding="utf-8")
    app = serve_mod._build_http_app(_graph_file(tmp_path), json_response=True)
    with _client(app) as client:
        headers = _init_session(client)
        bad = _call_tool(client, headers, "graph_stats", {"project_path": str(project)}, rid=2)
        assert "could not load graph.json" in bad
        assert "Nodes: 2" in _call_tool(client, headers, "graph_stats", {}, rid=3)


def test_corrupt_project_graph_sets_is_error(tmp_path):
    """#2714: same tool-failure/isError contract for a corrupt project graph."""
    project = Path(_project_with_graph(tmp_path, node_count=3))
    (project / "graphify-out" / "graph.json").write_text("{not json", encoding="utf-8")
    app = serve_mod._build_http_app(_graph_file(tmp_path), json_response=True)
    with _client(app) as client:
        headers = _init_session(client)
        result = _call_tool_result(client, headers, "graph_stats",
                                    {"project_path": str(project)}, rid=2)
        assert result.get("isError") is True, f"expected isError=True, got {result}"


def test_successful_tool_call_does_not_set_is_error(tmp_path):
    """#2714 follow-up: a normal, successful tool call must NOT carry
    isError=True (either unset or explicitly False is fine)."""
    app = serve_mod._build_http_app(_graph_file(tmp_path), json_response=True)
    with _client(app) as client:
        headers = _init_session(client)
        result = _call_tool_result(client, headers, "graph_stats", {}, rid=2)
        assert not result.get("isError"), f"unexpected isError on success: {result}"


def test_unknown_tool_sets_is_error(tmp_path):
    """#2714: an unknown tool name is also a tool-level failure."""
    app = serve_mod._build_http_app(_graph_file(tmp_path), json_response=True)
    with _client(app) as client:
        headers = _init_session(client)
        result = _call_tool_result(client, headers, "not_a_real_tool", {}, rid=2)
        assert result.get("isError") is True, f"expected isError=True, got {result}"


def test_stateless_mode_initialize(tmp_path):
    app = serve_mod._build_http_app(_graph_file(tmp_path), stateless=True, json_response=True)
    with _client(app) as client:
        resp = client.post("/mcp", headers=_MCP_HEADERS, json=_INIT_BODY)
        assert resp.status_code == 200


def test_stateless_with_timeout_does_not_raise(tmp_path):
    # session_timeout must be forced to None in stateless mode (the SDK raises
    # RuntimeError otherwise). Building + a request should just work.
    app = serve_mod._build_http_app(
        _graph_file(tmp_path), stateless=True, session_timeout=3600, json_response=True
    )
    with _client(app) as client:
        assert client.post("/mcp", headers=_MCP_HEADERS, json=_INIT_BODY).status_code == 200


def test_session_timeout_zero_disables(tmp_path):
    # 0 / non-positive must disable reaping without tripping the SDK's validation.
    app = serve_mod._build_http_app(_graph_file(tmp_path), session_timeout=0, json_response=True)
    with _client(app) as client:
        assert client.post("/mcp", headers=_MCP_HEADERS, json=_INIT_BODY).status_code == 200


# --- CLI argument parsing -------------------------------------------------

def test_cli_defaults_to_stdio(monkeypatch):
    calls = {}
    monkeypatch.setattr(serve_mod, "serve", lambda gp: calls.setdefault("stdio", gp))
    monkeypatch.setattr(
        serve_mod, "serve_http", lambda *a, **k: calls.setdefault("http", (a, k))
    )
    serve_mod._main(["graphify-out/graph.json"])
    assert calls.get("stdio") == "graphify-out/graph.json"
    assert "http" not in calls


def test_cli_http_passes_flags(monkeypatch):
    captured = {}
    monkeypatch.setattr(serve_mod, "serve", lambda gp: captured.setdefault("stdio", gp))
    monkeypatch.setattr(
        serve_mod, "serve_http", lambda gp, **k: captured.update(gp=gp, **k)
    )
    serve_mod._main([
        "g.json", "--transport", "http", "--host", "0.0.0.0",
        "--port", "9000", "--api-key", "k", "--stateless",
    ])
    assert captured["gp"] == "g.json"
    assert captured["host"] == "0.0.0.0"
    assert captured["port"] == 9000
    assert captured["api_key"] == "k"
    assert captured["stateless"] is True


def test_cli_api_key_from_env(monkeypatch):
    captured = {}
    monkeypatch.setenv("GRAPHIFY_API_KEY", "from-env")
    monkeypatch.setattr(serve_mod, "serve_http", lambda gp, **k: captured.update(**k))
    serve_mod._main(["g.json", "--transport", "http"])
    assert captured["api_key"] == "from-env"


def test_pr_tool_failure_sets_iserror(tmp_path, monkeypatch):
    """ADR-0001 finding 4: a PR tool that fails because gh is missing / not
    authenticated must return isError:true, not a successful text result."""
    import graphify.prs as prs_mod

    def _boom(*a, **k):
        raise RuntimeError("gh CLI not found or not authenticated. Run: gh auth login")

    monkeypatch.setattr(prs_mod, "fetch_prs", _boom)

    app = serve_mod._build_http_app(_graph_file(tmp_path), json_response=True)
    with _client(app) as client:
        headers = _init_session(client)
        resp = client.post("/mcp", headers=headers, json={
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "list_prs", "arguments": {}},
        })
        assert resp.status_code == 200
        result = resp.json()["result"]
        assert result.get("isError") is True, result
        assert "gh" in result["content"][0]["text"].lower()


def test_normal_tool_result_is_not_iserror(tmp_path):
    """A successful tool result must not be marked isError."""
    app = serve_mod._build_http_app(_graph_file(tmp_path), json_response=True)
    with _client(app) as client:
        headers = _init_session(client)
        resp = client.post("/mcp", headers=headers, json={
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "graph_stats", "arguments": {}},
        })
        assert resp.status_code == 200
        assert not resp.json()["result"].get("isError")
def _ambiguous_graph_file(tmp_path: Path) -> str:
    """A graph where the label 'extract' matches two nodes in different files."""
    graph = {
        "directed": True,
        "nodes": [
            {"id": "a", "label": "extract", "community": 0, "source_file": "a/x.py"},
            {"id": "b", "label": "extract", "community": 0, "source_file": "b/y.py"},
            {"id": "u", "label": "unique_helper", "community": 0, "source_file": "c/z.py"},
        ],
        "edges": [
            {"source": "a", "target": "u", "relation": "calls", "confidence": "EXTRACTED"},
        ],
    }
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(graph), encoding="utf-8")
    return str(p)


def test_get_node_and_get_neighbors_agree_on_ambiguous_label(tmp_path):
    """ADR-0001 finding 1: get_node must not silently return a G.nodes()
    iteration-order match for a hub name while get_neighbors reports the same
    lookup as ambiguous. Both now route through the shared resolver."""
    app = serve_mod._build_http_app(_ambiguous_graph_file(tmp_path), json_response=True)
    with _client(app) as client:
        headers = _init_session(client)
        node = _call_tool(client, headers, "get_node", {"label": "extract"}, rid=2)
        neighbors = _call_tool(client, headers, "get_neighbors", {"label": "extract"}, rid=3)
        assert node.startswith("Ambiguous:"), node
        assert neighbors.startswith("Ambiguous:"), neighbors
        # A unique label still resolves cleanly on get_node.
        unique = _call_tool(client, headers, "get_node", {"label": "unique_helper"}, rid=4)
        assert "Node: unique_helper" in unique, unique
