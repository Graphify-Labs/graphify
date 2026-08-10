"""Tests for `_parse_llm_json` robustness and the `_call_claude_cli`
subprocess argv shape introduced in the hollow-response fix.

These tests cover:
- The four parser failure modes described in PR #1062
- Extraction instructions delivered in the user turn (Claude Code >= 2.1)
- The GRAPHIFY_CLAUDE_CLI_MODEL env-var passthrough
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from graphify import llm


# ---------- _parse_llm_json: the four canonical failure modes ----------


def test_preamble_then_fence_is_parsed():
    """Claude often prefixes the JSON with a short preamble before the
    ```json fence. The original parser only stripped fences at offset 0,
    so any preamble caused json.loads to fail and the chunk to be
    dropped as a hollow response. The robust parser handles fences
    anywhere in the text."""
    raw = (
        "Here are the extracted entities:\n\n"
        '```json\n{"nodes": [{"id": "a"}], "edges": []}\n```'
    )
    result = llm._parse_llm_json(raw)
    assert result["nodes"] == [{"id": "a"}]
    assert result["edges"] == []


def test_prose_wrapped_json_without_fence_is_parsed():
    """Some models return prose around bare JSON with no markdown fence.
    The balanced-brace fallback extracts the first complete object."""
    raw = (
        'The extracted graph is {"nodes": [{"id": "b"}], "edges": []}. '
        "Hope this helps!"
    )
    result = llm._parse_llm_json(raw)
    assert result["nodes"] == [{"id": "b"}]


def test_raw_json_still_works():
    """Regression: clean JSON input (the original happy path) must keep
    parsing exactly as before."""
    raw = '{"nodes": [], "edges": [], "hyperedges": []}'
    result = llm._parse_llm_json(raw)
    assert result == {"nodes": [], "edges": [], "hyperedges": []}


def test_total_refusal_returns_empty_fragment():
    """When the model refuses or returns unrelated prose, the parser
    must degrade gracefully — return the empty fragment so the hollow
    detector takes over, never raise."""
    raw = "I cannot extract structured data from this content."
    result = llm._parse_llm_json(raw)
    assert result == {"nodes": [], "edges": [], "hyperedges": []}


# ---------- _parse_llm_json: secondary cases worth pinning ----------


def test_fence_with_uppercase_language_tag():
    raw = '```JSON\n{"nodes": [{"id": "x"}], "edges": []}\n```'
    result = llm._parse_llm_json(raw)
    assert result["nodes"] == [{"id": "x"}]


def test_fence_without_closing_backticks():
    """Truncated response: the model started the fence but ran out of
    tokens before closing it. We should still recover the JSON body."""
    raw = '```json\n{"nodes": [{"id": "y"}], "edges": []}'
    result = llm._parse_llm_json(raw)
    assert result["nodes"] == [{"id": "y"}]


def test_empty_response_returns_empty_fragment():
    assert llm._parse_llm_json("") == {"nodes": [], "edges": [], "hyperedges": []}


# ---------- _call_claude_cli: argv shape ----------


def _make_envelope(result_obj: dict) -> str:
    return json.dumps({
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": json.dumps(result_obj),
        "usage": {"input_tokens": 1, "output_tokens": 1,
                  "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
        "modelUsage": {"claude-opus-4-7": {}},
        "stop_reason": "end_turn",
    })


@patch("shutil.which", return_value="/usr/local/bin/claude")
@patch("subprocess.run")
def test_instructions_ride_in_user_turn_not_system_prompt(mock_run, _which):
    """Extraction instructions must be delivered in the user turn, not via
    --system-prompt.

    History: the original hollow-response cause was --append-system-prompt
    layering graphify's prompt on top of Claude Code's default agent prompt;
    the first fix switched to --system-prompt (replace). But newer Claude Code
    CLIs (>= ~2.1) don't treat --system-prompt as the sole authority — they
    keep the coding-agent context and reply conversationally to a bare file
    dump, which parses to zero nodes and gets bisected forever. The instructions
    now ride in the user turn (stdin) and neither system-prompt flag is used."""
    mock_run.return_value.returncode = 0
    mock_run.return_value.stdout = _make_envelope({"nodes": [], "edges": [], "hyperedges": []})
    mock_run.return_value.stderr = ""
    llm._call_claude_cli("payload")
    argv = mock_run.call_args.args[0]
    assert "--system-prompt" not in argv, (
        f"--system-prompt is ignored by Claude Code >= 2.1; argv: {argv}"
    )
    assert "--append-system-prompt" not in argv
    sent = mock_run.call_args.kwargs["input"]
    assert "graphify semantic extraction agent" in sent
    assert "output ONLY the JSON object" in sent
    assert "payload" in sent


@patch("shutil.which", return_value="/usr/local/bin/claude")
@patch("subprocess.run")
def test_model_env_var_adds_model_flag(mock_run, _which, monkeypatch):
    """GRAPHIFY_CLAUDE_CLI_MODEL must be forwarded to claude -p --model."""
    monkeypatch.setenv("GRAPHIFY_CLAUDE_CLI_MODEL", "haiku")
    mock_run.return_value.returncode = 0
    mock_run.return_value.stdout = _make_envelope({"nodes": [], "edges": [], "hyperedges": []})
    mock_run.return_value.stderr = ""
    llm._call_claude_cli("payload")
    argv = mock_run.call_args.args[0]
    assert "--model" in argv
    assert argv[argv.index("--model") + 1] == "haiku"


@patch("shutil.which", return_value="/usr/local/bin/claude")
@patch("subprocess.run")
def test_no_model_flag_when_env_var_unset(mock_run, _which, monkeypatch):
    """Default behaviour: when the env var is not set, --model is not
    added so claude-cli's own default kicks in."""
    monkeypatch.delenv("GRAPHIFY_CLAUDE_CLI_MODEL", raising=False)
    mock_run.return_value.returncode = 0
    mock_run.return_value.stdout = _make_envelope({"nodes": [], "edges": [], "hyperedges": []})
    mock_run.return_value.stderr = ""
    llm._call_claude_cli("payload")
    argv = mock_run.call_args.args[0]
    assert "--model" not in argv
