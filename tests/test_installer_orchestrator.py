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