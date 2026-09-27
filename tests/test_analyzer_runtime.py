"""Security contracts for bounded optional analyzer execution."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
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
