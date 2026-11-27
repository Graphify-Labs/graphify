"""Community labels, add-URL values and clone URLs must never be pasted into code.

Three runbooks still asked the agent to substitute free-text values into
executable source after the INPUT_PATH fix (#4762):

* ``labels = LABELS_DICT`` — Step 5 pasted the agent-built community-name
  dict straight into Python source; a label containing a quote or brace
  broke the literal and ran as code.
* ``ingest('URL', ..., author='AUTHOR', contributor='CONTRIBUTOR')`` — the
  URL and user names were pasted into Python string literals.
* ``graphify clone <github-url>`` and ``export obsidian --dir <path>`` —
  URLs and paths were pasted unquoted into shell command lines, where a
  ``&``, ``;`` or ``$()`` executes.

Every value now travels through a sidecar file the agent writes first:
``.graphify_labels.json`` (Step 5 reads it back instead of receiving a
dict literal), ``.graphify_add_url`` plus optional
``.graphify_add_author``/``.graphify_add_contributor``,
``.graphify_clone_url``/``.graphify_clone_branch``, and
``.graphify_obsidian_dir``. These tests ban the paste-the-value tokens
across all generated skill bodies and pin the sidecar mechanisms.
"""
from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
GEN = REPO_ROOT / "graphify"
BODIES = sorted(GEN.glob("skill*.md")) + sorted(GEN.glob("skills/*/references/*.md"))

# Every paste-the-value token removed by this change. The usage-table line
# ``/graphify <url1> <url2>`` stays: it documents how the *user* invokes the
# skill, not a command the agent runs, so it is deliberately not banned.
BANNED_TOKENS = (
    "'URL'",
    "'AUTHOR'",
    "'CONTRIBUTOR'",
    "LABELS_DICT",
    "clone <",
    "<github-url>",
    "--dir ~/",
    "Replace `URL`",
    "Replace `AUTHOR`",
    "Replace `CONTRIBUTOR`",
)


def test_no_generated_skill_pastes_add_labels_or_clone_values():
    """No paste-the-value placeholder may survive in any generated body."""
    assert len(BODIES) >= 15, f"expected the generated skill bodies, found {len(BODIES)}"
    offenders = []
    for body in BODIES:
        text = body.read_text(encoding="utf-8")
        for token in BANNED_TOKENS:
            if token in text:
                offenders.append(f"{body.relative_to(REPO_ROOT)}: {token}")
    assert not offenders, (
        "a paste-the-value placeholder survived in generated skills:\n  "
        + "\n  ".join(offenders)
        + "\n— values must travel through the graphify-out/ sidecar files, "
        "never into the command line or a Python string literal"
    )


@pytest.mark.parametrize(
    "skill_file", ("skill.md", "skill-aider.md", "skill-devin.md")
)
def test_step5_reads_labels_from_sidecar(skill_file: str):
    """Step 5 must read .graphify_labels.json, not take a pasted dict literal."""
    text = (GEN / skill_file).read_text(encoding="utf-8")
    assert "labels = {int(k): v for k, v in json.loads(Path('graphify-out/.graphify_labels.json')" in text


def test_add_flow_reads_url_and_names_from_sidecars():
    """The add runbook must read URL/author/contributor from sidecar files."""
    text = (GEN / "skills/claude/references/add-watch.md").read_text(encoding="utf-8")
    assert "graphify-out/.graphify_add_url" in text
    assert "_opt('.graphify_add_author')" in text
    assert "_opt('.graphify_add_contributor')" in text
    for monolith in ("skill-aider.md", "skill-devin.md"):
        body = (GEN / monolith).read_text(encoding="utf-8")
        assert "graphify-out/.graphify_add_url" in body, monolith


def test_clone_and_obsidian_dir_read_sidecars():
    """Clone URLs and the obsidian dir must arrive via sidecar files."""
    merge = (GEN / "skills/claude/references/github-and-merge.md").read_text(
        encoding="utf-8"
    )
    assert 'graphify clone "$(cat graphify-out/.graphify_clone_url)"' in merge
    assert ".graphify_clone_branch" in merge
    core = (GEN / "skill.md").read_text(encoding="utf-8")
    assert '--dir "$(cat graphify-out/.graphify_obsidian_dir)"' in core


def test_windows_skill_translates_sidecar_reads():
    """The PowerShell render must translate $(cat ...) to an evaluated subexpression.

    A plain ``(Get-Content ...)`` inside a double-quoted string is literal text
    in PowerShell — the ``$``-prefixed subexpression form is what evaluates,
    and the CR/LF-only ``TrimEnd`` matches bash ``$(...)`` trailing-newline
    stripping without touching boundary spaces in the value.
    """
    text = (GEN / "skill-windows.md").read_text(encoding="utf-8")
    assert "$(cat " not in text
    assert '$((Get-Content graphify-out\\.graphify_obsidian_dir -Raw).TrimEnd("`r","`n"))' in text
