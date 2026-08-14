from __future__ import annotations

import json
import sys
import types
from datetime import datetime, timezone
from types import SimpleNamespace

from graphify.prs import PRInfo, _resolve_triage_backend, triage_with_opus


def _install_streaming_openai(monkeypatch):
    constructor_calls: list[dict] = []
    request_calls: list[dict] = []

    class FakeStream:
        def __enter__(self):
            return iter([SimpleNamespace(choices=[])])

        def __exit__(self, _exc_type, _exc, _traceback):
            return False

    class FakeOpenAI:
        def __init__(self, **kwargs):
            constructor_calls.append(kwargs)
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(create=self._create),
            )

        @staticmethod
        def _create(**kwargs):
            request_calls.append(kwargs)
            return FakeStream()

    fake_module = types.ModuleType("openai")
    setattr(fake_module, "OpenAI", FakeOpenAI)
    monkeypatch.setitem(sys.modules, "openai", fake_module)
    return constructor_calls, request_calls


def test_openai_triage_uses_governed_headers_and_auto_model(monkeypatch, capsys) -> None:
    headers = {"x-privacy-tier": "local-only", "x-task-type": "code"}
    monkeypatch.setenv("GRAPHIFY_TRIAGE_BACKEND", "openai")
    monkeypatch.setenv("GRAPHIFY_OPENAI_MODEL", "auto")
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
    monkeypatch.setenv("GRAPHIFY_OPENAI_HEADERS_JSON", json.dumps(headers))
    constructor_calls, request_calls = _install_streaming_openai(monkeypatch)
    pr = PRInfo(
        number=1,
        title="Synthetic change",
        branch="feature",
        base_branch="v8",
        author="developer",
        is_draft=False,
        review_decision="",
        ci_status="SUCCESS",
        updated_at=datetime.now(timezone.utc),
        expected_base="v8",
    )

    triage_with_opus([pr], "v8")

    assert constructor_calls[0]["default_headers"] == headers
    assert request_calls[0]["model"] == "auto"
    assert "openai / auto" in capsys.readouterr().out


def test_openai_triage_model_uses_real_graphify_env_precedence(monkeypatch) -> None:
    monkeypatch.setenv("GRAPHIFY_TRIAGE_BACKEND", "openai")
    monkeypatch.delenv("GRAPHIFY_TRIAGE_MODEL", raising=False)
    monkeypatch.setenv("GRAPHIFY_OPENAI_MODEL", "auto")

    assert _resolve_triage_backend() == ("openai", "auto")


def test_explicit_triage_model_still_overrides_openai_model(monkeypatch) -> None:
    monkeypatch.setenv("GRAPHIFY_TRIAGE_BACKEND", "openai")
    monkeypatch.setenv("GRAPHIFY_TRIAGE_MODEL", "triage-override")
    monkeypatch.setenv("GRAPHIFY_OPENAI_MODEL", "auto")

    assert _resolve_triage_backend() == ("openai", "triage-override")
