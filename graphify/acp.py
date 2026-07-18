"""Small ACP client used by Graphify's provider-managed semantic backend.

The client deliberately speaks ACP through the official Python SDK.  The
adapter command is supplied by the host (normally Infernix's ``codex-acp``
wrapper), so Graphify does not need to know which subscription or agent
implementation is behind it.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
from collections.abc import Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AcpResult:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = "acp"
    stop_reason: str = "end_turn"


def _json_object(value: str, variable: str) -> dict[str, Any]:
    if not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{variable} must contain a JSON object: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"{variable} must contain a JSON object")
    return parsed


def _config_options(response: Any) -> set[str]:
    return {
        str(getattr(option, "id", ""))
        for option in (getattr(response, "config_options", None) or [])
        if getattr(option, "id", None)
    }


def _session_modes(response: Any) -> set[str]:
    modes = getattr(response, "modes", None)
    return {
        str(getattr(mode, "id", ""))
        for mode in (getattr(modes, "available_modes", None) or [])
        if getattr(mode, "id", None)
    }


class _GraphifyClient:
    def __init__(self) -> None:
        self.messages: list[str] = []
        self.usage: Any = None

    async def request_permission(self, options: list[Any], session_id: str, tool_call: Any, **kwargs: Any) -> Any:
        from acp.schema import DeniedOutcome, RequestPermissionResponse

        # ACP agents may request a tool even when the session is configured as
        # read-only.  Graphify is a pure extractor, so all such requests are
        # denied rather than delegated to a host callback.
        return RequestPermissionResponse(outcome=DeniedOutcome(outcome="cancelled"))

    async def session_update(self, session_id: str, update: Any, **kwargs: Any) -> None:
        from acp.schema import AgentMessageChunk, UsageUpdate

        if isinstance(update, AgentMessageChunk):
            content = update.content
            if getattr(content, "type", None) == "text":
                self.messages.append(content.text)
        elif isinstance(update, UsageUpdate):
            self.usage = update


async def _run_acp(
    prompt: str,
    *,
    command: str,
    args: list[str],
    config: Mapping[str, Any],
    model: str,
    images: list[Any],
    timeout: float,
    cwd: Path,
) -> AcpResult:
    try:
        from acp import PROTOCOL_VERSION, image_block, spawn_agent_process, text_block
        from acp.schema import ClientCapabilities, Implementation
    except ImportError as exc:
        raise ImportError(
            "ACP extraction requires graphifyy's `acp` extra. "
            "Install graphifyy[acp] or use the Nix acp package."
        ) from exc

    resolved_command = command.strip()
    if not resolved_command:
        raise RuntimeError(
            "No ACP adapter command configured. Set GRAPHIFY_ACP_BIN or install an ACP provider."
        )
    if os.path.sep not in resolved_command and shutil.which(resolved_command) is None:
        raise RuntimeError(
            f"ACP adapter {resolved_command!r} was not found on PATH. "
            "Set GRAPHIFY_ACP_BIN to the provider command."
        )

    environment = os.environ.copy()
    environment.setdefault("NO_BROWSER", "1")
    client = _GraphifyClient()
    async with spawn_agent_process(
        client,
        resolved_command,
        *args,
        env=environment,
        cwd=cwd,
    ) as (connection, _process):
        await asyncio.wait_for(
            connection.initialize(
                protocol_version=PROTOCOL_VERSION,
                client_capabilities=ClientCapabilities(),
                client_info=Implementation(name="graphify", version="0.9.18"),
            ),
            timeout=timeout,
        )
        session = await asyncio.wait_for(
            connection.new_session(cwd=str(cwd), mcp_servers=[]),
            timeout=timeout,
        )
        session_id = session.session_id
        advertised = _config_options(session)
        requested = dict(config)

        # ACP v1 exposes provider settings after session/new.  Only send
        # settings the agent advertises; this keeps the client generic across
        # adapters while avoiding the legacy adapter-specific `-c` flags.
        if model and "model" in advertised:
            await asyncio.wait_for(
                connection.set_config_option("model", session_id, model), timeout=timeout
            )
        elif model and getattr(session, "models", None) is not None:
            await asyncio.wait_for(connection.set_session_model(model, session_id), timeout=timeout)

        for option, value in requested.items():
            if option in advertised:
                await asyncio.wait_for(
                    connection.set_config_option(option, session_id, value), timeout=timeout
                )

        if "mode" not in advertised:
            modes = _session_modes(session)
            if "read-only" in modes:
                await asyncio.wait_for(connection.set_session_mode("read-only", session_id), timeout=timeout)

        content: list[Any] = [text_block(prompt)]
        for image in images:
            if getattr(image, "raw", None):
                content.append(image_block(image.b64, image.media_type, uri=str(image.path)))
        response = await asyncio.wait_for(connection.prompt(session_id, content), timeout=timeout)

        usage = getattr(response, "usage", None) or client.usage
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        stop_reason = str(getattr(response, "stop_reason", "end_turn"))
        return AcpResult(
            text="".join(client.messages),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=model or "acp",
            stop_reason=stop_reason,
        )


def _run_in_thread(coro: Any) -> Any:
    """Run ACP from sync code even when the caller already owns an event loop."""
    result: Future[Any] = Future()

    def runner() -> None:
        try:
            result.set_result(asyncio.run(coro))
        except BaseException as exc:  # propagate the original exception
            result.set_exception(exc)

    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="graphify-acp") as pool:
        pool.submit(runner).result()
    return result.result()


def run_acp(
    prompt: str,
    *,
    model: str | None = None,
    images: list[Any] | None = None,
    max_tokens: int = 8192,
    extraction: bool = False,
    deep_mode: bool = False,
) -> AcpResult:
    """Run one isolated, read-only ACP prompt and collect its text/usage."""
    command = os.environ.get("GRAPHIFY_ACP_BIN", "").strip() or "codex-acp"
    try:
        args_value = json.loads(os.environ.get("GRAPHIFY_ACP_ARGS_JSON", "[]"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"GRAPHIFY_ACP_ARGS_JSON must contain a JSON array: {exc}") from exc
    if not isinstance(args_value, list) or not all(isinstance(item, str) for item in args_value):
        raise ValueError("GRAPHIFY_ACP_ARGS_JSON must contain a JSON array of strings")

    selected_model = (model or os.environ.get("GRAPHIFY_ACP_MODEL", "").strip()).strip()
    config = _json_object(os.environ.get("GRAPHIFY_ACP_CONFIG_JSON", ""), "GRAPHIFY_ACP_CONFIG_JSON")
    config.setdefault("mode", "read-only")
    if os.environ.get("GRAPHIFY_ACP_REASONING_EFFORT", "").strip():
        config.setdefault("reasoning_effort", os.environ["GRAPHIFY_ACP_REASONING_EFFORT"].strip())

    message = prompt
    if extraction:
        from graphify.llm import _extraction_system

        message = (
            _extraction_system(deep=deep_mode)
            + "\n\n---\nNow extract the knowledge graph from the following source file(s) "
            + "and output ONLY the JSON object described above. No prose, no preamble, no markdown fences. "
            + f"Keep the response within roughly {max_tokens} output tokens.\n\n"
            + prompt
        )

    timeout = float(os.environ.get("GRAPHIFY_API_TIMEOUT", "600") or "600")
    if timeout <= 0:
        timeout = 600.0
    with tempfile.TemporaryDirectory(prefix="graphify-acp-") as working_directory:
        coro = _run_acp(
            message,
            command=command,
            args=args_value,
            config=config,
            model=selected_model,
            images=images or [],
            timeout=timeout,
            cwd=Path(working_directory),
        )
        try:
            import asyncio as _asyncio

            _asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        return _run_in_thread(coro)
