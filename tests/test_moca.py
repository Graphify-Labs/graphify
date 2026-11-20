"""Tests for graphify moca install / uninstall commands.

moca (https://github.com/adeotek/moca) is a skill-only Agent-Skills host:
it loads ~/.config/moca/skills/<name>/SKILL.md (or $XDG_CONFIG_HOME/moca/...)
and <project>/.moca/skills/<name>/SKILL.md. These tests pin the platform
registration, both scope destinations, the installed layout (SKILL.md +
references/ sidecar) and the CLI dispatch.
"""
from pathlib import Path
import os
import sys
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _moca_install_user(tmp_path):
    from graphify.__main__ import install
    old_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        with patch("graphify.__main__.Path.home", return_value=tmp_path):
            install(platform="moca")
    finally:
        os.chdir(old_cwd)


def _skill_path_user(tmp_path):
    return tmp_path / ".config" / "moca" / "skills" / "graphify" / "SKILL.md"


def _skill_path_project(project_dir):
    return project_dir / ".moca" / "skills" / "graphify" / "SKILL.md"


# ---------------------------------------------------------------------------
# User-scope install (graphify install --platform moca / graphify moca install)
# ---------------------------------------------------------------------------

def test_moca_install_user_creates_skill_file(tmp_path):
    """User-scope install copies the skill to ~/.config/moca/skills/graphify/SKILL.md."""
    _moca_install_user(tmp_path)
    assert _skill_path_user(tmp_path).exists()


def test_moca_install_user_creates_references_sidecar(tmp_path):
    """moca opts into progressive disclosure: the references/ sidecar ships too."""
    _moca_install_user(tmp_path)
    refs = _skill_path_user(tmp_path).parent / "references"
    assert (refs / "query.md").exists()


def test_moca_skill_file_contains_frontmatter(tmp_path):
    """Installed skill file must keep its YAML frontmatter (name + description)."""
    _moca_install_user(tmp_path)
    content = _skill_path_user(tmp_path).read_text()
    assert "name: graphify" in content
    assert "description:" in content


def test_moca_install_user_writes_no_rules_file(tmp_path):
    """moca has no always-on rules file: only the skill dir is written."""
    _moca_install_user(tmp_path)
    assert not (tmp_path / "AGENTS.md").exists()
    assert not (tmp_path / "CLAUDE.md").exists()


def test_moca_install_user_honors_xdg_config_home(tmp_path, monkeypatch):
    """With XDG_CONFIG_HOME set, the skill lands where moca actually reads it."""
    xdg = tmp_path / "xdg"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    _moca_install_user(tmp_path)
    assert (xdg / "moca" / "skills" / "graphify" / "SKILL.md").exists()
    assert not _skill_path_user(tmp_path).exists()


# ---------------------------------------------------------------------------
# User-scope uninstall
# ---------------------------------------------------------------------------

def test_moca_uninstall_user_removes_skill_file(tmp_path, capsys):
    from graphify.install import _remove_skill_file

    _moca_install_user(tmp_path)
    with patch("graphify.__main__.Path.home", return_value=tmp_path):
        removed = _remove_skill_file("moca")
    assert removed
    assert not _skill_path_user(tmp_path).exists()


def test_moca_uninstall_user_noop_when_not_installed(tmp_path, capsys):
    from graphify.install import _remove_skill_file

    with patch("graphify.__main__.Path.home", return_value=tmp_path):
        removed = _remove_skill_file("moca")
    assert not removed


# ---------------------------------------------------------------------------
# Project-scope install (graphify moca install --project)
# ---------------------------------------------------------------------------

def test_moca_install_project_creates_skill_file(tmp_path, monkeypatch):
    from graphify.install import _project_install

    proj = tmp_path / "proj"
    proj.mkdir()
    monkeypatch.chdir(proj)
    _project_install("moca", proj)
    assert _skill_path_project(proj).exists()


def test_moca_uninstall_project_removes_skill_file(tmp_path, monkeypatch, capsys):
    from graphify.install import _project_install, _project_uninstall

    proj = tmp_path / "proj"
    proj.mkdir()
    monkeypatch.chdir(proj)
    _project_install("moca", proj)
    _project_uninstall("moca", proj)
    assert not _skill_path_project(proj).exists()


# ---------------------------------------------------------------------------
# Platform config sanity
# ---------------------------------------------------------------------------

def test_moca_in_platform_config():
    """moca must be registered in _PLATFORM_CONFIG, reusing claude's bundle."""
    from graphify.__main__ import _PLATFORM_CONFIG
    assert "moca" in _PLATFORM_CONFIG
    assert _PLATFORM_CONFIG["moca"]["skill_file"] == "skill.md"
    assert _PLATFORM_CONFIG["moca"]["claude_md"] is False
    assert _PLATFORM_CONFIG["moca"]["skill_refs"] == "claude"


def test_moca_platform_skill_destination_user_scope(tmp_path):
    """User scope must be ~/.config/moca/skills/graphify/SKILL.md (no XDG set)."""
    from graphify.__main__ import _platform_skill_destination
    with patch("graphify.__main__.Path.home", return_value=tmp_path):
        dst = _platform_skill_destination("moca", project=False)
    assert dst == tmp_path / ".config" / "moca" / "skills" / "graphify" / "SKILL.md"


def test_moca_platform_skill_destination_user_scope_xdg(tmp_path, monkeypatch):
    """User scope must honor $XDG_CONFIG_HOME like moca itself does."""
    from graphify.__main__ import _platform_skill_destination
    xdg = tmp_path / "xdg"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    with patch("graphify.__main__.Path.home", return_value=tmp_path):
        dst = _platform_skill_destination("moca", project=False)
    assert dst == xdg / "moca" / "skills" / "graphify" / "SKILL.md"


def test_moca_platform_skill_destination_project_scope(tmp_path):
    """Project scope must be <project>/.moca/skills/graphify/SKILL.md."""
    from graphify.__main__ import _platform_skill_destination
    dst = _platform_skill_destination("moca", project=True, project_dir=tmp_path)
    assert dst == tmp_path / ".moca" / "skills" / "graphify" / "SKILL.md"


def test_moca_in_main_help_text(capsys, monkeypatch):
    """`graphify --help` must list moca in the platform list and per-platform section."""
    from graphify.__main__ import main
    monkeypatch.setattr(sys, "argv", ["graphify", "--help"])
    main()
    captured = capsys.readouterr().out
    assert "|moca" in captured, "moca missing from `graphify --help` platform list"
    assert "moca install" in captured, "`moca install` line missing from help text"
    assert "moca uninstall" in captured, "`moca uninstall` line missing from help text"
    assert "~/.config/moca" in captured, "moca user-scope path missing from help text"
    # Convention: `--project` is supported by all platforms but documented by none.
    moca_section = captured.split("moca install", 1)[1].split("\n\n", 1)[0]
    assert "--project" not in moca_section, (
        "moca help should NOT document --project — no other platform does"
    )


def test_moca_cli_install_and_uninstall(tmp_path, monkeypatch):
    """`graphify moca install` / `graphify moca uninstall` dispatch to the skill copy."""
    from graphify.__main__ import main

    monkeypatch.chdir(tmp_path)
    skill = Path.home() / ".config" / "moca" / "skills" / "graphify" / "SKILL.md"

    monkeypatch.setattr(sys, "argv", ["graphify", "moca", "install"])
    main()
    assert skill.exists()

    monkeypatch.setattr(sys, "argv", ["graphify", "moca", "uninstall"])
    main()
    assert not skill.exists()
