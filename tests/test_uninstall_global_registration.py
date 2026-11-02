"""Uninstalling the user-global skill also removes its global registration.

A global `graphify install --platform claude` (or `windows`) copies the skill to
~/.claude/skills/graphify/ and registers it with a `# graphify` block in
~/.claude/CLAUDE.md ($CLAUDE_CONFIG_DIR/CLAUDE.md when that is set);
`--platform codebuddy` does the same in ~/.codebuddy/CODEBUDDY.md. Every
uninstall that removed the global skill left that block behind, so Claude Code
and CodeBuddy kept being told, in every session, to use a skill that no longer
existed. Only the project-scoped uninstall removed its registration.

The suite-wide `_sandbox_home` fixture points Path.home() at a throwaway
directory, so these tests install and uninstall for real.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from graphify import install as install_mod
from graphify.install import (
    _SKILL_REGISTRATION_MARKER,
    claude_uninstall,
    codebuddy_uninstall,
    install,
    uninstall_all,
)

USER_NOTES = "# My notes\n- always run the tests\n"


@pytest.fixture
def project(tmp_path, monkeypatch):
    path = tmp_path / "project"
    path.mkdir()
    monkeypatch.chdir(path)
    return path


def _claude_md() -> Path:
    return Path.home() / ".claude" / "CLAUDE.md"


def _codebuddy_md() -> Path:
    return Path.home() / ".codebuddy" / "CODEBUDDY.md"


def _registered(path: Path) -> bool:
    return path.exists() and any(
        line.strip() == _SKILL_REGISTRATION_MARKER
        for line in path.read_text(encoding="utf-8").splitlines()
    )


UNINSTALLS = {
    "graphify uninstall": lambda project: uninstall_all(project),
    "graphify claude uninstall": lambda project: claude_uninstall(),
}


@pytest.mark.parametrize("platform", ["claude", "windows"])
@pytest.mark.parametrize("uninstall", sorted(UNINSTALLS))
def test_uninstall_removes_the_global_claude_registration(project, platform, uninstall):
    install(platform=platform)
    assert _registered(_claude_md())

    UNINSTALLS[uninstall](project)

    assert not (Path.home() / ".claude" / "skills" / "graphify" / "SKILL.md").exists()
    # The file held nothing but the block install created it with.
    assert not _claude_md().exists()


def test_uninstall_keeps_the_users_own_global_claude_md_content(project):
    _claude_md().parent.mkdir(parents=True)
    _claude_md().write_text(USER_NOTES, encoding="utf-8")
    install(platform="claude")
    assert _registered(_claude_md())

    uninstall_all(project)

    assert _claude_md().read_text(encoding="utf-8") == USER_NOTES


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_uninstall_restores_the_global_claude_md_byte_for_byte(project, newline):
    original = USER_NOTES.replace("\n", newline).encode("utf-8")
    _claude_md().parent.mkdir(parents=True)
    _claude_md().write_bytes(original)
    install(platform="claude")

    uninstall_all(project)

    assert _claude_md().read_bytes() == original


def test_uninstall_removes_the_registration_from_claude_config_dir(project, tmp_path, monkeypatch):
    config = tmp_path / "claude-config"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))
    install(platform="claude")
    assert _registered(config / "CLAUDE.md")

    uninstall_all(project)

    assert not (config / "CLAUDE.md").exists()
    assert not _claude_md().exists(), "the default profile was touched"


def test_a_project_scoped_uninstall_leaves_the_global_registration(project):
    """#2215: a project-scoped uninstall keeps the global skill, so its
    registration must stay too."""
    install(platform="claude")

    claude_uninstall(project)
    install_mod._project_uninstall("claude", project)

    assert (Path.home() / ".claude" / "skills" / "graphify" / "SKILL.md").exists()
    assert _registered(_claude_md())


def test_uninstall_edits_a_symlinked_global_claude_md_in_place(requires_symlinks, project, tmp_path):
    dotfile = tmp_path / "dotfiles" / "CLAUDE.md"
    dotfile.parent.mkdir()
    dotfile.write_text(USER_NOTES, encoding="utf-8")
    _claude_md().parent.mkdir(parents=True)
    _claude_md().symlink_to(dotfile)
    install(platform="claude")
    assert _registered(dotfile)

    uninstall_all(project)

    assert _claude_md().is_symlink(), "the user's symlink was replaced or deleted"
    assert dotfile.read_text(encoding="utf-8") == USER_NOTES


def test_an_unwritable_global_claude_md_does_not_abort_the_uninstall(project, monkeypatch, capsys):
    """A CLAUDE.md that nix/home-manager links into a read-only store is skipped
    with a hint, as install already does (#3474); the rest of uninstall runs."""
    install(platform="claude")
    install(platform="codebuddy")

    real_write = install_mod._write_keep_newline

    def refuse(path, text, newline="\n"):
        if Path(path) == _claude_md():
            raise PermissionError(13, "Read-only file system", str(path))
        return real_write(path, text, newline)

    monkeypatch.setattr(install_mod, "_write_keep_newline", refuse)
    monkeypatch.setattr(Path, "unlink", _refusing_unlink(Path.unlink, _claude_md()))

    uninstall_all(project)

    err = capsys.readouterr().err
    assert "CLAUDE.md" in err and "skipped" in err, err
    assert _registered(_claude_md()), "a refused write must leave the file as it was"
    # Everything after the refused file still ran.
    assert not (Path.home() / ".claude" / "skills" / "graphify" / "SKILL.md").exists()
    assert not _codebuddy_md().exists()


def _refusing_unlink(real_unlink, refused: Path):
    def unlink(self, *args, **kwargs):
        if self == refused:
            raise PermissionError(13, "Read-only file system", str(self))
        return real_unlink(self, *args, **kwargs)
    return unlink


@pytest.mark.parametrize("uninstall", ["graphify uninstall", "graphify codebuddy uninstall"])
def test_uninstall_removes_the_global_codebuddy_registration(project, uninstall):
    install(platform="codebuddy")
    assert _registered(_codebuddy_md())

    # Neither call finds a project CODEBUDDY.md here, the path that returned early.
    assert not (project / "CODEBUDDY.md").exists()
    if uninstall == "graphify uninstall":
        uninstall_all(project)
    else:
        codebuddy_uninstall()

    assert not (Path.home() / ".codebuddy" / "skills" / "graphify" / "SKILL.md").exists()
    assert not _codebuddy_md().exists()


def test_uninstall_keeps_the_users_own_codebuddy_md_content(project):
    _codebuddy_md().parent.mkdir(parents=True)
    _codebuddy_md().write_text(USER_NOTES, encoding="utf-8")
    install(platform="codebuddy")

    uninstall_all(project)

    assert _codebuddy_md().read_text(encoding="utf-8") == USER_NOTES


def test_a_second_uninstall_is_a_no_op(project):
    _claude_md().parent.mkdir(parents=True)
    _claude_md().write_text(USER_NOTES, encoding="utf-8")
    install(platform="claude")
    uninstall_all(project)
    after_first = _claude_md().read_bytes()

    uninstall_all(project)

    assert _claude_md().read_bytes() == after_first


def test_a_users_deeper_graphify_heading_survives(project):
    """Only the exact `# graphify` H1 block install wrote goes (#2062)."""
    notes = "# My notes\n\n## graphify\nmy own notes about graphify\n"
    _claude_md().parent.mkdir(parents=True)
    _claude_md().write_text(notes, encoding="utf-8")
    install(platform="claude")

    uninstall_all(project)

    assert _claude_md().read_text(encoding="utf-8") == notes


@pytest.mark.parametrize("relocated", [False, True], ids=["default", "CLAUDE_CONFIG_DIR"])
def test_uninstall_resolves_the_file_install_wrote(project, tmp_path, monkeypatch, relocated):
    """Install and uninstall each work out the global CLAUDE.md; a relocated
    profile must not be written by one and missed by the other (#2694)."""
    if relocated:
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude-config"))
    install(platform="claude")

    md, skill_ref = install_mod._claude_global_registration()

    assert _registered(md)
    assert f"(`{skill_ref}`)" in md.read_text(encoding="utf-8")
    assert install_mod._codebuddy_global_registration() == _codebuddy_md()


# The global files belong to the user, and every `graphify uninstall` visits
# them, also for users who never installed the skill there.

HAND_WRITTEN = {
    "notes only": "# graphify\nAlways run graphify update after edits.\n",
    "notes, then another H1": "# graphify\nmy rule\n\n# Other\nkeep\n",
    "a bullet naming graphify": "# graphify\n- **graphify** (`~/tools/graphify`) is my graph CLI\n",
}


@pytest.mark.parametrize("notes", sorted(HAND_WRITTEN))
@pytest.mark.parametrize("which", ["CLAUDE.md", "CODEBUDDY.md"])
def test_a_hand_written_graphify_section_in_a_global_file_survives(project, notes, which):
    md = _claude_md() if which == "CLAUDE.md" else _codebuddy_md()
    md.parent.mkdir(parents=True)
    md.write_text(HAND_WRITTEN[notes], encoding="utf-8")
    install(platform="codex")

    uninstall_all(project)

    assert md.read_text(encoding="utf-8") == HAND_WRITTEN[notes]


def test_a_global_file_with_both_kinds_of_section_is_left_with_a_hint(project, capsys):
    _claude_md().parent.mkdir(parents=True)
    _claude_md().write_text("# notes\n", encoding="utf-8")
    install(platform="claude")
    mixed = _claude_md().read_text(encoding="utf-8") + "\n# graphify\nmy own notes\n"
    _claude_md().write_text(mixed, encoding="utf-8")

    uninstall_all(project)

    assert _claude_md().read_text(encoding="utf-8") == mixed
    err = capsys.readouterr().err
    assert "did not write" in err and "by hand" in err, err


# What earlier versions appended: an em dash until the project-scope rework,
# a hyphen after it, both with a leading blank line and an older second line.
OLDER_BLOCKS = {
    "em dash": (
        "\n# graphify\n"
        "- **graphify** (`~/.claude/skills/graphify/SKILL.md`) "
        "— any input to knowledge graph. Trigger: `/graphify`\n"
        "When the user types `/graphify`, invoke the Skill tool "
        "with `skill: \"graphify\"` before doing anything else.\n"
    ),
    "hyphen": (
        "\n# graphify\n"
        "- **graphify** (`~/.claude/skills/graphify/SKILL.md`) "
        "- any input to knowledge graph. Trigger: `/graphify`\n"
        "When the user types `/graphify`, invoke the Skill tool "
        "with `skill: \"graphify\"` before doing anything else.\n"
    ),
}


@pytest.mark.parametrize("older", sorted(OLDER_BLOCKS))
def test_a_block_an_older_version_wrote_is_removed(project, older):
    _claude_md().parent.mkdir(parents=True)
    _claude_md().write_text(USER_NOTES + OLDER_BLOCKS[older], encoding="utf-8")

    uninstall_all(project)

    assert _claude_md().read_text(encoding="utf-8") == USER_NOTES


def test_a_bom_neither_hides_the_block_nor_is_lost(project):
    bom = "﻿"
    _claude_md().parent.mkdir(parents=True)
    _claude_md().write_text(bom + install_mod._skill_registration(), encoding="utf-8")
    uninstall_all(project)
    assert not _claude_md().exists()

    original = (bom + USER_NOTES).encode("utf-8")
    _claude_md().write_bytes(original)
    install(platform="claude")
    uninstall_all(project)
    assert _claude_md().read_bytes() == original


def test_an_unrelated_non_utf8_global_file_is_left_alone_quietly(project, capsys):
    raw = b"# notes\n\xff\xfe not utf-8\n"
    _claude_md().parent.mkdir(parents=True)
    _claude_md().write_bytes(raw)

    uninstall_all(project)

    assert _claude_md().read_bytes() == raw
    assert "skipped" not in capsys.readouterr().err
