"""Opt-in check against a real Ollama server: the whole prompt must reach the
model, not just as much as fits Ollama's default context (#4413). Every other
Ollama test fakes the openai client, so this is the one that exercises the
real `client.post` call and Ollama's own truncation.

    GRAPHIFY_TEST_OLLAMA_MODEL=qwen2.5:14b pytest tests/test_ollama_live.py

GRAPHIFY_TEST_OLLAMA_URL defaults to http://localhost:11434.
"""
from __future__ import annotations

import json
import os
import urllib.request

import pytest

from graphify import llm

MODEL = os.environ.get("GRAPHIFY_TEST_OLLAMA_MODEL", "").strip()
URL = os.environ.get("GRAPHIFY_TEST_OLLAMA_URL", "http://localhost:11434").rstrip("/")

pytestmark = pytest.mark.skipif(not MODEL, reason="set GRAPHIFY_TEST_OLLAMA_MODEL to run")
pytest.importorskip("openai")


def _real_prompt_tokens(system: str, user: str) -> int:
    # Same messages with a context far bigger than the prompt, so nothing is cut.
    body = {
        "model": MODEL,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "stream": False,
        "options": {"num_ctx": 65536, "num_predict": 1},
    }
    req = urllib.request.Request(f"{URL}/api/chat", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as resp:
        return json.load(resp)["prompt_eval_count"]


@pytest.mark.parametrize("user", [
    "The parser hands each token to the resolver, which looks it up in the symbol table. " * 400,
    "知识图谱把代码和文档连接起来，解析器把每个标记交给解析程序。" * 600,
], ids=["english", "chinese"])
def test_whole_prompt_reaches_the_model(monkeypatch, user):
    monkeypatch.delenv("GRAPHIFY_OLLAMA_NUM_CTX", raising=False)
    monkeypatch.setattr(llm, "_OLLAMA_NO_NATIVE", set())
    result = llm._call_openai_compat(f"{URL}/v1", "ollama", MODEL, user,
                                     max_completion_tokens=64, backend="ollama")
    expected = _real_prompt_tokens(llm._extraction_system(deep=False), user)
    assert expected > 4096, "prompt must be bigger than Ollama's default context"
    assert result["input_tokens"] == expected
