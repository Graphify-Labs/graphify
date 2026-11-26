"""End-to-end freshness tests over the real MCP stdio transport (mcp 2.x).

Each test spawns ``python -m graphify.serve <graph.json>`` as a subprocess and
talks to it with a real ``mcp`` ClientSession, so the ``call_tool`` hook, the
banner prefix and the ``graph_stats`` provenance lines are exercised exactly as
an agent would see them.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

pytest.importorskip("mcp")

from tests._freshness_client import call, clean_env, session  # noqa: E402
from tests._freshness_repo import (  # noqa: E402
    commit,
    graph_json,
    log_entries,
    make_repo,
)


@pytest.fixture(autouse=True)
def _fresh_state():
    from graphify import freshness

    freshness.reset_state()


@pytest.fixture
def repo(tmp_path) -> Path:
    return make_repo(tmp_path)


def _run(coro):
    return asyncio.run(coro)


def test_mcp_fresh_graph_has_no_banner(repo, tmp_path):
    log = tmp_path / "log"
    env = clean_env(GRAPHIFY_AUTO_REFRESH="1", GRAPHIFY_AUTO_REFRESH_LOG=str(log))

    async def scenario():
        async with session(str(graph_json(repo)), env) as s:
            return await call(s, "graph_stats", {"project_path": str(repo)})

    text, is_error = _run(scenario())
    assert is_error is False
    assert "[graphify]" not in text
    assert "Built at commit" in text
    assert "Freshness: fresh" in text
    assert log_entries(log) == []


def test_mcp_new_commit_rebuilds_once_and_answers_with_new_code(repo, tmp_path):
    log = tmp_path / "log"
    env = clean_env(GRAPHIFY_AUTO_REFRESH="1", GRAPHIFY_AUTO_REFRESH_LOG=str(log))
    (repo / "gamma.py").write_text("def added_fn(x):\n    return x + 1\n", encoding="utf-8")
    commit(repo, "feat: gamma")

    async def scenario():
        async with session(str(graph_json(repo)), env) as s:
            first, _ = await call(s, "get_node", {"label": "added_fn", "project_path": str(repo)})
            second, _ = await call(s, "graph_stats", {"project_path": str(repo)})
            third, _ = await call(s, "graph_stats", {"project_path": str(repo)})
            return first, second, third

    first, second, third = _run(scenario())
    assert "added_fn()" in first  # answer reflects the committed code
    assert "graph was behind HEAD" in first  # banner on the refreshing call
    assert "[graphify]" not in second  # fresh afterwards
    assert "[graphify]" not in third
    assert len(log_entries(log)) == 1


def test_mcp_missing_graph_is_built_once(repo, tmp_path):
    log = tmp_path / "log"
    env = clean_env(GRAPHIFY_AUTO_REFRESH="1", GRAPHIFY_AUTO_REFRESH_LOG=str(log))
    graph_json(repo).unlink()

    async def scenario():
        async with session(str(graph_json(repo)), env) as s:
            text, is_error = await call(s, "graph_stats", {"project_path": str(repo)})
            return text, is_error

    text, is_error = _run(scenario())
    assert is_error is False
    assert "Nodes:" in text
    assert graph_json(repo).exists()
    assert len(log_entries(log)) == 1


def test_mcp_failure_is_fail_open_and_no_retry(repo, tmp_path, monkeypatch):
    """A broken updater must not crash the server or retry on every call.

    The failure is injected in-process via ``GRAPHIFY_AUTO_REFRESH_*`` is not
    possible across the process boundary, so this test drives the freshness
    module directly rather than through the server.
    """
    from graphify import freshness

    freshness.reset_state()
    log = tmp_path / "log"
    monkeypatch.setenv("GRAPHIFY_AUTO_REFRESH", "1")
    monkeypatch.setenv("GRAPHIFY_AUTO_REFRESH_LOG", str(log))
    monkeypatch.setattr(freshness, "_update_command", lambda root: ["/nonexistent/graphify"])
    (repo / "gamma.py").write_text("def added_fn(x):\n    return x + 1\n", encoding="utf-8")
    commit(repo, "feat: gamma")
    assert freshness.ensure_fresh(str(repo)).state == "failed"
    assert freshness.ensure_fresh(str(repo)).state == "failed"
    assert len(log_entries(log)) == 1


def test_mcp_concurrent_calls_share_one_build(repo, tmp_path):
    log = tmp_path / "log"
    env = clean_env(GRAPHIFY_AUTO_REFRESH="1", GRAPHIFY_AUTO_REFRESH_LOG=str(log))
    (repo / "gamma.py").write_text("def added_fn(x):\n    return x + 1\n", encoding="utf-8")
    commit(repo, "feat: gamma")

    async def scenario():
        async with session(str(graph_json(repo)), env) as s:
            return await asyncio.gather(
                *[call(s, "graph_stats", {"project_path": str(repo)}) for _ in range(6)]
            )

    results = _run(scenario())
    assert all(is_error is False for _, is_error in results)
    assert len(log_entries(log)) == 1


def test_mcp_global_graph_without_project_path_is_untouched(tmp_path):
    # A graph whose directory is not a git repo: no project_path, no rebuild.
    graph_dir = tmp_path / "standalone"
    graph_dir.mkdir()
    graph = graph_dir / "graph.json"
    graph.write_text(
        json.dumps(
            {
                "directed": True,
                "nodes": [{"id": "n1", "label": "solo", "community": 0}],
                "edges": [],
            }
        ),
        encoding="utf-8",
    )
    log = tmp_path / "log"
    env = clean_env(GRAPHIFY_AUTO_REFRESH="1", GRAPHIFY_AUTO_REFRESH_LOG=str(log))

    async def scenario():
        async with session(str(graph), env) as s:
            return await call(s, "graph_stats", {})

    text, is_error = _run(scenario())
    assert is_error is False
    assert "Nodes: 1" in text
    assert "[graphify]" not in text
    assert log_entries(log) == []


def test_mcp_dirty_mode_default_off(repo, tmp_path):
    log = tmp_path / "log"
    env = clean_env(GRAPHIFY_AUTO_REFRESH="1", GRAPHIFY_AUTO_REFRESH_LOG=str(log))
    (repo / "alpha.py").write_text("def greet(name):\n    return 'EDITED'\n", encoding="utf-8")

    async def scenario():
        async with session(str(graph_json(repo)), env) as s:
            return await call(s, "graph_stats", {"project_path": str(repo)})

    text, _ = _run(scenario())
    assert "[graphify]" not in text  # uncommitted edit ignored by default
    assert log_entries(log) == []


def test_mcp_dirty_mode_rebuilds_on_edit(repo, tmp_path):
    log = tmp_path / "log"
    env = clean_env(
        GRAPHIFY_AUTO_REFRESH="1",
        GRAPHIFY_AUTO_REFRESH_DIRTY="1",
        GRAPHIFY_AUTO_REFRESH_LOG=str(log),
    )
    (repo / "alpha.py").write_text("def greet(name):\n    return 'EDITED'\n", encoding="utf-8")

    async def scenario():
        async with session(str(graph_json(repo)), env) as s:
            first, _ = await call(s, "graph_stats", {"project_path": str(repo)})
            second, _ = await call(s, "graph_stats", {"project_path": str(repo)})
            return first, second

    first, second = _run(scenario())
    assert "uncommitted changes" in first
    assert "[graphify]" not in second
    assert len(log_entries(log)) == 1
