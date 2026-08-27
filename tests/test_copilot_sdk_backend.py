"""Contract tests for the optional GitHub Copilot SDK backend."""
from __future__ import annotations

import asyncio
import base64
import importlib
import json
import os
import sys
import time
import traceback
import types
import warnings
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from graphify import copilot_sdk_backend as backend
from graphify import llm

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 compatibility
    import tomli as tomllib  # type: ignore[no-redef]


_GRAPH_JSON = json.dumps(
    {
        "nodes": [
            {
                "id": "alpha",
                "label": "Alpha",
                "file_type": "document",
                "source_file": "README.md",
            }
        ],
        "edges": [],
        "hyperedges": [],
    }
)


def _assistant_event(content: str = _GRAPH_JSON) -> SimpleNamespace:
    return SimpleNamespace(
        type="assistant.message",
        data=SimpleNamespace(content=content),
    )


def _install_fake_copilot(
    monkeypatch: pytest.MonkeyPatch,
    *,
    response: Any = ...,
    start_error: BaseException | None = None,
    create_error: BaseException | None = None,
    send_error: BaseException | None = None,
    disconnect_error: BaseException | None = None,
    stop_error: BaseException | None = None,
    start_wait: bool = False,
    create_wait: bool = False,
    send_wait: bool = False,
    constructor_delay: float = 0,
    usage_events: list[Any] | None = None,
) -> dict[str, Any]:
    """Install a deterministic SDK double that exposes lifecycle state."""
    state: dict[str, Any] = {
        "clients": [],
        "sessions": [],
        "starts": 0,
        "creates": 0,
        "sends": 0,
        "disconnects": 0,
        "stops": 0,
        "force_stops": 0,
    }
    final_response = _assistant_event() if response is ... else response

    class FakeSession:
        def __init__(self, options: dict[str, Any]):
            self.options = options
            state["sessions"].append(self)

        async def send_and_wait(self, prompt: str, **kwargs: Any) -> Any:
            state["sends"] += 1
            state["prompt"] = prompt
            state["send_kwargs"] = kwargs
            if send_wait:
                await asyncio.Event().wait()
            if send_error is not None:
                raise send_error
            handler = self.options.get("on_event")
            if handler is not None:
                for event in usage_events or []:
                    handler(event)
            return final_response

        async def disconnect(self) -> None:
            state["disconnects"] += 1
            if disconnect_error is not None:
                raise disconnect_error

    class FakeClient:
        def __init__(self, **options: Any):
            if constructor_delay:
                time.sleep(constructor_delay)
            self.options = options
            state["clients"].append(self)

        async def start(self) -> None:
            state["starts"] += 1
            if start_wait:
                await asyncio.Event().wait()
            if start_error is not None:
                raise start_error

        async def create_session(self, **options: Any) -> FakeSession:
            state["creates"] += 1
            if create_wait:
                await asyncio.Event().wait()
            if create_error is not None:
                raise create_error
            return FakeSession(options)

        async def stop(self) -> None:
            state["stops"] += 1
            if stop_error is not None:
                raise stop_error

        async def force_stop(self) -> None:
            state["force_stops"] += 1

    module = types.ModuleType("copilot")
    setattr(module, "CopilotClient", FakeClient)
    monkeypatch.setitem(sys.modules, "copilot", module)
    # The real optional package is Python 3.11+, but these contract tests use a
    # local SDK double and must also run in Graphify's Python 3.10 CI job.
    monkeypatch.setattr(backend, "_supported_python", lambda: None)
    return state


def _call(**overrides: Any) -> dict[str, Any]:
    options = {
        "system_prompt": "Return the Graphify extraction schema.",
        "model": None,
        "reasoning_effort": None,
        "context_tier": None,
        "timeout_seconds": 2,
    }
    options.update(overrides)
    return backend.call_copilot_sdk("<untrusted_source>source</untrusted_source>", **options)


def test_copilot_extra_is_optional_and_python_gated():
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    extras = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"][
        "optional-dependencies"
    ]
    expected = "github-copilot-sdk>=1.0.11,<2; python_version >= '3.11'"
    assert extras["copilot"] == [expected]
    assert expected in extras["all"]


def test_backend_metadata_marks_runtime_authenticated_providers_keyless():
    assert llm._backend_requires_api_key("openai") is True
    for name in ("ollama", "bedrock", "claude-cli", "copilot-sdk"):
        assert llm._backend_requires_api_key(name) is False


def test_resolve_settings_precedence_and_default_sentinels(monkeypatch):
    monkeypatch.setenv("GRAPHIFY_COPILOT_SDK_MODEL", "sdk-env-model")
    monkeypatch.setenv("GRAPHIFY_COPILOT_MODEL", "legacy-env-model")
    monkeypatch.setenv("COPILOT_MODEL", "runtime-model")
    monkeypatch.setenv("GRAPHIFY_COPILOT_REASONING_EFFORT", "high")
    monkeypatch.setenv("GRAPHIFY_COPILOT_CONTEXT_TIER", "long_context")
    assert backend.resolve_settings() == ("sdk-env-model", "high", "long_context")
    assert backend.resolve_settings(
        model="argument-model", reasoning_effort="low", context_tier="default"
    ) == ("argument-model", "low", "default")
    assert backend.resolve_settings(model="auto")[0] is None
    assert backend.resolve_settings(model=backend.COPILOT_DEFAULT_MODEL)[0] is None


@pytest.mark.parametrize(
    ("variable", "value", "message"),
    [
        ("GRAPHIFY_COPILOT_REASONING_EFFORT", "extreme", "reasoning effort"),
        ("GRAPHIFY_COPILOT_CONTEXT_TIER", "huge", "context tier"),
    ],
)
def test_invalid_settings_fail_before_sdk(monkeypatch, variable, value, message):
    monkeypatch.setattr(backend, "_supported_python", lambda: None)
    monkeypatch.setenv(variable, value)
    with pytest.raises(ValueError, match=message):
        _call()


def test_unsupported_python_error_is_actionable(monkeypatch):
    monkeypatch.setattr(backend.sys, "version_info", (3, 10, 0))
    with pytest.raises(RuntimeError, match="Python 3.11 or later"):
        _call()


@pytest.mark.skipif(sys.version_info < (3, 11), reason="SDK extra requires Python 3.11+")
def test_missing_optional_dependency_error_is_actionable(monkeypatch):
    monkeypatch.setitem(sys.modules, "copilot", None)
    with pytest.raises(ImportError, match=r'graphifyy\[copilot\]'):
        _call()


def test_blob_attachments_are_inline_and_hide_host_paths():
    images = [
        backend.CopilotImage(b"one", "image/png", "/private/source/diagram.png"),
        backend.CopilotImage(b"two", "image/jpeg", r"C:\secret\photo.jpg"),
    ]
    assert backend.blob_attachments(images) == [
        {
            "type": "blob",
            "data": base64.b64encode(b"one").decode("ascii"),
            "mimeType": "image/png",
            "displayName": "diagram.png",
        },
        {
            "type": "blob",
            "data": base64.b64encode(b"two").decode("ascii"),
            "mimeType": "image/jpeg",
            "displayName": "photo.jpg",
        },
    ]
    with pytest.raises(TypeError, match="must be bytes"):
        backend.blob_attachments(
            [backend.CopilotImage("pixels", "image/png", "x.png")]  # type: ignore[arg-type]
        )


def test_extract_files_direct_sends_inline_image_attachment(monkeypatch, tmp_path):
    image = tmp_path / "diagram.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    graph = json.dumps(
        {
            "nodes": [
                {
                    "id": "diagram",
                    "label": "Diagram",
                    "file_type": "image",
                    "source_file": "diagram.png",
                }
            ],
            "edges": [],
            "hyperedges": [],
        }
    )
    state = _install_fake_copilot(monkeypatch, response=_assistant_event(graph))

    result = llm.extract_files_direct(
        [image], backend="copilot-sdk", root=tmp_path
    )

    assert state["send_kwargs"]["attachments"] == [
        {
            "type": "blob",
            "data": base64.b64encode(image.read_bytes()).decode("ascii"),
            "mimeType": "image/png",
            "displayName": "diagram.png",
        }
    ]
    assert result["nodes"][0]["source_file"] == "diagram.png"


def test_usage_collector_keeps_only_numeric_root_session_metadata():
    collector = backend._UsageCollector()
    collector(
        SimpleNamespace(
            type="assistant.usage",
            data=SimpleNamespace(
                input_tokens=10,
                output_tokens=4,
                cache_read_tokens=2,
                cache_write_tokens=1,
                reasoning_tokens=3,
                cost=0.25,
                copilot_usage=SimpleNamespace(total_nano_aiu=999),
                model="gpt-test",
                finish_reason="stop",
            ),
        )
    )
    collector(
        SimpleNamespace(
            type="assistant.usage",
            agent_id="child",
            data=SimpleNamespace(input_tokens=999, output_tokens=999),
        )
    )
    collector(
        SimpleNamespace(
            type="session.usage_info",
            data=SimpleNamespace(current_tokens=20, token_limit=100),
        )
    )
    assert collector.values == {
        "input_tokens": 10,
        "output_tokens": 4,
        "cache_read_tokens": 2,
        "cache_write_tokens": 1,
        "reasoning_tokens": 3,
        "copilot_premium_request_cost": pytest.approx(0.25),
        "context_current_tokens": 20,
        "context_limit": 100,
        "model": "gpt-test",
        "finish_reason": "stop",
    }


def test_success_uses_official_send_and_wait_and_locked_down_session(monkeypatch, tmp_path):
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path / "copilot-home"))
    usage = SimpleNamespace(
        type="assistant.usage",
        data=SimpleNamespace(input_tokens=11, output_tokens=7, model="gpt-test"),
    )
    state = _install_fake_copilot(monkeypatch, usage_events=[usage])
    result = _call(model="gpt-test", reasoning_effort="high", context_tier="long_context")

    assert result["content"] == _GRAPH_JSON
    assert result["input_tokens"] == 11
    assert result["output_tokens"] == 7
    assert state["starts"] == state["creates"] == state["sends"] == 1
    assert state["disconnects"] == state["stops"] == 1
    assert state["prompt"].startswith(backend._USER_INSTRUCTION)
    assert "<untrusted_source>source</untrusted_source>" in state["prompt"]

    client_options = state["clients"][0].options
    assert client_options["use_logged_in_user"] is True
    assert client_options["mode"] == "empty"
    assert client_options["enable_remote_sessions"] is False
    assert client_options["base_directory"] == str(tmp_path / "copilot-home")
    assert Path(client_options["working_directory"]).name.startswith("graphify-copilot-")

    session_options = state["sessions"][0].options
    assert session_options["model"] == "gpt-test"
    assert session_options["reasoning_effort"] == "high"
    assert session_options["context_tier"] == "long_context"
    assert session_options["tools"] == []
    assert session_options["available_tools"] == []
    assert session_options["mcp_servers"] == {}
    for key in (
        "enable_session_telemetry",
        "enable_file_change_tracking",
        "enable_session_store",
        "enable_skills",
        "enable_config_discovery",
        "enable_on_demand_instruction_discovery",
        "enable_file_hooks",
        "enable_host_git_operations",
        "enable_mcp_apps",
    ):
        assert session_options[key] is False
    assert session_options["skip_custom_instructions"] is True
    assert session_options["memory"] == {"enabled": False}
    assert session_options["mcp_oauth_token_storage"] == "in-memory"
    assert session_options["embedding_cache_storage"] == "in-memory"
    assert session_options["working_directory"] == session_options["config_directory"]
    assert not Path(session_options["working_directory"]).exists()
    assert state["send_kwargs"]["timeout"] > 0


def test_every_request_gets_a_fresh_client_and_session(monkeypatch):
    state = _install_fake_copilot(monkeypatch)
    _call()
    _call()
    assert len(state["clients"]) == 2
    assert len(state["sessions"]) == 2
    assert state["starts"] == state["creates"] == state["sends"] == 2
    assert state["disconnects"] == state["stops"] == 2


def test_plain_completion_does_not_add_extraction_instruction(monkeypatch):
    state = _install_fake_copilot(monkeypatch, response=_assistant_event("label"))
    result = backend.call_copilot_sdk(
        "Name this community",
        system_prompt="",
        model=None,
        reasoning_effort=None,
        context_tier=None,
        timeout_seconds=2,
    )
    assert result["content"] == "label"
    assert state["prompt"] == "Name this community"
    assert state["sessions"][0].options["system_message"] is None


@pytest.mark.parametrize("stage", ["start", "create"])
def test_pre_dispatch_timeout_is_retry_safe(monkeypatch, stage):
    monkeypatch.setattr(backend, "_STARTUP_TIMEOUT_SECONDS", 0.01)
    state = _install_fake_copilot(
        monkeypatch,
        start_wait=stage == "start",
        create_wait=stage == "create",
    )
    with pytest.raises(backend.CopilotSdkTimeoutError) as exc_info:
        _call(timeout_seconds=0.1)
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
    assert state["sends"] == 0
    assert state["force_stops"] == 1


def test_runtime_setup_cannot_dispatch_after_deadline(monkeypatch):
    state = _install_fake_copilot(monkeypatch, constructor_delay=0.03)
    with pytest.raises(backend.CopilotSdkTimeoutError, match="runtime setup exceeded"):
        _call(timeout_seconds=0.01)
    assert state["starts"] == 0
    assert state["sends"] == 0
    assert state["stops"] == 1


@pytest.mark.parametrize(
    "failure",
    [asyncio.TimeoutError("SECRET_AUTH_HEADER"), RuntimeError("SECRET_CORPUS")],
)
def test_post_dispatch_failure_is_unknown_and_sanitized(monkeypatch, failure):
    state = _install_fake_copilot(monkeypatch, send_error=failure)
    with pytest.raises(backend.CopilotSdkUnknownOutcomeError) as exc_info:
        _call()
    rendered = "".join(traceback.format_exception(exc_info.value))
    assert "SECRET_AUTH_HEADER" not in rendered
    assert "SECRET_CORPUS" not in rendered
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
    assert state["sends"] == 1


def test_post_dispatch_timeout_force_stops_without_graceful_replay(monkeypatch):
    state = _install_fake_copilot(monkeypatch, send_wait=True)
    with pytest.raises(backend.CopilotSdkUnknownOutcomeError):
        _call(timeout_seconds=0.02)
    assert state["sends"] == 1
    assert state["force_stops"] == 1
    assert state["disconnects"] == state["stops"] == 0


def test_run_bounded_rejects_synchronous_callables_without_invoking_them():
    called = False

    def synchronous_operation() -> None:
        nonlocal called
        called = True

    async def run() -> None:
        with pytest.raises(TypeError, match="must be awaitable"):
            await backend._run_bounded(
                synchronous_operation,  # type: ignore[arg-type]
                timeout=0.01,
            )

    asyncio.run(run())
    assert called is False


def test_run_bounded_cancels_child_when_caller_is_cancelled():
    async def run() -> None:
        started = asyncio.Event()
        child_finished = asyncio.Event()
        abort_called = False

        async def operation() -> None:
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                child_finished.set()

        def abort() -> None:
            nonlocal abort_called
            abort_called = True

        caller = asyncio.create_task(
            backend._run_bounded(operation(), timeout=10, abort=abort)
        )
        await started.wait()
        caller.cancel()
        with pytest.raises(asyncio.CancelledError):
            await caller
        assert child_finished.is_set()
        assert abort_called is True

    asyncio.run(run())


def test_run_async_reports_tasks_that_ignore_bounded_cancellation(monkeypatch):
    monkeypatch.setattr(backend, "_CLEANUP_TIMEOUT_SECONDS", 0.01)

    async def stubborn() -> None:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            await asyncio.Event().wait()

    async def factory() -> str:
        asyncio.create_task(stubborn())
        return "ok"

    with pytest.warns(RuntimeWarning, match="remained pending"):
        assert backend._run_async(factory) == "ok"


def test_unknown_outcome_bypasses_graphify_adaptive_retry(monkeypatch, tmp_path):
    source = tmp_path / "a.md"
    source.write_text("Alpha", encoding="utf-8")
    calls = {"count": 0}

    def fail_once(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        calls["count"] += 1
        raise backend.CopilotSdkUnknownOutcomeError("outcome is unknown")

    monkeypatch.setattr(llm, "extract_files_direct", fail_once)
    with pytest.raises(backend.CopilotSdkUnknownOutcomeError):
        llm._extract_with_adaptive_retry(
            [source], "copilot-sdk", None, None, tmp_path, max_depth=3
        )
    assert calls["count"] == 1


def test_missing_assistant_message_is_a_clear_failure(monkeypatch):
    state = _install_fake_copilot(monkeypatch, response=None)
    with pytest.raises(RuntimeError, match="Copilot SDK request failed"):
        _call()
    assert state["sends"] == 1
    assert state["disconnects"] == state["stops"] == 1


def test_startup_errors_are_sanitized_and_actionable(monkeypatch):
    state = _install_fake_copilot(
        monkeypatch,
        start_error=RuntimeError("authentication failed: SECRET_TOKEN"),
    )
    with pytest.raises(RuntimeError, match="authentication or entitlement") as exc_info:
        _call()
    rendered = "".join(traceback.format_exception(exc_info.value))
    assert "SECRET_TOKEN" not in rendered
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
    assert state["sends"] == 0


def test_valid_response_survives_cleanup_failure_with_safe_warning(monkeypatch):
    state = _install_fake_copilot(
        monkeypatch,
        disconnect_error=RuntimeError("SECRET_DISCONNECT"),
        stop_error=RuntimeError("SECRET_STOP"),
    )
    with pytest.warns(RuntimeWarning, match="cleanup did not finish cleanly") as caught:
        result = _call()
    assert result["content"] == _GRAPH_JSON
    assert "SECRET" not in str(caught[0].message)
    assert state["disconnects"] == state["stops"] == state["force_stops"] == 1


def test_cleanup_failure_does_not_replace_primary_unknown_outcome(monkeypatch):
    _install_fake_copilot(
        monkeypatch,
        send_error=RuntimeError("SECRET_PRIMARY"),
        disconnect_error=RuntimeError("SECRET_CLEANUP"),
        stop_error=RuntimeError("SECRET_STOP"),
    )
    with warnings.catch_warnings(record=True) as caught:
        with pytest.raises(backend.CopilotSdkUnknownOutcomeError) as exc_info:
            _call()
    rendered = "".join(traceback.format_exception(exc_info.value))
    assert "SECRET" not in rendered
    assert caught == []


def test_process_control_exceptions_propagate_from_cleanup(monkeypatch):
    state = _install_fake_copilot(monkeypatch, disconnect_error=KeyboardInterrupt())
    with pytest.raises(KeyboardInterrupt):
        _call()
    assert state["stops"] == 1
    workspace = Path(state["clients"][0].options["working_directory"])
    assert not workspace.exists()


def test_task_cancellation_propagates(monkeypatch):
    module = types.ModuleType("copilot")
    setattr(module, "CopilotClient", object)
    monkeypatch.setitem(sys.modules, "copilot", module)

    async def cancel(**_kwargs: Any) -> dict[str, Any]:
        raise asyncio.CancelledError

    monkeypatch.setattr(backend, "_call_once", cancel)
    with pytest.raises(asyncio.CancelledError):
        backend._run_async(
            lambda: backend._call_async(
                prompt="source",
                system_prompt="system",
                model=None,
                reasoning_effort=None,
                context_tier=None,
                timeout_seconds=1,
                images=None,
            )
        )


def test_adapter_works_when_called_from_a_running_event_loop(monkeypatch):
    _install_fake_copilot(monkeypatch)

    async def invoke() -> dict[str, Any]:
        return _call()

    assert asyncio.run(invoke())["content"] == _GRAPH_JSON


def test_run_async_restores_a_dormant_caller_loop():
    original = asyncio.new_event_loop()
    asyncio.set_event_loop(original)
    try:
        assert backend._run_async(lambda: asyncio.sleep(0, result="ok")) == "ok"
        assert asyncio.get_event_loop() is original
    finally:
        asyncio.set_event_loop(None)
        original.close()


def test_permission_handler_rejects_tool_requests(monkeypatch):
    generated = types.ModuleType("copilot.generated")
    rpc = types.ModuleType("copilot.generated.rpc")

    class Reject:
        def __init__(self, *, feedback: str):
            self.feedback = feedback

    setattr(rpc, "PermissionDecisionReject", Reject)
    monkeypatch.setitem(sys.modules, "copilot.generated", generated)
    monkeypatch.setitem(sys.modules, "copilot.generated.rpc", rpc)
    decision = backend._deny_permission(object(), object())
    assert isinstance(decision, Reject)
    assert "does not permit tools" in decision.feedback


@pytest.mark.skipif(
    os.environ.get("GRAPHIFY_COPILOT_RUNTIME_SMOKE") != "1",
    reason="opt-in platform runtime smoke",
)
def test_official_runtime_starts_and_stops(tmp_path):
    if sys.version_info < (3, 11):
        pytest.skip("Copilot SDK requires Python 3.11+")
    CopilotClient = importlib.import_module("copilot").CopilotClient

    copilot_home = tmp_path / "copilot-home"
    work = tmp_path / "work"
    copilot_home.mkdir()
    work.mkdir()

    async def run() -> None:
        client = CopilotClient(
            use_logged_in_user=True,
            mode="empty",
            enable_remote_sessions=False,
            base_directory=str(copilot_home),
            working_directory=str(work),
        )
        await client.start()
        await client.stop()

    asyncio.run(run())


def test_extraction_wrapper_parses_graph_and_preserves_usage(monkeypatch):
    def fake_call(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "content": _GRAPH_JSON,
            "input_tokens": 10,
            "output_tokens": 4,
            "copilot_premium_request_cost": 0.5,
            "model": "gpt-test",
            "finish_reason": "stop",
        }

    monkeypatch.setattr(backend, "call_copilot_sdk", fake_call)
    result = llm._call_copilot_sdk("source", model=None)
    assert result["nodes"][0]["source_file"] == "README.md"
    assert result["input_tokens"] == 10
    assert result["output_tokens"] == 4
    assert result["copilot_premium_request_cost"] == pytest.approx(0.5)
    assert result["model"] == "gpt-test"


def test_plain_llm_wrapper_preserves_fractional_usage(monkeypatch):
    usage: dict[str, Any] = {}

    def fake_call(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "content": "Dependency Analysis",
            "input_tokens": 10,
            "output_tokens": 2,
            "copilot_premium_request_cost": 0.25,
        }

    monkeypatch.setattr(backend, "call_copilot_sdk", fake_call)
    assert llm._call_llm("prompt", backend="copilot-sdk", usage_out=usage) == (
        "Dependency Analysis"
    )
    assert usage["input"] == 10
    assert usage["output"] == 2
    assert usage["copilot_premium_request_cost"] == pytest.approx(0.25)
