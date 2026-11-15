"""num_ctx sizing for Ollama. Once num_ctx actually reached Ollama (#4413) the
estimate behind it mattered: chars/4 undercounts non-Latin scripts (2.8x for
Chinese, 3.7x for Hindi on qwen2.5) and the flat 400 tokens left for the
system prompt was short of the ~760 the extraction prompt takes.
"""
from __future__ import annotations

import pytest

from graphify import llm


@pytest.fixture(autouse=True)
def _no_env_override(monkeypatch):
    monkeypatch.delenv("GRAPHIFY_OLLAMA_NUM_CTX", raising=False)


def test_estimate_unchanged_for_english_and_code():
    text = "def handler(request):\n    return Response(status=200)\n" * 200
    assert llm._estimate_prompt_tokens(text) == len(text) // llm._CHARS_PER_TOKEN


def test_estimate_unchanged_for_accented_latin():
    text = "Größenänderung für Café und Façade " * 100
    assert llm._estimate_prompt_tokens(text) == len(text) // llm._CHARS_PER_TOKEN


@pytest.mark.parametrize("text", [
    "知识图谱把代码和文档连接起来" * 500,   # Chinese
    "ज्ञान ग्राफ कोड और दस्तावेज़ों को जोड़ता है" * 300,  # Hindi
    "Граф знаний связывает код и документы" * 300,  # Russian
], ids=["chinese", "hindi", "russian"])
def test_estimate_counts_non_latin_chars_as_tokens(text):
    non_latin = sum(1 for c in text if ord(c) > 0x24F)
    assert llm._estimate_prompt_tokens(text) >= non_latin
    assert llm._estimate_prompt_tokens(text) > len(text) // llm._CHARS_PER_TOKEN


def test_chinese_chunk_gets_room_for_its_tokens():
    # 20k Chinese chars is ~14k tokens on qwen2.5. chars/4 sized this at the
    # 8192 floor, so Ollama cut the prompt.
    msg = "知识图谱把代码和文档连接起来" * 1500
    extras = llm._ollama_request_extras(msg, 4096)
    assert extras["options"]["num_ctx"] >= len(msg) + 4096


def test_system_prompt_is_counted():
    msg = "x" * 40_000
    system = llm._extraction_system(deep=False)
    without = llm._ollama_request_extras(msg, 8192)["options"]["num_ctx"]
    with_sys = llm._ollama_request_extras(msg, 8192, system)["options"]["num_ctx"]
    assert with_sys - without == llm._estimate_prompt_tokens(system)


def test_extraction_call_sizes_for_its_system_prompt(monkeypatch):
    import sys
    import types

    sent = {}

    class _FakeOpenAI:
        def __init__(self, *_, **__):
            pass

        def post(self, path, *, body, **__):
            sent.update(body)
            return {"message": {"content": '{"nodes":[],"edges":[],"hyperedges":[]}'},
                    "done_reason": "stop", "prompt_eval_count": 1, "eval_count": 100}

    fake = types.ModuleType("openai")
    fake.OpenAI = _FakeOpenAI
    fake.APIStatusError = type("APIStatusError", (Exception,), {})
    monkeypatch.setitem(sys.modules, "openai", fake)
    monkeypatch.setattr(llm, "_OLLAMA_NO_NATIVE", set())

    msg = "x" * 40_000
    llm._call_openai_compat("http://localhost:11434/v1", "ollama", "m", msg,
                            max_completion_tokens=8192, backend="ollama", deep_mode=True)

    system = llm._extraction_system(deep=True)
    assert sent["options"]["num_ctx"] == (
        llm._estimate_prompt_tokens(msg) + llm._estimate_prompt_tokens(system) + 8192 + 2000
    )
