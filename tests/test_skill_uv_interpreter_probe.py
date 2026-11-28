"""#5182: Step 1 must pick the user's installed graphify, never a PyPI download.

Step 1 used to probe for a uv-installed interpreter with
``uv tool run --from graphifyy python``. When graphifyy is not installed as a uv
tool (a pip or pipx install on a machine that also has uv), that command builds a
throwaway env from the latest PyPI release, and Step 1 saved that interpreter to
``graphify-out/.graphify_python`` ahead of the user's own install.

These tests run the real Step 1 block from the generated skill files against stub
``uv`` / ``graphify`` / python executables and record which interpreter wins.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
GRAPHIFY_DIR = REPO_ROOT / "graphify"

# One file per Step 1 source fragment: shell/posix.md, core/aider.md, core/devin.md.
STEP1_SOURCES = ("skill.md", "skill-aider.md", "skill-devin.md")
POSIX_SKILL_FILES = sorted(
    p.name for p in GRAPHIFY_DIR.glob("skill*.md") if p.name != "skill-windows.md"
)


def _step1_block(filename: str) -> str:
    text = (GRAPHIFY_DIR / filename).read_text(encoding="utf-8")
    for match in re.finditer(r"```bash\n(.*?)\n```", text, re.DOTALL):
        if "graphify_root" in match.group(1):
            return match.group(1)
    raise AssertionError(f"could not find the Step 1 bash block in {filename}")


def _bash() -> str:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is not available")
    if sys.platform == "win32" and "system32" in bash.lower():
        pytest.skip("WSL bash cannot run the Windows test interpreter")
    return bash


def _posix(path: Path) -> str:
    """The path as bash sees it (Git Bash on Windows maps C:\\x to /c/x)."""
    resolved = str(path.resolve())
    if sys.platform == "win32" and len(resolved) > 1 and resolved[1] == ":":
        return f"/{resolved[0].lower()}{resolved[2:].replace(os.sep, '/')}"
    return resolved


def _stub_python(path: Path, name: str) -> None:
    """A python that logs who ran it, then runs the test interpreter (which has graphify)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "#!/bin/sh\n"
        f'echo "{name} $*" >> "$STUB_LOG"\n'
        f'exec "{_posix(Path(sys.executable))}" "$@"\n',
        encoding="utf-8",
        newline="\n",
    )
    path.chmod(0o755)


def _stub_uv(bin_dir: Path, tool_dir: Path, decoy: Path) -> None:
    """uv whose ``tool run`` behaves like the real one: the installed tool env if
    there is one, otherwise a fresh env resolved from PyPI (the decoy)."""
    installed = [tool_dir / "graphifyy" / "bin" / "python", tool_dir / "graphifyy" / "Scripts" / "python.exe"]
    run_branch = "".join(
        f'    if [ -x "{_posix(p)}" ]; then echo "{_posix(p)}"; exit 0; fi\n' for p in installed
    )
    script = (
        "#!/bin/sh\n"
        'echo "uv $*" >> "$STUB_LOG"\n'
        'if [ "$1 $2" = "tool dir" ]; then\n'
        # Real uv prints a native path (C:\Users\...\uv\tools on Windows, even under Git Bash).
        f"    echo '{tool_dir.resolve()}'; exit 0\n"
        "fi\n"
        'if [ "$1 $2" = "tool run" ]; then\n'
        f"{run_branch}"
        f'    echo "{_posix(decoy)}"; exit 0\n'
        "fi\n"
        "exit 0\n"
    )
    uv = bin_dir / "uv"
    uv.write_text(script, encoding="utf-8", newline="\n")
    uv.chmod(0o755)


def _stub_graphify(bin_dir: Path, interpreter: Path) -> None:
    exe = bin_dir / "graphify"
    exe.write_text(f"#!{_posix(interpreter)}\nimport graphify\n", encoding="utf-8", newline="\n")
    exe.chmod(0o755)


def _run_step1(skill_file: str, root: Path) -> tuple[str, list[str]]:
    """Run Step 1 in ``root/proj`` and return (interpreter that wrote .graphify_python, stub log)."""
    bash = _bash()
    proj = root / "proj"
    proj.mkdir()
    script = proj / "_step1.sh"
    script.write_text(_step1_block(skill_file).replace("INPUT_PATH", "."), encoding="utf-8", newline="\n")
    log = root / "stub.log"
    log.touch()
    env = {
        **os.environ,
        "PATH": f"{_posix(root / 'bin')}:/usr/bin:/bin",
        "STUB_LOG": _posix(log),
    }
    result = subprocess.run([bash, script.name], cwd=proj, env=env, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    calls = log.read_text(encoding="utf-8").splitlines()
    writers = [c.split()[0] for c in calls if "graphify-out/.graphify_python" in c]
    assert len(writers) == 1, calls
    return writers[0], calls


@pytest.fixture()
def env_root(tmp_path: Path) -> Path:
    (tmp_path / "bin").mkdir()
    _stub_python(tmp_path / "pypi-throwaway" / "python", "pypi-throwaway")
    return tmp_path


@pytest.mark.parametrize("skill_file", STEP1_SOURCES)
def test_pip_install_wins_over_a_pypi_download_when_uv_is_present(env_root: Path, skill_file: str):
    """graphify installed with pip/pipx, uv on PATH, graphifyy not a uv tool."""
    pip_python = env_root / "pipenv" / "python"
    _stub_python(pip_python, "pip-install")
    _stub_graphify(env_root / "bin", pip_python)
    _stub_uv(env_root / "bin", env_root / "uv-tools", env_root / "pypi-throwaway" / "python")

    writer, calls = _run_step1(skill_file, env_root)

    assert writer == "pip-install", calls
    assert not any(c.startswith("uv tool run") for c in calls), calls
    assert not any(c.startswith("uv tool install") for c in calls), calls


@pytest.mark.parametrize("layout", [("bin", "python"), ("Scripts", "python.exe")])
@pytest.mark.parametrize("skill_file", STEP1_SOURCES)
def test_uv_tool_install_is_found_without_running_uv_tool_run(
    env_root: Path, skill_file: str, layout: tuple[str, str]
):
    """graphifyy installed with ``uv tool install``; the Windows layout has no shebang to read."""
    tool_python = env_root / "uv-tools" / "graphifyy" / layout[0] / layout[1]
    _stub_python(tool_python, "uv-tool")
    if layout[0] == "bin":
        _stub_graphify(env_root / "bin", tool_python)
    _stub_uv(env_root / "bin", env_root / "uv-tools", env_root / "pypi-throwaway" / "python")

    writer, calls = _run_step1(skill_file, env_root)

    assert writer == "uv-tool", calls
    assert not any(c.startswith("uv tool run") for c in calls), calls


@pytest.mark.parametrize("skill_file", POSIX_SKILL_FILES)
def test_no_generated_skill_runs_uv_tool_run(skill_file: str):
    assert "uv tool run" not in _step1_block(skill_file), skill_file
