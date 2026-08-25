"""Tests for the kimi backend's reasoning_effort config (GRAPHIFY_KIMI_EFFORT).

Kimi K3 advertises valid_efforts ["low","high","max"] on /models; sending
nothing let the server default ("high") apply silently. The backend config now
carries an explicit effort, defaulting to "max", overridable via env — the
same import-time pattern as ANTHROPIC_BASE_URL on the claude backend.
"""

import importlib

from graphify import llm


def test_kimi_reasoning_effort_defaults_to_max(monkeypatch):
    monkeypatch.delenv("GRAPHIFY_KIMI_EFFORT", raising=False)
    reloaded = importlib.reload(llm)
    try:
        assert reloaded.BACKENDS["kimi"]["reasoning_effort"] == "max"
    finally:
        monkeypatch.undo()
        importlib.reload(llm)


def test_kimi_reasoning_effort_env_override(monkeypatch):
    monkeypatch.setenv("GRAPHIFY_KIMI_EFFORT", "low")
    reloaded = importlib.reload(llm)
    try:
        assert reloaded.BACKENDS["kimi"]["reasoning_effort"] == "low"
    finally:
        monkeypatch.undo()
        importlib.reload(llm)
