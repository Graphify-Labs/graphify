"""Tests for *_BASE_URL environment variable support on backends."""

import os
from unittest.mock import patch

from graphify import llm


def _reload_llm():
    import importlib
    importlib.reload(llm)


def test_kimi_base_url_from_env():
    """KIMI_BASE_URL overrides the hardcoded Kimi endpoint."""
    _reload_llm()
    with patch.dict(os.environ, {"KIMI_BASE_URL": "http://proxy.local/v1"}, clear=False):
        _reload_llm()
        assert llm.BACKENDS["kimi"]["base_url"] == "http://proxy.local/v1"
    os.environ.pop("KIMI_BASE_URL", None)
    _reload_llm()


def test_kimi_base_url_defaults_when_unset():
    """Without KIMI_BASE_URL, Kimi uses its default endpoint."""
    os.environ.pop("KIMI_BASE_URL", None)
    _reload_llm()
    assert llm.BACKENDS["kimi"]["base_url"] == "https://api.moonshot.ai/v1"


def test_gemini_base_url_from_env():
    """GEMINI_BASE_URL overrides the hardcoded Gemini endpoint."""
    os.environ.pop("GEMINI_BASE_URL", None)
    _reload_llm()
    with patch.dict(os.environ, {"GEMINI_BASE_URL": "http://proxy.local/gemini"}, clear=False):
        _reload_llm()
        assert llm.BACKENDS["gemini"]["base_url"] == "http://proxy.local/gemini"
    os.environ.pop("GEMINI_BASE_URL", None)
    _reload_llm()


def test_gemini_base_url_defaults_when_unset():
    """Without GEMINI_BASE_URL, Gemini uses its default endpoint."""
    os.environ.pop("GEMINI_BASE_URL", None)
    _reload_llm()
    assert llm.BACKENDS["gemini"]["base_url"] == "https://generativelanguage.googleapis.com/v1beta/openai/"


def test_deepseek_base_url_from_env():
    """DEEPSEEK_BASE_URL overrides the hardcoded DeepSeek endpoint."""
    os.environ.pop("DEEPSEEK_BASE_URL", None)
    _reload_llm()
    with patch.dict(os.environ, {"DEEPSEEK_BASE_URL": "http://proxy.local/deepseek"}, clear=False):
        _reload_llm()
        assert llm.BACKENDS["deepseek"]["base_url"] == "http://proxy.local/deepseek"
    os.environ.pop("DEEPSEEK_BASE_URL", None)
    _reload_llm()


def test_deepseek_base_url_defaults_when_unset():
    """Without DEEPSEEK_BASE_URL, DeepSeek uses its default endpoint."""
    os.environ.pop("DEEPSEEK_BASE_URL", None)
    _reload_llm()
    assert llm.BACKENDS["deepseek"]["base_url"] == "https://api.deepseek.com"
