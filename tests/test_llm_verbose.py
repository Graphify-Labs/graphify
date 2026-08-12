"""Tests for verbose LLM-call tracing (cluster-only --verbose / GRAPHIFY_LLM_VERBOSE)
and token-economics-only mode (--tokens / GRAPHIFY_LLM_TOKENS).

Backend calls are faked; no network. Covers the verbose/tokens toggles, the
exchange and token-line printers, Anthropic thinking capture, the claude-cli
stream-json parse, and the cluster-only CLI wiring including the label-run
token total.
"""
import json
import sys
import types

import graphify.llm as llm
from graphify.llm import (
    _call_llm,
    _claude_cli_stream_result,
    _verbose_llm_exchange,
    _verbose_llm_tokens,
)


def _fake_anthropic(captured, *, thinking="reasoning here", text='{"0": "Order Management"}'):
    """A minimal stand-in for the `anthropic` package."""
    class _Block:
        def __init__(self, type_, **fields):
            self.type = type_
            self.__dict__.update(fields)

    class _Usage:
        input_tokens = 10
        output_tokens = 20

    class _Response:
        content = [
            _Block("thinking", thinking=thinking),
            _Block("text", text=text),
        ]
        usage = _Usage()

    class _Messages:
        def create(self, **kwargs):
            captured.update(kwargs)
            return _Response()

    class _Client:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs

        messages = _Messages()

    return types.SimpleNamespace(Anthropic=_Client)


def test_llm_verbose_toggle(monkeypatch):
    monkeypatch.delenv("GRAPHIFY_LLM_VERBOSE", raising=False)
    monkeypatch.setattr(llm, "_LLM_VERBOSE", False)
    assert not llm._llm_verbose()
    monkeypatch.setenv("GRAPHIFY_LLM_VERBOSE", "1")
    assert llm._llm_verbose()
    monkeypatch.delenv("GRAPHIFY_LLM_VERBOSE")
    llm.set_llm_verbose(True)
    assert llm._llm_verbose()


def test_verbose_exchange_prints_all_sections(capsys):
    _verbose_llm_exchange(
        backend="claude", model="claude-sonnet-4-6", prompt="PROMPT BODY",
        thinking="THINKING BODY", text="RESPONSE BODY",
        usage={"input": 1234, "output": 56},
    )
    err = capsys.readouterr().err
    assert "backend=claude" in err
    assert "PROMPT BODY" in err
    assert "THINKING BODY" in err
    assert "RESPONSE BODY" in err
    assert "1,234 in · 56 out" in err


def test_verbose_exchange_marks_missing_thinking(capsys):
    _verbose_llm_exchange(
        backend="ollama", model="qwen", prompt="p",
        thinking=None, text="t", usage={"input": 1, "output": 2},
    )
    err = capsys.readouterr().err
    assert "(none returned by backend)" in err


def test_call_llm_claude_verbose_enables_thinking(monkeypatch, capsys):
    captured = {}
    monkeypatch.setitem(sys.modules, "anthropic", _fake_anthropic(captured))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.delenv("GRAPHIFY_LLM_VERBOSE", raising=False)
    monkeypatch.setattr(llm, "_LLM_VERBOSE", True)

    text = _call_llm("name this community", backend="claude", max_tokens=300)

    # Thinking enabled, budget >= 1024 and max_tokens bumped above it.
    assert captured["thinking"] == {"type": "enabled", "budget_tokens": 1024}
    assert captured["max_tokens"] == 2048
    # The reply is the TEXT block, not the thinking block that precedes it.
    assert text == '{"0": "Order Management"}'
    err = capsys.readouterr().err
    assert "reasoning here" in err
    assert "── response ──" in err
    assert "10 in · 20 out" in err


def test_call_llm_claude_non_verbose_unchanged(monkeypatch, capsys):
    captured = {}
    monkeypatch.setitem(sys.modules, "anthropic", _fake_anthropic(captured))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.delenv("GRAPHIFY_LLM_VERBOSE", raising=False)
    monkeypatch.setattr(llm, "_LLM_VERBOSE", False)

    text = _call_llm("name this community", backend="claude", max_tokens=300)

    assert "thinking" not in captured
    assert captured["max_tokens"] == 300
    assert text == '{"0": "Order Management"}'
    assert "[graphify llm]" not in capsys.readouterr().err


def test_claude_cli_stream_result_extracts_thinking():
    events = [
        {"type": "system", "subtype": "init"},
        {"type": "assistant", "message": {"content": [
            {"type": "thinking", "thinking": "hmm"},
            {"type": "text", "text": "partial"},
        ]}},
        {"type": "assistant", "message": {"content": [
            {"type": "thinking", "thinking": "more"},
        ]}},
        {"type": "result", "result": '{"0": "X"}', "is_error": False,
         "usage": {"input_tokens": 5, "output_tokens": 7}},
    ]
    stdout = "\n".join(json.dumps(e) for e in events)

    envelope, thinking = _claude_cli_stream_result(stdout)

    assert envelope["result"] == '{"0": "X"}'
    assert envelope["usage"]["output_tokens"] == 7
    assert thinking == "hmm\nmore"


def test_claude_cli_stream_result_requires_result_event():
    import pytest
    with pytest.raises(RuntimeError, match="no result event"):
        _claude_cli_stream_result('{"type": "system"}\n{"type": "assistant"}')


def test_label_cli_verbose_traces_and_totals(tmp_path, monkeypatch, capsys):
    import graphify.__main__ as cli

    out = tmp_path / "graphify-out"
    out.mkdir()
    graph = {
        "directed": False,
        "multigraph": False,
        "nodes": [{"id": "n1", "label": "OrderService", "community": 0}],
        "links": [],
    }
    (out / "graph.json").write_text(json.dumps(graph), encoding="utf-8")

    def fake_generate(G, communities, *, backend=None, model=None, gods=None,
                      quiet=False, max_concurrency=4, batch_size=100, usage_out=None):
        if usage_out is not None:
            usage_out["input"] = 100
            usage_out["output"] = 42
        return {0: "Orders"}, "llm"

    monkeypatch.setattr("graphify.llm.generate_community_labels", fake_generate)
    monkeypatch.setattr("graphify.export.to_html", lambda *args, **kwargs: None)
    # Restore the module global after the run even though the CLI flips it.
    monkeypatch.setattr(llm, "_LLM_VERBOSE", False)
    monkeypatch.setattr(
        sys, "argv",
        ["graphify", "label", str(tmp_path), "--backend", "claude", "--verbose", "--no-viz"],
    )

    cli.main()

    assert llm._LLM_VERBOSE is True
    err = capsys.readouterr().err
    assert "label run total: 100 in · 42 out" in err
    # claude pricing: (100*3 + 42*15) / 1e6 = $0.00093
    assert "~$0.0009 @ claude" in err


def test_llm_tokens_toggle(monkeypatch):
    monkeypatch.delenv("GRAPHIFY_LLM_TOKENS", raising=False)
    monkeypatch.setattr(llm, "_LLM_TOKENS", False)
    assert not llm._llm_tokens()
    monkeypatch.setenv("GRAPHIFY_LLM_TOKENS", "1")
    assert llm._llm_tokens()
    monkeypatch.delenv("GRAPHIFY_LLM_TOKENS")
    llm.set_llm_tokens(True)
    assert llm._llm_tokens()


def test_tokens_line_prints_counts_only(capsys):
    _verbose_llm_tokens(
        backend="claude", model="claude-sonnet-4-6",
        prompt="PROMPT BODY", usage={"input": 1234, "output": 56},
    )
    err = capsys.readouterr().err
    assert "backend=claude" in err
    assert "1,234 in · 56 out" in err
    # The one-liner never leaks bodies.
    assert "PROMPT BODY" not in err
    assert "── prompt ──" not in err


def test_call_llm_claude_tokens_mode_is_side_effect_free(monkeypatch, capsys):
    captured = {}
    monkeypatch.setitem(sys.modules, "anthropic", _fake_anthropic(captured))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.delenv("GRAPHIFY_LLM_VERBOSE", raising=False)
    monkeypatch.delenv("GRAPHIFY_LLM_TOKENS", raising=False)
    monkeypatch.setattr(llm, "_LLM_VERBOSE", False)
    monkeypatch.setattr(llm, "_LLM_TOKENS", True)

    text = _call_llm("name this community", backend="claude", max_tokens=300)

    # Unlike verbose, tokens mode does not shape the call: no extended
    # thinking, max_tokens untouched.
    assert "thinking" not in captured
    assert captured["max_tokens"] == 300
    assert text == '{"0": "Order Management"}'
    err = capsys.readouterr().err
    assert "10 in · 20 out" in err
    # …and no bodies are dumped.
    assert "name this community" not in err
    assert "reasoning here" not in err


def test_call_llm_verbose_takes_precedence_over_tokens(monkeypatch, capsys):
    captured = {}
    monkeypatch.setitem(sys.modules, "anthropic", _fake_anthropic(captured))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.delenv("GRAPHIFY_LLM_VERBOSE", raising=False)
    monkeypatch.delenv("GRAPHIFY_LLM_TOKENS", raising=False)
    monkeypatch.setattr(llm, "_LLM_VERBOSE", True)
    monkeypatch.setattr(llm, "_LLM_TOKENS", True)

    _call_llm("name this community", backend="claude", max_tokens=300)

    err = capsys.readouterr().err
    # Full exchange (which already carries the token line), not the one-liner.
    assert "── prompt ──" in err
    assert "── response ──" in err


def test_label_cli_tokens_prints_run_total(tmp_path, monkeypatch, capsys):
    import graphify.__main__ as cli

    out = tmp_path / "graphify-out"
    out.mkdir()
    graph = {
        "directed": False,
        "multigraph": False,
        "nodes": [{"id": "n1", "label": "OrderService", "community": 0}],
        "links": [],
    }
    (out / "graph.json").write_text(json.dumps(graph), encoding="utf-8")

    def fake_generate(G, communities, *, backend=None, model=None, gods=None,
                      quiet=False, max_concurrency=4, batch_size=100, usage_out=None):
        if usage_out is not None:
            usage_out["input"] = 100
            usage_out["output"] = 42
        return {0: "Orders"}, "llm"

    monkeypatch.setattr("graphify.llm.generate_community_labels", fake_generate)
    monkeypatch.setattr("graphify.export.to_html", lambda *args, **kwargs: None)
    # Restore the module global after the run even though the CLI flips it.
    monkeypatch.setattr(llm, "_LLM_TOKENS", False)
    monkeypatch.setattr(
        sys, "argv",
        ["graphify", "label", str(tmp_path), "--backend", "claude", "--tokens", "--no-viz"],
    )

    cli.main()

    assert llm._LLM_TOKENS is True
    assert llm._LLM_VERBOSE is False
    err = capsys.readouterr().err
    assert "label run total: 100 in · 42 out" in err
    assert "~$0.0009 @ claude" in err
