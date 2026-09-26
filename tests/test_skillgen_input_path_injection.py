"""#3642: Step 1's INPUT_PATH substitution into a bash command is a command
injection vector.

INPUT_PATH is a literal placeholder in every generated skill file, meant to
be substituted by the agent following the instructions with the resolved
scan path before it runs the bash block. A malicious or merely
untrusted-source path substituted into `echo "$(cd INPUT_PATH && pwd)" ...`
executed as shell code the moment Step 1 ran, before any Python code was
ever reached -- the outer double quotes do not stop `$()`/backtick
expansion, and the bare `cd INPUT_PATH` was itself unquoted.

These tests extract the actual Step 1 bash block from a committed,
generated skill file, substitute INPUT_PATH the way an agent would, and
execute it for real, so the fix is verified against the artifact users
actually receive rather than against the fragment source alone.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_MD = REPO_ROOT / "graphify" / "skill.md"


def _extract_step1_bash_block() -> str:
    text = SKILL_MD.read_text(encoding="utf-8")
    for match in re.finditer(r"```bash\n(.*?)\n```", text, re.DOTALL):
        block = match.group(1)
        if "graphify_root" in block:
            return block
    raise AssertionError("could not find the Step 1 bash block in skill.md")


@pytest.fixture()
def step1_script() -> str:
    return _extract_step1_bash_block()


def _run_step1(script: str, input_path_value: str, cwd: Path) -> subprocess.CompletedProcess:
    substituted = script.replace("INPUT_PATH", input_path_value)
    return subprocess.run(
        ["bash", "-c", substituted],
        cwd=cwd, capture_output=True, text=True,
        env={**os.environ, "PATH": os.environ.get("PATH", "")},
    )


def test_step1_does_not_execute_a_command_substitution_in_input_path(tmp_path):
    """A malicious path containing $(...) must never run as shell code."""
    script = _extract_step1_bash_block()
    sentinel = tmp_path / "PWNED"
    malicious = f"$(touch {sentinel})"

    _run_step1(script, malicious, cwd=tmp_path)

    assert not sentinel.exists(), (
        "a $(...) command substitution inside the substituted INPUT_PATH "
        "must never execute"
    )


def test_step1_does_not_execute_a_semicolon_separated_command_in_input_path(tmp_path):
    """A malicious path using `;` to chain a second command must never run."""
    script = _extract_step1_bash_block()
    sentinel = tmp_path / "PWNED2"
    malicious = f"nonexistent; touch {sentinel} #"

    _run_step1(script, malicious, cwd=tmp_path)

    assert not sentinel.exists(), (
        "a semicolon-separated command inside the substituted INPUT_PATH "
        "must never execute"
    )


def test_step1_still_resolves_a_legitimate_path(tmp_path):
    """The fix must not break the ordinary, non-malicious case."""
    script = _extract_step1_bash_block()
    project = tmp_path / "my project"
    project.mkdir()

    result = _run_step1(script, str(project), cwd=tmp_path)

    marker = tmp_path / "graphify-out" / ".graphify_root"
    assert marker.exists(), (
        f"a legitimate path must still be resolved and written; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert marker.read_text(encoding="utf-8") == str(project.resolve())


def test_step1_still_fails_loudly_on_a_nonexistent_path(tmp_path):
    """A path that does not exist must still fail, matching the original
    `cd INPUT_PATH` behavior, not silently write a bogus marker."""
    script = _extract_step1_bash_block()

    result = _run_step1(script, "does/not/exist", cwd=tmp_path)

    marker = tmp_path / "graphify-out" / ".graphify_root"
    assert result.returncode != 0
    assert not marker.exists() or marker.read_text(encoding="utf-8") == ""
