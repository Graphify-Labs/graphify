"""Bounded, shell-free process execution for optional semantic analyzers."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import signal
import subprocess
import tempfile
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
        # Temporary streams make analyzer completion independent of pipe EOF.
        # Compiler helpers may inherit stdout/stderr and outlive their parent;
        # pipe-reader threads would otherwise extend or defeat the deadline.
        with tempfile.TemporaryFile() as stdout_stream, tempfile.TemporaryFile() as stderr_stream:
            # The request validator requires an absolute executable and text-only
            # argv; shell interpretation is explicitly disabled below.
            process = subprocess.Popen(  # nosec B603
                command,
                cwd=cwd,
                env=self._environment(request.environment),
                stdout=stdout_stream,
                stderr=stderr_stream,
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
            deadline = time.monotonic() + request.timeout_seconds
            timed_out = False
            output_limit_exceeded = False
            while True:
                output_limit_exceeded = self._stream_exceeded(
                    stdout_stream, request.max_stdout_bytes
                ) or self._stream_exceeded(stderr_stream, request.max_stderr_bytes)
                if output_limit_exceeded:
                    self._kill_process_tree(process)
                    break
                if process.poll() is not None:
                    # The direct analyzer may exit before helpers that inherited
                    # its capture handles. Clean its POSIX process group before
                    # reading a bounded snapshot of the temporary streams.
                    self._kill_process_tree(process)
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    timed_out = True
                    self._kill_process_tree(process)
                    break
                time.sleep(min(0.05, remaining))

            returncode = process.wait()
            output_limit_exceeded = output_limit_exceeded or (
                self._stream_exceeded(stdout_stream, request.max_stdout_bytes)
                or self._stream_exceeded(stderr_stream, request.max_stderr_bytes)
            )
            return AnalyzerProcessResult(
                returncode=returncode,
                stdout=self._read_prefix(stdout_stream, request.max_stdout_bytes),
                stderr=self._read_prefix(stderr_stream, request.max_stderr_bytes),
                timed_out=timed_out,
                output_limit_exceeded=output_limit_exceeded,
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
    def _stream_exceeded(stream: object, byte_limit: int) -> bool:
        return os.fstat(stream.fileno()).st_size > byte_limit

    @staticmethod
    def _read_prefix(stream: object, byte_limit: int) -> bytes:
        stream.seek(0)
        return stream.read(byte_limit)

    @staticmethod
    def _kill_process_tree(process: subprocess.Popen) -> None:
        try:
            if os.name != "nt":
                # start_new_session gives every analyzer an isolated process
                # group. The group can remain alive after its leader exits, so
                # cleanup must not depend on the parent's current return code.
                os.killpg(process.pid, signal.SIGKILL)
            elif process.poll() is None:
                process.kill()
        except ProcessLookupError:
            pass
