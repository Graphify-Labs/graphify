"""#197: the skill must not ship inline Python for its pipeline steps.

The skill used to carry each step as `$(cat graphify-out/.graphify_python) -c "..."`.
That form trips Claude Code's command_substitution and "newline followed by #"
approval prompts once per step and cannot be allowlisted, so a run cost ~30 manual
confirms. The steps are now plain `graphify pipeline <step>` calls, so what is left
in a skill file must be Step 1's interpreter *detection* only — never a pipeline
step, and never an instruction to read back an interpreter path.
"""

import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_GLOB = "skill*.md"

#: Steps the skill must invoke as subcommands rather than inline Python.
PIPELINE_COMMANDS = [
    "graphify pipeline detect",
    "graphify pipeline extract-ast",
    "graphify pipeline empty-semantic",
    "graphify pipeline cache-check",
    "graphify pipeline merge-chunks",
    "graphify pipeline save-cache",
    "graphify pipeline merge-semantic",
    "graphify pipeline merge-extraction",
    "graphify pipeline build",
    "graphify pipeline diagnose",
    "graphify pipeline label",
    "graphify pipeline save-manifest",
    "graphify pipeline cleanup",
]

#: skill-aider.md and skill-devin.md are hand-authored per-platform skill files with
#: their own inline-Python pipelines; they are not generated from core.md and are
#: tracked separately. Everything generated from core.md must be clean.
GENERATED_SKILLS = [
    p for p in sorted((REPO_ROOT / "graphify").glob(SKILL_GLOB))
    if p.name not in ("skill-aider.md", "skill-devin.md")
]

#: The on-demand reference flows (update/query/add-watch/transcribe/exports) are
#: rendered per host under graphify/skills/<host>/references/. They must be clean
#: too: #197 is about the Claude Code skill, which loads these on demand, so a
#: remaining inline block there would still prompt.
GENERATED_REFERENCES = sorted((REPO_ROOT / "graphify" / "skills").rglob("references/*.md"))

#: The interpreter-detection block (Step 1) still legitimately runs `python -c` to
#: find the interpreter that has graphify — that is what installs it. These lines are
#: the only allowed `-c` sites.
_INSTALL_ALLOWED = (
    "print(sys.executable)",
    '-c "import graphify"',
    "write(sys.executable)",
    # Step 1's stdlib-only scan-root write (heredoc stdin, no graphify import).
    "os.getcwd()",
)


def _inline_c_sites(text: str) -> list[tuple[int, str]]:
    return [
        (i, line)
        for i, line in enumerate(text.splitlines(), 1)
        if re.search(r'(?<![A-Za-z0-9_-])-c\s+["\']', line)
    ]


ALL_SKILL_AND_REFERENCE_FILES = GENERATED_SKILLS + GENERATED_REFERENCES


@pytest.mark.parametrize("path", ALL_SKILL_AND_REFERENCE_FILES, ids=lambda p: p.name)
def test_generated_skill_has_no_inline_python_pipeline_step(path: Path):
    """No generated skill may shell out to `python -c` outside Step 1 detection."""
    text = path.read_text(encoding="utf-8", errors="replace")
    offenders = [
        (i, line) for i, line in _inline_c_sites(text)
        if not any(ok in line for ok in _INSTALL_ALLOWED)
    ]
    assert not offenders, (
        f"{path.name} still runs inline Python outside the Step 1 install block. "
        "Each step must be a `graphify pipeline <step>` call so the skill needs no "
        "interpreter substitution and `Bash(graphify *)` stays allowlistable (#197):\n"
        + "\n".join(f"  {i}: {line.strip()[:100]}" for i, line in offenders)
    )


@pytest.mark.parametrize("path", ALL_SKILL_AND_REFERENCE_FILES, ids=lambda p: p.name)
def test_generated_skill_never_instructs_reading_back_the_interpreter(path: Path):
    """The `$(cat graphify-out/.graphify_python)` indirection must be gone.

    That substitution is what triggered Claude Code's command_substitution prompt on
    every step, and no step needs it now that each one is a console-script call.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    # A *write* of the interpreter path in Step 1 is fine, and prose may mention the
    # file. What must not survive is a *read* of it — the `$(cat ...)` / `Get-Content`
    # indirection that used to precede every inline-python pipeline step.
    assert "$(cat graphify-out/.graphify_python)" not in text, (
        f"{path.name} still substitutes an interpreter path into a bash block (#197)"
    )
    assert "Get-Content graphify-out" not in text, (
        f"{path.name} still reads the interpreter path on PowerShell (#197)"
    )


@pytest.mark.parametrize("path", GENERATED_SKILLS, ids=lambda p: p.name)
def test_generated_skill_calls_every_pipeline_step(path: Path):
    """Every step the skill runs must exist as a `graphify pipeline` subcommand."""
    text = path.read_text(encoding="utf-8", errors="replace")
    missing = [cmd for cmd in PIPELINE_COMMANDS if cmd not in text]
    assert not missing, f"{path.name} is missing pipeline steps: {missing}"


def test_core_fragment_is_the_source_of_truth_and_is_clean():
    """core.md is the single source the generated skills are built from."""
    core = REPO_ROOT / "tools" / "skillgen" / "fragments" / "core" / "core.md"
    text = core.read_text(encoding="utf-8")
    offenders = [
        (i, line) for i, line in _inline_c_sites(text)
        if not any(ok in line for ok in _INSTALL_ALLOWED)
    ]
    assert not offenders, "core.md still carries inline pipeline Python"
    assert "$(cat graphify-out/.graphify_python)" not in text, (
        "core.md still substitutes an interpreter path into a bash block"
    )


@pytest.mark.parametrize("path", GENERATED_SKILLS, ids=lambda p: p.name)
def test_generated_skill_carries_no_bare_is_directed_placeholder(path: Path):
    """IS_DIRECTED was a code-substitution marker in a python block; the CLI takes a flag."""
    text = path.read_text(encoding="utf-8", errors="replace")
    assert "IS_DIRECTED" not in text, (
        f"{path.name} still asks for IS_DIRECTED to be substituted into code; "
        "pass --directed to `graphify pipeline build` instead"
    )
    assert "LABELS_DICT" not in text, (
        f"{path.name} still asks for LABELS_DICT to be pasted into code; "
        "pass --labels '<json>' to `graphify pipeline label` instead"
    )