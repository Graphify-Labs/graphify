"""#1686 - a wedged local Ollama request must not multiply --api-timeout by the
SDK's 6 transient-error retries into a ~20min block. Ollama defaults to 0 SDK
retries so the timeout is the effective wall-clock bound; an explicit
GRAPHIFY_MAX_RETRIES still wins.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import graphify.llm as llm


def _capture_client_kwargs(monkeypatch):
    captured: dict = {}

    def _factory(**kwargs):
        captured.update(kwargs)
        client = MagicMock()
        resp = MagicMock()
        resp.choices[0].message.content = '{"nodes": [], "edges": [], "hyperedges": []}'
        resp.choices[0].finish_reason = "stop"
        resp.usage.prompt_tokens = 1
        resp.usage.completion_tokens = 1
        client.chat.completions.create.return_value = resp
        return client

    monkeypatch.setattr("openai.OpenAI", _factory)
    return captured


def test_ollama_defaults_to_zero_sdk_retries(monkeypatch):
    monkeypatch.delenv("GRAPHIFY_MAX_RETRIES", raising=False)
    captured = _capture_client_kwargs(monkeypatch)
    llm._call_openai_compat("http://localhost:11434/v1", "ollama", "m",
                            "def f(): pass", backend="ollama")
    assert captured.get("max_retries") == 0


def test_ollama_honors_explicit_max_retries(monkeypatch):
    monkeypatch.setenv("GRAPHIFY_MAX_RETRIES", "3")
    captured = _capture_client_kwargs(monkeypatch)
    llm._call_openai_compat("http://localhost:11434/v1", "ollama", "m",
                            "def f(): pass", backend="ollama")
    assert captured.get("max_retries") == 3


def test_cloud_backend_keeps_default_retries(monkeypatch):
    monkeypatch.delenv("GRAPHIFY_MAX_RETRIES", raising=False)
    captured = _capture_client_kwargs(monkeypatch)
    llm._call_openai_compat("https://api.moonshot.cn/v1", "sk-x", "m",
                            "def f(): pass", backend="kimi")
    assert captured.get("max_retries") == 6  # default retained for rate-limited clouds


def test_api_timeout_is_passed_to_client(monkeypatch):
    monkeypatch.setenv("GRAPHIFY_API_TIMEOUT", "180")
    captured = _capture_client_kwargs(monkeypatch)
    llm._call_openai_compat("http://localhost:11434/v1", "ollama", "m",
                            "def f(): pass", backend="ollama")
    assert captured.get("timeout") == 180.0
