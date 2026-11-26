"""Minimal scripted MCP stdio client for the freshness experiment.

Spawns ``python -m graphify.serve <graph.json>`` with a chosen environment and
calls tools through a real mcp ClientSession (mcp 2.x). Used by the pytest
suite and by ``scripts/run_cases.py``.
"""
from __future__ import annotations

import asyncio
import os
import sys
from contextlib import asynccontextmanager


def clean_env(**overrides: str) -> dict:
    """Base env for the spawned server: drop pytest/hash-seed leakage so the
    server behaves as it would in production."""
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("PYTEST_CURRENT_TEST", "PYTHONHASHSEED")
    }
    env.update({k: str(v) for k, v in overrides.items()})
    return env


@asynccontextmanager
async def session(graph_json: str, env: dict | None = None):
    # mcp is an optional extra; imported lazily so this helper (and the
    # mcp-free unit tests that import the module) does not require it.
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "graphify.serve", graph_json],
        env=env if env is not None else clean_env(),
        cwd=os.path.dirname(graph_json) or None,
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()
            yield s


async def call(s, name: str, arguments: dict | None = None) -> tuple[str, bool]:
    result = await s.call_tool(name, arguments or {})
    text = ""
    if getattr(result, "content", None):
        text = result.content[0].text
    return text, bool(getattr(result, "isError", False))
