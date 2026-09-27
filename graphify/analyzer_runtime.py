"""Bounded, shell-free process execution for optional semantic analyzers."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import os
from pathlib import Path
import signal
import subprocess
import threading
import time
from typing import BinaryIO, Mapping, Protocol


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
    stdout_limit_exceeded: bool = False
    stderr_limit_exceeded: bool = False
    cleanup_error: str = ""


class _BoundedPipeReader:
    """Drain one process pipe while retaining no more than its byte budget."""

    _CHUNK_BYTES = 64 * 1024

    def __init__(
        self,
        stream: BinaryIO,
        byte_limit: int,
        *,
        drain_after_limit: bool = False,
    ) -> None:
        self._stream = stream
        self._byte_limit = byte_limit
        self._drain_after_limit = drain_after_limit
        self._buffer = bytearray()
        self._thread = threading.Thread(target=self._read, daemon=True)
        self.limit_exceeded = False
        self.error = ""

    @property
    def data(self) -> bytes:
        return bytes(self._buffer)

    def start(self) -> None:
        self._thread.start()

    def join(self, timeout: float) -> bool:
        self._thread.join(timeout)
        return not self._thread.is_alive()

    def _read(self) -> None:
        try:
            while True:
                remaining = self._byte_limit - len(self._buffer)
                # Reading one byte beyond the budget distinguishes an exact-size
                # stream from overflow without retaining the excess byte.
                read_size = (
                    self._CHUNK_BYTES
                    if self.limit_exceeded
                    else min(self._CHUNK_BYTES, remaining + 1)
                )
                chunk = self._stream.read(read_size)
                if not chunk:
                    return
                if remaining and not self.limit_exceeded:
                    self._buffer.extend(chunk[:remaining])
                if not self.limit_exceeded and len(chunk) > remaining:
                    self.limit_exceeded = True
                    if not self._drain_after_limit:
                        return
        except (OSError, ValueError) as exc:
            self.error = f"{type(exc).__name__}: {exc}"
        finally:
            try:
                self._stream.close()
            except OSError:
                pass


class _ProcessTree(Protocol):
    def terminate(self) -> None: ...


class _PosixProcessTree:
    """Own a process group created by ``start_new_session=True``."""

    def __init__(self, process: subprocess.Popen) -> None:
        self._pid = process.pid

    def terminate(self) -> None:
        try:
            os.killpg(self._pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


class _WindowsJobApiContract(Protocol):
    def create_kill_on_close_job(self) -> int: ...

    def assign_process(self, job_handle: int, process_handle: int) -> None: ...

    def close_handle(self, job_handle: int) -> None: ...


class _WindowsJobApi:
    """Minimal ctypes wrapper for a kill-on-close Windows Job Object."""

    _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
    _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000

    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes

        class BasicLimitInformation(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class IoCounters(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", ctypes.c_uint64),
                ("WriteOperationCount", ctypes.c_uint64),
                ("OtherOperationCount", ctypes.c_uint64),
                ("ReadTransferCount", ctypes.c_uint64),
                ("WriteTransferCount", ctypes.c_uint64),
                ("OtherTransferCount", ctypes.c_uint64),
            ]

        class ExtendedLimitInformation(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", BasicLimitInformation),
                ("IoInfo", IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        self._ctypes = ctypes
        self._information_type = ExtendedLimitInformation
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        # ctypes otherwise assumes 32-bit integers for arguments and return
        # values, which truncates kernel handles in a 64-bit Python process.
        self._kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self._kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        self._kernel32.SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        self._kernel32.SetInformationJobObject.restype = wintypes.BOOL
        self._kernel32.AssignProcessToJobObject.argtypes = [
            wintypes.HANDLE,
            wintypes.HANDLE,
        ]
        self._kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        self._kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self._kernel32.CloseHandle.restype = wintypes.BOOL

    def create_kill_on_close_job(self) -> int:
        job = self._kernel32.CreateJobObjectW(None, None)
        if not job:
            raise self._ctypes.WinError(self._ctypes.get_last_error())
        information = self._information_type()
        information.BasicLimitInformation.LimitFlags = (
            self._JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        )
        configured = self._kernel32.SetInformationJobObject(
            job,
            self._JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            self._ctypes.byref(information),
            self._ctypes.sizeof(information),
        )
        if not configured:
            error = self._ctypes.WinError(self._ctypes.get_last_error())
            self._kernel32.CloseHandle(job)
            raise error
        return int(job)

    def assign_process(self, job_handle: int, process_handle: int) -> None:
        if not self._kernel32.AssignProcessToJobObject(job_handle, process_handle):
            raise self._ctypes.WinError(self._ctypes.get_last_error())

    def close_handle(self, job_handle: int) -> None:
        if not self._kernel32.CloseHandle(job_handle):
            raise self._ctypes.WinError(self._ctypes.get_last_error())


class _WindowsProcessTree:
    """Own every analyzer descendant through a kill-on-close Job Object."""

    def __init__(
        self,
        process: object,
        *,
        api: _WindowsJobApiContract | None = None,
    ) -> None:
        self._api = api or _WindowsJobApi()
        self._job_handle = self._api.create_kill_on_close_job()
        try:
            process_handle = int(getattr(process, "_handle"))
            self._api.assign_process(self._job_handle, process_handle)
        except Exception:
            self._api.close_handle(self._job_handle)
            self._job_handle = 0
            raise

    def terminate(self) -> None:
        if self._job_handle:
            handle, self._job_handle = self._job_handle, 0
            # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE terminates the full tree even
            # when the direct analyzer has already exited.
            self._api.close_handle(handle)


class AnalyzerRuntime:
    """Execute an already-selected analyzer under a common safety policy.

    This boundary deliberately does not claim to be an operating-system
    sandbox. It prevents shell interpretation, credential inheritance,
    unbounded pipe growth, and lingering process trees. Callers still
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
        # Pipes provide kernel backpressure; each reader retains only its byte
        # budget. Oversized stdout closes promptly, while stderr continues to
        # drain without retaining excess bytes, so no disk file can grow.
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
        try:
            process_tree = self._process_tree(process)
        except Exception:
            try:
                process.kill()
            except OSError:
                pass
            try:
                process.wait(timeout=1.0)
            except (OSError, subprocess.TimeoutExpired):
                pass
            process.stdout.close()
            process.stderr.close()
            raise

        stdout_reader = _BoundedPipeReader(process.stdout, request.max_stdout_bytes)
        # Discard excess diagnostics while continuing to drain stderr. Closing
        # that pipe early could make a compiler abort before its valid stdout
        # payload is complete.
        stderr_reader = _BoundedPipeReader(
            process.stderr,
            request.max_stderr_bytes,
            drain_after_limit=True,
        )
        stdout_reader.start()
        stderr_reader.start()

        deadline = time.monotonic() + request.timeout_seconds
        timed_out = False
        cleanup_error = ""
        while True:
            # An oversized AST can never be valid JSON, so stop work promptly.
            # Oversized stderr is safe to truncate while stdout continues.
            if stdout_reader.limit_exceeded:
                cleanup_error = self._terminate_tree(process_tree, process)
                break
            if process.poll() is not None:
                cleanup_error = self._terminate_tree(process_tree, process)
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                cleanup_error = self._terminate_tree(process_tree, process)
                break
            time.sleep(min(0.01, remaining))

        returncode, wait_error = self._bounded_wait(process)
        cleanup_error = self._combine_errors(cleanup_error, wait_error)
        for name, reader in (("stdout", stdout_reader), ("stderr", stderr_reader)):
            if not reader.join(0.5):
                cleanup_error = self._combine_errors(
                    cleanup_error,
                    f"{name} capture did not close after process-tree cleanup",
                )
            elif reader.error:
                cleanup_error = self._combine_errors(
                    cleanup_error,
                    f"{name} capture failed: {reader.error}",
                )

        stdout_exceeded = stdout_reader.limit_exceeded
        stderr_exceeded = stderr_reader.limit_exceeded
        return AnalyzerProcessResult(
            returncode=returncode,
            stdout=stdout_reader.data,
            stderr=stderr_reader.data,
            timed_out=timed_out,
            output_limit_exceeded=stdout_exceeded or stderr_exceeded,
            stdout_limit_exceeded=stdout_exceeded,
            stderr_limit_exceeded=stderr_exceeded,
            cleanup_error=cleanup_error,
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
        # NaN never satisfies an ordered comparison and infinity never reaches a
        # deadline. Reject both, plus bool/string lookalikes, before spawning.
        if (
            isinstance(request.timeout_seconds, bool)
            or not isinstance(request.timeout_seconds, (int, float))
            or not math.isfinite(request.timeout_seconds)
            or request.timeout_seconds <= 0
        ):
            raise ValueError("analyzer timeout must be a finite positive number")
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
    def _process_tree(process: subprocess.Popen) -> _ProcessTree:
        if os.name == "nt":
            return _WindowsProcessTree(process)
        return _PosixProcessTree(process)

    @staticmethod
    def _terminate_tree(
        process_tree: _ProcessTree,
        process: subprocess.Popen,
    ) -> str:
        try:
            process_tree.terminate()
            return ""
        except OSError as exc:
            error = f"{type(exc).__name__}: {exc}"
            # A denied tree operation must not leave the direct analyzer able to
            # block this runtime indefinitely. Descendant cleanup is reported.
            try:
                if process.poll() is None:
                    process.kill()
            except OSError as kill_exc:
                error = AnalyzerRuntime._combine_errors(
                    error,
                    f"direct process cleanup failed: {type(kill_exc).__name__}: {kill_exc}",
                )
            return error

    @staticmethod
    def _bounded_wait(process: subprocess.Popen) -> tuple[int, str]:
        try:
            return process.wait(timeout=1.0), ""
        except subprocess.TimeoutExpired:
            return -1, "direct analyzer did not exit after cleanup"

    @staticmethod
    def _combine_errors(first: str, second: str) -> str:
        if not first:
            return second
        if not second:
            return first
        return f"{first}; {second}"
