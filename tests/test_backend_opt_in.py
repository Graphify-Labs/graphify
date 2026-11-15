"""Explicit backend selection + disable switch for ambient-key auto-detection (#4361).

`detect_backend()` picks a cloud provider purely from whichever API key is set
in the environment, and community labeling additionally falls back to `claude -p`
when the CLI is on PATH. Keys in a developer environment are often there for
other tools, so a bare `graphify extract .` could send uncached documents to a
provider the user did not intend.

These tests pin the additions that put the user back in control:

- `GRAPHIFY_BACKEND=<name>` selects a backend explicitly, overriding ambient keys;
- `GRAPHIFY_BACKEND=none` disables every LLM backend, including the `claude -p`
  fallback, so the AST pass keeps working;
- auto-detection reports the exact environment variable that selected it.
"""
from __future__ import annotations

import pytest

from graphify import llm

DISABLE_SENTINELS = ["none", "off", "disable", "disabled"]


def test_detect_backend_with_source_names_the_ambient_variable(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "ambient")
    backend, source = llm.detect_backend_with_source()
    assert backend == "gemini"
    assert source == "auto-detected from GEMINI_API_KEY"
    assert llm.detect_backend() == "gemini"


def test_graphify_backend_selects_explicitly(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "ambient")
    monkeypatch.setenv("GRAPHIFY_BACKEND", "openai")
    backend, source = llm.detect_backend_with_source()
    assert backend == "openai", "GRAPHIFY_BACKEND must win over an ambient key"
    assert source == "GRAPHIFY_BACKEND=openai"


@pytest.mark.parametrize("sentinel", DISABLE_SENTINELS)
def test_graphify_backend_none_disables(monkeypatch, sentinel):
    monkeypatch.setenv("GEMINI_API_KEY", "ambient")
    monkeypatch.setenv("GRAPHIFY_BACKEND", sentinel)
    assert llm.detect_backend() is None
    assert llm.backend_disabled_by_env() is True
    _, source = llm.detect_backend_with_source()
    assert source == f"GRAPHIFY_BACKEND={sentinel}"


def test_backend_not_disabled_when_unset(monkeypatch):
    assert llm.backend_disabled_by_env() is False


def test_extract_files_direct_refuses_cleanly_when_disabled(monkeypatch):
    monkeypatch.setenv("GRAPHIFY_BACKEND", "none")
    with pytest.raises(ValueError, match="GRAPHIFY_BACKEND=none"):
        llm.extract_files_direct([], backend=None)


def test_generate_community_labels_skips_claude_cli_when_disabled(monkeypatch):
    monkeypatch.setenv("GRAPHIFY_BACKEND", "none")
    monkeypatch.setattr(llm, "_claude_cli_available", lambda: True)

    calls = {"n": 0}

    def _spy(*args, **kwargs):  # pragma: no cover - must not run
        calls["n"] += 1
        return {}

    monkeypatch.setattr(llm, "label_communities", _spy)

    labels, source = llm.generate_community_labels(
        None, {0: ["a"], 1: ["b"]}, quiet=True
    )
    assert source == "placeholder"
    assert labels == {0: "Community 0", 1: "Community 1"}
    assert calls["n"] == 0, "no backend may be contacted when GRAPHIFY_BACKEND=none"
