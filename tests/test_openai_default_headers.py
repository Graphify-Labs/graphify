"""Tests for governed headers on OpenAI-compatible Graphify requests."""

from __future__ import annotations

import json
import sys
import types
from types import SimpleNamespace

import pytest

from graphify import llm


def _install_fake_openai(monkeypatch):
    constructor_calls: list[dict] = []
    request_calls: list[dict] = []

    class FakeOpenAI:
        def __init__(self, **kwargs):
            constructor_calls.append(kwargs)
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(create=self._create),
            )

        @staticmethod
        def _create(**kwargs):
            request_calls.append(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content='{"nodes":[],"edges":[],"hyperedges":[]}'),
                        finish_reason="stop",
                    )
                ],
                usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
            )

    fake_module = types.ModuleType("openai")
    setattr(fake_module, "OpenAI", FakeOpenAI)
    monkeypatch.setitem(sys.modules, "openai", fake_module)
    return constructor_calls, request_calls


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_headers_are_empty_when_environment_is_unset_or_blank(monkeypatch, raw):
    if raw is None:
        monkeypatch.delenv("GRAPHIFY_OPENAI_HEADERS_JSON", raising=False)
    else:
        monkeypatch.setenv("GRAPHIFY_OPENAI_HEADERS_JSON", raw)

    assert llm._openai_default_headers() == {}


def test_headers_accept_synapse_metadata_and_trim_names(monkeypatch):
    monkeypatch.setenv(
        "GRAPHIFY_OPENAI_HEADERS_JSON",
        json.dumps(
            {
                " x-privacy-tier ": "local-only",
                "x-task-type": "code",
            }
        ),
    )

    assert llm._openai_default_headers() == {
        "x-privacy-tier": "local-only",
        "x-task-type": "code",
    }


def test_headers_reject_invalid_json(monkeypatch):
    monkeypatch.setenv("GRAPHIFY_OPENAI_HEADERS_JSON", "{not-json")

    with pytest.raises(ValueError, match="must contain valid JSON"):
        llm._openai_default_headers()


@pytest.mark.parametrize("raw", ["[]", "null", '"x-task-type"'])
def test_headers_reject_non_object_json(monkeypatch, raw):
    monkeypatch.setenv("GRAPHIFY_OPENAI_HEADERS_JSON", raw)

    with pytest.raises(ValueError, match="must be a JSON object"):
        llm._openai_default_headers()


def test_headers_reject_non_string_values(monkeypatch):
    monkeypatch.setenv("GRAPHIFY_OPENAI_HEADERS_JSON", '{"x-task-type": 42}')

    with pytest.raises(ValueError, match="values must be strings"):
        llm._openai_default_headers()


@pytest.mark.parametrize("name", ["", "   ", "bad header", "bad:header", "héader"])
def test_headers_reject_blank_or_invalid_names(monkeypatch, name):
    monkeypatch.setenv("GRAPHIFY_OPENAI_HEADERS_JSON", json.dumps({name: "safe"}))

    with pytest.raises(ValueError, match="invalid header name"):
        llm._openai_default_headers()


@pytest.mark.parametrize(
    "name",
    [
        "authorization",
        "proxy-authorization",
        "api-key",
        "x-api-key",
        "cookie",
        "set-cookie",
        "host",
        "content-length",
        "transfer-encoding",
    ],
)
def test_headers_reject_protected_names_case_insensitively(monkeypatch, name):
    secret = "must-not-appear-in-error"
    monkeypatch.setenv(
        "GRAPHIFY_OPENAI_HEADERS_JSON",
        json.dumps({f" {name.upper()} ": secret}),
    )

    with pytest.raises(ValueError, match="cannot set protected headers") as error:
        llm._openai_default_headers()
    assert secret not in str(error.value)


def test_headers_reject_line_breaks_without_leaking_values(monkeypatch):
    secret = "must-not-appear-in-error\r\ninjected: value"
    monkeypatch.setenv(
        "GRAPHIFY_OPENAI_HEADERS_JSON",
        json.dumps({"x-task-type": secret}),
    )

    with pytest.raises(ValueError, match="invalid header value") as error:
        llm._openai_default_headers()
    assert secret not in str(error.value)


def test_headers_reject_duplicate_names_after_normalization(monkeypatch):
    monkeypatch.setenv(
        "GRAPHIFY_OPENAI_HEADERS_JSON",
        '{"X-Task-Type": "code", " x-task-type ": "other"}',
    )

    with pytest.raises(ValueError, match="duplicate header names"):
        llm._openai_default_headers()


def test_extraction_client_receives_synapse_headers_and_auto_model(monkeypatch):
    expected_headers = {
        "x-privacy-tier": "local-only",
        "x-task-type": "code",
    }
    monkeypatch.setenv("GRAPHIFY_OPENAI_HEADERS_JSON", json.dumps(expected_headers))
    constructor_calls, request_calls = _install_fake_openai(monkeypatch)

    llm._call_openai_compat(
        "https://synapse.example/v1",
        "fake-key",
        "auto",
        "user message",
        backend="openai",
    )

    assert constructor_calls[0]["default_headers"] == expected_headers
    assert request_calls[0]["model"] == "auto"


def test_lightweight_client_receives_synapse_headers_and_auto_model(monkeypatch):
    expected_headers = {
        "x-privacy-tier": "local-only",
        "x-task-type": "code",
    }
    monkeypatch.setenv("GRAPHIFY_OPENAI_HEADERS_JSON", json.dumps(expected_headers))
    monkeypatch.setenv("GRAPHIFY_OPENAI_MODEL", "auto")
    monkeypatch.setattr(llm, "_get_backend_api_key", lambda _backend: "fake-key")
    constructor_calls, request_calls = _install_fake_openai(monkeypatch)

    llm._call_llm("label this", backend="openai")

    assert constructor_calls[0]["default_headers"] == expected_headers
    assert request_calls[0]["model"] == "auto"
