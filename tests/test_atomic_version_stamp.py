"""Regression tests for atomic `.graphify_version` stamp writes (#3286)."""
from __future__ import annotations

import os

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
