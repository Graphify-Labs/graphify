"""Tests for the subscription-authenticated Codex CLI backend."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from graphify import llm


def _codex_events(result: dict) -> str:
    return "\n".join(
        [
            json.dumps({"type": "thread.started", "thread_id": "test"}),
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {
                        "type": "agent_message",
                        "text": json.dumps(result),
                    },
                }
            ),
            json.dumps(
                {
                    "type": "turn.completed",
                    "usage": {
                        "input_tokens": 10,
                        "cached_input_tokens": 4,
                        "output_tokens": 7,
                    },
                }
            ),
        ]
    )


def test_codex_cli_backend_requires_no_api_key(monkeypatch):
    result = {"nodes": [], "edges": [], "hyperedges": []}
    completed = MagicMock(returncode=0, stdout=_codex_events(result), stderr="")
    monkeypatch.delenv("GRAPHIFY_CODEX_CLI_MODEL", raising=False)
    with patch("shutil.which", return_value="/fake/bin/codex"), \
         patch("subprocess.run", return_value=completed) as run:
        parsed = llm._call_codex_cli("source", max_tokens=512)

    assert parsed["nodes"] == []
    assert parsed["input_tokens"] == 14
    assert parsed["output_tokens"] == 7
    argv = run.call_args.args[0]
    assert argv[0] == "/fake/bin/codex"
    assert argv[1:3] == ["exec", "--ephemeral"]
    assert "--sandbox" in argv and argv[argv.index("--sandbox") + 1] == "read-only"
    assert "--ignore-user-config" in argv
    assert "--ignore-rules" in argv
    assert "--json" in argv
    assert "--model" not in argv


def test_codex_cli_forwards_explicit_model(monkeypatch):
    result = {"nodes": [], "edges": [], "hyperedges": []}
    completed = MagicMock(returncode=0, stdout=_codex_events(result), stderr="")
    with patch("shutil.which", return_value="/fake/bin/codex"), \
         patch("subprocess.run", return_value=completed) as run:
        llm._call_codex_cli("source", model="gpt-test", max_tokens=512)

    argv = run.call_args.args[0]
    assert argv[argv.index("--model") + 1] == "gpt-test"


def test_codex_cli_extract_prompt_contains_schema_and_source(monkeypatch):
    result = {"nodes": [], "edges": [], "hyperedges": []}
    completed = MagicMock(returncode=0, stdout=_codex_events(result), stderr="")
    with patch("shutil.which", return_value="/fake/bin/codex"), \
         patch("subprocess.run", return_value=completed) as run:
        llm._call_codex_cli("UNIQUE_SOURCE_MARKER", max_tokens=512)

    sent = run.call_args.kwargs["input"]
    assert "graphify semantic extraction agent" in sent
    assert "output ONLY the JSON object" in sent
    assert "UNIQUE_SOURCE_MARKER" in sent


def test_extract_files_direct_dispatches_without_an_api_key(tmp_path):
    source = tmp_path / "note.md"
    source.write_text("# Subscription route\n")
    result = {"nodes": [], "edges": [], "hyperedges": []}
    with patch("graphify.llm._call_codex_cli", return_value=result) as call:
        assert llm.extract_files_direct([source], backend="codex-cli", root=tmp_path) is result
    assert call.called


def test_codex_cli_missing_binary_is_actionable():
    with patch("shutil.which", return_value=None):
        try:
            llm._call_codex_cli("source")
        except RuntimeError as exc:
            assert "GRAPHIFY_CODEX_BIN" in str(exc)
            assert "codex login" in str(exc)
        else:
            raise AssertionError("expected a missing Codex CLI error")


def test_codex_cli_is_registered_as_zero_cost_backend():
    assert "codex-cli" in llm.BACKENDS
    assert llm.BACKENDS["codex-cli"]["pricing"] == {"input": 0.0, "output": 0.0}
    assert llm.estimate_cost("codex-cli", 1_000_000, 1_000_000) == 0.0
