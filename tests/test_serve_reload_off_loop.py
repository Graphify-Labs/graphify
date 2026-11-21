"""MCP requests are not blocked by a graph.json reload (#5371).

#5181 made ``_GraphContextCache.load`` hand a stale entry to a second caller
while a rebuild is in flight, but ``call_tool`` / ``read_resource`` ran the
load synchronously on the event loop, so no second caller could ever get in.
These tests drive the server's own request handlers concurrently.
"""
from __future__ import annotations

import json
import os
import time

import anyio
import pytest

pytest.importorskip("mcp")
from mcp import types  # noqa: E402

from graphify import serve as serve_mod  # noqa: E402

DELAY = 0.8
GRAPH = {"directed": True, "nodes": [{"id": "a", "label": "A", "community": 0}], "edges": []}


def _server(tmp_path, monkeypatch, slow_only=None):
    path = tmp_path / "graph.json"
    path.write_text(json.dumps(GRAPH))
    server = serve_mod._build_server(str(path))  # warm load, fast
    original = serve_mod._GraphContextCache._load_entry

    def slow(self, resolved_path, key):
        if slow_only is None or slow_only in resolved_path:
            time.sleep(DELAY)  # stands in for parsing a large graph.json
        return original(self, resolved_path, key)

    monkeypatch.setattr(serve_mod._GraphContextCache, "_load_entry", slow)
    later = time.time() + 10
    os.utime(path, (later, later))  # what any rebuild does
    return server


def _call_params(arguments=None):
    return ("tools/call", types.CallToolRequestParams(name="graph_stats", arguments=arguments or {}))


def _read_params(uri):
    return ("resources/read", types.ReadResourceRequestParams(uri=uri))


async def _send(server, method, params) -> str:
    """Dispatch one request to the server's own handler, on mcp 1.x or 2.x."""
    if hasattr(server, "request_handlers"):  # mcp 1.x
        if method == "tools/call":
            req = types.CallToolRequest(method=method, params=params)
            return (await server.request_handlers[types.CallToolRequest](req)).root.content[0].text
        req = types.ReadResourceRequest(method=method, params=params)
        return (await server.request_handlers[types.ReadResourceRequest](req)).root.contents[0].text
    # mcp 2.x: graphify's on_* callbacks ignore the request context
    result = await server.get_request_handler(method).handler(None, params)
    return result.content[0].text if method == "tools/call" else result.contents[0].text


async def _timed(server, req, out, k, arrival):
    # Each request has a planned arrival time and is timed from it. Timing
    # from when the coroutine starts would hide the stall: a load blocking
    # the event loop also delays the start of every other coroutine.
    await anyio.sleep_until(arrival)
    await _send(server, *req)
    out[k] = anyio.current_time() - arrival


def _concurrent(server, reqs):
    async def main():
        out = {}
        base = anyio.current_time()
        async with anyio.create_task_group() as tg:
            for k, req in enumerate(reqs):
                tg.start_soon(_timed, server, req, out, k, base + 0.05 * k)
        return [out[k] for k in range(len(reqs))]

    return anyio.run(main)


def test_concurrent_tool_calls_served_from_current_graph_during_reload(tmp_path, monkeypatch):
    times = _concurrent(_server(tmp_path, monkeypatch), [_call_params() for _ in range(3)])
    assert times[0] >= DELAY  # the call that triggered the reload pays for it
    assert max(times[1:]) < DELAY / 2, times  # the others get the current graph


def test_resource_read_not_blocked_by_a_tool_call_reload(tmp_path, monkeypatch):
    times = _concurrent(_server(tmp_path, monkeypatch), [_call_params(), _read_params("graphify://stats")])
    assert times[1] < DELAY / 2, times


def test_project_call_during_default_reload_answers_its_own_graph(tmp_path, monkeypatch):
    """A project_path call that arrives while the default graph reloads in a
    worker thread is answered quickly from the project's graph, and the call
    that triggered the reload is still answered from the default graph."""
    proj = tmp_path / "proj"
    (proj / "graphify-out").mkdir(parents=True)
    nodes = [{"id": f"p{i}", "label": f"P{i}", "community": 0} for i in range(3)]
    (proj / "graphify-out" / "graph.json").write_text(json.dumps({**GRAPH, "nodes": nodes}))
    server = _server(tmp_path, monkeypatch, slow_only=str(tmp_path / "graph.json"))
    out, took = {}, {}

    async def call(k, arguments, arrival):
        await anyio.sleep_until(arrival)
        out[k] = await _send(server, *_call_params(arguments))
        took[k] = anyio.current_time() - arrival

    async def main():
        base = anyio.current_time()
        async with anyio.create_task_group() as tg:
            tg.start_soon(call, 0, {}, base)
            tg.start_soon(call, 1, {"project_path": str(proj)}, base + 0.05)

    anyio.run(main)
    assert "Nodes: 1" in out[0], out
    assert "Nodes: 3" in out[1], out
    assert took[1] < DELAY / 2, took
