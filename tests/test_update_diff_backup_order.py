"""#4539: the ``--update`` graph diff needs a backup of graph.json taken BEFORE the merge.

The runbook's diff block reads ``.graphify_old.json`` after Step 4 and compares it with the
merged graph. The instruction that writes that backup used to sit after the diff block, so an
agent following the runbook top to bottom reached it only once Step 4 had already rewritten
graph.json: the diff had nothing to compare against and printed nothing at all.

This reads the RENDERED runbooks and checks the order the agent meets the steps in: the
backup comes before the merge block, and the diff block says so when the backup is missing
instead of skipping in silence.
"""
from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

SHARED_HOSTS = ["agents", "amp", "claude", "claw", "codex", "copilot", "droid", "kilo",
                "kiro", "opencode", "pi", "trae", "vscode", "windows"]

# (rendered runbook, merge anchor, backup path as that runbook names it)
RUNBOOKS = [
    pytest.param(f"graphify/skills/{h}/references/update.md", "build_merge(",
                 "graphify-out/.graphify_old.json", id=h)
    for h in SHARED_HOSTS
] + [
    pytest.param("graphify/skill-devin.md", "G_existing.update(",
                 "graphify-out/.graphify_old.json", id="devin"),
    # aider keeps its working files in the project root, not graphify-out/
    pytest.param("graphify/skill-aider.md", "G_existing.update(", ".graphify_old.json", id="aider"),
]


def _update_section(text: str) -> str:
    start = text.index("## For --update")
    end = text.index("## For --cluster-only", start)
    return text[start:end]


@pytest.mark.parametrize("rel, merge_anchor, backup", RUNBOOKS)
def test_backup_is_taken_before_the_merge(rel, merge_anchor, backup):
    section = _update_section((REPO_ROOT / rel).read_text(encoding="utf-8"))
    backup_cmd = f"cp graphify-out/graph.json {backup}"
    assert backup_cmd in section, f"{rel}: --update section has no `{backup_cmd}`"
    assert section.index(backup_cmd) < section.index(merge_anchor), (
        f"{rel}: the graph.json backup is written after the merge block, so the "
        "post-Step-4 diff has no pre-update graph to compare against"
    )


@pytest.mark.parametrize("rel, merge_anchor, backup", RUNBOOKS)
def test_diff_reports_a_missing_backup(rel, merge_anchor, backup):
    section = _update_section((REPO_ROOT / rel).read_text(encoding="utf-8"))
    diff_block = section[section.index("show the graph diff"):]
    assert "if old_data:" in diff_block, f"{rel}: diff block not found"
    assert "else:" in diff_block.split("if old_data:", 1)[1].split("```", 1)[0], (
        f"{rel}: the diff block prints nothing when {backup} is missing"
    )
