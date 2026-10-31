"""Actual stdio MCP session parity against production saved-graph CLI consumers."""
from __future__ import annotations

import asyncio
import os
import sys

import pytest

pytest.importorskip("mcp", reason="QML-013-AC04 requires the optional MCP SDK")

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402
from mcp.types import CallToolResult  # noqa: E402

from tests.qt_consumer_helpers import cli, saved_graph  # noqa: E402


def text_result(result):
    # MCP SDK object attributes changed to snake_case; the protocol alias stays
    # isError. Assert the real result's public wire projection across SDK versions.
    assert result.model_dump(by_alias=True)["isError"] is False, result
    return "\n".join(item.text for item in result.content if item.type == "text").strip()


def test_qml013_ac04_sdk_tool_error_is_rejected():
    """A real SDK result decoded from an error wire payload cannot pass parity."""
    result = CallToolResult.model_validate({"content": [{"type": "text", "text": "tool failed"}],
                                          "isError": True})
    with pytest.raises(AssertionError):
        text_result(result)


def test_stdio_query_path_and_source_node_agree_with_cli(tmp_path, monkeypatch, capsys):
    path, _, component, prop, read = saved_graph(tmp_path)
    monkeypatch.chdir(tmp_path)
    query = cli(monkeypatch, capsys, path, "query", read["id"])
    route = cli(monkeypatch, capsys, path, "path", component["id"], prop["id"])
    parameters = StdioServerParameters(command=sys.executable,
        args=["-X", "utf8", "-m", "graphify.serve", "--graph", str(path)],
        env={**os.environ, "PYTHONUTF8": "1"}, cwd=str(tmp_path))

    async def exercise():
        async with stdio_client(parameters) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                tools = await session.list_tools()
                assert {"query_graph", "shortest_path", "get_node"} <= {tool.name for tool in tools.tools}
                actual_query = await session.call_tool("query_graph", {"question": read["id"], "depth": 2})
                actual_route = await session.call_tool("shortest_path", {"source": component["id"], "target": prop["id"]})
                actual_node = await session.call_tool("get_node", {"node_id": prop["id"]})
                assert text_result(actual_query) == query
                assert text_result(actual_route) == route
                assert "Main.qml" in text_result(actual_node) and prop["id"] in text_result(actual_node)
    asyncio.run(asyncio.wait_for(exercise(), timeout=25))
