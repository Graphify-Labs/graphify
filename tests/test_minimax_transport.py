"""Exercise the real SDK serializer through an offline HTTP transport."""

import base64
import json
import os
import subprocess
import sys

import pytest

from graphify import llm


@pytest.fixture
def wire(monkeypatch):
    openai = pytest.importorskip("openai")
    httpx = pytest.importorskip("httpx")
    requests = []
    real_client = openai.OpenAI

    def respond(request):
        requests.append((str(request.url), json.loads(request.content)))
        return httpx.Response(200, json={
            "id": "offline-response", "object": "chat.completion", "created": 0,
            "model": requests[-1][1]["model"],
            "choices": [{"index": 0, "finish_reason": "stop", "message": {
                "role": "assistant", "content": '{"nodes":[],"edges":[],"hyperedges":[]}',
                "reasoning_content": "Offline reasoning fixture.",
            }}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        })

    def client(**kwargs):
        return real_client(**kwargs, http_client=httpx.Client(
            transport=httpx.MockTransport(respond), trust_env=False,
        ))

    monkeypatch.setattr(openai, "OpenAI", client)
    monkeypatch.setenv("MINIMAX_API_KEY", "offline-fixture")
    monkeypatch.delenv("MINIMAX_MODEL", raising=False)
    monkeypatch.delenv("GRAPHIFY_MINIMAX_MODEL", raising=False)
    monkeypatch.delenv("GRAPHIFY_MAX_OUTPUT_TOKENS", raising=False)
    return requests


@pytest.mark.parametrize("base_url", [
    "https://api.minimax.io/v1", "https://api.minimaxi.com/v1",
    "https://proxy.example/minimax/v1",
])
@pytest.mark.parametrize("entrypoint", ["extract", "label"])
@pytest.mark.parametrize("disable", [False, True])
@pytest.mark.parametrize("selection,expected", [
    ("default", "MiniMax-M3.1-Flash"),
    ("m3", "MiniMax-M3"),
    ("legacy", "MiniMax-M2.7"),
    ("saved", "saved-custom-model"),
    ("explicit", "explicit-custom-model"),
])
def test_serialized_model_selection_and_thinking(
    monkeypatch, tmp_path, wire, base_url, entrypoint, disable, selection, expected,
):
    monkeypatch.setitem(llm.BACKENDS["minimax"], "base_url", base_url)
    monkeypatch.setenv("GRAPHIFY_DISABLE_THINKING", "1" if disable else "0")
    model = None
    if selection in ("m3", "legacy", "explicit"):
        model = expected
        monkeypatch.setenv("GRAPHIFY_MINIMAX_MODEL", "saved-custom-model")
    elif selection == "saved":
        monkeypatch.setenv("GRAPHIFY_MINIMAX_MODEL", expected)
    if entrypoint == "extract":
        source = tmp_path / "notes.md"
        source.write_text("A document for extraction.")
        result = llm.extract_files_direct(
            [source], backend="minimax", root=tmp_path, model=model,
        )
        assert result["input_tokens"] == 10
    else:
        llm._call_llm("Label the community.", backend="minimax", model=model)
    assert len(wire) == 1
    url, payload = wire[0]
    assert url == base_url + "/chat/completions"
    assert payload["model"] == expected
    assert payload["stream"] is False
    assert payload["max_completion_tokens"] == (16384 if entrypoint == "extract" else 200)
    if disable and expected not in ("MiniMax-M3.1-Flash", "MiniMax-M2.7"):
        assert payload["thinking"] == {"type": "disabled"}
    else:
        assert "thinking" not in payload
    # Omission selects Flash's adaptive thinking / max effort API defaults.
    assert "reasoning_effort" not in payload
    assert "service_tier" not in payload
    assert "reasoning_split" not in payload
    assert "extra_body" not in payload
    assert payload["messages"][-1]["role"] == "user"


@pytest.mark.parametrize("model,vision", [
    ("MiniMax-M3.1-Flash", True), ("MiniMax-M3", True), ("MiniMax-M2.7", False),
])
def test_serialized_image_input_is_preserved(tmp_path, wire, model, vision):
    source = tmp_path / "image.png"
    pixels = b"\x89PNG\r\n\x1a\nfixture"
    source.write_bytes(pixels)
    llm.extract_files_direct([source], backend="minimax", model=model, root=tmp_path)
    content = wire[0][1]["messages"][-1]["content"]
    if vision:
        image = next(part for part in content if part["type"] == "image_url")
        assert image["image_url"]["url"] == (
            "data:image/png;base64," + base64.b64encode(pixels).decode()
        )
    else:
        assert isinstance(content, str)
        assert "image.png" in content


@pytest.mark.parametrize("entrypoint", ["extract", "label"])
def test_custom_extra_body_wins(monkeypatch, tmp_path, wire, entrypoint):
    monkeypatch.setitem(llm.BACKENDS["minimax"], "extra_body", {
        "thinking": {"type": "adaptive"}, "reasoning_effort": "low",
    })
    monkeypatch.setenv("GRAPHIFY_DISABLE_THINKING", "1")
    if entrypoint == "extract":
        llm.extract_files_direct([], backend="minimax", root=tmp_path)
    else:
        llm._call_llm("Label.", backend="minimax")
    assert wire[0][1]["thinking"] == {"type": "adaptive"}
    assert wire[0][1]["reasoning_effort"] == "low"


@pytest.mark.parametrize("saved", ["MiniMax-M3", "MiniMax-M2.7", "custom-model"])
def test_minimax_model_import_override(saved):
    env = {key: value for key, value in os.environ.items()
           if key not in ("MINIMAX_MODEL", "GRAPHIFY_MINIMAX_MODEL")}
    env["MINIMAX_MODEL"] = saved
    result = subprocess.run([
        sys.executable, "-c",
        "from graphify.llm import _default_model_for_backend; "
        "print(_default_model_for_backend('minimax'))",
    ], env=env, text=True, capture_output=True, check=True)
    assert result.stdout.strip() == saved


def test_flash_pricing():
    assert llm.estimate_cost("minimax", 1_000_000, 500_000) == pytest.approx(0.45)


@pytest.mark.parametrize("env_key,backend", [
    ("ANTHROPIC_API_KEY", "claude"), ("OPENAI_API_KEY", "openai"),
    ("DEEPSEEK_API_KEY", "deepseek"), ("AWS_REGION", "bedrock"),
])
def test_existing_cloud_detection_priority(monkeypatch, env_key, backend):
    monkeypatch.setenv("MINIMAX_API_KEY", "offline-fixture")
    monkeypatch.setenv(env_key, "offline-fixture")
    assert llm.detect_backend() == backend
