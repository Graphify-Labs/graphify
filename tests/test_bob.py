"""Tests for graphify bob install / uninstall commands (IBM Bob)."""
from pathlib import Path
import sys
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bob_install_user(tmp_path):
    from graphify.__main__ import install
    import os
    old_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        with patch("graphify.__main__.Path.home", return_value=tmp_path):
            install(platform="bob")
    finally:
        os.chdir(old_cwd)


def _skill_path_user(tmp_path):
    return tmp_path / ".bob" / "skills" / "graphify" / "SKILL.md"


def _skill_path_project(project_dir):
    return project_dir / ".bob" / "skills" / "graphify" / "SKILL.md"


def _rules_path(project_dir):
    return project_dir / ".bob" / "rules" / "graphify.md"


# ---------------------------------------------------------------------------
# User-scope install (graphify install --platform bob)
# ---------------------------------------------------------------------------

def test_bob_install_user_creates_skill_file(tmp_path):
    """User-scope install copies skill to ~/.bob/skills/graphify/SKILL.md."""
    _bob_install_user(tmp_path)
    assert _skill_path_user(tmp_path).exists()


def test_bob_install_user_installs_references_sidecar(tmp_path):
    """Bob rides kiro's split bundle, so references/ must land next to SKILL.md."""
    _bob_install_user(tmp_path)
    refs = _skill_path_user(tmp_path).parent / "references"
    assert refs.is_dir()


def test_bob_skill_file_references_graphify_query(tmp_path):
    """The skill must mention graphify query (query-first policy)."""
    _bob_install_user(tmp_path)
    content = _skill_path_user(tmp_path).read_text(encoding="utf-8")
    assert "graphify query" in content or "/graphify query" in content


def test_bob_install_user_does_not_write_rules(tmp_path):
    """User-scope install does NOT write .bob/rules/ — that's project-only."""
    _bob_install_user(tmp_path)
    assert not _rules_path(tmp_path).exists()


# ---------------------------------------------------------------------------
# Project install (graphify bob install)
# ---------------------------------------------------------------------------

def test_bob_install_creates_skill_and_rules(tmp_path, monkeypatch):
    """`graphify bob install` writes .bob/skills/ + .bob/rules/graphify.md."""
    from graphify.__main__ import main
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    monkeypatch.setattr(sys, "argv", ["graphify", "bob", "install"])
    with patch("graphify.__main__.Path.home", return_value=home):
        main()
    assert _skill_path_project(project).exists()
    assert _rules_path(project).exists()
    assert not _skill_path_user(home).exists()


def test_bob_rules_content_recommends_graphify_query(tmp_path):
    """The rules file must use the query-first policy."""
    from graphify.__main__ import _bob_install
    _bob_install(tmp_path)
    content = _rules_path(tmp_path).read_text(encoding="utf-8")
    assert "graphify query" in content
    assert "GRAPH_REPORT.md" in content


def test_bob_install_idempotent(tmp_path, capsys):
    """Installing twice does not change the rules file and prints 'no change'."""
    from graphify.__main__ import _bob_install
    _bob_install(tmp_path)
    content_first = _rules_path(tmp_path).read_text(encoding="utf-8")
    _bob_install(tmp_path)
    content_second = _rules_path(tmp_path).read_text(encoding="utf-8")
    assert content_first == content_second
    assert "no change" in capsys.readouterr().out


def test_bob_install_project_flag_hints_git_add(tmp_path, monkeypatch, capsys):
    """`graphify install --project --platform bob` prints a git add hint."""
    from graphify.__main__ import main
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    monkeypatch.setattr(sys, "argv", ["graphify", "install", "--project", "--platform", "bob"])
    with patch("graphify.__main__.Path.home", return_value=home):
        main()
    out = capsys.readouterr().out
    assert "git add" in out
    assert _skill_path_project(project).exists()
    assert _rules_path(project).exists()


# ---------------------------------------------------------------------------
# Uninstall
# ---------------------------------------------------------------------------

def test_bob_uninstall_removes_skill_and_rules(tmp_path, monkeypatch):
    """`graphify bob uninstall` removes both the skill tree and the rules file."""
    from graphify.__main__ import main
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    with patch("graphify.__main__.Path.home", return_value=home):
        monkeypatch.setattr(sys, "argv", ["graphify", "bob", "install"])
        main()
        monkeypatch.setattr(sys, "argv", ["graphify", "bob", "uninstall"])
        main()
    assert not _skill_path_project(project).exists()
    assert not _rules_path(project).exists()


def test_bob_uninstall_noop_when_not_installed(tmp_path, monkeypatch, capsys):
    """Uninstall prints 'nothing to remove' when nothing is installed."""
    from graphify.__main__ import main
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["graphify", "bob", "uninstall"])
    with patch("graphify.__main__.Path.home", return_value=tmp_path):
        main()
    assert "nothing to remove" in capsys.readouterr().out


def test_bob_uninstall_does_not_touch_user_scope(tmp_path, monkeypatch):
    """Project uninstall must not remove the user-scope skill file."""
    from graphify.__main__ import main
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    user_skill = _skill_path_user(home)
    user_skill.parent.mkdir(parents=True, exist_ok=True)
    user_skill.write_text("user skill")
    monkeypatch.chdir(project)
    with patch("graphify.__main__.Path.home", return_value=home):
        monkeypatch.setattr(sys, "argv", ["graphify", "bob", "install"])
        main()
        monkeypatch.setattr(sys, "argv", ["graphify", "bob", "uninstall"])
        main()
    assert user_skill.exists()


# ---------------------------------------------------------------------------
# Platform config sanity
# ---------------------------------------------------------------------------

def test_bob_in_platform_config():
    """bob must be registered in _PLATFORM_CONFIG, riding kiro's bundle."""
    from graphify.__main__ import _PLATFORM_CONFIG
    assert "bob" in _PLATFORM_CONFIG
    assert _PLATFORM_CONFIG["bob"]["skill_file"] == "skill-kiro.md"
    assert _PLATFORM_CONFIG["bob"]["skill_refs"] == "kiro"
    assert _PLATFORM_CONFIG["bob"]["claude_md"] is False


def test_bob_platform_skill_destination_user_scope(tmp_path):
    """User-scope destination must be ~/.bob/skills/graphify/SKILL.md."""
    from graphify.__main__ import _platform_skill_destination
    with patch("graphify.__main__.Path.home", return_value=tmp_path):
        dst = _platform_skill_destination("bob", project=False)
    assert dst == tmp_path / ".bob" / "skills" / "graphify" / "SKILL.md"


def test_bob_platform_skill_destination_project_scope(tmp_path):
    """Project-scope destination must be <project>/.bob/skills/graphify/SKILL.md."""
    from graphify.__main__ import _platform_skill_destination
    dst = _platform_skill_destination("bob", project=True, project_dir=tmp_path)
    assert dst == tmp_path / ".bob" / "skills" / "graphify" / "SKILL.md"


def test_bob_in_main_help_text(capsys, monkeypatch):
    """`graphify --help` must list bob in the platform list and per-platform section."""
    from graphify.__main__ import main
    monkeypatch.setattr(sys, "argv", ["graphify", "--help"])
    main()
    captured = capsys.readouterr().out
    assert "|bob" in captured, "bob missing from `graphify --help` platform list"
    assert "bob install" in captured, "`bob install` line missing from help text"
    assert "bob uninstall" in captured, "`bob uninstall` line missing from help text"
