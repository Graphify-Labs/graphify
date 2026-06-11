"""Tests for OPENAI_BASE_URL / OPENAI_MODEL overrides on the openai backend.

These env vars point `--backend openai` at any OpenAI-compatible server
(llama.cpp, vLLM, LM Studio, ...) without a providers.json entry.
"""

import importlib

from graphify import llm


def test_openai_defaults_without_env(monkeypatch):
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    reloaded = importlib.reload(llm)
    try:
        assert reloaded.BACKENDS["openai"]["base_url"] == "https://api.openai.com/v1"
        assert reloaded.BACKENDS["openai"]["default_model"] == "gpt-4.1-mini"
    finally:
        monkeypatch.undo()
        importlib.reload(llm)


def test_openai_base_url_and_model_env_override(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:8080/v1")
    monkeypatch.setenv("OPENAI_MODEL", "my-local-model")
    reloaded = importlib.reload(llm)
    try:
        assert reloaded.BACKENDS["openai"]["base_url"] == "http://localhost:8080/v1"
        assert reloaded.BACKENDS["openai"]["default_model"] == "my-local-model"
    finally:
        monkeypatch.undo()
        importlib.reload(llm)


def test_graphify_openai_model_wins_over_openai_model(monkeypatch):
    # model_env_key (GRAPHIFY_OPENAI_MODEL) is resolved at call time and takes
    # precedence over the import-time OPENAI_MODEL default.
    monkeypatch.setenv("OPENAI_MODEL", "env-default-model")
    monkeypatch.setenv("GRAPHIFY_OPENAI_MODEL", "graphify-override-model")
    reloaded = importlib.reload(llm)
    try:
        assert reloaded._default_model_for_backend("openai") == "graphify-override-model"
    finally:
        monkeypatch.undo()
        importlib.reload(llm)
