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
    if sys.platform == "win32":
        if len(input_path_value) > 2 and input_path_value[1] == ":":
            drive = input_path_value[0].lower()
            rest = input_path_value[2:].replace("\\", "/")
            input_path_value = f"/mnt/{drive}{rest}"
        else:
            def _conv(m: re.Match) -> str:
                clean_path = m.group(2).replace("\\", "/")
                return f"/mnt/{m.group(1).lower()}/{clean_path}"
            input_path_value = re.sub(r"([A-Za-z]):[\\/]([^\s\"'`;#|)\n]+)", _conv, input_path_value)
    substituted = script.replace("INPUT_PATH", input_path_value).replace("\r\n", "\n")
    if sys.platform == "win32":
        # On Windows, writing to a temp script file avoids CreateProcess quote-escaping
        # mangling double quotes inside `bash -c "..."`. Must use LF newlines for bash.
        script_file = cwd / "_run_step1.sh"
        script_file.write_text(substituted, encoding="utf-8", newline="\n")
        return subprocess.run(
            ["bash", "_run_step1.sh"],
            cwd=cwd, capture_output=True, text=True,
            env={**os.environ, "PATH": os.environ.get("PATH", "")},
        )
    return subprocess.run(
        ["bash", "-c", substituted],
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
    malicious = payload_fn(sentinel)

    _run_step1(script, malicious, cwd=tmp_path)

    assert not sentinel.exists(), (
        f"hostile {attack_name} inside substituted INPUT_PATH for {skill_file} "
        f"must never execute as shell code"
    )


# --- Backwards-compatible legacy test entry points ---------------------------


def test_step1_does_not_execute_a_command_substitution_in_input_path(tmp_path: Path):
    """A malicious path containing $(...) must never run as shell code."""
    script = _extract_step1_bash_block()
    sentinel = tmp_path / "PWNED"
    malicious = f"$(touch {sentinel})"

    _run_step1(script, malicious, cwd=tmp_path)

    assert not sentinel.exists(), (
        "a $(...) command substitution inside the substituted INPUT_PATH "
        "must never execute"
    )


def test_step1_does_not_execute_a_semicolon_separated_command_in_input_path(tmp_path: Path):
    """A malicious path using `;` to chain a second command must never run."""
    script = _extract_step1_bash_block()
    sentinel = tmp_path / "PWNED2"
    malicious = f"nonexistent; touch {sentinel} #"

    _run_step1(script, malicious, cwd=tmp_path)

    assert not sentinel.exists(), (
        "a semicolon-separated command inside the substituted INPUT_PATH "
        "must never execute"
    )


# --- Legitimate path handling & non-existent path failure ---------------------


@pytest.mark.parametrize("skill_file", ALL_TESTED_SKILL_FILES)
def test_step1_still_resolves_a_legitimate_path(tmp_path: Path, skill_file: str):
    """The fix must not break ordinary paths, including paths with spaces."""
    script = _extract_step1_bash_block(skill_file)
    project = tmp_path / "my project with spaces"
    project.mkdir()

    result = _run_step1(script, str(project), cwd=tmp_path)

    marker = tmp_path / "graphify-out" / ".graphify_root"
    assert marker.exists(), (
        f"a legitimate path must still be resolved and written for {skill_file}; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    marker_content = marker.read_text(encoding="utf-8").strip()
    if sys.platform == "win32" and project.drive:
        drive_letter = project.drive[0].lower()
        if marker_content.startswith(f"/mnt/{drive_letter}/"):
            resolved_marker = Path(f"{drive_letter.upper()}:{marker_content[6:]}").resolve()
        elif marker_content.startswith(f"/{drive_letter}/"):
            resolved_marker = Path(f"{drive_letter.upper()}:{marker_content[2:]}").resolve()
        else:
            resolved_marker = Path(marker_content).resolve()
    else:
        resolved_marker = Path(marker_content).resolve()
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
