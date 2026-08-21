"""Tests for reasoning_effort resolution on the ollama backend.

Reasoning-tuned local models served through Ollama (nemotron, deepseek-r1,
qwq — the same families _THINK_BLOCK_RE strips a <think> block for) narrate a
chain of thought in a separate `message.reasoning` field before answering.
`.content` itself is never hollow (confirmed live against nemotron-3-super via
raw /v1/chat/completions calls), so this isn't a JSON-parsing problem — but the
narration shares the request's time/token budget, and on a real multi-file
extraction chunk it can consume enough of both that the client's --api-timeout
trips and a chunk fails with nothing left to bisect. `reasoning_effort="high"`
measurably cuts the narration (and total tokens) roughly in half for the same
prompt, which is the difference between finishing under timeout and not.
"""

from graphify import llm


def test_ollama_model_is_reasoning_matches_known_families():
    assert llm._ollama_model_is_reasoning("nemotron-3-super:120b-a12b-q4_K_M")
    assert llm._ollama_model_is_reasoning("deepseek-r1:32b")
    assert llm._ollama_model_is_reasoning("qwq:32b")
    # Provider-prefixed form, matching _model_requires_default_temperature's
    # existing "openai/gpt-5" style stripping.
    assert llm._ollama_model_is_reasoning("nvidia/nemotron-3-super")


def test_ollama_model_is_reasoning_false_for_unrecognised_models():
    assert not llm._ollama_model_is_reasoning("qwen2.5-coder:7b")
    assert not llm._ollama_model_is_reasoning("llama3.1:8b")
    assert not llm._ollama_model_is_reasoning("")
    assert not llm._ollama_model_is_reasoning(None)


def test_resolve_reasoning_effort_defaults_high_for_ollama_reasoning_model(monkeypatch):
    monkeypatch.delenv("GRAPHIFY_OLLAMA_REASONING_EFFORT", raising=False)

    assert llm._resolve_reasoning_effort({}, "nemotron-3-super:120b", "ollama") == "high"


def test_resolve_reasoning_effort_none_for_ollama_non_reasoning_model(monkeypatch):
    monkeypatch.delenv("GRAPHIFY_OLLAMA_REASONING_EFFORT", raising=False)

    assert llm._resolve_reasoning_effort({}, "qwen2.5-coder:7b", "ollama") is None


def test_resolve_reasoning_effort_unaffected_for_non_ollama_backends(monkeypatch):
    monkeypatch.setenv("GRAPHIFY_OLLAMA_REASONING_EFFORT", "high")

    # Named "nemotron" or not, a non-ollama backend never gets the ollama-only
    # default or the ollama-only env override.
    assert llm._resolve_reasoning_effort({}, "nemotron-3-super:120b", "claude") is None
    assert llm._resolve_reasoning_effort(
        {"reasoning_effort": "low"}, "gemini-3-flash-preview", "gemini"
    ) == "low"


def test_resolve_reasoning_effort_env_override_wins_over_default(monkeypatch):
    monkeypatch.setenv("GRAPHIFY_OLLAMA_REASONING_EFFORT", "low")

    assert llm._resolve_reasoning_effort({}, "nemotron-3-super:120b", "ollama") == "low"
    # Env override applies even to a model that wouldn't otherwise default to
    # anything — an explicit user choice always wins.
    assert llm._resolve_reasoning_effort({}, "qwen2.5-coder:7b", "ollama") == "low"


def test_resolve_reasoning_effort_env_force_omit(monkeypatch):
    for sentinel in ("none", "omit", "default", "NONE", "Omit"):
        monkeypatch.setenv("GRAPHIFY_OLLAMA_REASONING_EFFORT", sentinel)
        assert llm._resolve_reasoning_effort({}, "nemotron-3-super:120b", "ollama") is None


def test_resolve_reasoning_effort_backend_config_default_takes_precedence(monkeypatch):
    monkeypatch.delenv("GRAPHIFY_OLLAMA_REASONING_EFFORT", raising=False)

    # If a future ollama-family config ever sets its own default, that wins
    # over the reasoning-model fallback rather than being silently overridden.
    assert (
        llm._resolve_reasoning_effort({"reasoning_effort": "medium"}, "nemotron-3-super:120b", "ollama")
        == "medium"
    )
