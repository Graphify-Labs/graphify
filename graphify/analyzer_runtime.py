"""Bounded, shell-free process execution for optional semantic analyzers."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import signal
import subprocess
import threading
import time
from typing import Mapping


@dataclass(frozen=True)
class AnalyzerProcessRequest:
    """Validated process inputs and resource limits for one analyzer run."""

    command: tuple[str, ...]
    cwd: Path
    timeout_seconds: float = 30.0
    max_stdout_bytes: int = 128 * 1024 * 1024
    max_stderr_bytes: int = 32 * 1024
    environment: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class AnalyzerProcessResult:
    """Captured process result with explicit timeout and truncation states."""

    returncode: int
    stdout: bytes
    stderr: bytes
    timed_out: bool = False
    output_limit_exceeded: bool = False


class AnalyzerRuntime:
    """Execute an already-selected analyzer under a common safety policy.

    This boundary deliberately does not claim to be an operating-system
    sandbox. It prevents shell interpretation, credential inheritance,
    unbounded pipe growth, and lingering POSIX process trees. Callers still
    must use fixed analyzer commands and treat repository configuration as
    untrusted input.
    """

    _INHERITED_ENV = (
        "PATH",
        "SYSTEMROOT",
        "WINDIR",
        "PATHEXT",
        "COMSPEC",
        "LANG",
        "LC_ALL",
    )

    def __init__(self, project_root: Path | str) -> None:
        self.project_root = Path(project_root).resolve()

    def run(self, request: AnalyzerProcessRequest) -> AnalyzerProcessResult:
        command, cwd = self._validate(request)
        overflow = threading.Event()
        stdout_parts: list[bytes] = []
        stderr_parts: list[bytes] = []
        # The request validator requires an absolute executable and text-only
        # argv; shell interpretation is explicitly disabled below.
        process = subprocess.Popen(  # nosec B603
            command,
            cwd=cwd,
            env=self._environment(request.environment),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            shell=False,
            close_fds=True,
            start_new_session=os.name != "nt",
            creationflags=(
                subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
                if os.name == "nt"
                else 0
            ),
        )
        assert process.stdout is not None and process.stderr is not None
        readers = (
            self._reader(process.stdout, request.max_stdout_bytes, overflow, stdout_parts),
            self._reader(process.stderr, request.max_stderr_bytes, overflow, stderr_parts),
        )
        for reader in readers:
            reader.start()

        deadline = time.monotonic() + request.timeout_seconds
        timed_out = False
        while process.poll() is None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                self._kill_process_tree(process)
                break
            if overflow.wait(min(0.05, remaining)):
                self._kill_process_tree(process)
                break

        returncode = process.wait()
        for reader in readers:
            reader.join(timeout=2)
        process.stdout.close()
        process.stderr.close()
        return AnalyzerProcessResult(
            returncode=returncode,
            stdout=stdout_parts[0] if stdout_parts else b"",
            stderr=stderr_parts[0] if stderr_parts else b"",
            timed_out=timed_out,
            output_limit_exceeded=overflow.is_set(),
        )

    def _validate(self, request: AnalyzerProcessRequest) -> tuple[tuple[str, ...], Path]:
        if not request.command or not all(
            isinstance(argument, str) and argument and "\0" not in argument
            for argument in request.command
        ):
            raise ValueError("analyzer command must contain non-empty text arguments")
        executable = Path(request.command[0])
        if not executable.is_absolute():
            raise ValueError("analyzer executable must be an absolute path")
        cwd = Path(request.cwd).resolve()
        try:
            cwd.relative_to(self.project_root)
        except ValueError as exc:
            raise ValueError("working directory escapes project root") from exc
        if not cwd.is_dir():
            raise ValueError("analyzer working directory does not exist")
        if request.timeout_seconds <= 0:
            raise ValueError("analyzer timeout must be positive")
        if request.max_stdout_bytes < 0 or request.max_stderr_bytes < 0:
            raise ValueError("analyzer output limits cannot be negative")
        return request.command, cwd

    @classmethod
    def _environment(cls, additions: Mapping[str, str]) -> dict[str, str]:
        environment = {
            name: os.environ[name]
            for name in cls._INHERITED_ENV
            if name in os.environ and name != "PATH"
        }
        # A repository can influence the parent PATH (for example through a
        # development shell). Analyzer executables are absolute, and child-tool
        # lookup uses the platform's trusted default rather than that inherited
        # repository-controlled search order.
        environment["PATH"] = os.defpath
        for name, value in additions.items():
            if not isinstance(name, str) or not name or "=" in name or "\0" in name:
                raise ValueError("invalid analyzer environment name")
            if not isinstance(value, str) or "\0" in value:
                raise ValueError("invalid analyzer environment value")
            environment[name] = value
        return environment

    @staticmethod
    def _reader(
        stream: object,
        byte_limit: int,
        overflow: threading.Event,
        destination: list[bytes],
    ) -> threading.Thread:
        def read_stream() -> None:
            retained = bytearray()
            total = 0
            read = getattr(stream, "read1", getattr(stream, "read"))
            while chunk := read(64 * 1024):
                total += len(chunk)
                if len(retained) < byte_limit:
                    retained.extend(chunk[:byte_limit - len(retained)])
                if total > byte_limit:
                    overflow.set()
            destination.append(bytes(retained))

        return threading.Thread(target=read_stream, daemon=True)

    @staticmethod
    def _kill_process_tree(process: subprocess.Popen) -> None:
        if process.poll() is not None:
            return
        try:
            if os.name != "nt":
                # start_new_session gives every analyzer an isolated process
                # group, so timeout cleanup also reaches compiler helpers.
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        except ProcessLookupError:
            pass
