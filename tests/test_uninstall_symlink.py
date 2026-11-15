"""Uninstall through a symlinked instructions file.

When removing graphify's section leaves an instructions file empty, uninstall
deletes the file. If that path is a symlink, deleting it removed only the link
and left graphify's section in the file the link points to.
"""
from pathlib import Path

import pytest

from graphify.install import (
    _AGENTS_MD_MARKER,
    _CLAUDE_MD_MARKER,
    _CODEBUDDY_MD_MARKER,
    _GEMINI_MD_MARKER,
    _SKILL_REGISTRATION_MARKER,
    _VSCODE_INSTRUCTIONS_MARKER,
    _agents_uninstall,
    _remove_claude_skill_registration,
    claude_uninstall,
    codebuddy_uninstall,
    gemini_uninstall,
    vscode_uninstall,
)

# (instructions file relative to the project, graphify's heading, uninstall call)
CASES = [
    (".claude/CLAUDE.md", _SKILL_REGISTRATION_MARKER, _remove_claude_skill_registration),
    ("CLAUDE.md", _CLAUDE_MD_MARKER, claude_uninstall),
    ("GEMINI.md", _GEMINI_MD_MARKER, gemini_uninstall),
    (".github/copilot-instructions.md", _VSCODE_INSTRUCTIONS_MARKER, vscode_uninstall),
    ("AGENTS.md", _AGENTS_MD_MARKER, _agents_uninstall),
    ("CODEBUDDY.md", _CODEBUDDY_MD_MARKER, codebuddy_uninstall),
]
IDS = [rel for rel, _, _ in CASES]


def _section(marker: str) -> str:
    return f"{marker}\n\ngraphify rules\n"


@pytest.mark.parametrize("rel,marker,uninstall", CASES, ids=IDS)
def test_uninstall_empties_symlink_target_and_keeps_link(requires_symlinks, tmp_path, rel, marker, uninstall):
    project = tmp_path / "project"
    target = tmp_path / "dotfiles" / "rules.md"
    target.parent.mkdir()
    target.write_text(_section(marker), encoding="utf-8")
    link = project / rel
    link.parent.mkdir(parents=True)
    link.symlink_to(target)

    uninstall(project)

    assert link.is_symlink(), "the user's symlink was deleted"
    assert link.resolve() == target.resolve()
    assert marker not in target.read_text(encoding="utf-8"), "graphify's section is still in the link target"


@pytest.mark.parametrize("rel,marker,uninstall", CASES, ids=IDS)
def test_uninstall_still_deletes_a_regular_file_left_empty(tmp_path, rel, marker, uninstall):
    project = tmp_path / "project"
    path = project / rel
    path.parent.mkdir(parents=True)
    path.write_text(_section(marker), encoding="utf-8")

    uninstall(project)

    assert not path.exists()
