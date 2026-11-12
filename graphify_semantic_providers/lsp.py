"""Bounded, local Language Server Protocol runner.

The runner collects observable symbol/call/reference facts.  It does not store
source text, model reasoning, environment variables, or server stderr.  It uses
argv execution without a shell and constrains every source path to the selected
workspace root.
"""

from __future__ import annotations

import hashlib
import json
import os
import queue
import shutil

# The bounded LSP adapter intentionally owns a local provider process.
import subprocess  # nosec B404
import threading
import time
from pathlib import Path
from typing import Any, Protocol

from graphify.security import sanitize_metadata

from .contracts import ProviderKind, ProviderRun, ProviderSpec, ProviderStatus


MAX_MESSAGE_BYTES = 8 * 1024 * 1024
MAX_SOURCE_BYTES = 2 * 1024 * 1024
_PROVIDER_ENV_ALLOWLIST = {
    "APPDATA",
    "BUNDLE_GEMFILE",
    "CARGO_HOME",
    "COMSPEC",
    "DOTNET_ROOT",
    "GEM_HOME",
    "GEM_PATH",
    "GOMODCACHE",
    "GOPATH",
    "GOROOT",
    "HOME",
    "JAVA_HOME",
    "KOTLIN_HOME",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "LOCALAPPDATA",
    "NODE_PATH",
    "NUGET_PACKAGES",
    "PATH",
    "PATHEXT",
    "PHP_INI_SCAN_DIR",
    "PYTHONPATH",
    "RBENV_ROOT",
    "RUSTUP_HOME",
    "RUSTUP_TOOLCHAIN",
    "SHELL",
    "SYSTEMROOT",
    "TEMP",
    "TMP",
    "TMPDIR",
    "USER",
    "USERNAME",
    "VIRTUAL_ENV",
    "XDG_CACHE_HOME",
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
}


class RpcTransport(Protocol):
    notifications: list[dict[str, Any]]

    def notify(self, method: str, params: dict[str, Any]) -> None: ...

    def request(self, method: str, params: dict[str, Any], timeout: float) -> Any: ...

    def close(self, timeout: float = 2.0) -> None: ...


class StdioJsonRpc:
    """Minimal LSP JSON-RPC transport with message and time bounds."""

    def __init__(self, command: tuple[str, ...], root: Path) -> None:
        # Provider manifests are operator-trusted configuration and commands are argv-only.
        self._process = subprocess.Popen(  # nosec B603
            list(command),
            cwd=root,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            shell=False,
            env=_provider_environment(),
        )
        if self._process.stdin is None or self._process.stdout is None:
            raise RuntimeError("language server stdio was not created")
        self._stdin = self._process.stdin
        self._stdout = self._process.stdout
        self._messages: queue.Queue[dict[str, Any] | BaseException] = queue.Queue()
        self._write_lock = threading.Lock()
        self._next_id = 1
        self.notifications: list[dict[str, Any]] = []
        self._reader_thread = threading.Thread(target=self._reader, daemon=True)
        self._reader_thread.start()

    def _reader(self) -> None:
        try:
            while True:
                headers: dict[str, str] = {}
                while True:
                    raw = self._stdout.readline()
                    if not raw:
                        return
                    if raw in {b"\r\n", b"\n"}:
                        break
                    text = raw.decode("ascii", errors="strict").strip()
                    if ":" not in text:
                        raise RuntimeError("malformed LSP header")
                    key, value = text.split(":", 1)
                    headers[key.lower().strip()] = value.strip()
                length = int(headers.get("content-length", "0"))
                if length <= 0 or length > MAX_MESSAGE_BYTES:
                    raise RuntimeError("invalid or oversized LSP message")
                body = self._stdout.read(length)
                if len(body) != length:
                    raise RuntimeError("truncated LSP message")
                message = json.loads(body)
                if isinstance(message, dict):
                    self._messages.put(message)
        except BaseException as exc:  # noqa: BLE001 - delivered to waiting request.
            self._messages.put(exc)

    def _send(self, message: dict[str, Any]) -> None:
        body = json.dumps(message, separators=(",", ":")).encode("utf-8")
        if len(body) > MAX_MESSAGE_BYTES:
            raise RuntimeError("outbound LSP message exceeds limit")
        framed = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body
        with self._write_lock:
            self._stdin.write(framed)
            self._stdin.flush()

    def notify(self, method: str, params: dict[str, Any]) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def request(self, method: str, params: dict[str, Any], timeout: float) -> Any:
        request_id = self._next_id
        self._next_id += 1
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"LSP request timed out: {method}")
            try:
                message = self._messages.get(timeout=remaining)
            except queue.Empty as exc:
                raise TimeoutError(f"LSP request timed out: {method}") from exc
            if isinstance(message, BaseException):
                raise RuntimeError("language server transport failed") from message
            if message.get("id") == request_id:
                if "error" in message:
                    error = message.get("error") or {}
                    code = error.get("code", "unknown")
                    detail = str(error.get("message", "server error")).replace("\n", " ")[:160]
                    raise RuntimeError(f"LSP request failed ({method}, code={code}): {detail}")
                return message.get("result")
            if "method" in message and "id" in message:
                self._answer_server_request(message)
            elif "method" in message:
                if len(self.notifications) < 1_000:
                    self.notifications.append(message)

    def _answer_server_request(self, message: dict[str, Any]) -> None:
        method = str(message.get("method", ""))
        if method == "workspace/configuration":
            items = (message.get("params") or {}).get("items") or []
            result: Any = [{} for _ in items] if isinstance(items, list) else []
        elif method == "workspace/workspaceFolders":
            result = []
        elif method == "workspace/applyEdit":
            result = {
                "applied": False,
                "failureReason": "semantic provider client is read-only",
            }
        elif method == "window/showDocument":
            result = {"success": False}
        else:
            result = None
        self._send({"jsonrpc": "2.0", "id": message["id"], "result": result})

    def close(self, timeout: float = 2.0) -> None:
        if self._process.poll() is None:
            try:
                self.request("shutdown", {}, timeout)
                self.notify("exit", {})
                self._process.wait(timeout=timeout)
            except (RuntimeError, TimeoutError, subprocess.TimeoutExpired):
                self._process.terminate()
                try:
                    self._process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    self._process.kill()


def resolve_command(spec: ProviderSpec) -> tuple[str, ...] | None:
    """Resolve only the executable; arguments remain immutable provider data."""

    override = os.environ.get(spec.binary_env, "").strip()
    binary = override or spec.command[0]
    resolved = shutil.which(binary) if not Path(binary).is_absolute() else binary
    if not resolved or not Path(resolved).is_file():
        return None
    # Do not resolve executable symlinks. Toolchain multiplexers such as rustup
    # select the real binary from argv[0]; resolving ``rust-analyzer`` to the
    # ``rustup`` target would start rustup with no subcommand and silently break
    # LSP startup.
    return (str(Path(resolved).absolute()), *spec.command[1:])


def discover_files(root: Path, spec: ProviderSpec, max_files: int) -> list[Path]:
    root = root.resolve()
    result: list[Path] = []
    ignored = {".git", "node_modules", "target", "dist", "build", ".venv", "vendor"}
    for candidate in sorted(root.rglob("*")):
        if len(result) >= max_files:
            break
        if not candidate.is_file() or candidate.suffix.lower() not in spec.extensions:
            continue
        relative = candidate.relative_to(root)
        if any(part in ignored for part in relative.parts):
            continue
        resolved = candidate.resolve()
        if not resolved.is_relative_to(root) or candidate.stat().st_size > MAX_SOURCE_BYTES:
            continue
        result.append(resolved)
    return result


def run_provider(
    spec: ProviderSpec,
    root: Path,
    *,
    max_files: int = 200,
    max_symbols: int = 5_000,
    max_relationship_requests: int = 500,
    request_timeout: float = 20.0,
    transport_factory: Any = StdioJsonRpc,
) -> ProviderRun:
    """Run one provider without making it a prerequisite for native Graphify."""

    root = root.resolve()
    command = resolve_command(spec)
    if command is None and transport_factory is StdioJsonRpc:
        return ProviderRun(
            provider=spec.name,
            status=ProviderStatus.UNAVAILABLE,
            reason_code="binary_not_found",
        )
    files = discover_files(root, spec, max_files)
    if not files:
        return ProviderRun(
            provider=spec.name,
            status=ProviderStatus.COMPLETED,
            reason_code="no_matching_files",
        )

    run = ProviderRun(
        provider=spec.name,
        provider_kind=ProviderKind.SEMANTIC,
        status=ProviderStatus.COMPLETED,
    )
    run.files_considered = len(files)
    transport: RpcTransport | None = None
    try:
        transport = transport_factory(command or spec.command, root)
        if transport is None:
            raise RuntimeError("provider transport was not created")
        initialize = transport.request(
            "initialize",
            {
                "processId": os.getpid(),
                "rootUri": root.as_uri(),
                "workspaceFolders": [{"uri": root.as_uri(), "name": root.name}],
                "capabilities": {
                    "workspace": {
                        "applyEdit": False,
                        "workspaceEdit": {"documentChanges": False},
                    },
                    "textDocument": {
                        "documentSymbol": {"hierarchicalDocumentSymbolSupport": True},
                        "references": {},
                        "implementation": {},
                        "callHierarchy": {},
                    },
                },
                "initializationOptions": spec.initialization_options,
            },
            request_timeout,
        )
        run.requests += 1
        if isinstance(initialize, dict):
            run.version = str(((initialize.get("serverInfo") or {}).get("version") or "unknown"))
            capabilities = initialize.get("capabilities") or {}
        else:
            capabilities = {}
        transport.notify("initialized", {})

        budget_exhausted = False
        for path in files:
            if len(run.nodes) >= max_symbols:
                budget_exhausted = True
                break
            source = path.read_text(encoding="utf-8", errors="replace")
            language_id = _language_id(path, spec)
            uri = path.as_uri()
            transport.notify(
                "textDocument/didOpen",
                {
                    "textDocument": {
                        "uri": uri,
                        "languageId": language_id,
                        "version": 1,
                        "text": source,
                    }
                },
            )
            symbols = transport.request(
                "textDocument/documentSymbol",
                {"textDocument": {"uri": uri}},
                request_timeout,
            )
            run.requests += 1
            flattened = _flatten_symbols(symbols, uri)
            remaining = max_symbols - len(run.nodes)
            if len(flattened) > remaining:
                budget_exhausted = True
            flattened = flattened[:remaining]
            _append_symbols(run, flattened, root, spec)
            run.files_processed += 1

            for symbol in flattened:
                if run.relationship_requests >= max_relationship_requests:
                    budget_exhausted = True
                    break
                position = _position(symbol)
                if capabilities.get("referencesProvider"):
                    refs = transport.request(
                        "textDocument/references",
                        {
                            "textDocument": {"uri": symbol["uri"]},
                            "position": position,
                            "context": {"includeDeclaration": False},
                        },
                        request_timeout,
                    )
                    run.requests += 1
                    run.relationship_requests += 1
                    budget_exhausted |= _append_locations(
                        run, symbol, refs, root, spec, "references", max_symbols
                    )
                if (
                    capabilities.get("implementationProvider")
                    and run.relationship_requests < max_relationship_requests
                ):
                    impls = transport.request(
                        "textDocument/implementation",
                        {"textDocument": {"uri": symbol["uri"]}, "position": position},
                        request_timeout,
                    )
                    run.requests += 1
                    run.relationship_requests += 1
                    budget_exhausted |= _append_locations(
                        run, symbol, impls, root, spec, "implemented_by", max_symbols
                    )
                if (
                    capabilities.get("callHierarchyProvider")
                    and run.relationship_requests < max_relationship_requests
                ):
                    prepared = transport.request(
                        "textDocument/prepareCallHierarchy",
                        {"textDocument": {"uri": symbol["uri"]}, "position": position},
                        request_timeout,
                    )
                    run.requests += 1
                    run.relationship_requests += 1
                    if (
                        isinstance(prepared, list)
                        and prepared
                        and run.relationship_requests < max_relationship_requests
                    ):
                        calls = transport.request(
                            "callHierarchy/outgoingCalls",
                            {"item": prepared[0]},
                            request_timeout,
                        )
                        run.requests += 1
                        run.relationship_requests += 1
                        budget_exhausted |= _append_calls(
                            run, symbol, calls, root, spec, max_symbols
                        )
                if run.relationship_requests >= max_relationship_requests:
                    budget_exhausted = True
                    break
            transport.notify("textDocument/didClose", {"textDocument": {"uri": uri}})

        if budget_exhausted:
            run.status = ProviderStatus.BUDGET_EXHAUSTED
            run.reason_code = "semantic_budget_exhausted"
        _deduplicate(run)
        return run
    except (OSError, RuntimeError, TimeoutError, ValueError) as exc:
        run.status = ProviderStatus.FAILED
        run.reason_code = type(exc).__name__.lower()
        run.warnings.append(str(exc)[:240])
        return run
    finally:
        if transport is not None:
            transport.close()


def _flatten_symbols(payload: Any, default_uri: str) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        return []
    result: list[dict[str, Any]] = []

    def walk(item: Any, parent: str | None = None) -> None:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            return
        raw_location = item.get("location")
        location: dict[str, Any] = raw_location if isinstance(raw_location, dict) else {}
        uri = str(location.get("uri") or default_uri)
        item_range = item.get("selectionRange") or item.get("range") or location.get("range") or {}
        record = {
            "name": item["name"],
            "kind": item.get("kind", 0),
            "uri": uri,
            "range": item_range,
            "detail": str(item.get("detail", ""))[:240],
            "parent_key": parent,
        }
        record["key"] = _symbol_key(record)
        result.append(record)
        children = item.get("children") or []
        if isinstance(children, list):
            for child in children:
                walk(child, record["key"])

    for value in payload:
        walk(value)
    return result


def _append_symbols(
    run: ProviderRun, symbols: list[dict[str, Any]], root: Path, spec: ProviderSpec
) -> None:
    by_key: dict[str, str] = {}
    for symbol in symbols:
        source_file = _relative_uri(symbol["uri"], root)
        if source_file is None:
            continue
        node_id = _node_id(spec.name, symbol["key"])
        by_key[symbol["key"]] = node_id
        line = _line(symbol.get("range"))
        run.nodes.append(
            {
                "id": node_id,
                "label": symbol["name"],
                "file_type": "code",
                "source_file": source_file,
                "source_location": f"L{line}" if line else "",
                "metadata": _evidence_metadata(
                    run,
                    {
                        "semantic_kind": str(symbol.get("kind", 0)),
                        "semantic_detail": symbol.get("detail", ""),
                        "semantic_language": _language_id(Path(source_file), spec),
                        "semantic_range": _source_range(symbol.get("range")),
                    },
                ),
            }
        )
    for symbol in symbols:
        parent_id = by_key.get(str(symbol.get("parent_key", "")))
        child_id = by_key.get(symbol["key"])
        if parent_id and child_id:
            source_file = _relative_uri(symbol["uri"], root) or ""
            run.edges.append(
                _edge(
                    parent_id,
                    child_id,
                    "contains",
                    run,
                    source_file,
                    f"L{_line(symbol.get('range'))}" if _line(symbol.get("range")) else "",
                )
            )


def _append_locations(
    run: ProviderRun,
    source_symbol: dict[str, Any],
    locations: Any,
    root: Path,
    spec: ProviderSpec,
    relation: str,
    max_symbols: int,
) -> bool:
    if isinstance(locations, dict):
        locations = [locations]
    if not isinstance(locations, list):
        return False
    exhausted = False
    existing_ids = {str(node.get("id", "")) for node in run.nodes}
    source_id = _node_id(spec.name, source_symbol["key"])
    for location in locations[:100]:
        if not isinstance(location, dict):
            continue
        uri = location.get("uri") or location.get("targetUri")
        source_file = _relative_uri(str(uri or ""), root)
        if source_file is None:
            continue
        location_range = location.get("range") or location.get("targetSelectionRange") or {}
        line = _line(location_range)
        target_id = _node_id(spec.name, f"file:{source_file}")
        if target_id not in existing_ids:
            if len(existing_ids) >= max_symbols:
                exhausted = True
                continue
            run.nodes.append(
                {
                    "id": target_id,
                    "label": Path(source_file).name,
                    "file_type": "code",
                    "source_file": source_file,
                    "source_location": f"L{line}" if line else "",
                    "metadata": _evidence_metadata(
                        run,
                        {
                            "semantic_kind": "file",
                            "semantic_range": _source_range(location_range),
                        },
                    ),
                }
            )
            existing_ids.add(target_id)
        run.edges.append(
            _edge(
                source_id,
                target_id,
                relation,
                run,
                source_file,
                f"L{line}" if line else "",
            )
        )
    return exhausted


def _append_calls(
    run: ProviderRun,
    source_symbol: dict[str, Any],
    calls: Any,
    root: Path,
    spec: ProviderSpec,
    max_symbols: int,
) -> bool:
    if not isinstance(calls, list):
        return False
    exhausted = False
    existing_ids = {str(node.get("id", "")) for node in run.nodes}
    source_id = _node_id(spec.name, source_symbol["key"])
    for call in calls[:100]:
        target = call.get("to") if isinstance(call, dict) else None
        if not isinstance(target, dict) or not isinstance(target.get("name"), str):
            continue
        source_file = _relative_uri(str(target.get("uri", "")), root)
        if source_file is None:
            continue
        target_symbol = {
            "name": target["name"],
            "uri": target.get("uri", ""),
            "range": target.get("selectionRange") or target.get("range") or {},
        }
        key = _symbol_key(target_symbol)
        target_id = _node_id(spec.name, key)
        line = _line(target_symbol["range"])
        if target_id not in existing_ids:
            if len(existing_ids) >= max_symbols:
                exhausted = True
                continue
            run.nodes.append(
                {
                    "id": target_id,
                    "label": target["name"],
                    "file_type": "code",
                    "source_file": source_file,
                    "source_location": f"L{line}" if line else "",
                    "metadata": _evidence_metadata(
                        run,
                        {
                            "semantic_kind": str(target.get("kind", 0)),
                            "semantic_range": _source_range(target_symbol["range"]),
                        },
                    ),
                }
            )
            existing_ids.add(target_id)
        run.edges.append(
            _edge(
                source_id,
                target_id,
                "calls",
                run,
                source_file,
                f"L{line}" if line else "",
            )
        )
    return exhausted


def _edge(
    source: str,
    target: str,
    relation: str,
    run: ProviderRun,
    source_file: str,
    source_location: str = "",
) -> dict[str, Any]:
    return {
        "source": source,
        "target": target,
        "relation": relation,
        "confidence": "EXTRACTED",
        "weight": 1.0,
        "source_file": source_file,
        "source_location": source_location,
        "context": "language_server",
        "metadata": _evidence_metadata(run),
    }


def _evidence_metadata(run: ProviderRun, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "semantic_provider": run.provider,
        "evidence_provider": run.provider,
        "evidence_provider_kind": run.provider_kind.value,
        "evidence_run_id": run.run_id,
        "evidence_timestamp": run.timestamp,
        "evidence_confidence": "EXTRACTED_SEMANTIC",
    }
    metadata.update(extra or {})
    return sanitize_metadata(metadata)


def _source_range(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    raw_start = value.get("start")
    raw_end = value.get("end")
    start: dict[str, Any] = raw_start if isinstance(raw_start, dict) else {}
    end: dict[str, Any] = raw_end if isinstance(raw_end, dict) else {}
    values = (
        start.get("line"),
        start.get("character"),
        end.get("line"),
        end.get("character"),
    )
    if any(isinstance(item, bool) or not isinstance(item, int) or item < 0 for item in values):
        return ""
    coordinates = [item for item in values if isinstance(item, int) and not isinstance(item, bool)]
    line_start, column_start, line_end, column_end = coordinates
    return f"L{line_start + 1}:C{column_start + 1}-L{line_end + 1}:C{column_end + 1}"


def _symbol_key(symbol: dict[str, Any]) -> str:
    start = (symbol.get("range") or {}).get("start") or {}
    return f"{symbol.get('uri', '')}:{start.get('line', -1)}:{start.get('character', -1)}:{symbol.get('name', '')}"


def _node_id(provider: str, key: str) -> str:
    digest = hashlib.sha256(f"{provider}:{key}".encode()).hexdigest()[:20]
    return f"semantic_{digest}"


def _position(symbol: dict[str, Any]) -> dict[str, int]:
    start = (symbol.get("range") or {}).get("start") or {}
    line = start.get("line", 0)
    character = start.get("character", 0)
    return {
        "line": line if isinstance(line, int) and not isinstance(line, bool) and line >= 0 else 0,
        "character": character
        if isinstance(character, int) and not isinstance(character, bool) and character >= 0
        else 0,
    }


def _line(value: Any) -> int:
    line = ((value or {}).get("start") or {}).get("line", -1) if isinstance(value, dict) else -1
    return line + 1 if isinstance(line, int) and not isinstance(line, bool) and line >= 0 else 0


def _relative_uri(uri: str, root: Path) -> str | None:
    if not uri.startswith("file://"):
        return None
    from urllib.parse import unquote, urlparse

    path = Path(unquote(urlparse(uri).path)).resolve()
    if not path.is_relative_to(root):
        return None
    return path.relative_to(root).as_posix()


def _language_id(path: Path, spec: ProviderSpec) -> str:
    suffix = path.suffix.lower()
    if suffix in {".js", ".jsx", ".mjs", ".cjs"}:
        return "javascriptreact" if suffix == ".jsx" else "javascript"
    if suffix in {".ts", ".tsx"}:
        return "typescriptreact" if suffix == ".tsx" else "typescript"
    return spec.languages[0]


def _deduplicate(run: ProviderRun) -> None:
    nodes: dict[str, dict[str, Any]] = {}
    for node in run.nodes:
        nodes.setdefault(str(node.get("id", "")), node)
    edges: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for edge in run.edges:
        key = (
            str(edge.get("source", "")),
            str(edge.get("target", "")),
            str(edge.get("relation", "")),
            str(edge.get("source_file", "")),
        )
        edges.setdefault(key, edge)
    run.nodes = list(nodes.values())
    run.edges = list(edges.values())


def _provider_environment() -> dict[str, str]:
    """Forward runtime configuration without copying unrelated credentials."""

    return {
        key: value for key, value in os.environ.items() if key.upper() in _PROVIDER_ENV_ALLOWLIST
    }
