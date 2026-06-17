"""Tests for ANTHROPIC_BASE_URL / ANTHROPIC_MODEL overrides on the claude backend.

These env vars point `--backend claude` at any Anthropic-compatible endpoint
(LiteLLM proxy, gateways, ...) without a providers.json entry — mirroring the
OPENAI_BASE_URL / OPENAI_MODEL pattern.
"""

import importlib

from graphify import llm


def test_claude_defaults_without_env(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    reloaded = importlib.reload(llm)
    try:
        assert reloaded.BACKENDS["claude"]["base_url"] == "https://api.anthropic.com"
        assert reloaded.BACKENDS["claude"]["default_model"] == "claude-sonnet-4-6"
    finally:
        monkeypatch.undo()
        importlib.reload(llm)


def test_claude_base_url_and_model_env_override(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://localhost:4000")
    monkeypatch.setenv("ANTHROPIC_MODEL", "my-proxied-model")
    reloaded = importlib.reload(llm)
    try:
        assert reloaded.BACKENDS["claude"]["base_url"] == "http://localhost:4000"
        assert reloaded.BACKENDS["claude"]["default_model"] == "my-proxied-model"
    finally:
        monkeypatch.undo()
        importlib.reload(llm)
