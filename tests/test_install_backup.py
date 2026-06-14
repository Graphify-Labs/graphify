"""Tests for the install/uninstall backup safety net (_backup_config_file)."""
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    """Sandbox Path.home() so backups land under the temp dir, never the real
    ~/.graphify/backups."""
    home = tmp_path / "_home"
    home.mkdir()
    monkeypatch.setattr("graphify.__main__.Path.home", lambda: home)
    monkeypatch.delenv("GRAPHIFY_NO_BACKUP", raising=False)
    return home


def _backups_root(home):
    return home / ".graphify" / "backups"


def test_backup_noop_when_file_absent(tmp_path, _isolated_home):
    from graphify.__main__ import _backup_config_file
    assert _backup_config_file(tmp_path / "does-not-exist.md") is None
    assert not _backups_root(_isolated_home).exists()


def test_backup_copies_existing_file(tmp_path, _isolated_home):
    from graphify.__main__ import _backup_config_file
    f = tmp_path / "CLAUDE.md"
    f.write_text("original user content\n")
    dst = _backup_config_file(f)
    assert dst is not None and dst.exists()
    assert dst.read_text() == "original user content\n"
    assert _backups_root(_isolated_home) in dst.parents


def test_backup_disabled_by_env(tmp_path, monkeypatch, _isolated_home):
    from graphify.__main__ import _backup_config_file
    monkeypatch.setenv("GRAPHIFY_NO_BACKUP", "1")
    f = tmp_path / "CLAUDE.md"
    f.write_text("content\n")
    assert _backup_config_file(f) is None
    assert not _backups_root(_isolated_home).exists()


def test_install_backs_up_existing_claude_md(tmp_path, monkeypatch, _isolated_home):
    """A global install that appends to an existing ~/.claude/CLAUDE.md snapshots
    the pre-install file first."""
    from graphify.__main__ import install
    monkeypatch.chdir(tmp_path)
    home_md = _isolated_home / ".claude" / "CLAUDE.md"
    home_md.parent.mkdir(parents=True, exist_ok=True)
    home_md.write_text("# pre-existing rules\n")

    install(platform="claude")  # appends the # graphify block → triggers backup

    backups = list(_backups_root(_isolated_home).rglob("*CLAUDE.md"))
    assert backups, "expected a CLAUDE.md backup under ~/.graphify/backups/"
    assert any("pre-existing rules" in b.read_text() for b in backups)


def test_uninstall_backs_up_before_stripping(tmp_path, monkeypatch, _isolated_home):
    """Uninstall snapshots CLAUDE.md before it strips the graphify section."""
    from graphify.__main__ import claude_install, claude_uninstall
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "CLAUDE.md"
    target.write_text("# my project\n\nkeep this.\n")
    claude_install(tmp_path)  # appends ## graphify section
    claude_uninstall(tmp_path)  # strips it → backup of the pre-strip file

    backups = list(_backups_root(_isolated_home).rglob("*CLAUDE.md"))
    assert backups, "expected a CLAUDE.md backup before uninstall stripped it"
