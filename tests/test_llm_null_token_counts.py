"""Regression tests for #4325: null token counts from LLM backends must not crash extraction.

Some OpenAI-compatible gateways (and custom providers) return a `usage` object
whose token-count fields are `null`. Reading them verbatim left `None` in
`result["input_tokens"]` / `result["output_tokens"]`, which crashed downstream
(`'<' not supported between 'NoneType' and 'int'` in the ollama low-token
warning, and `None` propagating through the per-chunk merge).
"""

import sys
import types
from types import SimpleNamespace

from graphify import llm

_NODE_JSON = '{"nodes": [{"id": "a", "label": "A"}], "edges": [], "hyperedges": []}'


def _fake_openai_null_usage(monkeypatch):
    class _Completions:
        def create(self, **kw):
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content=_NODE_JSON),
                        finish_reason="stop",
                    )
                ],
                usage=SimpleNamespace(prompt_tokens=None, completion_tokens=None),
            )

    mod = types.ModuleType("openai")
    client = SimpleNamespace(chat=SimpleNamespace(completions=_Completions()))
    mod.OpenAI = lambda **kw: client
    mod.AzureOpenAI = lambda **kw: client
    monkeypatch.setitem(sys.modules, "openai", mod)


def _fake_anthropic_null_usage(monkeypatch):
    class _Messages:
        def create(self, **kw):
            return SimpleNamespace(
                content=[SimpleNamespace(text=_NODE_JSON, type="text")],
                usage=SimpleNamespace(input_tokens=None, output_tokens=None),
                stop_reason="end_turn",
            )

    mod = types.ModuleType("anthropic")
    mod.Anthropic = lambda **kw: SimpleNamespace(messages=_Messages())
    monkeypatch.setitem(sys.modules, "anthropic", mod)


def _fake_boto3_null_usage(monkeypatch):
    converse_resp = {
        "output": {"message": {"content": [{"text": _NODE_JSON}]}},
        "usage": {"inputTokens": None, "outputTokens": None},
        "stopReason": "end_turn",
    }

    class _Client:
        def converse(self, **kw):
            return converse_resp

    class _Session:
        def __init__(self, *a, **k):
            pass

        def client(self, *a, **k):
            return _Client()

    mod = types.ModuleType("boto3")
    mod.Session = _Session
    botocore_mod = types.ModuleType("botocore")
    config_mod = types.ModuleType("botocore.config")
    config_mod.Config = lambda **kw: SimpleNamespace(**kw)
    exceptions_mod = types.ModuleType("botocore.exceptions")
    exceptions_mod.ClientError = type("ClientError", (Exception,), {})
    botocore_mod.config = config_mod
    botocore_mod.exceptions = exceptions_mod
    monkeypatch.setitem(sys.modules, "boto3", mod)
    monkeypatch.setitem(sys.modules, "botocore", botocore_mod)
    monkeypatch.setitem(sys.modules, "botocore.config", config_mod)
    monkeypatch.setitem(sys.modules, "botocore.exceptions", exceptions_mod)


def test_openai_compat_null_token_counts_coerced_to_zero(monkeypatch):
    _fake_openai_null_usage(monkeypatch)
    result = llm._call_openai_compat(
        "https://example.invalid/v1", "k", "m", "text", backend="openai"
    )
    assert result["input_tokens"] == 0
    assert result["output_tokens"] == 0


def test_azure_null_token_counts_coerced_to_zero(monkeypatch):
    _fake_openai_null_usage(monkeypatch)
    result = llm._call_azure("k", "https://example.invalid", "m", "text")
    assert result["input_tokens"] == 0
    assert result["output_tokens"] == 0


def test_claude_null_token_counts_coerced_to_zero(monkeypatch):
    _fake_anthropic_null_usage(monkeypatch)
    result = llm._call_claude("k", "claude-sonnet-4-6", "text")
    assert result["input_tokens"] == 0
    assert result["output_tokens"] == 0


def test_bedrock_null_token_counts_coerced_to_zero(monkeypatch):
    _fake_boto3_null_usage(monkeypatch)
    result = llm._call_bedrock("model", "text")
    assert result["input_tokens"] == 0
    assert result["output_tokens"] == 0
