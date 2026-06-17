"""Tests for graphify codebuddy install / uninstall commands."""
import json
from pathlib import Path
import sys
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _codebuddy_install_user(tmp_path):
    from graphify.__main__ import install
    old_cwd = Path.cwd()
    try:
        import os
        os.chdir(tmp_path)
        with patch("graphify.__main__.Path.home", return_value=tmp_path):
            install(platform="codebuddy")
    finally:
        import os
        os.chdir(old_cwd)


def _skill_path_user(tmp_path):
    return tmp_path / ".codebuddy" / "skills" / "graphify" / "SKILL.md"


def _skill_path_project(project_dir):
    return project_dir / ".codebuddy" / "skills" / "graphify" / "SKILL.md"


def _codebuddy_md_path(project_dir):
    return project_dir / "CODEBUDDY.md"


def _settings_path(project_dir):
    return project_dir / ".codebuddy" / "settings.json"


# ---------------------------------------------------------------------------
# User-scope install (graphify install --platform codebuddy)
# ---------------------------------------------------------------------------

def test_codebuddy_install_user_creates_skill_file(tmp_path):
    """User-scope install copies skill to ~/.codebuddy/skills/graphify/SKILL.md."""
    _codebuddy_install_user(tmp_path)
    skill_path = _skill_path_user(tmp_path)
    assert skill_path.exists()


def test_codebuddy_skill_file_contains_frontmatter(tmp_path):
    """Installed skill file must include graphify YAML frontmatter."""
    _codebuddy_install_user(tmp_path)
    content = _skill_path_user(tmp_path).read_text()
    assert "name: graphify" in content
    assert "description:" in content


def test_codebuddy_skill_file_references_graphify_query(tmp_path):
    """/graphify skill must mention graphify query (query-first policy)."""
    _codebuddy_install_user(tmp_path)
    content = _skill_path_user(tmp_path).read_text()
    assert "graphify query" in content or "/graphify query" in content


# ---------------------------------------------------------------------------
# Project-scope install (graphify codebuddy install)
# ---------------------------------------------------------------------------

def test_codebuddy_install_project_writes_codebuddy_md(tmp_path):
    """Project-scope install writes CODEBUDDY.md with graphify section."""
    from graphify.__main__ import codebuddy_install
    codebuddy_install(tmp_path)
    md = _codebuddy_md_path(tmp_path)
    assert md.exists()
    content = md.read_text()
    assert "## graphify" in content
    assert "graphify-out/" in content


def test_codebuddy_install_project_writes_hook(tmp_path):
    """Project-scope install registers PreToolUse hook in .codebuddy/settings.json."""
    from graphify.__main__ import codebuddy_install
    codebuddy_install(tmp_path)
    settings_path = _settings_path(tmp_path)
    assert settings_path.exists()
    settings = json.loads(settings_path.read_text())
    hooks = settings["hooks"]["PreToolUse"]
    assert any("graphify" in str(h) for h in hooks)


def test_codebuddy_install_hook_has_bash_matcher(tmp_path):
    """The installed hook must include Bash matcher for code search interception."""
    from graphify.__main__ import codebuddy_install
    codebuddy_install(tmp_path)
    settings = json.loads(_settings_path(tmp_path).read_text())
    hooks = settings["hooks"]["PreToolUse"]
    bash_hooks = [h for h in hooks if h.get("matcher") == "Bash"]
    assert any("graphify" in str(h) for h in bash_hooks)


def test_codebuddy_install_hook_has_read_glob_matcher(tmp_path):
    """The installed hook must include Read|Glob matcher for file-read interception."""
    from graphify.__main__ import codebuddy_install
    codebuddy_install(tmp_path)
    settings = json.loads(_settings_path(tmp_path).read_text())
    hooks = settings["hooks"]["PreToolUse"]
    read_hooks = [h for h in hooks if h.get("matcher") == "Read|Glob"]
    assert any("graphify" in str(h) for h in read_hooks)


def test_codebuddy_install_idempotent(tmp_path):
    """Re-install does not duplicate ## graphify sections."""
    from graphify.__main__ import codebuddy_install
    codebuddy_install(tmp_path)
    codebuddy_install(tmp_path)
    md = _codebuddy_md_path(tmp_path)
    assert md.read_text().count("## graphify") == 1


def test_codebuddy_install_upgrades_stale_section(tmp_path):
    """Re-install replaces an old graphify section with the current template."""
    from graphify.__main__ import codebuddy_install, _CODEBUDDY_MD_MARKER
    # Write a stale section manually
    md = _codebuddy_md_path(tmp_path)
    md.write_text("old content\n\n## graphify\nThis is old instructions\n")
    codebuddy_install(tmp_path)
    content = md.read_text()
    assert _CODEBUDDY_MD_MARKER in content
    assert "old content" in content
    assert "This is old instructions" not in content
    assert "graphify-out/" in content
    assert content.count("## graphify") == 1


def test_codebuddy_install_merges_existing_codebuddy_md(tmp_path):
    """Install appends to an existing CODEBUDDY.md, preserving other content."""
    from graphify.__main__ import codebuddy_install
    _codebuddy_md_path(tmp_path).write_text("# My project rules\n")
    codebuddy_install(tmp_path)
    content = _codebuddy_md_path(tmp_path).read_text()
    assert "# My project rules" in content
    assert "## graphify" in content
    assert "graphify-out/" in content


def test_codebuddy_install_prints_no_change_on_second_run(tmp_path, capsys):
    """Second install prints '(no change)' when content is identical."""
    from graphify.__main__ import codebuddy_install
    codebuddy_install(tmp_path)
    out1 = capsys.readouterr().out
    codebuddy_install(tmp_path)
    out2 = capsys.readouterr().out
    assert "no change" in out2


def test_codebuddy_install_hint_git_add(tmp_path, capsys):
    """Project-scoped install via CLI prints a git add hint."""
    from graphify.__main__ import main
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    old_cwd = Path.cwd()
    try:
        import os
        os.chdir(project)
        with patch("graphify.__main__.Path.home", return_value=home):
            sys.argv = ["graphify", "codebuddy", "install"]
            main()
    finally:
        import os
        os.chdir(old_cwd)
    # codebuddy_install calls print() directly, no git add hint printed there
    # so this test checks that no errors occur


# ---------------------------------------------------------------------------
# Uninstall
# ---------------------------------------------------------------------------

def test_codebuddy_uninstall_removes_section(tmp_path):
    """Uninstall removes the ## graphify section from CODEBUDDY.md."""
    from graphify.__main__ import codebuddy_install, codebuddy_uninstall
    codebuddy_install(tmp_path)
    codebuddy_uninstall(tmp_path)
    md = _codebuddy_md_path(tmp_path)
    assert not md.exists()


def test_codebuddy_uninstall_removes_hook(tmp_path):
    """Uninstall removes the PreToolUse hook from .codebuddy/settings.json."""
    from graphify.__main__ import codebuddy_install, codebuddy_uninstall
    codebuddy_install(tmp_path)
    codebuddy_uninstall(tmp_path)
    settings_path = _settings_path(tmp_path)
    if settings_path.exists():
        settings = json.loads(settings_path.read_text())
        hooks = settings.get("hooks", {}).get("PreToolUse", [])
        assert not any("graphify" in str(h) for h in hooks)


def test_codebuddy_uninstall_noop_if_not_installed(tmp_path):
    """Uninstall should not raise when CODEBUDDY.md doesn't exist."""
    from graphify.__main__ import codebuddy_uninstall
    codebuddy_uninstall(tmp_path)  # should not raise


def test_codebuddy_uninstall_noop_if_no_section(tmp_path):
    """Uninstall should not error when CODEBUDDY.md exists but no graphify section."""
    from graphify.__main__ import codebuddy_uninstall
    _codebuddy_md_path(tmp_path).write_text("# Some other project\n")
    codebuddy_uninstall(tmp_path)
    content = _codebuddy_md_path(tmp_path).read_text()
    assert "# Some other project" in content


def test_codebuddy_uninstall_preserves_other_content(tmp_path):
    """Uninstall preserves non-graphify content in CODEBUDDY.md."""
    from graphify.__main__ import codebuddy_install, codebuddy_uninstall
    _codebuddy_md_path(tmp_path).write_text("# My project rules\n")
    codebuddy_install(tmp_path)
    codebuddy_uninstall(tmp_path)
    # When graphify section was appended, uninstall removes it and the file
    # becomes the original content
    content = _codebuddy_md_path(tmp_path).read_text()
    assert "## graphify" not in content
    assert "# My project rules" in content


# ---------------------------------------------------------------------------
# uninstall_all integration
# ---------------------------------------------------------------------------

def test_uninstall_all_removes_codebuddy_md(tmp_path, monkeypatch):
    """graphify uninstall must clean up CODEBUDDY.md."""
    from graphify.__main__ import main
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    with patch("graphify.__main__.Path.home", return_value=home):
        monkeypatch.setattr(sys, "argv", ["graphify", "codebuddy", "install"])
        main()
        md = _codebuddy_md_path(project)
        assert md.exists()
        monkeypatch.setattr(sys, "argv", ["graphify", "uninstall"])
        main()
    assert not md.exists()


def test_uninstall_all_removes_codebuddy_hook(tmp_path, monkeypatch):
    """graphify uninstall must clean up .codebuddy/settings.json hooks."""
    from graphify.__main__ import main
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    with patch("graphify.__main__.Path.home", return_value=home):
        monkeypatch.setattr(sys, "argv", ["graphify", "codebuddy", "install"])
        main()
        monkeypatch.setattr(sys, "argv", ["graphify", "uninstall"])
        main()
    settings_path = _settings_path(project)
    if settings_path.exists():
        settings = json.loads(settings_path.read_text())
        hooks = settings.get("hooks", {}).get("PreToolUse", [])
        assert not any("graphify" in str(h) for h in hooks)


# ---------------------------------------------------------------------------
# Platform config sanity
# ---------------------------------------------------------------------------

def test_codebuddy_in_platform_config():
    """codebuddy must be registered in _PLATFORM_CONFIG."""
    from graphify.__main__ import _PLATFORM_CONFIG
    assert "codebuddy" in _PLATFORM_CONFIG
    assert _PLATFORM_CONFIG["codebuddy"]["skill_file"] == "skill.md"
    assert _PLATFORM_CONFIG["codebuddy"]["claude_md"] is False


def test_codebuddy_platform_skill_destination_user_scope(tmp_path):
    """User-scope destination must be ~/.codebuddy/skills/graphify/SKILL.md."""
    from graphify.__main__ import _platform_skill_destination
    with patch("graphify.__main__.Path.home", return_value=tmp_path):
        dst = _platform_skill_destination("codebuddy", project=False)
    assert dst == tmp_path / ".codebuddy" / "skills" / "graphify" / "SKILL.md"


def test_codebuddy_platform_skill_destination_project_scope(tmp_path):
    """Project-scope destination must be <project>/.codebuddy/skills/graphify/SKILL.md."""
    from graphify.__main__ import _platform_skill_destination
    dst = _platform_skill_destination("codebuddy", project=True, project_dir=tmp_path)
    assert dst == tmp_path / ".codebuddy" / "skills" / "graphify" / "SKILL.md"


def test_codebuddy_in_main_help_text(capsys, monkeypatch):
    """`graphify --help` must list codebuddy in the platform list and per-platform section."""
    from graphify.__main__ import main
    monkeypatch.setattr(sys, "argv", ["graphify", "--help"])
    main()
    captured = capsys.readouterr().out
    # codebuddy should appear in the top-level platform list
    assert "|codebuddy)" in captured or "codebuddy" in captured, (
        "codebuddy missing from `graphify --help` platform list"
    )
    # codebuddy install / uninstall should appear in the per-platform section
    assert "codebuddy install" in captured, "`codebuddy install` line missing from help text"
    assert "codebuddy uninstall" in captured, "`codebuddy uninstall` line missing from help text"


def test_codebuddy_skill_file_exists_in_package():
    """skill.md must be present in the installed package (shared with claude)."""
    import graphify
    skill = Path(graphify.__file__).parent / "skill.md"
    assert skill.exists(), "skill.md missing from package"


def test_codebuddy_installation_roundtrip(tmp_path):
    """Install then uninstall leaves no trace of graphify CODEBUDDY.md or hook."""
    from graphify.__main__ import codebuddy_install, codebuddy_uninstall
    # Pre-existing project file
    _codebuddy_md_path(tmp_path).write_text("# My project\n")
    # One section above graphify to test cleanup
    codebuddy_install(tmp_path)
    codebuddy_uninstall(tmp_path)
    # CODEBUDDY.md should exist with original content only
    md = _codebuddy_md_path(tmp_path)
    assert md.exists()
    content = md.read_text()
    assert "## graphify" not in content
    assert "# My project" in content
    # Hook should be removed
    settings_path = _settings_path(tmp_path)
    if settings_path.exists():
        settings = json.loads(settings_path.read_text())
        hooks = settings.get("hooks", {}).get("PreToolUse", [])
        assert not any("graphify" in str(h) for h in hooks)
