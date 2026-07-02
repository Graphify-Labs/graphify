"""Tests for graphify.installer orchestrator (install / uninstall)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from graphify.installer import install as run_install, uninstall as run_uninstall
from graphify.installer.manifest import InstallManifest, load_manifest, manifest_path


def test_install_writes_manifest(tmp_path, monkeypatch):
    """On a clean install, a manifest is written to <install_path>/.graphify_install.json."""
    # Pretend we found exactly one host (claude).
    claude_host = next(
        h for h in __import__("graphify.installer.host_probe", fromlist=["KNOWN_HOSTS"]).KNOWN_HOSTS
        if h.name == "claude"
    )
    monkeypatch.setattr(
        "graphify.installer.detect_hosts", lambda *, root=None: [claude_host]
    )
    monkeypatch.setattr("graphify.installer.path_win.add_to_user_path", lambda p: None)
    monkeypatch.setattr("graphify.installer.path_win.remove_from_user_path", lambda p: None)

    manifest_file = tmp_path / ".graphify_install.json"
    run_install(
        install_path=tmp_path,
        user_root=tmp_path,
        version="0.9.1",
        manifest_target=manifest_file,
    )
    assert manifest_file.exists()
    m = load_manifest(manifest_file)
    assert m.version == "0.9.1"
    assert m.install_path == tmp_path
    assert "claude" in m.hosts


def test_install_writes_skill_for_detected_host(tmp_path, monkeypatch):
    claude_host = next(
        h for h in __import__("graphify.installer.host_probe", fromlist=["KNOWN_HOSTS"]).KNOWN_HOSTS
        if h.name == "claude"
    )
    monkeypatch.setattr(
        "graphify.installer.detect_hosts", lambda *, root=None: [claude_host]
    )
    monkeypatch.setattr("graphify.installer.path_win.add_to_user_path", lambda p: None)

    # Provide a fake package so skill_copy has something to read.
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "skill.md").write_text("# claude\n", encoding="utf-8")
    monkeypatch.setattr(
        "graphify.installer.skill_copy._pick_skill_body", lambda h: "# claude\n"
    )

    run_install(
        install_path=tmp_path / "install",
        user_root=tmp_path,
        version="0.9.1",
        manifest_target=tmp_path / "install" / ".graphify_install.json",
    )
    skill_dir = tmp_path / ".claude" / "skills" / "graphify"
    assert (skill_dir / "SKILL.md").exists()


def test_install_with_no_hosts_still_succeeds(tmp_path, monkeypatch):
    monkeypatch.setattr("graphify.installer.detect_hosts", lambda *, root=None: [])
    monkeypatch.setattr("graphify.installer.path_win.add_to_user_path", lambda p: None)
    manifest_file = tmp_path / ".graphify_install.json"
    run_install(
        install_path=tmp_path,
        user_root=tmp_path,
        version="0.9.1",
        manifest_target=manifest_file,
    )
    m = load_manifest(manifest_file)
    assert m.hosts == []


def test_install_writes_gf_bundled_skills(tmp_path, monkeypatch):
    """Offline installer must write all 15 bundled (gf-*) skills per detected host.

    copy_bundled_skills is called from install() after copy_skill — verifies the
    wiring from Task 4.1 actually places the bundled skills on disk.
    """
    from graphify.installer.host_probe import KNOWN_HOSTS
    claude_host = next(h for h in KNOWN_HOSTS if h.name == "claude")

    monkeypatch.setattr(
        "graphify.installer.detect_hosts", lambda *, root=None: [claude_host]
    )
    monkeypatch.setattr("graphify.installer.path_win.add_to_user_path", lambda p: None)

    # Fake the per-host body so copy_skill has something to read; copy_bundled_skills
    # reads from the real package (since package_root defaults to None → importlib).
    monkeypatch.setattr(
        "graphify.installer.skill_copy._pick_skill_body", lambda h: "# claude stub\n"
    )

    run_install(
        install_path=tmp_path / "install",
        user_root=tmp_path,
        version="0.9.1",
        manifest_target=tmp_path / "install" / ".graphify_install.json",
    )

    # The 15 bundled skills land under <user_root>/.claude/skills/gf-*/
    bundled_root = tmp_path / ".claude" / "skills"
    # Spot-check: brainstorming (superpowers, no references sidecar)
    assert (bundled_root / "gf-brainstorming" / "SKILL.md").exists()
    # Spot-check: llm-wiki SKILL.md is present (the only has_references=True skill)
    llm_wiki_dir = bundled_root / "gf-llm-wiki"
    assert (llm_wiki_dir / "SKILL.md").exists()
    # Spot-check: a third superpowers skill (different from brainstorming)
    assert (bundled_root / "gf-writing-plans" / "SKILL.md").exists()


def test_install_skips_gf_skills_for_unsupported_host(tmp_path, monkeypatch, capsys):
    """copy_bundled_skills returns [] for cursor/gemini → no gf-* dirs leak.

    cursor and gemini need format adapters (v2 work); the offline installer must
    not write SKILL.md into their trees even if detected.
    """
    from graphify.installer.host_probe import KNOWN_HOSTS
    cursor_host = next(h for h in KNOWN_HOSTS if h.name == "cursor")

    monkeypatch.setattr(
        "graphify.installer.detect_hosts", lambda *, root=None: [cursor_host]
    )
    monkeypatch.setattr("graphify.installer.path_win.add_to_user_path", lambda p: None)
    monkeypatch.setattr(
        "graphify.installer.skill_copy._pick_skill_body", lambda h: "# cursor stub\n"
    )

    run_install(
        install_path=tmp_path / "install",
        user_root=tmp_path,
        version="0.9.1",
        manifest_target=tmp_path / "install" / ".graphify_install.json",
    )

    # No gf-* skill dir should be created under .cursor/
    cursor_root = tmp_path / ".cursor"
    if cursor_root.exists():
        # Either no .cursor dir at all, or no gf-* inside it
        gf_dirs = list(cursor_root.rglob("gf-*"))
        assert not gf_dirs, f"unsupported host should not get gf-* skills, found: {gf_dirs}"


def test_uninstall_removes_manifest_and_skill_dirs(tmp_path, monkeypatch):
    # Set up an existing install.
    claude_host = next(
        h for h in __import__("graphify.installer.host_probe", fromlist=["KNOWN_HOSTS"]).KNOWN_HOSTS
        if h.name == "claude"
    )
    skill_dir = tmp_path / ".claude" / "skills" / "graphify"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("x", encoding="utf-8")

    manifest = InstallManifest(
        version="0.9.1",
        install_path=tmp_path,
        hosts=["claude"],
        user_path_added=True,
        skill_dirs=[str(skill_dir)],
    )
    from graphify.installer.manifest import save_manifest
    manifest_file = tmp_path / "manifest.json"
    save_manifest(manifest, manifest_file)

    monkeypatch.setattr("graphify.installer.path_win.remove_from_user_path", lambda p: None)
    run_uninstall(manifest_file=manifest_file)
    assert not skill_dir.exists()
    # Manifest is consumed.
    assert not manifest_file.exists()