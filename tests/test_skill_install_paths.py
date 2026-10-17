"""Regression coverage for Codex install and skill output paths."""
from __future__ import annotations

import base64
import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _codex_hook_entry(tmp_path: Path, *, project: bool = True) -> dict[str, Any]:
    from graphify.install import _install_codex_hook

    _install_codex_hook(tmp_path, project=project)
    settings = json.loads((tmp_path / ".codex" / "hooks.json").read_text(encoding="utf-8"))
    return next(
        hook
        for group in settings["hooks"]["PreToolUse"]
        for hook in group["hooks"]
        if hook.get("type") == "command"
    )


@pytest.mark.skipif(os.name == "nt", reason="POSIX hook command is exercised with /bin/sh")
def test_codex_hook_skips_missing_graphify_and_preserves_installed_failures(tmp_path: Path) -> None:
    entry = _codex_hook_entry(tmp_path)
    command = entry["command"]

    missing_path = tmp_path / "empty path"
    missing_path.mkdir()
    missing = subprocess.run(
        ["/bin/sh", "-c", command],
        cwd=tmp_path,
        env={"PATH": str(missing_path)},
        input="{}",
        text=True,
        capture_output=True,
        check=False,
    )
    assert missing.returncode == 0
    assert missing.stderr == ""

    bin_dir = tmp_path / "installed tools"
    bin_dir.mkdir()
    args_path = tmp_path / "hook args"
    graphify = bin_dir / "graphify"
    graphify.write_text(
        '#!/bin/sh\nprintf \'%s\\0\' "$@" > "$HOOK_ARGS"\n'
        'exit "$HOOK_EXIT_CODE"\n',
        encoding="utf-8",
    )
    graphify.chmod(0o755)
    installed = subprocess.run(
        ["/bin/sh", "-c", command],
        cwd=tmp_path,
        env={
            "PATH": str(bin_dir),
            "HOOK_ARGS": str(args_path),
            "HOOK_EXIT_CODE": "23",
        },
        input="{}",
        text=True,
        capture_output=True,
        check=False,
    )
    assert installed.returncode == 23
    assert args_path.read_bytes().split(b"\0") == [b"hook-check", b""]


@pytest.mark.skipif(os.name == "nt", reason="POSIX hook command is exercised with /bin/sh")
def test_codex_profile_hook_skips_missing_absolute_executable_and_propagates_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = tmp_path / "user profile" / "graphify"
    monkeypatch.setattr("shutil.which", lambda _name: str(executable))
    command = _codex_hook_entry(tmp_path, project=False)["command"]
    empty_path = tmp_path / "empty path"
    empty_path.mkdir()

    missing = subprocess.run(
        ["/bin/sh", "-c", command],
        cwd=tmp_path,
        env={"PATH": str(empty_path)},
        input="{}",
        text=True,
        capture_output=True,
        check=False,
    )
    assert missing.returncode == 0
    assert missing.stderr == ""

    executable.parent.mkdir()
    executable.write_text("#!/bin/sh\nexit 23\n", encoding="utf-8")
    executable.chmod(0o755)
    installed = subprocess.run(
        ["/bin/sh", "-c", command],
        cwd=tmp_path,
        env={"PATH": str(empty_path)},
        input="{}",
        text=True,
        capture_output=True,
        check=False,
    )
    assert installed.returncode == 23


def test_codex_hook_has_a_windows_fail_open_command(tmp_path: Path) -> None:
    entry = _codex_hook_entry(tmp_path)
    command = entry.get("commandWindows")
    assert isinstance(command, str)
    parts = command.split()
    encoded_flag = parts.index("-EncodedCommand")
    script = base64.b64decode(parts[encoded_flag + 1]).decode("utf-16le")
    assert "Get-Command graphify" in script
    assert "exit $LASTEXITCODE" in script
    assert "exit 0" in script


def test_codex_user_profile_windows_hook_keeps_its_resolved_executable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("shutil.which", lambda _name: r"C:\Users\First Last\graphify.EXE")
    entry = _codex_hook_entry(tmp_path, project=False)
    command = entry["commandWindows"]
    parts = command.split()
    encoded_flag = parts.index("-EncodedCommand")
    script = base64.b64decode(parts[encoded_flag + 1]).decode("utf-16le")
    assert "C:/Users/First Last/graphify.EXE" in script


def _bash_blocks(markdown: str) -> list[str]:
    fence = chr(96) * 3
    return [part.split("\n" + fence, 1)[0] for part in markdown.split(fence + "bash\n")[1:]]


@pytest.mark.skipif(os.name == "nt", reason="the shared POSIX reference uses Bash")
@pytest.mark.parametrize("block_index", [0, 1])
def test_add_watch_runs_saved_interpreter_from_a_path_with_spaces(
    tmp_path: Path, block_index: int
) -> None:
    reference = (
        ROOT / "tools" / "skillgen" / "fragments" / "references" / "shared" / "add-watch.md"
    ).read_text(encoding="utf-8")
    blocks = _bash_blocks(reference)
    assert len(blocks) == 2

    project = tmp_path / "project with spaces"
    output = project / "graphify-out"
    python_dir = tmp_path / "python environment with spaces"
    project.mkdir()
    output.mkdir()
    python_dir.mkdir()
    fake_python = python_dir / "python"
    args_path = tmp_path / "captured args"
    fake_python.write_text(
        '#!/bin/sh\nprintf \'%s\\0\' "$@" > "$HOOK_ARGS"\n',
        encoding="utf-8",
    )
    fake_python.chmod(0o755)
    (output / ".graphify_python").write_text(str(fake_python), encoding="utf-8")
    (output / ".graphify_root").write_text(str(project), encoding="utf-8")

    environment = os.environ.copy()
    environment["HOOK_ARGS"] = str(args_path)
    result = subprocess.run(
        ["/bin/bash", "-c", blocks[block_index]],
        cwd=project,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    args = args_path.read_bytes().split(b"\0")[:-1]
    if block_index == 0:
        assert args[0] == b"-c"
        assert len(args) == 2
    else:
        assert args == [
            b"-m",
            b"graphify.watch",
            str(project).encode(),
            b"--debounce",
            b"3",
        ]


def _bash_block_after(reference: str, marker: str) -> str:
    start = reference.index(marker)
    fence_start = reference.index("```bash\n", start) + len("```bash\n")
    fence_end = reference.index("\n```", fence_start)
    return reference[fence_start:fence_end]


def _run_clone_workflow(
    workflow: str, tmp_path: Path, *, fail_url: str = ""
) -> tuple[subprocess.CompletedProcess[str], list[list[bytes]]]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True)
    home = tmp_path / "home with spaces"
    home.mkdir()
    call_log = tmp_path / "graphify-calls"
    fake_graphify = bin_dir / "graphify"
    fake_graphify.write_text(
        r'''#!/bin/sh
printf '%s\0' "$@" >> "$GRAPHIFY_CALLS"
printf '\036' >> "$GRAPHIFY_CALLS"
if [ "$1" = "clone" ]; then
    printf 'Cloning repository...\nReady at: %s\n%s\n' "$4" "$4"
    if [ "$2" = "$FAIL_CLONE_URL" ]; then
        exit 23
    fi
fi
''',
        encoding="utf-8",
    )
    fake_graphify.chmod(0o755)

    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{bin_dir}{os.pathsep}{environment.get('PATH', '')}",
            "HOME": str(home),
            "GRAPHIFY_CALLS": str(call_log),
            "FAIL_CLONE_URL": fail_url,
        }
    )
    result = subprocess.run(
        ["/bin/bash", "-c", workflow],
        cwd=tmp_path,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    if not call_log.exists():
        return result, []
    calls = [
        record.split(b"\0")[:-1]
        for record in call_log.read_bytes().split(b"\x1e")
        if record
    ]
    return result, calls


@pytest.mark.skipif(os.name == "nt", reason="Bash clone workflow is exercised on POSIX")
def test_single_repo_clone_uses_explicit_path_with_spaces(tmp_path: Path) -> None:
    reference = (
        ROOT
        / "tools"
        / "skillgen"
        / "fragments"
        / "references"
        / "shared"
        / "github-and-merge.md"
    ).read_text(encoding="utf-8")
    workflow = _bash_block_after(reference, "**Single repo:**")

    assert "LOCAL_PATH=$(graphify clone" not in workflow
    assert 'LOCAL_PATH="$HOME/graphify repos/repo"' in workflow
    assert 'graphify clone "https://github.com/owner/repo" --out "$LOCAL_PATH" &&' in workflow

    result, calls = _run_clone_workflow(workflow, tmp_path)
    assert result.returncode == 0, result.stderr
    assert len(calls) == 2
    expected_path = str(tmp_path / "home with spaces" / "graphify repos" / "repo").encode()
    assert calls[0] == [
        b"clone",
        b"https://github.com/owner/repo",
        b"--out",
        expected_path,
    ]
    assert calls[1] == [b"extract", expected_path]


@pytest.mark.skipif(os.name == "nt", reason="Bash clone workflow is exercised on POSIX")
def test_cross_repo_clone_workflow_uses_explicit_paths_and_stops_on_failure(
    tmp_path: Path,
) -> None:
    reference = (
        ROOT
        / "tools"
        / "skillgen"
        / "fragments"
        / "references"
        / "shared"
        / "github-and-merge.md"
    ).read_text(encoding="utf-8")
    workflow = _bash_block_after(reference, "**Multiple repos (cross-repo graph):**")

    for name in ("REPO1_PATH", "REPO2_PATH"):
        assert f'graphify extract "${name}"' in workflow
        assert f'"${name}/graphify-out/graph.json"' in workflow
        assert f"{name}=$(graphify clone" not in workflow
        assert f'--out "${name}"' in workflow
    assert "Run /graphify on each local path" not in workflow

    failed, failed_calls = _run_clone_workflow(
        workflow, tmp_path / "failed", fail_url="https://github.com/owner/repo1"
    )
    assert failed.returncode == 23
    assert failed_calls == [
        [
            b"clone",
            b"https://github.com/owner/repo1",
            b"--out",
            str(tmp_path / "failed" / "home with spaces" / "graphify repos" / "repo1").encode(),
        ]
    ]

    successful, calls = _run_clone_workflow(workflow, tmp_path / "successful")
    assert successful.returncode == 0, successful.stderr
    assert successful.stdout.count("Ready at:") == 2
    home = tmp_path / "successful" / "home with spaces"
    repo1 = str(home / "graphify repos" / "repo1").encode()
    repo2 = str(home / "graphify repos" / "repo2").encode()
    assert calls[:4] == [
        [b"clone", b"https://github.com/owner/repo1", b"--out", repo1],
        [b"clone", b"https://github.com/owner/repo2", b"--out", repo2],
        [b"extract", repo1],
        [b"extract", repo2],
    ]
    assert calls[4] == [
        b"merge-graphs",
        repo1 + b"/graphify-out/graph.json",
        repo2 + b"/graphify-out/graph.json",
        b"--out",
        b"graphify-out/cross-repo-graph.json",
    ]


def test_completion_reports_the_pipeline_output_directory() -> None:
    core = (ROOT / "tools" / "skillgen" / "fragments" / "core" / "core.md").read_text(
        encoding="utf-8"
    )
    start = core.index("Tell the user (omit the obsidian line unless --obsidian was given):")
    end = core.index("Then paste these sections from GRAPH_REPORT.md directly into the chat:", start)
    completion = core[start:end]

    assert "Outputs in OUTPUT_DIR/" in completion
    assert "Path('graphify-out').resolve()" in completion
    assert "current working directory" in completion
    assert "Replace PATH_TO_DIR with the actual absolute path" not in completion
