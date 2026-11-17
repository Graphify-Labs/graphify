"""Host-side Docker build and isolated container execution."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import TextIO


HARNESS_DIR = Path(__file__).resolve().parent
DEFAULT_IMAGE = "graphify-install-sandbox-v8:local"
BUILD_TIMEOUT_SECONDS = 900
RUN_TIMEOUT_SECONDS = 7200

CONTAINER_REPO = "/mnt/graphify-repo"
CONTAINER_OUTPUT = "/sandbox-out"
CONTAINER_HOME = "/tmp/graphify-home"
CONTAINER_XDG = "/tmp/graphify-xdg"
CONTAINER_PROJECT = "/tmp/graphify-project"
CONTAINER_USER_CWD = "/tmp/graphify-user-cwd"
CONTAINER_SOURCE = "/tmp/graphify-source"

PhaseHandler = Callable[[str], None]
OutputHandler = Callable[[str, str, str], None]


def build_image_command(runtime: str, image: str) -> list[str]:
    return [runtime, "build", "--tag", image, str(HARNESS_DIR)]


def build_run_command(
    *,
    runtime: str,
    image: str,
    repo: Path,
    output: Path,
    target: str | None,
    all_targets: bool,
    scope: str,
) -> list[str]:
    if bool(target) == bool(all_targets):
        raise ValueError("select exactly one target mode")
    command = [runtime, "run", "--rm"]
    if hasattr(os, "getuid") and hasattr(os, "getgid"):
        command.extend(["--user", f"{os.getuid()}:{os.getgid()}"])
    for key, value in {
        "HOME": CONTAINER_HOME,
        "XDG_CONFIG_HOME": CONTAINER_XDG,
        "GRAPHIFY_SANDBOX_REPO": CONTAINER_REPO,
        "GRAPHIFY_SANDBOX_OUTPUT": CONTAINER_OUTPUT,
        "GRAPHIFY_SANDBOX_PROJECT": CONTAINER_PROJECT,
        "GRAPHIFY_SANDBOX_USER_CWD": CONTAINER_USER_CWD,
        "GRAPHIFY_SANDBOX_SOURCE": CONTAINER_SOURCE,
    }.items():
        command.extend(["--env", f"{key}={value}"])
    command.extend(
        [
            "--volume",
            f"{repo}:{CONTAINER_REPO}:ro",
            "--volume",
            f"{output}:{CONTAINER_OUTPUT}:rw",
            "--workdir",
            CONTAINER_PROJECT,
            image,
            "--scope",
            scope,
        ]
    )
    if all_targets:
        command.append("--all")
    else:
        command.extend(["--target", str(target)])
    return command


def _emit(
    *,
    phase: str,
    stream: str,
    text: str,
    on_output: OutputHandler | None,
) -> None:
    if on_output is not None:
        on_output(phase, stream, text)
        return
    destination = sys.stderr if stream == "stderr" else sys.stdout
    print(text, end="", file=destination, flush=True)


def _pipe_output(
    pipe: TextIO,
    *,
    phase: str,
    stream: str,
    on_output: OutputHandler | None,
) -> None:
    try:
        for line in iter(pipe.readline, ""):
            _emit(
                phase=phase,
                stream=stream,
                text=line,
                on_output=on_output,
            )
    finally:
        pipe.close()


def _stop_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def _run(
    argv: list[str],
    timeout: int,
    *,
    phase: str,
    on_output: OutputHandler | None = None,
) -> int:
    _emit(
        phase=phase,
        stream="command",
        text=f"$ {shlex.join(argv)}\n",
        on_output=on_output,
    )
    try:
        process = subprocess.Popen(
            argv,
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
    except FileNotFoundError:
        _emit(
            phase=phase,
            stream="stderr",
            text=f"error: container runtime not found: {argv[0]}\n",
            on_output=on_output,
        )
        return 127

    assert process.stdout is not None
    assert process.stderr is not None
    threads = [
        threading.Thread(
            target=_pipe_output,
            args=(process.stdout,),
            kwargs={
                "phase": phase,
                "stream": "stdout",
                "on_output": on_output,
            },
        ),
        threading.Thread(
            target=_pipe_output,
            args=(process.stderr,),
            kwargs={
                "phase": phase,
                "stream": "stderr",
                "on_output": on_output,
            },
        ),
    ]
    for thread in threads:
        thread.start()
    try:
        return process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        _emit(
            phase=phase,
            stream="stderr",
            text=(
                f"error: command timed out after {timeout} seconds: "
                f"{shlex.join(argv)}\n"
            ),
            on_output=on_output,
        )
        _stop_process(process)
        return 124
    finally:
        _stop_process(process)
        for thread in threads:
            thread.join()


def run_sandbox(
    *,
    repo: Path,
    output: Path,
    target: str | None,
    all_targets: bool,
    scope: str,
    runtime: str = "docker",
    image: str = DEFAULT_IMAGE,
    on_phase: PhaseHandler | None = None,
    on_output: OutputHandler | None = None,
) -> int:
    output.mkdir(parents=True, exist_ok=True)
    if on_phase is not None:
        on_phase("docker_build")
    build = _run(
        build_image_command(runtime, image),
        BUILD_TIMEOUT_SECONDS,
        phase="docker_build",
        on_output=on_output,
    )
    if build:
        return build
    if on_phase is not None:
        on_phase("container")
    return _run(
        build_run_command(
            runtime=runtime,
            image=image,
            repo=repo,
            output=output,
            target=target,
            all_targets=all_targets,
            scope=scope,
        ),
        RUN_TIMEOUT_SECONDS,
        phase="container",
        on_output=on_output,
    )
