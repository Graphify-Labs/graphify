"""MCP parity with the CLI: the `affected` tool and `seeds` on `query_graph` (#5254)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("mcp")
pytest.importorskip("starlette")

from starlette.testclient import TestClient  # noqa: E402

from graphify import serve as serve_mod  # noqa: E402

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

_GRAPH = {
    "directed": True,
    "nodes": [
        {"id": "app_main", "label": "run_app()", "source_file": "app.py", "source_location": "L3", "community": 0},
        {"id": "lib_helper", "label": "helper()", "source_file": "lib.py", "source_location": "L1", "community": 0},
        {"id": "a_dup", "label": "dup()", "source_file": "a.py", "source_location": "L1", "community": 1},
        {"id": "b_dup", "label": "dup()", "source_file": "b.py", "source_location": "L1", "community": 1},
    ],
    "edges": [
        {"source": "app_main", "target": "lib_helper", "relation": "calls", "confidence": "EXTRACTED"},
    ],
}


def _project(tmp_path: Path) -> str:
    out = tmp_path / "proj" / "graphify-out"
    out.mkdir(parents=True)
    (out / "graph.json").write_text(json.dumps(_GRAPH), encoding="utf-8")
    return str(out / "graph.json")


def _session(client) -> dict:
    init = client.post("/mcp", headers=_MCP_HEADERS, json=_INIT_BODY)
    assert init.status_code == 200
    session_id = init.headers.get("mcp-session-id")
    assert session_id, "stateful transport should return a session id"
    headers = {**_MCP_HEADERS, "mcp-session-id": session_id}
    client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "method": "notifications/initialized"})
    return headers


def _rpc(client, headers, method, params, rid):
    resp = client.post("/mcp", headers=headers, json={
        "jsonrpc": "2.0", "id": rid, "method": method, "params": params,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert "result" in body, f"MCP error reply: {body.get('error')}"
    return body["result"]


def _call(client, headers, name, arguments, rid) -> str:
    result = _rpc(client, headers, "tools/call", {"name": name, "arguments": arguments}, rid)
    return result["content"][0]["text"]


@pytest.fixture()
def mcp(tmp_path):
    app = serve_mod._build_http_app(_project(tmp_path), json_response=True)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        yield client, _session(client)


def test_tools_list_exposes_affected_and_seeds(mcp):
    client, headers = mcp
    tools = {t["name"]: t for t in _rpc(client, headers, "tools/list", {}, 2)["tools"]}
    assert "affected" in tools
    assert "target" in tools["affected"]["inputSchema"]["required"]
    assert tools["query_graph"]["inputSchema"]["properties"]["seeds"]["type"] == "array"


def test_affected_lists_callers_of_a_symbol(mcp):
    client, headers = mcp
    text = _call(client, headers, "affected", {"target": "helper()"}, 2)
    assert text.startswith("Affected nodes for helper()")
    assert "run_app()" in text


def test_affected_accepts_a_repo_relative_file_path(mcp):
    client, headers = mcp
    # Resolves through the graph root derived from <root>/graphify-out/graph.json,
    # the same rule as the CLI.
    text = _call(client, headers, "affected", {"target": "lib.py"}, 2)
    assert text.startswith("Affected nodes for")
    assert "run_app()" in text


def test_affected_absolute_path_uses_the_shared_graph_root(tmp_path):
    # A graph that lives outside `<root>/graphify-out` (shared/nested output
    # dir) names its project root in `.graphify_root`; an absolute file path must
    # still relativize against that root, as in the CLI.
    project = tmp_path / "project"
    project.mkdir()
    shared = tmp_path / "shared-out"
    shared.mkdir()
    (shared / "graph.json").write_text(json.dumps(_GRAPH), encoding="utf-8")
    (shared / ".graphify_root").write_text(str(project), encoding="utf-8")
    app = serve_mod._build_http_app(str(shared / "graph.json"), json_response=True)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        headers = _session(client)
        target = str(project / "lib.py")
        text = _call(client, headers, "affected", {"target": target}, 2)
        assert text.startswith("Affected nodes for")
        assert "run_app()" in text
        seeded = _call(client, headers, "query_graph", {"question": "zzqx", "seeds": [target]}, 3)
        assert "No unique node match" not in seeded
        assert "run_app()" in seeded


def test_affected_ambiguous_label_is_a_candidate_list_not_a_guess(mcp):
    client, headers = mcp
    text = _call(client, headers, "affected", {"target": "dup()"}, 2)
    assert "Affected nodes for" not in text
    assert "a.py" in text and "b.py" in text


def test_affected_unknown_target_fails_closed(mcp):
    client, headers = mcp
    assert _call(client, headers, "affected", {"target": "nope_nothing"}, 2).startswith("No unique node match")


def test_affected_rejects_bad_arguments(mcp):
    client, headers = mcp
    assert "Provide a target" in _call(client, headers, "affected", {}, 2)
    assert "depth must be an integer" in _call(client, headers, "affected", {"target": "helper()", "depth": "x"}, 3)
    assert "relations must be a list" in _call(client, headers, "affected", {"target": "helper()", "relations": [1]}, 4)


def test_query_graph_seeds_start_from_the_given_node(mcp):
    client, headers = mcp
    # The question shares no keyword with the graph: only the seed can anchor it,
    # and `run_app()` (the seed's caller) is reached by traversal, not echoed.
    text = _call(client, headers, "query_graph", {"question": "zzqx", "seeds": ["helper()"]}, 2)
    assert "No unique node match" not in text
    assert "run_app()" in text


def test_query_graph_unresolvable_seed_fails_closed(mcp):
    client, headers = mcp
    text = _call(client, headers, "query_graph", {"question": "helper", "seeds": ["nope_nothing"]}, 2)
    assert text.startswith("No unique node match for --seed")


def test_query_graph_rejects_malformed_seeds(mcp):
    client, headers = mcp
    text = _call(client, headers, "query_graph", {"question": "helper", "seeds": [1]}, 2)
    assert text.startswith("error: seeds must be a list")


def test_query_graph_rejects_whitespace_only_seeds(mcp):
    client, headers = mcp
    text = _call(client, headers, "query_graph", {"question": "helper", "seeds": ["   "]}, 2)
    assert text.startswith("error: seeds must be a list")


def test_affected_without_any_graph_is_an_error_not_a_crash(tmp_path):
    # A pure multi-project server (no default graph): `affected` without a
    # project_path reports an error like every other tool, and still works when
    # the call names a project.
    project = tmp_path / "proj"
    (project / "graphify-out").mkdir(parents=True)
    (project / "graphify-out" / "graph.json").write_text(json.dumps(_GRAPH), encoding="utf-8")
    app = serve_mod._build_http_app(str(tmp_path / "missing" / "graph.json"), json_response=True)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        headers = _session(client)
        text = _call(client, headers, "affected", {"target": "helper()"}, 2)
        assert text.startswith("Error executing affected")
        ok = _call(client, headers, "affected", {"target": "helper()", "project_path": str(project)}, 3)
        assert ok.startswith("Affected nodes for helper()")
        assert "run_app()" in ok
