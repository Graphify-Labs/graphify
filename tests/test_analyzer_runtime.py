"""Security contracts for bounded optional analyzer execution."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import tempfile
import time

import pytest

from graphify.analyzer_runtime import AnalyzerProcessRequest, AnalyzerRuntime


def _python() -> str:
    executable = shutil.which("python3") or shutil.which("python")
    assert executable is not None
    return executable


def test_runtime_uses_a_minimal_explicit_environment(tmp_path: Path):
    """Analyzer children must not inherit credentials from the Graphify process."""
    runtime = AnalyzerRuntime(tmp_path)
    request = AnalyzerProcessRequest(
        command=(
            _python(),
            "-c",
            "import os,sys;sys.stdout.write('|'.join(sorted(os.environ)))",
        ),
        cwd=tmp_path,
        timeout_seconds=5,
        max_stdout_bytes=4096,
    )

    result = runtime.run(request)

    names = set(result.stdout.decode().split("|"))
    assert "PATH" in names
    assert "HOME" not in names
    assert "AWS_SECRET_ACCESS_KEY" not in names
    assert "GITHUB_TOKEN" not in names


def test_runtime_rejects_working_directories_outside_project(tmp_path: Path):
    runtime = AnalyzerRuntime(tmp_path)
    request = AnalyzerProcessRequest(
        command=(_python(), "-c", "pass"),
        cwd=tmp_path.parent,
    )

    with pytest.raises(ValueError, match="working directory escapes project root"):
        runtime.run(request)


@pytest.mark.parametrize(
    "timeout",
    [float("nan"), float("inf"), float("-inf"), "5", None, True],
)
def test_runtime_rejects_non_finite_or_non_numeric_timeouts(
    tmp_path: Path,
    timeout: object,
):
    """Invalid deadline values must be rejected before an analyzer is spawned."""
    request = AnalyzerProcessRequest(
        command=(_python(), "-c", "raise SystemExit('must not run')"),
        cwd=tmp_path,
        timeout_seconds=timeout,  # type: ignore[arg-type]
    )

    with pytest.raises(ValueError, match="finite positive number"):
        AnalyzerRuntime(tmp_path).run(request)


def test_runtime_bounds_stdout_while_process_is_running(tmp_path: Path):
    runtime = AnalyzerRuntime(tmp_path)
    request = AnalyzerProcessRequest(
        command=(
            _python(),
            "-c",
            "import sys,time;sys.stdout.write('x'*8192);sys.stdout.flush();time.sleep(10)",
        ),
        cwd=tmp_path,
        timeout_seconds=5,
        max_stdout_bytes=1024,
    )

    result = runtime.run(request)

    assert result.output_limit_exceeded is True
    assert len(result.stdout) == 1024


def test_runtime_reports_stderr_overflow_without_discarding_stdout(tmp_path: Path):
    """A diagnostic cap must not be misreported as loss of analyzer payload."""
    script = (
        "import os\n"
        "for _ in range(128): os.write(2,b'e'*1024)\n"
        "os.write(1,b'{}')"
    )
    request = AnalyzerProcessRequest(
        command=(_python(), "-c", script),
        cwd=tmp_path,
        timeout_seconds=5,
        max_stdout_bytes=1024,
        max_stderr_bytes=128,
    )

    result = AnalyzerRuntime(tmp_path).run(request)

    assert result.returncode == 0
    assert result.stdout == b"{}"
    assert result.stderr == b"e" * 128
    assert result.stdout_limit_exceeded is False
    assert result.stderr_limit_exceeded is True
    assert result.output_limit_exceeded is True


def test_runtime_does_not_use_unbounded_temporary_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """Analyzer output must remain pipe-bounded instead of growing a disk file."""
    def reject_temporary_file(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("temporary output capture attempted")

    monkeypatch.setattr(tempfile, "TemporaryFile", reject_temporary_file)
    result = AnalyzerRuntime(tmp_path).run(AnalyzerProcessRequest(
        command=(_python(), "-c", "print('bounded', end='')"),
        cwd=tmp_path,
        timeout_seconds=5,
    ))

    assert result.stdout == b"bounded"


@pytest.mark.skipif(os.name == "nt", reason="POSIX process-group assertion")
def test_runtime_does_not_wait_for_inherited_pipes_after_parent_exits(
    tmp_path: Path,
):
    """A short-lived analyzer must not let a surviving child defeat the deadline."""
    script = (
        "import subprocess,sys;"
        "subprocess.Popen([sys.executable,'-c','import time;time.sleep(1.5)']);"
        "sys.stdout.write('ready');sys.stdout.flush()"
    )
    runtime = AnalyzerRuntime(tmp_path)
    request = AnalyzerProcessRequest(
        command=(_python(), "-c", script),
        cwd=tmp_path,
        timeout_seconds=0.2,
    )

    started = time.monotonic()
    result = runtime.run(request)
    elapsed = time.monotonic() - started

    assert elapsed < 1.0
    assert result.timed_out is False
    assert result.stdout == b"ready"


@pytest.mark.skipif(os.name == "nt", reason="POSIX process-group assertion")
def test_runtime_kills_descendants_after_timeout(tmp_path: Path):
    """Timeout cleanup must stop children, not only the analyzer parent."""
    marker = tmp_path / "child-survived"
    script = (
        "import subprocess,sys,time;"
        "subprocess.Popen([sys.executable,'-c',"
        f"\"import time,pathlib;time.sleep(1);pathlib.Path({str(marker)!r}).write_text('bad')\"]);"
        "time.sleep(10)"
    )
    runtime = AnalyzerRuntime(tmp_path)
    request = AnalyzerProcessRequest(
        command=(_python(), "-c", script),
        cwd=tmp_path,
        timeout_seconds=0.2,
    )

    result = runtime.run(request)

    assert result.timed_out is True
    # A surviving grandchild would create this marker after its parent timed out.
    time.sleep(1.2)
    assert not marker.exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX cleanup failure assertion")
def test_runtime_reports_cleanup_denial_without_escaping(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """OS cleanup denial must remain a bounded analyzer failure, not an exception."""
    def deny_cleanup(_pid: int, _signal: int) -> None:
        raise PermissionError("cleanup denied")

    monkeypatch.setattr(os, "killpg", deny_cleanup)
    result = AnalyzerRuntime(tmp_path).run(AnalyzerProcessRequest(
        command=(_python(), "-c", "import time;time.sleep(10)"),
        cwd=tmp_path,
        timeout_seconds=0.05,
    ))

    assert result.timed_out is True
    assert result.cleanup_error == "PermissionError: cleanup denied"


def test_windows_process_tree_owns_and_closes_a_kill_on_close_job():
    """Windows cleanup must own descendants rather than killing only the parent."""
    from graphify import analyzer_runtime

    events: list[tuple[str, int]] = []

    class FakeApi:
        def create_kill_on_close_job(self) -> int:
            events.append(("create", 41))
            return 41

        def assign_process(self, job_handle: int, process_handle: int) -> None:
            events.append(("assign", job_handle))
            assert process_handle == 73

        def close_handle(self, job_handle: int) -> None:
            events.append(("close", job_handle))

    class FakeProcess:
        _handle = 73

    tree = analyzer_runtime._WindowsProcessTree(FakeProcess(), api=FakeApi())
    tree.terminate()

    assert events == [("create", 41), ("assign", 41), ("close", 41)]


def test_windows_job_api_declares_pointer_sized_handle_signatures(
    monkeypatch: pytest.MonkeyPatch,
):
    """ctypes must not truncate 64-bit Windows handles through default signatures."""
    import ctypes
    from ctypes import wintypes
    from graphify import analyzer_runtime

    class FakeFunction:
        restype: object = None
        argtypes: object = None

        def __call__(self, *_args: object) -> int:
            return 1

    class FakeKernel32:
        CreateJobObjectW = FakeFunction()
        SetInformationJobObject = FakeFunction()
        AssignProcessToJobObject = FakeFunction()
        CloseHandle = FakeFunction()

    kernel32 = FakeKernel32()
    monkeypatch.setattr(ctypes, "WinDLL", lambda *_args, **_kwargs: kernel32, raising=False)

    analyzer_runtime._WindowsJobApi()

    assert kernel32.CreateJobObjectW.argtypes == [ctypes.c_void_p, wintypes.LPCWSTR]
    assert kernel32.SetInformationJobObject.argtypes[0] is wintypes.HANDLE
    assert kernel32.CloseHandle.argtypes == [wintypes.HANDLE]
