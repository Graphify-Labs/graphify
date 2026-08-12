"""Tests for the GitHub Copilot SDK backend and CLI fallback.

The official SDK, runtime, executable, network, and enterprise credentials are
all replaced with fakes. These tests therefore exercise Graphify's transport
lifecycle and dispatch without transmitting data or requiring a Copilot seat.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from graphify import llm

_RESPONSE = json.dumps(
    {
        "nodes": [
            {
                "id": "policy",
                "label": "Policy",
                "file_type": "document",
                "source_file": "policy.md",
            }
        ],
        "edges": [],
        "hyperedges": [],
    }
)


@pytest.fixture(autouse=True)
def reset_sdk_runtime():
    llm._discard_copilot_sdk_runtime()
    llm._COPILOT_SDK_FALLBACK_WARNED.clear()
    yield
    llm._discard_copilot_sdk_runtime()
    llm._COPILOT_SDK_FALLBACK_WARNED.clear()


class _FakeBridge:
    def __init__(self, text: str = _RESPONSE):
        self.text = text
        self.calls: list[dict] = []

    def complete(self, prompt, *, model, attachments=None):
        self.calls.append(
            {"prompt": prompt, "model": model, "attachments": attachments}
        )
        return self.text


def _ok_graph(nodes=None):
    return {
        "nodes": nodes or [],
        "edges": [],
        "hyperedges": [],
        "input_tokens": 1,
        "output_tokens": 1,
        "model": "auto",
        "finish_reason": "stop",
    }


def test_backend_registered_with_zero_cost_and_vision():
    cfg = llm.BACKENDS["copilot-sdk"]
    assert cfg["default_model"] == "auto"
    assert cfg["vision"] is True
    assert cfg["pricing"] == {"input": 0.0, "output": 0.0}
    assert llm.estimate_cost("copilot-sdk", 1_000_000, 1_000_000) == 0.0


def test_default_model_precedence(monkeypatch):
    for name in (
        "GRAPHIFY_COPILOT_SDK_MODEL",
        "GRAPHIFY_COPILOT_MODEL",
        "COPILOT_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)
    assert llm._default_model_for_backend("copilot-sdk") == "auto"

    monkeypatch.setenv("COPILOT_MODEL", "gpt-5-mini")
    assert llm._default_model_for_backend("copilot-sdk") == "gpt-5-mini"

    monkeypatch.setenv("GRAPHIFY_COPILOT_MODEL", "gpt-5.2")
    assert llm._default_model_for_backend("copilot-sdk") == "gpt-5.2"

    monkeypatch.setenv("GRAPHIFY_COPILOT_SDK_MODEL", "claude-sonnet-4.6")
    assert llm._default_model_for_backend("copilot-sdk") == "claude-sonnet-4.6"


def test_sdk_requires_python_311(monkeypatch):
    monkeypatch.setattr(llm.sys, "version_info", (3, 10, 14))

    with pytest.raises(llm._CopilotSdkUnavailable, match="Python 3.11"):
        llm._load_copilot_sdk()


def test_sdk_capability_check_fails_closed_for_legacy_client():
    class LegacyClient:
        def __init__(
            self,
            *,
            connection=None,
            working_directory=None,
            use_logged_in_user=True,
            enable_remote_sessions=False,
        ):
            pass

    with pytest.raises(llm._CopilotSdkUnavailable, match="mode"):
        llm._require_supported_kwargs(
            LegacyClient,
            {
                "connection",
                "working_directory",
                "use_logged_in_user",
                "enable_remote_sessions",
                "mode",
            },
            api_name="CopilotClient",
        )


def test_sdk_extraction_parses_graph_and_estimates_usage(monkeypatch):
    bridge = _FakeBridge()
    monkeypatch.setattr(llm, "_get_copilot_sdk_runtime", lambda: bridge)

    result = llm._call_copilot_sdk("source", model="auto")

    assert result["nodes"][0]["id"] == "policy"
    assert result["model"] == "auto"
    assert result["finish_reason"] == "stop"
    assert result["input_tokens"] > 0
    assert result["output_tokens"] > 0
    assert "graphify semantic extraction agent" in bridge.calls[0]["prompt"]
    assert "output ONLY the JSON object" in bridge.calls[0]["prompt"]


def test_sdk_images_are_file_attachments_not_loaded_as_base64(tmp_path, monkeypatch):
    image = tmp_path / "diagram.png"
    image.write_bytes(b"not-a-real-image-but-no-read-is-required")
    bridge = _FakeBridge()
    monkeypatch.setattr(llm, "_get_copilot_sdk_runtime", lambda: bridge)

    result = llm.extract_files_direct(
        [image],
        backend="copilot-sdk",
        root=tmp_path,
    )

    assert result["nodes"][0]["id"] == "policy"
    call = bridge.calls[0]
    assert call["attachments"] == [
        {"type": "file", "path": str(image.resolve())}
    ]
    assert "source_file: diagram.png" in call["prompt"]
    assert "not shown" not in call["prompt"]


def test_sdk_transport_failure_falls_back_to_cli(monkeypatch, capsys):
    def fail_sdk():
        raise llm._CopilotSdkUnavailable("SDK package missing")

    cli = MagicMock(return_value=_RESPONSE)
    monkeypatch.setattr(llm, "_get_copilot_sdk_runtime", fail_sdk)
    monkeypatch.setattr(llm, "_run_copilot_cli", cli)

    result = llm._call_copilot_sdk("source", model="auto")

    assert result["nodes"][0]["id"] == "policy"
    cli.assert_called_once()
    assert cli.call_args.kwargs["model"] == "auto"
    assert "falling back to copilot-cli" in capsys.readouterr().err


def test_fallback_warning_is_emitted_once(monkeypatch, capsys):
    monkeypatch.setattr(
        llm,
        "_get_copilot_sdk_runtime",
        MagicMock(side_effect=llm._CopilotSdkUnavailable("not installed")),
    )
    monkeypatch.setattr(llm, "_run_copilot_cli", MagicMock(return_value="ok"))

    assert llm._run_copilot_sdk("one", model="auto") == "ok"
    assert llm._run_copilot_sdk("two", model="auto") == "ok"

    assert capsys.readouterr().err.count("falling back to copilot-cli") == 1


def test_fallback_can_be_disabled(monkeypatch):
    monkeypatch.setenv("GRAPHIFY_COPILOT_SDK_FALLBACK", "0")
    monkeypatch.setattr(
        llm,
        "_get_copilot_sdk_runtime",
        MagicMock(side_effect=llm._CopilotSdkUnavailable("not installed")),
    )
    cli = MagicMock()
    monkeypatch.setattr(llm, "_run_copilot_cli", cli)

    with pytest.raises(RuntimeError, match="fallback is disabled"):
        llm._run_copilot_sdk("prompt", model="auto")
    cli.assert_not_called()


def test_both_transport_failures_are_reported(monkeypatch):
    monkeypatch.setattr(
        llm,
        "_get_copilot_sdk_runtime",
        MagicMock(side_effect=llm._CopilotSdkUnavailable("SDK unavailable")),
    )
    monkeypatch.setattr(
        llm,
        "_run_copilot_cli",
        MagicMock(side_effect=RuntimeError("CLI unauthenticated")),
    )

    with pytest.raises(RuntimeError, match="Both GitHub Copilot transports failed") as exc:
        llm._run_copilot_sdk("prompt", model="auto")
    assert "SDK unavailable" in str(exc.value)
    assert "CLI unauthenticated" in str(exc.value)


def test_cli_fallback_prompt_does_not_claim_image_pixels_are_attached(
    tmp_path, monkeypatch
):
    image = tmp_path / "diagram.png"
    image.write_bytes(b"pixels")
    ref = llm._ImageRef(image, "diagram.png", "image/png", None)
    monkeypatch.setattr(
        llm,
        "_get_copilot_sdk_runtime",
        MagicMock(side_effect=llm._CopilotSdkUnavailable("SDK unavailable")),
    )
    cli = MagicMock(return_value=_RESPONSE)
    monkeypatch.setattr(llm, "_run_copilot_cli", cli)

    llm._call_copilot_sdk("source", model="auto", images=[ref])

    fallback_prompt = cli.call_args.args[0]
    assert "source_file: diagram.png (not shown" in fallback_prompt


def test_extract_files_direct_dispatches_without_api_key(tmp_path, monkeypatch):
    source = tmp_path / "policy.md"
    source.write_text("# Policy\n", encoding="utf-8")
    call = MagicMock(return_value=_ok_graph([{"id": "policy"}]))
    monkeypatch.setattr(llm, "_call_copilot_sdk", call)

    result = llm.extract_files_direct(
        [source],
        backend="copilot-sdk",
        root=tmp_path,
    )

    assert result["nodes"][0]["id"] == "policy"
    call.assert_called_once()
    assert call.call_args.kwargs["model"] == "auto"


def test_simple_completion_path_uses_sdk(monkeypatch):
    sdk = MagicMock(return_value="compact answer")
    monkeypatch.setattr(llm, "_run_copilot_sdk", sdk)
    usage = {}

    out = llm._call_llm(
        "Summarize this",
        backend="copilot-sdk",
        model="auto",
        usage_out=usage,
    )

    assert out == "compact answer"
    assert usage["input"] > 0
    assert usage["output"] > 0
    assert sdk.call_args.kwargs["model"] == "auto"


def test_detect_backend_does_not_auto_select_copilot_sdk(monkeypatch):
    for key in (
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "MOONSHOT_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "DEEPSEEK_API_KEY",
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_ENDPOINT",
        "AWS_PROFILE",
        "AWS_REGION",
        "AWS_DEFAULT_REGION",
        "OLLAMA_BASE_URL",
        "OLLAMA_HOST",
    ):
        monkeypatch.delenv(key, raising=False)
    assert llm.detect_backend() is None


def test_extract_corpus_parallel_sdk_runs_serially(tmp_path, monkeypatch):
    files = [tmp_path / f"f{i}.md" for i in range(6)]
    for source in files:
        source.write_text("hello", encoding="utf-8")

    def fake_extract(chunk, *_, **__):
        return _ok_graph([{"id": Path(source).stem} for source in chunk])

    monkeypatch.delenv("GRAPHIFY_COPILOT_SDK_PARALLEL", raising=False)
    with patch("graphify.llm.extract_files_direct", side_effect=fake_extract), patch(
        "graphify.llm.ThreadPoolExecutor"
    ) as pool:
        result = llm.extract_corpus_parallel(
            files,
            backend="copilot-sdk",
            model="auto",
            root=tmp_path,
            token_budget=None,
            chunk_size=2,
            max_concurrency=4,
        )

    pool.assert_not_called()
    assert len(result["nodes"]) == 6


def test_sdk_runtime_reuses_client_and_denies_tools(monkeypatch):
    state = {
        "clients": [],
        "sessions": [],
        "connections": [],
        "deleted_sessions": [],
    }

    class FakeReject:
        def __init__(self, *, feedback):
            self.feedback = feedback

    class FakeConnection:
        def __init__(self, path):
            self.path = path
            self.env = None

        @staticmethod
        def for_stdio(*, path):
            value = FakeConnection(path)
            state["connections"].append(value)
            return value

    class FakeSession:
        def __init__(self, kwargs):
            self.kwargs = kwargs
            self.send_calls = []
            self.disconnected = False
            state["sessions"].append(self)

        async def send_and_wait(self, prompt, **kwargs):
            self.send_calls.append((prompt, kwargs))
            return SimpleNamespace(data=SimpleNamespace(content="answer"))

        async def disconnect(self):
            self.disconnected = True

    class FakeClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.started = False
            self.stopped = False
            state["clients"].append(self)

        async def start(self):
            self.started = True

        async def stop(self):
            self.stopped = True

        async def create_session(self, **kwargs):
            return FakeSession(kwargs)

        async def delete_session(self, session_id):
            state["deleted_sessions"].append(session_id)

    monkeypatch.setenv("COPILOT_GH_HOST", "example.ghe.com")
    monkeypatch.setattr(
        llm,
        "_load_copilot_sdk",
        lambda: (FakeClient, FakeConnection, FakeReject),
    )

    runtime = llm._CopilotSdkRuntime(
        cli_path="/managed/copilot",
        use_bundled_runtime=False,
    )
    try:
        assert runtime.complete("first", model="auto") == "answer"
        assert runtime.complete(
            "second",
            model="gpt-5.2",
            attachments=[{"type": "file", "path": "/tmp/image.png"}],
        ) == "answer"

        assert len(state["clients"]) == 1
        assert len(state["sessions"]) == 2
        client = state["clients"][0]
        assert client.started is True
        connection = client.kwargs["connection"]
        assert connection.path == "/managed/copilot"
        assert connection.env["COPILOT_GH_HOST"] == "example.ghe.com"
        assert connection.env["COPILOT_PLUGIN_DIR_ONLY"] == "true"
        assert connection.env["COPILOT_HOME"] == client.kwargs["base_directory"]
        assert client.kwargs["mode"] == "empty"
        assert client.kwargs["use_logged_in_user"] is True
        assert "env" not in client.kwargs
        assert Path(client.kwargs["working_directory"]).exists()
        assert Path(client.kwargs["base_directory"]).exists()

        first = state["sessions"][0]
        assert first.kwargs["model"] == "auto"
        assert first.kwargs["available_tools"] == []
        assert first.kwargs["mcp_servers"] == {}
        assert first.kwargs["memory"] == {"enabled": False}
        assert first.kwargs["infinite_sessions"] == {"enabled": False}
        assert first.kwargs["enable_config_discovery"] is False
        decision = first.kwargs["on_permission_request"](object(), {})
        assert isinstance(decision, FakeReject)
        assert "disables all agent tools" in decision.feedback
        assert first.disconnected is True

        second = state["sessions"][1]
        assert second.send_calls[0][1]["attachments"] == [
            {"type": "file", "path": "/tmp/image.png"}
        ]
        assert state["deleted_sessions"] == [
            first.kwargs["session_id"],
            second.kwargs["session_id"],
        ]
        assert state["deleted_sessions"][0] != state["deleted_sessions"][1]
    finally:
        workdir = Path(state["clients"][0].kwargs["working_directory"])
        runtime.close()
    assert state["clients"][0].stopped is True
    assert not workdir.exists()


def test_sdk_runtime_can_explicitly_use_bundled_cli(monkeypatch):
    state = {}

    class FakeReject:
        def __init__(self, *, feedback):
            self.feedback = feedback

    class FakeConnection:
        @staticmethod
        def for_stdio(*, path):  # pragma: no cover - must not be called
            raise AssertionError(path)

    class FakeSession:
        async def send_and_wait(self, prompt, **kwargs):
            return SimpleNamespace(data=SimpleNamespace(content="ok"))

        async def disconnect(self):
            return None

    class FakeClient:
        def __init__(self, **kwargs):
            state["kwargs"] = kwargs

        async def start(self):
            return None

        async def stop(self):
            return None

        async def create_session(self, **kwargs):
            return FakeSession()

        async def delete_session(self, session_id):
            state["deleted_session"] = session_id

    monkeypatch.setattr(
        llm,
        "_load_copilot_sdk",
        lambda: (FakeClient, FakeConnection, FakeReject),
    )
    runtime = llm._CopilotSdkRuntime(cli_path=None, use_bundled_runtime=True)
    try:
        assert runtime.complete("hello", model="auto") == "ok"
        assert "connection" not in state["kwargs"]
        assert state["kwargs"]["env"]["COPILOT_HOME"] == state["kwargs"]["base_directory"]
        assert state["deleted_session"].startswith("graphify-")
    finally:
        runtime.close()


def test_sdk_runtime_cleanup_failure_is_fatal(monkeypatch):
    class FakeReject:
        def __init__(self, *, feedback):
            self.feedback = feedback

    class FakeConnection:
        env = None

        @staticmethod
        def for_stdio(*, path):
            return FakeConnection()

    class FakeSession:
        async def send_and_wait(self, prompt, **kwargs):
            return SimpleNamespace(data=SimpleNamespace(content="answer"))

        async def disconnect(self):
            return None

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def start(self):
            return None

        async def stop(self):
            return None

        async def create_session(self, **kwargs):
            return FakeSession()

        async def delete_session(self, session_id):
            raise RuntimeError("disk cleanup denied")

    monkeypatch.setattr(
        llm,
        "_load_copilot_sdk",
        lambda: (FakeClient, FakeConnection, FakeReject),
    )
    runtime = llm._CopilotSdkRuntime(
        cli_path="/managed/copilot",
        use_bundled_runtime=False,
    )
    try:
        with pytest.raises(RuntimeError, match="cleanup could not be verified"):
            runtime.complete("hello", model="auto")
    finally:
        runtime.close()
