"""Tests for the `cursor-cli` backend.

Mirrors tests/test_claude_cli_backend.py: mocks subprocess.run +
shutil.which so the suite runs on CI without the `cursor-agent`
binary or a live network call.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from graphify import llm

_ENVELOPE = {
    "type": "result",
    "subtype": "success",
    "is_error": False,
    "result": json.dumps({
        "nodes": [
            {"id": "foo_module", "label": "Foo", "file_type": "document", "source_file": "foo.md"},
            {"id": "foo_greet", "label": "greet", "file_type": "code", "source_file": "foo.md"},
        ],
        "edges": [
            {"source": "foo_module", "target": "foo_greet",
             "relation": "references", "confidence": "EXTRACTED", "confidence_score": 1.0},
        ],
        "hyperedges": [],
        "input_tokens": 0,
        "output_tokens": 0,
    }),
    "session_id": "c71b4c4b-0000-0000-0000-000000000000",
    "usage": {"inputTokens": 15946, "outputTokens": 31, "cacheReadTokens": 5376},
}

_ERROR_ENVELOPE = {
    "type": "result",
    "subtype": "error",
    "is_error": True,
    "result": "API Error: Rate limit reached",
    "usage": {"inputTokens": 0, "outputTokens": 0},
}


@pytest.fixture
def fake_cursor(monkeypatch):
    completed = MagicMock(returncode=0, stdout=json.dumps(_ENVELOPE), stderr="")
    monkeypatch.setattr(llm, "_response_is_hollow", lambda raw, parsed: False)
    with patch("shutil.which", return_value="/fake/bin/cursor-agent"), \
         patch("subprocess.run", return_value=completed) as run:
        yield run


def test_returns_parsed_nodes_and_edges(fake_cursor):
    result = llm._call_cursor_cli("dummy", max_tokens=8192)
    assert len(result["nodes"]) == 2
    assert len(result["edges"]) == 1


def test_token_accounting_uses_envelope_usage(fake_cursor):
    # cursor-agent reports camelCase token counts in the JSON envelope.
    result = llm._call_cursor_cli("dummy", max_tokens=8192)
    assert result["input_tokens"] == 15946
    assert result["output_tokens"] == 31
    assert result["finish_reason"] == "stop"


def test_raises_when_cli_missing():
    with patch("shutil.which", return_value=None):
        with pytest.raises(RuntimeError, match="Cursor Agent CLI not found"):
            llm._call_cursor_cli("dummy", max_tokens=8192)


def test_raises_on_nonzero_exit():
    completed = MagicMock(returncode=2, stdout="", stderr="auth failed")
    with patch("shutil.which", return_value="/fake/bin/cursor-agent"), \
         patch("subprocess.run", return_value=completed):
        with pytest.raises(RuntimeError, match="cursor-agent -p failed"):
            llm._call_cursor_cli("dummy", max_tokens=8192)


def test_raises_on_error_envelope_with_zero_exit():
    # cursor-agent flags API failures with is_error in the stdout envelope
    # while exiting 0. Parsing `result` as model output would yield an empty
    # graph that the hollow-retry path then bisects forever (#2554).
    completed = MagicMock(
        returncode=0, stdout=json.dumps(_ERROR_ENVELOPE), stderr="",
    )
    with patch("shutil.which", return_value="/fake/bin/cursor-agent"), \
         patch("subprocess.run", return_value=completed):
        with pytest.raises(RuntimeError, match="Rate limit reached"):
            llm._call_cursor_cli("dummy", max_tokens=8192)


def test_raises_on_error_envelope_when_stderr_carries_the_cause():
    completed = MagicMock(
        returncode=1, stdout=json.dumps(_ERROR_ENVELOPE), stderr="",
    )
    with patch("shutil.which", return_value="/fake/bin/cursor-agent"), \
         patch("subprocess.run", return_value=completed):
        with pytest.raises(RuntimeError, match="Rate limit reached"):
            llm._call_cursor_cli("dummy", max_tokens=8192)


def test_raises_on_garbage_envelope():
    # A non-JSON stdout with exit 0 must fail loudly rather than parse to an
    # empty graph (#2554).
    completed = MagicMock(returncode=0, stdout="not json", stderr="")
    with patch("shutil.which", return_value="/fake/bin/cursor-agent"), \
         patch("subprocess.run", return_value=completed):
        with pytest.raises(RuntimeError, match="unparseable JSON envelope"):
            llm._call_cursor_cli("dummy", max_tokens=8192)


def test_call_llm_raises_on_error_envelope():
    # _call_llm feeds community labeling and the dedup tiebreaker; an error
    # envelope must not leak its prose into the graph as a label (#2554).
    completed = MagicMock(
        returncode=0, stdout=json.dumps(_ERROR_ENVELOPE), stderr="",
    )
    with patch("shutil.which", return_value="/fake/bin/cursor-agent"), \
         patch("subprocess.run", return_value=completed):
        with pytest.raises(RuntimeError, match="Rate limit reached"):
            llm._call_llm("dummy", backend="cursor-cli")


def test_call_llm_success_still_returns_result_text():
    envelope = dict(_ENVELOPE, result="a fine label")
    completed = MagicMock(returncode=0, stdout=json.dumps(envelope), stderr="")
    with patch("shutil.which", return_value="/fake/bin/cursor-agent"), \
         patch("subprocess.run", return_value=completed):
        assert llm._call_llm("dummy", backend="cursor-cli") == "a fine label"


def test_call_llm_accumulates_usage(fake_cursor):
    usage_out: dict = {}
    llm._call_llm("dummy", backend="cursor-cli", usage_out=usage_out)
    assert usage_out["input"] == 15946
    assert usage_out["output"] == 31


def test_extract_files_direct_dispatches_to_cursor_cli(tmp_path, fake_cursor):
    f = tmp_path / "foo.md"
    f.write_text("# Foo\n\nThe greet() helper formats a name.\n")
    result = llm.extract_files_direct(files=[f], backend="cursor-cli", root=tmp_path)
    assert fake_cursor.called
    assert len(result["nodes"]) == 2


def test_backend_registered_with_zero_cost():
    assert "cursor-cli" in llm.BACKENDS
    pricing = llm.BACKENDS["cursor-cli"]["pricing"]
    assert pricing["input"] == 0.0
    assert pricing["output"] == 0.0
    assert llm.estimate_cost("cursor-cli", 1_000_000, 1_000_000) == 0.0


# ---------- invocation shape ----------


def test_trust_and_ask_flags_in_subprocess(fake_cursor):
    # --trust satisfies non-interactive workspace trust; ask mode keeps the
    # agent read-only over the corpus it is extracting from.
    llm._call_cursor_cli("dummy", max_tokens=8192)
    argv = fake_cursor.call_args.args[0]
    assert "--trust" in argv
    assert "--mode" in argv
    assert "ask" in argv
    assert "--output-format" in argv
    assert "json" in argv


def test_prompt_travels_over_stdin(fake_cursor):
    # Real extraction chunks exceed argv size limits (Linux MAX_ARG_STRLEN
    # is 128 KB; chunks reach 240-306 KB), so the prompt must ride stdin.
    llm._call_cursor_cli("UNIQUE_SOURCE_MARKER", max_tokens=8192)
    argv = fake_cursor.call_args.args[0]
    assert "UNIQUE_SOURCE_MARKER" not in " ".join(argv)
    sent = fake_cursor.call_args.kwargs["input"]
    assert "UNIQUE_SOURCE_MARKER" in sent


def test_no_model_flag_by_default(fake_cursor):
    # Without GRAPHIFY_CURSOR_CLI_MODEL the CLI's own model routing (auto)
    # decides; graphify must not pin one.
    llm._call_cursor_cli("dummy", max_tokens=8192)
    argv = fake_cursor.call_args.args[0]
    assert "--model" not in argv


def test_model_env_var_pins_model(fake_cursor, monkeypatch):
    monkeypatch.setenv("GRAPHIFY_CURSOR_CLI_MODEL", "composer-2.5")
    llm._call_cursor_cli("dummy", max_tokens=8192)
    argv = fake_cursor.call_args.args[0]
    assert "--model" in argv
    assert "composer-2.5" in argv


# ---------- extraction instructions delivered in the user turn ----------
# Same failure mode as claude-cli (#2076/#2554): a bare file dump with no
# explicit request makes a coding agent reply conversationally, which parses
# to zero nodes. The instructions ride in the user turn instead.


def test_extraction_instructions_ride_in_user_turn(fake_cursor):
    """The full extraction schema, an explicit imperative, and the source must
    all be delivered via stdin."""
    llm._call_cursor_cli("UNIQUE_SOURCE_MARKER", max_tokens=8192)
    sent = fake_cursor.call_args.kwargs["input"]
    assert "graphify semantic extraction agent" in sent
    assert "output ONLY the JSON object" in sent
    assert "UNIQUE_SOURCE_MARKER" in sent


def test_user_turn_preserves_untrusted_source_guardrails(fake_cursor):
    """The <untrusted_source> guardrails from _extraction_system must survive
    the move into the user turn (prompt-injection defence is unchanged)."""
    llm._call_cursor_cli("dummy", max_tokens=8192)
    sent = fake_cursor.call_args.kwargs["input"]
    assert "untrusted_source" in sent
