"""Regression tests for atomic `.graphify_version` stamp writes (#3286)."""
from __future__ import annotations

import os
import stat
import sys

import pytest

import graphify.install as install


def test_write_version_stamp_is_atomic_and_cleans_tmp(tmp_path):
    skill_dst = tmp_path / "skills" / "graphify" / "SKILL.md"
    skill_dst.parent.mkdir(parents=True)
    skill_dst.write_text("skill", encoding="utf-8")

    install._write_version_stamp(skill_dst, "1.2.3")

    stamp = skill_dst.parent / ".graphify_version"
    assert stamp.read_text(encoding="utf-8") == "1.2.3"
    assert {p.name for p in skill_dst.parent.iterdir()} == {"SKILL.md", ".graphify_version"}


def test_write_version_stamp_preserves_existing_on_replace_failure(tmp_path, monkeypatch):
    skill_dst = tmp_path / "skills" / "graphify" / "SKILL.md"
    skill_dst.parent.mkdir(parents=True)
    skill_dst.write_text("skill", encoding="utf-8")
    stamp = skill_dst.parent / ".graphify_version"
    stamp.write_text("old", encoding="utf-8")

    def boom(src, dst):
        raise OSError("simulated failure")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        install._write_version_stamp(skill_dst, "new")

    assert stamp.read_text(encoding="utf-8") == "old"
    assert not (skill_dst.parent / ".graphify_version.tmp").exists()


def test_write_version_stamp_replaces_symlink_instead_of_following(tmp_path):
    """Managed-dotfile case: os.replace must replace the symlink, not write through."""
    real_store = tmp_path / "dotfiles" / ".graphify_version"
    real_store.parent.mkdir(parents=True)
    real_store.write_text("from-dotfiles", encoding="utf-8")

    skill_dir = tmp_path / "skills" / "graphify"
    skill_dir.mkdir(parents=True)
    skill_dst = skill_dir / "SKILL.md"
    skill_dst.write_text("skill", encoding="utf-8")

    link = skill_dir / ".graphify_version"
    try:
        link.symlink_to(real_store)
    except OSError as exc:
        pytest.skip(f"symlink creation not permitted: {exc}")

    install._write_version_stamp(skill_dst, "installed")

    assert link.is_symlink() is False
    assert link.read_text(encoding="utf-8") == "installed"
    assert real_store.read_text(encoding="utf-8") == "from-dotfiles"


def test_write_version_stamp_ignores_precreated_predictable_tmp_symlink(tmp_path):
    """A pre-created symlink at .graphify_version.tmp must not overwrite its target."""
    sentinel = tmp_path / "outside" / "sentinel.txt"
    sentinel.parent.mkdir(parents=True)
    sentinel.write_text("sentinel-untouched\n", encoding="utf-8")

    skill_dir = tmp_path / "skills" / "graphify"
    skill_dir.mkdir(parents=True)
    skill_dst = skill_dir / "SKILL.md"
    skill_dst.write_text("skill", encoding="utf-8")

    predictable_tmp = skill_dir / ".graphify_version.tmp"
    try:
        predictable_tmp.symlink_to(sentinel)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation not permitted: {exc}")

    install._write_version_stamp(skill_dst, "1.2.3")

    assert sentinel.read_text(encoding="utf-8") == "sentinel-untouched\n"
    assert (skill_dir / ".graphify_version").read_text(encoding="utf-8") == "1.2.3"
    assert not list(skill_dir.glob(".graphify_version.*.tmp"))


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX mode bits only")
def test_write_version_stamp_permissions_without_touching_umask(tmp_path, monkeypatch):
    """New stamps keep mkstemp 0600 permissions; existing regular stamps preserve mode without os.umask."""
    skill_dir = tmp_path / "skills" / "graphify"
    skill_dir.mkdir(parents=True)
    skill_dst = skill_dir / "SKILL.md"
    skill_dst.write_text("skill", encoding="utf-8")
    stamp = skill_dir / ".graphify_version"

    def forbid_umask(_mask):
        raise AssertionError("os.umask must not be called")

    monkeypatch.setattr(os, "umask", forbid_umask)

    install._write_version_stamp(skill_dst, "1.0.0")
    assert stat.S_IMODE(stamp.stat().st_mode) == 0o600

    stamp.chmod(0o644)
    install._write_version_stamp(skill_dst, "2.0.0")
    assert stamp.read_text(encoding="utf-8") == "2.0.0"
    assert stat.S_IMODE(stamp.stat().st_mode) == 0o644
