"""Tests for graphify claude install / uninstall commands."""
from pathlib import Path
import pytest
from graphify.__main__ import claude_install, claude_uninstall, _CLAUDE_MD_MARKER, _CLAUDE_MD_SECTION


# ---------------------------------------------------------------------------
# install
# ---------------------------------------------------------------------------

def test_install_creates_claude_md(tmp_path):
    """Creates CLAUDE.md when none exists."""
    claude_install(tmp_path)
    target = tmp_path / "CLAUDE.md"
    assert target.exists()
    assert _CLAUDE_MD_MARKER in target.read_text()


def test_install_contains_expected_rules(tmp_path):
    """Written section includes the three rules."""
    claude_install(tmp_path)
    content = (tmp_path / "CLAUDE.md").read_text()
    assert "GRAPH_REPORT.md" in content
    assert "wiki/index.md" in content
    assert "graphify update" in content


def test_install_appends_to_existing_claude_md(tmp_path):
    """Appends to an existing CLAUDE.md without clobbering it."""
    target = tmp_path / "CLAUDE.md"
    target.write_text("# Existing content\n\nSome rules here.\n")
    claude_install(tmp_path)
    content = target.read_text()
    assert "Existing content" in content
    assert _CLAUDE_MD_MARKER in content


def test_install_is_idempotent(tmp_path, capsys):
    """Running install twice does not duplicate the section."""
    claude_install(tmp_path)
    claude_install(tmp_path)
    content = (tmp_path / "CLAUDE.md").read_text()
    assert content.count(_CLAUDE_MD_MARKER) == 1
    captured = capsys.readouterr()
    assert "already configured" in captured.out


def test_install_idempotent_message(tmp_path, capsys):
    """Second install prints the 'already configured' message."""
    claude_install(tmp_path)
    capsys.readouterr()  # clear first call output
    claude_install(tmp_path)
    out = capsys.readouterr().out
    assert "already configured" in out


# ---------------------------------------------------------------------------
# uninstall
# ---------------------------------------------------------------------------

def test_uninstall_removes_section(tmp_path):
    """Removes the graphify section after it was installed."""
    claude_install(tmp_path)
    claude_uninstall(tmp_path)
    target = tmp_path / "CLAUDE.md"
    # File may or may not exist depending on whether it was empty
    if target.exists():
        assert _CLAUDE_MD_MARKER not in target.read_text()


def test_uninstall_preserves_other_content(tmp_path):
    """Uninstall keeps pre-existing content outside the graphify section."""
    target = tmp_path / "CLAUDE.md"
    target.write_text("# My Project\n\nSome rules.\n")
    claude_install(tmp_path)
    claude_uninstall(tmp_path)
    assert target.exists()
    content = target.read_text()
    assert "My Project" in content
    assert "Some rules" in content
    assert _CLAUDE_MD_MARKER not in content


def test_uninstall_no_op_when_not_installed(tmp_path, capsys):
    """Uninstall on a CLAUDE.md without graphify section prints a message and exits cleanly."""
    target = tmp_path / "CLAUDE.md"
    target.write_text("# Other stuff\n")
    claude_uninstall(tmp_path)
    out = capsys.readouterr().out
    assert "not found" in out or "nothing to do" in out


def test_uninstall_no_op_when_no_file(tmp_path, capsys):
    """Uninstall when no CLAUDE.md exists prints a message and exits cleanly."""
    claude_uninstall(tmp_path)
    out = capsys.readouterr().out
    assert "No CLAUDE.md" in out or "nothing to do" in out


# ---------------------------------------------------------------------------
# settings.json PreToolUse hook
# ---------------------------------------------------------------------------

def test_install_creates_settings_json(tmp_path):
    """claude_install also writes .claude/settings.json with PreToolUse hook."""
    import json
    claude_install(tmp_path)
    settings_path = tmp_path / ".claude" / "settings.json"
    assert settings_path.exists()
    settings = json.loads(settings_path.read_text())
    hooks = settings.get("hooks", {}).get("PreToolUse", [])
    assert any(h.get("matcher") == "Bash" for h in hooks)


def test_install_settings_json_idempotent(tmp_path):
    """Running claude_install twice does not duplicate the PreToolUse hook."""
    import json
    claude_install(tmp_path)
    claude_install(tmp_path)
    settings_path = tmp_path / ".claude" / "settings.json"
    settings = json.loads(settings_path.read_text())
    hooks = settings.get("hooks", {}).get("PreToolUse", [])
    bash_hooks = [h for h in hooks if h.get("matcher") == "Bash" and "graphify" in str(h)]
    assert len(bash_hooks) == 1


def test_uninstall_removes_settings_hook(tmp_path):
    """claude_uninstall removes the PreToolUse hook from settings.json."""
    import json
    claude_install(tmp_path)
    claude_uninstall(tmp_path)
    settings_path = tmp_path / ".claude" / "settings.json"
    if settings_path.exists():
        settings = json.loads(settings_path.read_text())
        hooks = settings.get("hooks", {}).get("PreToolUse", [])
        assert not any(h.get("matcher") == "Bash" and "graphify" in str(h) for h in hooks)


# ---------------------------------------------------------------------------
# local-only variants: settings.local.json / CLAUDE.local.md (#1731)
# ---------------------------------------------------------------------------

def test_uninstall_removes_hook_from_settings_local_json(tmp_path):
    """A hook relocated to .claude/settings.local.json is removed on uninstall."""
    import json
    claude_install(tmp_path)
    # User moved the hook out of the committed settings.json into the local-only file.
    (tmp_path / ".claude" / "settings.json").rename(tmp_path / ".claude" / "settings.local.json")
    claude_uninstall(tmp_path)
    local = tmp_path / ".claude" / "settings.local.json"
    hooks = json.loads(local.read_text()).get("hooks", {}).get("PreToolUse", [])
    assert not any("graphify" in str(h) for h in hooks)


def test_uninstall_removes_section_from_dot_claude_local_md(tmp_path):
    """Instructions relocated to .claude/CLAUDE.local.md are removed on uninstall."""
    claude_install(tmp_path)
    local_md = tmp_path / ".claude" / "CLAUDE.local.md"
    local_md.write_text((tmp_path / "CLAUDE.md").read_text())
    (tmp_path / "CLAUDE.md").unlink()
    claude_uninstall(tmp_path)
    assert not local_md.exists() or _CLAUDE_MD_MARKER not in local_md.read_text()


def test_uninstall_removes_section_from_root_claude_local_md(tmp_path):
    """Instructions relocated to root CLAUDE.local.md are removed on uninstall."""
    claude_install(tmp_path)
    local_md = tmp_path / "CLAUDE.local.md"
    local_md.write_text((tmp_path / "CLAUDE.md").read_text())
    (tmp_path / "CLAUDE.md").unlink()
    claude_uninstall(tmp_path)
    assert not local_md.exists() or _CLAUDE_MD_MARKER not in local_md.read_text()


def test_uninstall_cleans_both_standard_and_local(tmp_path):
    """When the section lives in both CLAUDE.md and a local variant, both are cleaned."""
    claude_install(tmp_path)
    claude_md = tmp_path / "CLAUDE.md"
    local_md = tmp_path / ".claude" / "CLAUDE.local.md"
    local_md.write_text(claude_md.read_text())  # duplicated into the local file too
    claude_uninstall(tmp_path)
    for f in (claude_md, local_md):
        assert not f.exists() or _CLAUDE_MD_MARKER not in f.read_text()


def test_uninstall_preserves_other_content_in_local_md(tmp_path):
    """Uninstall keeps non-graphify content in CLAUDE.local.md."""
    claude_install(tmp_path)
    local_md = tmp_path / ".claude" / "CLAUDE.local.md"
    local_md.write_text("# Local notes\n\nkeep me\n\n" + (tmp_path / "CLAUDE.md").read_text())
    claude_uninstall(tmp_path)
    assert local_md.exists()
    content = local_md.read_text()
    assert "Local notes" in content
    assert "keep me" in content
    assert _CLAUDE_MD_MARKER not in content


def test_uninstall_tolerates_unreadable_local_md(tmp_path):
    """A non-UTF-8 CLAUDE.local.md must not abort uninstall (it has no marker to strip)."""
    claude_install(tmp_path)
    local_md = tmp_path / ".claude" / "CLAUDE.local.md"
    local_md.write_bytes(b"\xff\xfe not valid utf-8 \x80\x81")
    claude_uninstall(tmp_path)  # must not raise
    assert local_md.read_bytes() == b"\xff\xfe not valid utf-8 \x80\x81"  # left untouched
