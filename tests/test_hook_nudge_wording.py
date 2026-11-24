"""#2202 - hook reminders arrive in the agent's tool-result stream. Phrased as
commands ("MANDATORY", "You MUST", "include it in every subagent prompt") they
read like a prompt injection, and agents flag or ignore them. They must state
facts instead.
"""
from __future__ import annotations

import io
import json
import re
import sys

import pytest

from graphify import cli

_COMMANDING = re.compile(r"MANDATORY|\bMUST\b|every subagent prompt|subagent prompt", re.I)


@pytest.mark.parametrize("name", ["_SEARCH_NUDGE", "_READ_NUDGE", "_READ_NUDGE_STALE"])
def test_nudges_state_facts_not_commands(name):
    text = json.loads(getattr(cli, name))["hookSpecificOutput"]["additionalContext"]
    assert not _COMMANDING.search(text), text


def test_strict_deny_does_not_ask_to_spread_itself_to_subagents():
    reason = json.loads(cli._READ_DENY)["hookSpecificOutput"]["permissionDecisionReason"]
    assert "subagent" not in reason.lower()


@pytest.mark.parametrize("kind, tool_input", [
    ("search", {"command": "grep -rn foo src/"}),
    ("read", {"file_path": "src/app.py"}),
])
def test_emitted_reminder_has_no_commands(tmp_path, monkeypatch, kind, tool_input):
    (tmp_path / "graphify-out").mkdir()
    (tmp_path / "graphify-out" / "graph.json").write_text("{}", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    payload = json.dumps({"session_id": "s1", "tool_input": tool_input}).encode()
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(payload)))
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    cli._run_hook_guard(kind)
    text = json.loads(out.getvalue())["hookSpecificOutput"]["additionalContext"]
    assert "graphify query" in text
    assert not _COMMANDING.search(text), text
