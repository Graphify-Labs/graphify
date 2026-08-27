"""Contract tests for the optional GitHub Copilot SDK backend."""
from __future__ import annotations

import asyncio
import base64
import gc
import importlib
import json
import os
import re
import sys
import threading
import time
import traceback
import types
import warnings
from concurrent.futures import ThreadPoolExecutor
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
    disconnect_wait: bool = False,
    stop_error: BaseException | None = None,
    constructor_error: BaseException | None = None,
    start_wait: bool = False,
    start_ignores_cancellation: bool = False,
    create_wait: bool = False,
    send_wait: bool = False,
    send_ignores_cancellation: bool = False,
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
                while True:
                    try:
                        await asyncio.Event().wait()
                    except asyncio.CancelledError:
                        if not send_ignores_cancellation:
                            raise
            if send_error is not None:
                raise send_error
            handler = self.options.get("on_event")
            if handler is not None:
                for event in usage_events or []:
                    handler(event)
            return final_response

        async def disconnect(self) -> None:
            state["disconnects"] += 1
            if disconnect_wait:
                await asyncio.Event().wait()
            if disconnect_error is not None:
                raise disconnect_error

    class FakeClient:
        def __init__(self, **options: Any):
            if constructor_delay:
                time.sleep(constructor_delay)
            if constructor_error is not None:
                raise constructor_error
            self.options = options
            state["clients"].append(self)

        async def start(self) -> None:
            state["starts"] += 1
            if start_wait:
                while True:
                    try:
                        await asyncio.Event().wait()
                    except asyncio.CancelledError:
                        if not start_ignores_cancellation:
                            raise
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
    class ModelLimitsOverride:
        def __init__(self, *, max_output_tokens: int | None = None):
            self.max_output_tokens = max_output_tokens

    class ModelCapabilitiesOverride:
        def __init__(self, *, limits: Any = None):
            self.supports = None
            self.limits = limits

    setattr(module, "CopilotClient", FakeClient)
    setattr(module, "ModelCapabilitiesOverride", ModelCapabilitiesOverride)
    setattr(module, "ModelLimitsOverride", ModelLimitsOverride)
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
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    package_name = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"][
        "name"
    ]
    monkeypatch.setitem(sys.modules, "copilot", None)
    with pytest.raises(
        ImportError,
        match=rf'{re.escape(package_name)}\[copilot\]',
    ):
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
    assert collector.snapshot() == {
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


def test_usage_collector_serializes_concurrent_callbacks():
    collector = backend._UsageCollector()
    event = SimpleNamespace(
        type="assistant.usage",
        data=SimpleNamespace(input_tokens=1, output_tokens=2, cost=0.25),
    )
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(collector, [event] * 1000))
    usage = collector.snapshot()
    assert usage["input_tokens"] == 1000
    assert usage["output_tokens"] == 2000
    assert usage["copilot_premium_request_cost"] == 250


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
    assert "{prompt}" not in state["prompt"]
    assert "{system_prompt}" not in state["prompt"]

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


def test_public_adapter_optional_settings_have_safe_defaults(monkeypatch):
    state = _install_fake_copilot(monkeypatch, response=_assistant_event("label"))

    result = backend.call_copilot_sdk("Name this community")

    assert result["content"] == "label"
    assert state["prompt"] == "Name this community"
    options = state["sessions"][0].options
    assert options["system_message"] is None
    assert options["model"] is None
    assert options["reasoning_effort"] is None
    assert options["context_tier"] is None


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
    started = time.monotonic()
    with pytest.raises(backend.CopilotSdkTimeoutError, match="runtime setup exceeded"):
        _call(timeout_seconds=0.01)
    assert time.monotonic() - started < 0.1
    assert state["starts"] == 0
    assert state["sends"] == 0
    assert state["stops"] == 0


def test_stubborn_pre_dispatch_start_is_cleanup_error_not_retryable_timeout(
    monkeypatch,
):
    monkeypatch.setattr(backend, "_CLEANUP_TIMEOUT_SECONDS", 0.01)
    state = _install_fake_copilot(
        monkeypatch,
        start_wait=True,
        start_ignores_cancellation=True,
    )
    with pytest.warns(RuntimeWarning) as caught:
        with pytest.raises(backend.CopilotSdkCleanupError):
            _call(timeout_seconds=0.01)
    warning_text = "\n".join(str(item.message) for item in caught)
    assert "operation remained pending" in warning_text
    assert "tasks remained pending" in warning_text
    assert state["starts"] == 1
    assert state["sends"] == 0
    assert state["force_stops"] == 1


def test_timed_out_constructor_owns_workspace_until_worker_exits(monkeypatch):
    monkeypatch.setattr(backend, "_CLEANUP_TIMEOUT_SECONDS", 0.01)
    constructor_started = threading.Event()
    release_constructor = threading.Event()
    paths: list[Path] = []

    class Client:
        def __init__(self, **options: Any):
            paths.append(Path(options["working_directory"]))
            constructor_started.set()
            release_constructor.wait()

    real_executor = backend._DaemonThreadPoolExecutor

    class StartedExecutor(real_executor):
        def submit(self, fn: Any, /, *args: Any, **kwargs: Any) -> Any:
            future = super().submit(fn, *args, **kwargs)
            assert constructor_started.wait(timeout=1)
            return future

    monkeypatch.setattr(backend, "_DaemonThreadPoolExecutor", StartedExecutor)
    module = types.ModuleType("copilot")
    setattr(module, "CopilotClient", Client)
    monkeypatch.setitem(sys.modules, "copilot", module)
    monkeypatch.setattr(backend, "_supported_python", lambda: None)

    try:
        with pytest.raises(
            backend.CopilotSdkTimeoutError, match="runtime setup exceeded"
        ):
            _call(timeout_seconds=0.01)
        assert constructor_started.is_set()
        assert paths[0].exists()
    finally:
        release_constructor.set()
    deadline = time.monotonic() + 1
    while paths[0].exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert not paths[0].exists()


def test_successful_constructor_never_joins_worker_on_event_loop(monkeypatch):
    real_executor = backend._DaemonThreadPoolExecutor

    class NoJoinExecutor(real_executor):
        def shutdown_bounded(self, _timeout: float) -> bool:
            raise AssertionError("constructor path must not join a worker")

    class Client:
        def __init__(self, **_options: Any):
            pass

    monkeypatch.setattr(backend, "_DaemonThreadPoolExecutor", NoJoinExecutor)

    async def run() -> None:
        resources = backend._CopilotResources()
        client = await backend._construct_client(Client, resources, timeout=1)
        assert isinstance(client, Client)
        resources.client = None
        await resources.__aexit__(RuntimeError, None, None)

    asyncio.run(run())


def test_constructor_failure_has_no_unbound_cleanup_state(monkeypatch):
    state = _install_fake_copilot(
        monkeypatch,
        constructor_error=RuntimeError("SECRET_CONSTRUCTOR"),
    )
    with pytest.raises(RuntimeError, match="Copilot SDK request failed") as exc_info:
        _call()
    assert "SECRET_CONSTRUCTOR" not in "".join(
        traceback.format_exception(exc_info.value)
    )
    assert state["clients"] == []
    assert state["sessions"] == []


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
    with pytest.raises(
        backend.CopilotSdkUnknownOutcomeError,
        match="timed out after source dispatch",
    ):
        _call(timeout_seconds=0.02)
    assert state["sends"] == 1
    assert state["force_stops"] == 1
    assert state["disconnects"] == state["stops"] == 0


def test_post_dispatch_cleanup_failure_remains_unknown_and_not_retryable(monkeypatch):
    state = _install_fake_copilot(
        monkeypatch,
        send_error=backend.CopilotSdkCleanupError("SECRET_CLEANUP"),
    )
    with pytest.raises(
        backend.CopilotSdkUnknownOutcomeError,
        match="cleanup did not complete after source dispatch",
    ) as exc_info:
        _call()
    assert "SECRET_CLEANUP" not in "".join(
        traceback.format_exception(exc_info.value)
    )
    assert state["sends"] == 1


def test_stubborn_post_dispatch_send_is_unknown_and_never_replayed(monkeypatch):
    monkeypatch.setattr(backend, "_CLEANUP_TIMEOUT_SECONDS", 0.01)
    state = _install_fake_copilot(
        monkeypatch,
        send_wait=True,
        send_ignores_cancellation=True,
    )
    with pytest.warns(RuntimeWarning) as caught:
        with pytest.raises(
            backend.CopilotSdkUnknownOutcomeError,
            match="cleanup did not complete after source dispatch",
        ):
            _call(timeout_seconds=0.01)
    warning_text = "\n".join(str(item.message) for item in caught)
    assert "operation remained pending" in warning_text
    assert "tasks remained pending" in warning_text
    assert state["sends"] == 1
    assert state["force_stops"] == 1


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

        async def abort() -> None:
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


def test_repeated_cancellation_cannot_interrupt_operation_cleanup():
    async def run() -> None:
        started = asyncio.Event()
        cleanup_started = asyncio.Event()
        release_cleanup = asyncio.Event()
        finished = asyncio.Event()

        async def operation() -> None:
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cleanup_started.set()
                await release_cleanup.wait()
                finished.set()

        caller = asyncio.create_task(
            backend._run_bounded(operation(), timeout=10)
        )
        await started.wait()
        caller.cancel()
        await cleanup_started.wait()
        caller.cancel()
        release_cleanup.set()
        with pytest.raises(asyncio.CancelledError):
            await caller
        assert finished.is_set()

    asyncio.run(run())


def test_run_bounded_timeout_survives_async_abort_failure():
    async def operation() -> None:
        await asyncio.Event().wait()

    async def abort() -> None:
        raise RuntimeError("abort failed")

    async def run() -> None:
        with pytest.raises(asyncio.TimeoutError):
            await backend._run_bounded(operation(), timeout=0.01, abort=abort)

    asyncio.run(run())


def test_run_bounded_rejects_synchronous_abort_without_invoking_it():
    abort_called = False

    async def operation() -> None:
        await asyncio.Event().wait()

    def abort() -> None:
        nonlocal abort_called
        abort_called = True

    async def run() -> None:
        with pytest.raises(TypeError, match="abort callback must be async"):
            await backend._run_bounded(
                operation(), timeout=0.01, abort=abort  # type: ignore[arg-type]
            )

    asyncio.run(run())
    assert abort_called is False


def test_run_bounded_accepts_async_callable_abort():
    class Abort:
        def __init__(self) -> None:
            self.called = False

        async def __call__(self) -> None:
            self.called = True

    async def operation() -> None:
        await asyncio.Event().wait()

    async def run() -> None:
        abort = Abort()
        with pytest.raises(asyncio.TimeoutError):
            await backend._run_bounded(operation(), timeout=0.01, abort=abort)
        assert abort.called is True

    asyncio.run(run())


def test_run_bounded_timeout_cancels_and_drains_operation():
    async def run() -> None:
        finished = asyncio.Event()

        async def operation() -> None:
            try:
                await asyncio.Event().wait()
            finally:
                finished.set()

        with pytest.raises(asyncio.TimeoutError):
            await backend._run_bounded(operation(), timeout=0.01)
        assert finished.is_set()

    asyncio.run(run())


def test_run_bounded_preserves_primary_control_flow_failure():
    class ControlSignal(BaseException):
        pass

    async def operation() -> None:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            raise ControlSignal

    async def run() -> None:
        with pytest.raises(ControlSignal):
            await backend._run_bounded(operation(), timeout=0.01)

    asyncio.run(run())


def test_late_cancellation_cannot_interrupt_timeout_abort_cleanup():
    async def run() -> None:
        abort_started = asyncio.Event()
        release_abort = asyncio.Event()
        operation_finished = asyncio.Event()
        abort_finished = asyncio.Event()

        async def operation() -> None:
            try:
                await asyncio.Event().wait()
            finally:
                operation_finished.set()

        async def abort() -> None:
            abort_started.set()
            try:
                await release_abort.wait()
            finally:
                abort_finished.set()

        caller = asyncio.create_task(
            backend._run_bounded(operation(), timeout=0.01, abort=abort)
        )
        await abort_started.wait()
        caller.cancel()
        release_abort.set()
        with pytest.raises(asyncio.CancelledError):
            await caller
        assert operation_finished.is_set()
        assert abort_finished.is_set()

    asyncio.run(run())


def test_force_stop_is_idempotent_under_concurrent_cleanup():
    class Client:
        calls = 0

        async def force_stop(self) -> None:
            self.calls += 1
            await asyncio.sleep(0)

    async def run() -> int:
        resources = backend._CopilotResources()
        client = Client()
        resources.client = client
        await asyncio.gather(resources.force_stop(), resources.force_stop())
        await resources.__aexit__(None, None, None)
        return client.calls

    assert asyncio.run(run()) == 1


def test_successful_force_stop_clears_terminated_runtime_handles():
    class Client:
        async def force_stop(self) -> None:
            return None

    async def run() -> None:
        resources = backend._CopilotResources()
        resources.client = Client()
        resources.session = object()

        await resources.force_stop()

        assert resources.force_stopped is True
        assert resources.client is None
        assert resources.session is None
        await resources.__aexit__(None, None, None)

    asyncio.run(run())


def test_force_stop_is_bounded_while_holding_lifecycle_lock(monkeypatch):
    monkeypatch.setattr(backend, "_CLEANUP_TIMEOUT_SECONDS", 0.01)

    class Client:
        async def force_stop(self) -> None:
            await asyncio.Event().wait()

    async def run() -> None:
        resources = backend._CopilotResources()
        resources.client = Client()
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(resources.force_stop(), timeout=0.1)
        assert resources._lifecycle_lock.locked() is False
        await resources.__aexit__(RuntimeError, None, None)

    asyncio.run(run())


def test_session_creation_is_rejected_after_terminal_cleanup_starts():
    factory_called = False

    async def run() -> None:
        nonlocal factory_called
        resources = backend._CopilotResources()
        resources._terminal_cleanup_started = True

        def create_session() -> Any:
            nonlocal factory_called
            factory_called = True
            raise AssertionError("terminal cleanup must reject before creation")

        with pytest.raises(backend.CopilotSdkCleanupError):
            await resources.track_created_session(create_session)
        assert resources.session is None
        await resources.__aexit__(RuntimeError, None, None)

    asyncio.run(run())
    assert factory_called is False


def test_failed_session_creation_releases_reservation():
    async def run() -> None:
        resources = backend._CopilotResources()

        async def create_session() -> None:
            raise RuntimeError("creation failed")

        with pytest.raises(RuntimeError, match="creation failed"):
            await resources.track_created_session(create_session)
        assert resources._in_flight_session_creations == 0
        await resources.__aexit__(RuntimeError, None, None)

    asyncio.run(run())


def test_session_transfer_finishes_when_cancelled_waiting_for_lifecycle_lock():
    state = {"disconnects": 0}
    creation_started = asyncio.Event()
    release_creation = asyncio.Event()

    class Session:
        async def disconnect(self) -> None:
            state["disconnects"] += 1

    async def create_session() -> Session:
        creation_started.set()
        await release_creation.wait()
        return Session()

    async def run() -> None:
        resources = backend._CopilotResources()
        tracking = asyncio.create_task(
            resources.track_created_session(create_session)
        )
        await creation_started.wait()
        await resources._lifecycle_lock.acquire()
        release_creation.set()
        await asyncio.sleep(0)
        tracking.cancel()
        resources._terminal_cleanup_started = True
        resources._lifecycle_lock.release()
        with pytest.raises(asyncio.CancelledError):
            await tracking
        assert resources.session is None
        assert resources._in_flight_session_creations == 0
        await resources.__aexit__(RuntimeError, None, None)

    asyncio.run(run())
    assert state["disconnects"] == 1


def test_cancelled_late_session_remains_owned_when_disconnect_times_out(monkeypatch):
    monkeypatch.setattr(backend, "_CLEANUP_TIMEOUT_SECONDS", 0.01)
    disconnect_started = asyncio.Event()
    calls = 0

    class Session:
        async def disconnect(self) -> None:
            nonlocal calls
            calls += 1
            if calls == 1:
                disconnect_started.set()
                await asyncio.Event().wait()

    async def run() -> None:
        resources = backend._CopilotResources()
        session = Session()
        creation_started = asyncio.Event()
        release_creation = asyncio.Event()

        async def create_session() -> Session:
            creation_started.set()
            await release_creation.wait()
            return session

        tracking = asyncio.create_task(
            resources.track_created_session(create_session)
        )
        await creation_started.wait()
        await resources.force_stop()
        release_creation.set()
        await disconnect_started.wait()
        tracking.cancel()
        with pytest.raises(asyncio.CancelledError):
            await tracking
        assert resources.session is session
        assert resources._in_flight_session_creations == 0
        await resources.__aexit__(RuntimeError, None, None)
        assert resources.session is None

    asyncio.run(run())
    assert calls == 2


def test_in_flight_session_creation_keeps_workspace_until_late_disconnect():
    creation_started = asyncio.Event()
    release_creation = asyncio.Event()
    disconnect_workspace_states: list[bool] = []
    cleanup_lock_states: list[bool] = []

    async def run() -> None:
        resources = backend._CopilotResources()
        assert resources.workspace is not None
        workspace = Path(resources.workspace.name)
        cleanup_workspace_locked = resources._cleanup_workspace_locked

        def record_cleanup_lock() -> bool:
            cleanup_lock_states.append(resources._lifecycle_lock.locked())
            return cleanup_workspace_locked()

        resources._cleanup_workspace_locked = record_cleanup_lock  # type: ignore[method-assign]

        class Client:
            async def force_stop(self) -> None:
                return None

        class Session:
            async def disconnect(self) -> None:
                disconnect_workspace_states.append(workspace.exists())

        async def create_session() -> Session:
            creation_started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                await release_creation.wait()
            return Session()

        resources.client = Client()
        tracking = asyncio.create_task(
            resources.track_created_session(create_session)
        )
        await creation_started.wait()
        tracking.cancel()
        await resources.force_stop()
        await resources.__aexit__(RuntimeError, None, None)
        assert workspace.exists()

        release_creation.set()
        with pytest.raises(
            backend.CopilotSdkCleanupError, match="after terminal cleanup"
        ):
            await tracking
        assert disconnect_workspace_states == [True]
        assert cleanup_lock_states and all(cleanup_lock_states)
        assert not workspace.exists()

    asyncio.run(run())


def test_unsafe_workspace_cleanup_survives_resource_garbage_collection():
    async def quarantine() -> Path:
        resources = backend._CopilotResources()
        assert resources.workspace is not None
        path = Path(resources.workspace.name)
        resources._terminal_cleanup_started = True
        resources._in_flight_session_creations = 1
        async with resources._lifecycle_lock:
            assert resources._cleanup_workspace_locked() is False
        return path

    path = asyncio.run(quarantine())
    gc.collect()
    assert path.exists()
    with backend._QUARANTINED_WORKSPACES_LOCK:
        quarantined = next(
            workspace
            for workspace in backend._QUARANTINED_WORKSPACES
            if Path(workspace.name) == path
        )
        backend._QUARANTINED_WORKSPACES.remove(quarantined)
    quarantined.cleanup()
    assert not path.exists()


def test_cleanup_waits_for_in_flight_force_stop():
    release = asyncio.Event()
    calls: list[str] = []

    class Client:
        async def force_stop(self) -> None:
            calls.append("force-start")
            await release.wait()
            calls.append("force-finish")

        async def stop(self) -> None:
            calls.append("stop")

    async def run() -> None:
        resources = backend._CopilotResources()
        resources.client = Client()
        stopping = asyncio.create_task(resources.force_stop())
        while calls != ["force-start"]:
            await asyncio.sleep(0)
        cleanup = asyncio.create_task(resources.__aexit__(None, None, None))
        await asyncio.sleep(0)
        assert not cleanup.done()
        release.set()
        await asyncio.gather(stopping, cleanup)

    asyncio.run(run())
    assert calls == ["force-start", "force-finish"]


def test_cleanup_does_not_block_forever_behind_hung_force_stop(monkeypatch):
    monkeypatch.setattr(backend, "_CLEANUP_TIMEOUT_SECONDS", 0.01)
    started = asyncio.Event()
    state = {"graceful_stops": 0}

    class Client:
        async def force_stop(self) -> None:
            started.set()
            await asyncio.Event().wait()

        async def stop(self) -> None:
            state["graceful_stops"] += 1

    async def run() -> None:
        resources = backend._CopilotResources()
        assert resources.workspace is not None
        workspace = Path(resources.workspace.name)
        resources.client = Client()
        stopping = asyncio.create_task(resources.force_stop())
        await started.wait()
        with pytest.warns(RuntimeWarning, match="cleanup did not finish cleanly"):
            await asyncio.wait_for(
                resources.__aexit__(None, None, None), timeout=0.1
            )
        assert workspace.exists()
        assert state["graceful_stops"] == 0
        stopping.cancel()
        with pytest.raises(asyncio.CancelledError):
            await stopping
        await resources.__aexit__(RuntimeError, None, None)
        assert not workspace.exists()

    asyncio.run(run())
    assert state["graceful_stops"] == 1


def test_cancellation_during_force_stop_check_finishes_resource_cleanup():
    release = asyncio.Event()
    force_started = asyncio.Event()

    class Client:
        async def force_stop(self) -> None:
            force_started.set()
            await release.wait()

        async def stop(self) -> None:
            raise AssertionError("completed force-stop must skip graceful stop")

    async def run() -> None:
        resources = backend._CopilotResources()
        assert resources.workspace is not None
        workspace = Path(resources.workspace.name)
        resources.client = Client()
        stopping = asyncio.create_task(resources.force_stop())
        await force_started.wait()
        cleanup = asyncio.create_task(resources.__aexit__(None, None, None))
        await asyncio.sleep(0)
        cleanup.cancel()
        release.set()
        await stopping
        with pytest.raises(asyncio.CancelledError):
            await cleanup
        assert not workspace.exists()

    asyncio.run(run())


def test_run_async_reports_tasks_that_ignore_bounded_cancellation(monkeypatch):
    monkeypatch.setattr(backend, "_CLEANUP_TIMEOUT_SECONDS", 0.01)

    async def stubborn() -> None:
        while True:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                continue

    async def factory() -> str:
        asyncio.create_task(stubborn())
        return "ok"

    with pytest.warns(RuntimeWarning, match="remained pending"):
        assert backend._run_async(factory) == "ok"


def test_timed_out_stubborn_operation_is_owned_by_loop_shutdown(monkeypatch):
    monkeypatch.setattr(backend, "_CLEANUP_TIMEOUT_SECONDS", 0.01)
    cancellations = 0

    async def stubborn() -> None:
        nonlocal cancellations
        while True:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancellations += 1

    async def run() -> None:
        with pytest.warns(RuntimeWarning, match="operation remained pending"):
            with pytest.raises(backend.CopilotSdkCleanupError):
                await backend._run_bounded(stubborn(), timeout=0)

    with pytest.warns(RuntimeWarning, match="tasks remained pending"):
        backend._run_async(run)
    assert cancellations >= 2


def test_run_async_closes_loop_when_shutdown_fails(monkeypatch):
    created: list[asyncio.AbstractEventLoop] = []
    real_new_event_loop = asyncio.new_event_loop

    def new_event_loop() -> asyncio.AbstractEventLoop:
        loop = real_new_event_loop()
        created.append(loop)
        return loop

    def fail_shutdown(
        _executor: backend._DaemonThreadPoolExecutor, _timeout: float
    ) -> bool:
        raise RuntimeError("shutdown failed")

    monkeypatch.setattr(asyncio, "new_event_loop", new_event_loop)
    monkeypatch.setattr(
        backend._DaemonThreadPoolExecutor,
        "shutdown_bounded",
        fail_shutdown,
    )

    with pytest.raises(RuntimeError, match="shutdown failed"):
        backend._run_async(lambda: asyncio.sleep(0, result="ok"))
    assert len(created) == 1
    assert created[0].is_closed()


def test_run_async_cancels_tasks_spawned_during_shutdown():
    state = {"child_started": False, "child_finished": False}

    async def child() -> None:
        state["child_started"] = True
        try:
            await asyncio.Event().wait()
        finally:
            state["child_finished"] = True

    async def parent() -> None:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            asyncio.create_task(child())
            await asyncio.sleep(0)
            raise

    async def factory() -> str:
        asyncio.create_task(parent())
        return "ok"

    with warnings.catch_warnings():
        warnings.filterwarnings("error", category=RuntimeWarning)
        assert backend._run_async(factory) == "ok"
    assert state == {"child_started": True, "child_finished": True}


def test_run_async_drains_default_executor_before_returning():
    state = {"finished": False}

    def work() -> None:
        time.sleep(0.02)
        state["finished"] = True

    async def factory() -> str:
        asyncio.get_running_loop().run_in_executor(None, work)
        return "ok"

    assert backend._run_async(factory) == "ok"
    assert state["finished"] is True


def test_run_async_bounds_default_executor_shutdown(monkeypatch):
    monkeypatch.setattr(backend, "_CLEANUP_TIMEOUT_SECONDS", 0.01)
    started = threading.Event()
    release = threading.Event()

    state = {"daemon": False}

    def work() -> None:
        state["daemon"] = threading.current_thread().daemon
        started.set()
        release.wait()

    async def factory() -> str:
        asyncio.get_running_loop().run_in_executor(None, work)
        while not started.is_set():
            await asyncio.sleep(0)
        return "ok"

    try:
        with pytest.warns(RuntimeWarning, match="default executor"):
            assert backend._run_async(factory) == "ok"
        assert state["daemon"] is True
    finally:
        release.set()


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


def test_cleanup_timeout_force_stops_runtime(monkeypatch):
    monkeypatch.setattr(backend, "_CLEANUP_TIMEOUT_SECONDS", 0.01)
    state = _install_fake_copilot(monkeypatch, disconnect_wait=True)
    with pytest.warns(RuntimeWarning, match="cleanup did not finish cleanly"):
        assert _call()["content"] == _GRAPH_JSON
    assert state["disconnects"] == 1
    assert state["force_stops"] == 1
    assert state["stops"] == 0


def test_session_created_during_timeout_is_tracked_for_cleanup(monkeypatch):
    monkeypatch.setattr(backend, "_STARTUP_TIMEOUT_SECONDS", 0.01)
    release = asyncio.Event()
    state = {"disconnects": 0, "stops": 0}

    class Session:
        async def disconnect(self) -> None:
            state["disconnects"] += 1

    class Client:
        async def start(self) -> None:
            return None

        async def create_session(self, **_kwargs: Any) -> Session:
            try:
                await release.wait()
            except asyncio.CancelledError:
                release.set()
            return Session()

        async def stop(self) -> None:
            state["stops"] += 1

    with pytest.raises(backend.CopilotSdkTimeoutError):
        backend._run_async(
            lambda: backend._call_once(
                client_type=lambda **_kwargs: Client(),
                prompt="source",
                system_prompt="system",
                model=None,
                reasoning_effort=None,
                context_tier=None,
                timeout_seconds=0.1,
                attachments=[],
            )
        )
    assert state == {"disconnects": 1, "stops": 1}


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
    assert state["stops"] + state["force_stops"] == 1
    workspace = Path(state["clients"][0].options["working_directory"])
    assert not workspace.exists()


def test_cleanup_cancellation_replaces_a_primary_request_failure(monkeypatch):
    state = _install_fake_copilot(
        monkeypatch,
        send_error=RuntimeError("SECRET_PRIMARY"),
        disconnect_error=asyncio.CancelledError(),
    )
    with pytest.raises(asyncio.CancelledError):
        _call()
    assert state["disconnects"] == state["stops"] == 1
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
                max_output_tokens=None,
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


def test_run_async_never_changes_the_callers_event_loop_policy_state():
    original = asyncio.new_event_loop()
    asyncio.set_event_loop(original)
    caller_thread = threading.get_ident()

    async def identify_thread() -> int:
        return threading.get_ident()

    try:
        worker_thread = backend._run_async(identify_thread)
        assert worker_thread != caller_thread
        assert asyncio.get_event_loop() is original
    finally:
        asyncio.set_event_loop(None)
        original.close()


def test_run_bounded_tracks_abort_task_that_ignores_cancellation(monkeypatch):
    monkeypatch.setattr(backend, "_CLEANUP_TIMEOUT_SECONDS", 0.01)

    async def stubborn() -> None:
        while True:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                continue

    async def run() -> None:
        with pytest.warns(RuntimeWarning, match="remained pending"):
            with pytest.raises(backend.CopilotSdkCleanupError):
                await backend._run_bounded(
                    asyncio.Event().wait(), timeout=0, abort=stubborn
                )

    with pytest.warns(RuntimeWarning, match="tasks remained pending"):
        backend._run_async(run)


def test_daemon_executor_serializes_submit_with_shutdown():
    executor = backend._DaemonThreadPoolExecutor(
        max_workers=1, thread_name_prefix="graphify-test"
    )
    first_started = threading.Event()
    release_first = threading.Event()

    def first() -> str:
        first_started.set()
        release_first.wait()
        return "first"

    first_future = executor.submit(first)
    assert first_started.wait(timeout=1)
    accepted: list[Any] = []
    rejected: list[BaseException] = []

    def submit_second() -> None:
        try:
            accepted.append(executor.submit(lambda: "second"))
        except BaseException as error:
            rejected.append(error)

    submitter = threading.Thread(target=submit_second)
    submitter.start()
    submitter.join(timeout=1)
    executor.shutdown(wait=False)
    release_first.set()

    assert first_future.result(timeout=1) == "first"
    assert not rejected
    assert accepted[0].result(timeout=1) == "second"
    assert executor.shutdown_bounded(1) is True


def test_daemon_executor_starts_fixed_workers_before_shutdown():
    executor = backend._DaemonThreadPoolExecutor(
        max_workers=2, thread_name_prefix="graphify-eager-test"
    )
    assert len(executor._daemon_threads) == 2
    assert all(worker.is_alive() for worker in executor._daemon_threads)
    assert executor.shutdown_bounded(1) is True
    assert not any(worker.is_alive() for worker in executor._daemon_threads)


def test_daemon_executor_cancels_pending_work_without_losing_stop_marker():
    executor = backend._DaemonThreadPoolExecutor(
        max_workers=1, thread_name_prefix="graphify-cancel-test"
    )
    started = threading.Event()
    release = threading.Event()

    def running() -> str:
        started.set()
        release.wait()
        return "done"

    running_future = executor.submit(running)
    assert started.wait(timeout=1)
    pending = [executor.submit(lambda: "must not run") for _ in range(2)]

    executor.shutdown(wait=False, cancel_futures=True)
    assert all(future.cancelled() for future in pending)
    release.set()

    assert running_future.result(timeout=1) == "done"
    assert executor.shutdown_bounded(1) is True


def test_daemon_executor_cancel_callback_can_reenter_executor():
    executor = backend._DaemonThreadPoolExecutor(
        max_workers=1, thread_name_prefix="graphify-callback-test"
    )
    started = threading.Event()
    release = threading.Event()

    def running() -> None:
        started.set()
        release.wait()

    executor.submit(running)
    assert started.wait(timeout=1)
    pending = executor.submit(lambda: None)
    callback_finished = threading.Event()

    def reenter(_future) -> None:
        with pytest.raises(RuntimeError, match="after shutdown"):
            executor.submit(lambda: None)
        callback_finished.set()

    pending.add_done_callback(reenter)
    shutdown = threading.Thread(
        target=executor.shutdown,
        kwargs={"wait": False, "cancel_futures": True},
        daemon=True,
    )
    shutdown.start()
    shutdown.join(timeout=1)

    assert not shutdown.is_alive()
    assert callback_finished.wait(timeout=1)
    release.set()
    assert executor.shutdown_bounded(1) is True


def test_daemon_executor_shutdown_bounded_guarantees_current_worker_exit():
    executor = backend._DaemonThreadPoolExecutor(
        max_workers=1, thread_name_prefix="graphify-test"
    )
    result = executor.submit(lambda: executor.shutdown_bounded(0.1))
    assert result.result(timeout=1) is True
    assert executor.shutdown_bounded(1) is True


def test_concurrent_worker_shutdown_does_not_join_peer_workers():
    executor = backend._DaemonThreadPoolExecutor(
        max_workers=2, thread_name_prefix="graphify-peer-shutdown-test"
    )
    ready = threading.Barrier(2)

    def stop_from_worker() -> str:
        ready.wait(timeout=1)
        executor.shutdown(wait=True)
        return "stopped"

    futures = [executor.submit(stop_from_worker) for _ in range(2)]
    assert [future.result(timeout=1) for future in futures] == ["stopped", "stopped"]
    assert executor.shutdown_bounded(1) is True


def test_concurrent_worker_bounded_shutdown_does_not_join_peer_workers():
    executor = backend._DaemonThreadPoolExecutor(
        max_workers=2, thread_name_prefix="graphify-peer-bounded-test"
    )
    ready = threading.Barrier(2)

    def stop_from_worker() -> bool:
        ready.wait(timeout=1)
        return executor.shutdown_bounded(1)

    futures = [executor.submit(stop_from_worker) for _ in range(2)]
    assert [future.result(timeout=1) for future in futures] == [True, True]
    assert executor.shutdown_bounded(1) is True


def test_daemon_executor_rejects_submit_after_shutdown_snapshot():
    executor = backend._DaemonThreadPoolExecutor(
        max_workers=1, thread_name_prefix="graphify-test"
    )
    executor.shutdown(wait=False)
    with pytest.raises(RuntimeError, match="after shutdown"):
        executor.submit(lambda: None)
    assert executor.shutdown_bounded(1) is True


def test_max_output_tokens_use_official_model_capabilities(monkeypatch):
    state = _install_fake_copilot(monkeypatch)
    assert _call(max_output_tokens=1234)["content"] == _GRAPH_JSON
    capabilities = state["sessions"][0].options["model_capabilities"]
    assert capabilities.limits.max_output_tokens == 1234


@pytest.mark.parametrize("value", [0, -1, True, 1.5, "10"])
def test_max_output_tokens_must_be_a_positive_integer(value):
    with pytest.raises(ValueError, match="positive integer"):
        _call(max_output_tokens=value)


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


def test_extraction_wrapper_forwards_max_output_tokens(monkeypatch):
    captured: dict[str, Any] = {}

    def fake_call(*_args: Any, **kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"content": _GRAPH_JSON}

    monkeypatch.setattr(backend, "call_copilot_sdk", fake_call)
    llm._call_copilot_sdk("source", max_tokens=4321)
    assert captured["max_output_tokens"] == 4321


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
