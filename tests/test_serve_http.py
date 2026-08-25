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


def test_tools_list_token_budget_default_is_20000(tmp_path):
    """Owner's order 2026-08-24: the default graph-answer budget is 20000
    tokens (2000 starved multi-node answers). Every tool that advertises a
    token_budget input must carry the new default in its schema."""
    app = serve_mod._build_http_app(_graph_file(tmp_path), json_response=True)
    with _client(app) as client:
        init = client.post("/mcp", headers=_MCP_HEADERS, json=_INIT_BODY)
        assert init.status_code == 200
        session_id = init.headers.get("mcp-session-id")
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
        budget_defaults = {
            t["name"]: t["inputSchema"]["properties"]["token_budget"]["default"]
            for t in resp.json()["result"]["tools"]
            if "token_budget" in t.get("inputSchema", {}).get("properties", {})
        }
        assert set(budget_defaults) == {"query_graph", "get_neighbors", "get_community"}
        assert all(v == 20000 for v in budget_defaults.values()), budget_defaults


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


# --- orientation stamp: MCP graph reads refresh the strict-hook freshness stamp


def _stamp_path(graph_file: str) -> Path:
    """The 'recently oriented' stamp the strict read hook checks, next to the
    graph that answered (same location cli._touch_query_stamp writes)."""
    return Path(graph_file).parent / "cache" / "last_query_stamp"


def _age_stamp(stamp: Path) -> None:
    stamp.parent.mkdir(parents=True, exist_ok=True)
    stamp.write_text("0")
    import os

    os.utime(stamp, (1000, 1000))


def test_mcp_query_graph_touches_orientation_stamp(tmp_path):
    """query_graph is orientation: an agent that consulted the graph through
    the MCP server must be as 'recently oriented' as one that ran the CLI
    `graphify query` — otherwise the strict read hook denies its next read."""
    graph_file = _graph_file(tmp_path)
    app = serve_mod._build_http_app(graph_file, json_response=True)
    with _client(app) as client:
        headers = _init_session(client)
        assert not _stamp_path(graph_file).exists()
        assert "Alpha" in _call_tool(client, headers, "query_graph", {"question": "Alpha"}, rid=2)
        assert _stamp_path(graph_file).exists()


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("query_graph", {"question": "Alpha"}),
        ("get_node", {"label": "Alpha"}),
        ("get_neighbors", {"label": "Alpha"}),
        ("shortest_path", {"source": "Alpha", "target": "Beta"}),
    ],
)
def test_mcp_orientation_tools_refresh_aged_stamp(tmp_path, tool, arguments):
    """Each MCP twin of the stamping CLI commands (query/path/explain) must
    refresh an existing-but-old stamp on a successful call."""
    graph_file = _graph_file(tmp_path)
    stamp = _stamp_path(graph_file)
    _age_stamp(stamp)
    app = serve_mod._build_http_app(graph_file, json_response=True)
    with _client(app) as client:
        headers = _init_session(client)
        _call_tool(client, headers, tool, arguments, rid=2)
    assert stamp.stat().st_mtime > 1000, f"{tool} did not refresh the stamp"


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("graph_stats", {}),
        ("god_nodes", {}),
        ("get_community", {"community_id": 0}),
    ],
)
def test_mcp_non_orientation_tools_leave_stamp_alone(tmp_path, tool, arguments):
    """Graph-level browsing does not stamp on the CLI (`god-nodes` never
    touches it) and must not stamp over MCP either."""
    graph_file = _graph_file(tmp_path)
    stamp = _stamp_path(graph_file)
    _age_stamp(stamp)
    app = serve_mod._build_http_app(graph_file, json_response=True)
    with _client(app) as client:
        headers = _init_session(client)
        _call_tool(client, headers, tool, arguments, rid=2)
    assert stamp.stat().st_mtime == 1000, f"{tool} unexpectedly refreshed the stamp"


def test_mcp_project_path_query_stamps_that_project(tmp_path):
    """A project_path call stamps next to the graph that answered — the
    project's graphify-out/cache — not next to the server's default graph."""
    proj = _project_with_graph(tmp_path, node_count=3)
    default_graph = _graph_file(tmp_path)
    app = serve_mod._build_http_app(default_graph, json_response=True)
    with _client(app) as client:
        headers = _init_session(client)
        _call_tool(client, headers, "query_graph", {"question": "N1", "project_path": proj}, rid=2)
    assert (Path(proj) / "graphify-out" / "cache" / "last_query_stamp").exists()
    assert not _stamp_path(default_graph).exists()


def test_mcp_failed_call_does_not_stamp(tmp_path):
    """A tool error is not orientation: a query against a missing project graph
    must leave no freshness stamp anywhere."""
    default_graph = _graph_file(tmp_path)
    missing = tmp_path / "no-such-project"
    app = serve_mod._build_http_app(default_graph, json_response=True)
    with _client(app) as client:
        headers = _init_session(client)
        out = _call_tool(
            client, headers, "query_graph",
            {"question": "Alpha", "project_path": str(missing)}, rid=2,
        )
    assert "not found" in out.lower()
    assert not _stamp_path(default_graph).exists()
    assert not (missing / "graphify-out" / "cache" / "last_query_stamp").exists()


# --- cache key: a sidecar-only change must invalidate the graph context --------


def test_sidecar_only_change_invalidates_cached_context(tmp_path, monkeypatch):
    """A `graphify reflect` run rewrites only .graphify_learning.json, never
    graph.json. The context cache used to key on graph.json's (mtime_ns, size)
    alone, so a running server kept serving lesson annotations from the old
    sidecar until the graph itself changed. The sidecar's (mtime_ns, size) —
    (0, 0) when absent — is now part of the key."""
    graph_file = _graph_file(tmp_path)
    sidecar = tmp_path / ".graphify_learning.json"

    original_load = serve_mod._load_graph
    loads = {"n": 0}

    def counting_load(path: str):
        loads["n"] += 1
        return original_load(path)

    monkeypatch.setattr(serve_mod, "_load_graph", counting_load)

    app = serve_mod._build_http_app(graph_file, json_response=True)
    with _client(app) as client:
        headers = _init_session(client)
        # 1. No sidecar: un-annotated answer. (The server start already loaded
        #    the default graph once.)
        out = _call_tool(client, headers, "query_graph", {"question": "Alpha"}, rid=2)
        assert "learning=" not in out
        assert loads["n"] == 1

        # 2. Sidecar appears, graph.json untouched: the same running server
        #    must reload and annotate.
        sidecar.write_text(
            json.dumps({"version": 1, "nodes": {"a": {"status": "preferred"}}}),
            encoding="utf-8",
        )
        out = _call_tool(client, headers, "query_graph", {"question": "Alpha"}, rid=3)
        assert "learning=preferred" in out
        assert loads["n"] == 2

        # 3. Nothing changed: still a cache hit.
        out = _call_tool(client, headers, "query_graph", {"question": "Alpha"}, rid=4)
        assert "learning=preferred" in out
        assert loads["n"] == 2

        # 4. Sidecar rewritten (a fresh reflect run): reload, new verdict.
        sidecar.write_text(
            json.dumps({"version": 1, "nodes": {"a": {"status": "contested"}}}),
            encoding="utf-8",
        )
        out = _call_tool(client, headers, "query_graph", {"question": "Alpha"}, rid=5)
        assert "learning=contested" in out
        assert loads["n"] == 3

        # 5. Sidecar vanishes: reload again, annotations gone.
        sidecar.unlink()
        out = _call_tool(client, headers, "query_graph", {"question": "Alpha"}, rid=6)
        assert "learning=" not in out
        assert loads["n"] == 4


def test_sidecar_change_invalidates_project_context_too(tmp_path, monkeypatch):
    """Same contract on the LRU (project_path) side of the cache."""
    proj = _project_with_graph(tmp_path, node_count=3)
    default_graph = _graph_file(tmp_path)
    sidecar = Path(proj) / "graphify-out" / ".graphify_learning.json"

    app = serve_mod._build_http_app(default_graph, json_response=True)
    with _client(app) as client:
        headers = _init_session(client)
        out = _call_tool(client, headers, "query_graph",
                         {"question": "N1", "project_path": proj}, rid=2)
        assert "learning=" not in out
        sidecar.write_text(
            json.dumps({"version": 1, "nodes": {"n1": {"status": "preferred"}}}),
            encoding="utf-8",
        )
        out = _call_tool(client, headers, "query_graph",
                         {"question": "N1", "project_path": proj}, rid=3)
        assert "learning=preferred" in out
