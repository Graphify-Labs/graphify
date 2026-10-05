"""#3642, #3742, #3844: INPUT_PATH substitution into bash commands is a command
injection vector.

INPUT_PATH is a literal placeholder in generated skill files, meant to
be substituted by the agent following the instructions with the resolved
scan path before it runs bash blocks. A malicious or merely
untrusted-source path substituted into an unquoted shell command line
executes as shell code the moment the line runs, before any Python code
is reached.

These tests extract the actual Step 1 and --watch bash blocks from committed,
generated skill files (including the Aider and Devin monoliths), verify that
the artifacts users actually receive are safe against hostile inputs, and
execute Step 1 with hostile paths to prove no injected commands run.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from tests.shell_portability import resolve_shell_path, select_shell_executable

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_MD = REPO_ROOT / "graphify" / "skill.md"

MONOLITH_SKILL_FILES = ("skill-aider.md", "skill-devin.md")
ALL_TESTED_SKILL_FILES = ("skill.md", "skill-aider.md", "skill-devin.md")


def _extract_step1_bash_block(filename: str = "skill.md") -> str:
    text = (REPO_ROOT / "graphify" / filename).read_text(encoding="utf-8")
    for match in re.finditer(r"```bash\n(.*?)\n```", text, re.DOTALL):
        block = match.group(1)
        if "graphify_root" in block:
            return block
    raise AssertionError(f"could not find the Step 1 bash block in {filename}")


def _extract_watch_bash_block(filename: str) -> str:
    text = (REPO_ROOT / "graphify" / filename).read_text(encoding="utf-8")
    m = re.search(r"## For --watch.*?(```bash\n.*?\n```)", text, re.DOTALL)
    if not m:
        raise AssertionError(f"could not find the --watch section in {filename}")
    block = re.search(r"```bash\n(.*?)\n```", m.group(1), re.DOTALL)
    if not block:
        raise AssertionError(f"could not find the --watch bash block in {filename}")
    return block.group(1).strip()


@pytest.fixture()
def step1_script() -> str:
    return _extract_step1_bash_block()


def _run_step1(script: str, input_path_value: str, cwd: Path) -> subprocess.CompletedProcess:
    # Admit the shell explicitly; the heredoc preserves Python stdin payload bytes.
    # Preserve the fixture's native spelling; Windows alone does not imply WSL.
    substituted = script.replace("INPUT_PATH", input_path_value).replace("\r\n", "\n")
    if sys.platform == "win32":
        # On Windows, writing to a temp script file avoids CreateProcess quote-escaping
        # mangling double quotes inside `bash -c "..."`. Must use LF newlines for bash.
        script_file = cwd / "_run_step1.sh"
        script_file.write_text(substituted, encoding="utf-8", newline="\n")
        return subprocess.run(
            [select_shell_executable("bash"), "_run_step1.sh"],
            cwd=cwd, capture_output=True, text=True,
            env={**os.environ, "PATH": os.environ.get("PATH", "")},
        )
    return subprocess.run(
        [select_shell_executable("bash"), "-c", substituted],
        cwd=cwd, capture_output=True, text=True,
        env={**os.environ, "PATH": os.environ.get("PATH", "")},
    )


# --- #3844: Monolith --watch contract tests ----------------------------------


@pytest.mark.parametrize("skill_file", MONOLITH_SKILL_FILES)
def test_monolith_watch_does_not_contain_raw_input_path_placeholder(skill_file: str):
    """The monolith --watch block must not interpolate raw INPUT_PATH into shell code."""
    block = _extract_watch_bash_block(skill_file)
    assert "INPUT_PATH" not in block, (
        f"{skill_file} --watch command still contains raw INPUT_PATH placeholder: {block!r}"
    )


@pytest.mark.parametrize("skill_file", MONOLITH_SKILL_FILES)
def test_monolith_watch_uses_trusted_graphify_root(skill_file: str):
    """The monolith --watch block must read from trusted .graphify_root and .graphify_python."""
    block = _extract_watch_bash_block(skill_file)
    assert "graphify-out/.graphify_root" in block, (
        f"{skill_file} --watch command does not reference graphify-out/.graphify_root"
    )
    assert "graphify-out/.graphify_python" in block, (
        f"{skill_file} --watch command does not reference graphify-out/.graphify_python"
    )
    assert block == (
        '$(cat graphify-out/.graphify_python) -m graphify.watch '
        '"$(cat graphify-out/.graphify_root)" --debounce 3'
    )


# --- Step 1 hostile INPUT_PATH injection resistance --------------------------


HOSTILE_PAYLOADS = [
    ("cmd_subst", lambda s: f"$(touch {s})"),
    ("backticks", lambda s: f"`touch {s}`"),
    ("semicolon", lambda s: f"nonexistent; touch {s} #"),
    ("and_chain", lambda s: f"nonexistent && touch {s}"),
    ("pipe_chain", lambda s: f"nonexistent | touch {s}"),
    ("newline", lambda s: f"nonexistent\ntouch {s}\n"),
]


@pytest.mark.parametrize("skill_file", ALL_TESTED_SKILL_FILES)
@pytest.mark.parametrize("attack_name,payload_fn", HOSTILE_PAYLOADS)
def test_step1_does_not_execute_hostile_input_path(
    tmp_path: Path, skill_file: str, attack_name: str, payload_fn
):
    """A hostile INPUT_PATH containing shell metacharacters must never execute."""
    script = _extract_step1_bash_block(skill_file)
    sentinel = tmp_path / f"PWNED_{attack_name}_{skill_file.replace('.', '_')}"
    # Relative sentinels are reachable by the actual shell on every host. A
    # Windows backslash path can otherwise make a vulnerable control look safe.
    malicious = payload_fn(sentinel.name)

    result = _run_step1(script, malicious, cwd=tmp_path)

    assert not sentinel.exists(), (
        f"hostile {attack_name} inside substituted INPUT_PATH for {skill_file} "
        f"must never execute as shell code"
    )
    assert result.returncode != 0, "a hostile nonexistent path must be rejected"
    assert (tmp_path / "graphify-out" / ".graphify_python").is_file()
    assert not (tmp_path / "graphify-out" / ".graphify_root").exists()
    _run_step1("true INPUT_PATH\n", malicious, cwd=tmp_path)
    assert sentinel.is_file(), "unsafe control must reach the same sentinel"


# --- Backwards-compatible legacy test entry points ---------------------------


def test_step1_does_not_execute_a_command_substitution_in_input_path(tmp_path: Path):
    """A malicious path containing $(...) must never run as shell code."""
    script = _extract_step1_bash_block()
    sentinel = tmp_path / "PWNED"
    malicious = f"$(touch {sentinel.name})"

    result = _run_step1(script, malicious, cwd=tmp_path)

    assert not sentinel.exists(), (
        "a $(...) command substitution inside the substituted INPUT_PATH "
        "must never execute"
    )
    assert result.returncode != 0, "a hostile nonexistent path must be rejected"
    assert (tmp_path / "graphify-out" / ".graphify_python").is_file()
    assert not (tmp_path / "graphify-out" / ".graphify_root").exists()
    _run_step1("true INPUT_PATH\n", malicious, cwd=tmp_path)
    assert sentinel.is_file(), "unsafe control must reach the same sentinel"


def test_step1_does_not_execute_a_semicolon_separated_command_in_input_path(tmp_path: Path):
    """A malicious path using `;` to chain a second command must never run."""
    script = _extract_step1_bash_block()
    sentinel = tmp_path / "PWNED2"
    malicious = f"nonexistent; touch {sentinel.name} #"

    result = _run_step1(script, malicious, cwd=tmp_path)

    assert not sentinel.exists(), (
        "a semicolon-separated command inside the substituted INPUT_PATH "
        "must never execute"
    )
    assert result.returncode != 0, "a hostile nonexistent path must be rejected"
    assert (tmp_path / "graphify-out" / ".graphify_python").is_file()
    assert not (tmp_path / "graphify-out" / ".graphify_root").exists()
    _run_step1("true INPUT_PATH\n", malicious, cwd=tmp_path)
    assert sentinel.is_file(), "unsafe control must reach the same sentinel"


# --- Legitimate path handling & non-existent path failure ---------------------


@pytest.mark.parametrize("skill_file", ALL_TESTED_SKILL_FILES)
def test_step1_still_resolves_a_legitimate_path(tmp_path: Path, skill_file: str):
    """The fix must not break ordinary paths, including paths with spaces."""
    script = _extract_step1_bash_block(skill_file)
    project = tmp_path / "my project with spaces"
    project.mkdir()

    result = _run_step1(script, str(project), cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    marker = tmp_path / "graphify-out" / ".graphify_root"
    assert marker.exists(), (
        f"a legitimate path must still be resolved and written for {skill_file}; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    marker_content = marker.read_text(encoding="utf-8").strip()
    resolved_marker = resolve_shell_path(marker_content, shell="bash")
    assert resolved_marker == project.resolve()
    assert marker_content.endswith("my project with spaces")


@pytest.mark.parametrize("skill_file", ALL_TESTED_SKILL_FILES)
def test_step1_still_fails_loudly_on_a_nonexistent_path(tmp_path: Path, skill_file: str):
    """A path that does not exist must still fail, matching the original
    `cd INPUT_PATH` behavior, not silently write a bogus marker."""
    script = _extract_step1_bash_block(skill_file)

    result = _run_step1(script, "does/not/exist", cwd=tmp_path)

    marker = tmp_path / "graphify-out" / ".graphify_root"
    assert result.returncode != 0
    assert not marker.exists() or marker.read_text(encoding="utf-8") == ""
