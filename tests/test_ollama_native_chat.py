"""#4413 - Ollama's OpenAI-compatible /v1 endpoint ignores `options`, so the
derived num_ctx never reached the server and prompts were cut to Ollama's
default context. The ollama backend now uses the native /api/chat endpoint,
and falls back to /v1 for servers that don't have it.
"""
from __future__ import annotations

import sys
import types

import pytest

from graphify import llm


class _StatusError(Exception):
    def __init__(self, message, status_code):
        super().__init__(message)
        self.status_code = status_code


def _reply(content='{"nodes":[{"id":"x"}],"edges":[],"hyperedges":[]}', done_reason="stop"):
    return {
        "message": {"role": "assistant", "content": content},
        "done_reason": done_reason,
        "prompt_eval_count": 6316,
        "eval_count": 901,
    }


def _install(monkeypatch, *, post_error=None, reply=None):
    calls = {"post": [], "create": []}

    class _Resp:
        class _Choice:
            class message:
                content = '{"nodes":[{"id":"v1"}],"edges":[],"hyperedges":[]}'
            finish_reason = "stop"

        class usage:
            prompt_tokens = 4096
            completion_tokens = 50

        choices = [_Choice()]

    class _FakeOpenAI:
        def __init__(self, *_, **__):
            self.chat = self
            self.completions = self

        def create(self, **kwargs):
            calls["create"].append(kwargs)
            return _Resp()

        def post(self, path, *, body, cast_to):
            calls["post"].append((path, body))
            if post_error is not None:
                raise post_error
            return reply if reply is not None else _reply()

    mod = types.ModuleType("openai")
    mod.OpenAI = _FakeOpenAI
    mod.APIStatusError = _StatusError
    monkeypatch.setitem(sys.modules, "openai", mod)
    monkeypatch.setattr(llm, "_OLLAMA_NO_NATIVE", set(), raising=False)
    monkeypatch.delenv("GRAPHIFY_OLLAMA_NUM_CTX", raising=False)
    monkeypatch.delenv("GRAPHIFY_OLLAMA_KEEP_ALIVE", raising=False)
    monkeypatch.delenv("GRAPHIFY_DISABLE_THINKING", raising=False)
    return calls


def _call(base_url="http://localhost:11434/v1", **kwargs):
    return llm._call_openai_compat(
        base_url, "ollama", "qwen2.5:14b", "x" * 40_000,
        temperature=0, max_completion_tokens=8192, backend="ollama", **kwargs,
    )


def test_ollama_uses_native_chat_with_num_ctx(monkeypatch):
    calls = _install(monkeypatch)

    result = _call()

    assert calls["create"] == []
    path, body = calls["post"][0]
    assert path == "http://localhost:11434/api/chat"
    assert body["model"] == "qwen2.5:14b"
    assert body["stream"] is False
    assert [m["role"] for m in body["messages"]] == ["system", "user"]
    assert body["messages"][1]["content"].endswith("x" * 100)
    # 40k chars is ~10k tokens; num_ctx must cover it plus the output cap.
    assert body["options"]["num_ctx"] > 10_000 + 8192
    assert body["options"]["num_predict"] == 8192
    assert body["options"]["temperature"] == 0
    assert body["keep_alive"] == "30m"
    assert "think" not in body
    assert result["nodes"] == [{"id": "x"}]
    assert result["input_tokens"] == 6316
    assert result["output_tokens"] == 901
    assert result["finish_reason"] == "stop"


@pytest.mark.parametrize("base_url", [
    "http://localhost:11434/v1",
    "http://localhost:11434/v1/",
    "http://localhost:11434",
])
def test_native_url_drops_the_v1_suffix(monkeypatch, base_url):
    calls = _install(monkeypatch)

    _call(base_url)

    assert calls["post"][0][0] == "http://localhost:11434/api/chat"


def test_native_length_maps_to_length(monkeypatch):
    _install(monkeypatch, reply=_reply('{"nodes": [{"id":', done_reason="length"))

    assert _call()["finish_reason"] == "length"


def test_native_empty_reply_is_hollow(monkeypatch):
    _install(monkeypatch, reply=_reply(""))

    assert _call()["finish_reason"] == "hollow"


def test_native_sends_images(monkeypatch, tmp_path):
    calls = _install(monkeypatch)
    ref = llm._ImageRef(path=tmp_path / "a.png", rel="a.png", media_type="image/png", raw=b"\x89PNG")

    _call(images=[ref])

    user = calls["post"][0][1]["messages"][1]
    assert user["images"] == [ref.b64]
    assert "a.png" in user["content"]


def test_server_without_native_chat_falls_back_to_v1_once(monkeypatch, capsys):
    calls = _install(monkeypatch, post_error=_StatusError("Unexpected endpoint or method.", 404))

    first = _call("http://127.0.0.1:1234/v1")
    second = _call("http://127.0.0.1:1234/v1")

    assert len(calls["post"]) == 1, "a /v1-only server must not be probed on every chunk"
    assert len(calls["create"]) == 2
    assert first["nodes"] == [{"id": "v1"}]
    assert second["input_tokens"] == 4096
    assert "falling back" in capsys.readouterr().err


def test_unknown_model_is_raised_not_treated_as_missing_endpoint(monkeypatch):
    calls = _install(
        monkeypatch,
        post_error=_StatusError("Error code: 404 - {'error': \"model 'nope' not found\"}", 404),
    )

    with pytest.raises(_StatusError):
        _call()

    assert calls["create"] == []
    assert llm._OLLAMA_NO_NATIVE == set()


def test_other_server_errors_are_raised(monkeypatch):
    calls = _install(monkeypatch, post_error=_StatusError("internal error", 500))

    with pytest.raises(_StatusError):
        _call()

    assert calls["create"] == []


def test_explicit_extra_body_keeps_v1(monkeypatch):
    calls = _install(monkeypatch)

    _call(extra_body={"options": {"num_ctx": 4096}})

    assert calls["post"] == []
    assert calls["create"][0]["extra_body"] == {"options": {"num_ctx": 4096}}


def test_other_backends_never_use_native_chat(monkeypatch):
    calls = _install(monkeypatch)

    llm._call_openai_compat(
        "https://api.openai.com/v1", "sk-test", "gpt-4.1-mini", "u",
        temperature=0, max_completion_tokens=8192, backend="openai",
    )

    assert calls["post"] == []
    assert len(calls["create"]) == 1


def test_call_llm_ollama_uses_native_chat(monkeypatch):
    # Community labeling goes through _call_llm; its batches are sized for a
    # 16k context and were cut to Ollama's default the same way (#4413).
    calls = _install(monkeypatch, reply=_reply("Console Rendering"))
    monkeypatch.setattr(llm, "_get_backend_api_key", lambda _backend: "ollama")
    usage: dict = {}

    out = llm._call_llm("y" * 40_000, backend="ollama", max_tokens=1024, usage_out=usage)

    assert out == "Console Rendering"
    assert calls["create"] == []
    path, body = calls["post"][0]
    assert path.endswith("/api/chat")
    assert [m["role"] for m in body["messages"]] == ["user"]
    assert body["options"]["num_ctx"] > 10_000
    assert body["options"]["num_predict"] == 1024
    assert usage == {"input": 6316, "output": 901}


def test_call_llm_ollama_falls_back_to_v1(monkeypatch):
    calls = _install(monkeypatch, post_error=_StatusError("Unexpected endpoint or method.", 404))
    monkeypatch.setattr(llm, "_get_backend_api_key", lambda _backend: "ollama")

    out = llm._call_llm("label this", backend="ollama")

    assert len(calls["create"]) == 1
    assert out.startswith('{"nodes"')
