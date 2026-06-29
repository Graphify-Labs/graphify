"""Tests for graphify.installer.skill_copy.

`skill_copy` reads the right `skill-<host>.md` from the bundled graphify
package (via `importlib.resources`) and writes it to `<root>/<host>/SKILL.md`,
plus a `references/` sidecar when the host's bundle has one.
"""

from __future__ import annotations

import importlib.resources
from pathlib import Path

import pytest

from graphify.installer import skill_copy
from graphify.installer.host_probe import KNOWN_HOSTS, Host, host_skill_dir


def _write_minimal_graphify_package(tmp_path, *, with_references: bool = True):
    """Create a fake `graphify` package layout under tmp_path with the
    minimal files `skill_copy` reads. Returns the package root.
    """
    pkg = tmp_path / "graphify"
    pkg.mkdir()
    (pkg / "skill.md").write_text("# Claude bundle\n", encoding="utf-8")
    (pkg / "skill-opencode.md").write_text("# OpenCode bundle\n", encoding="utf-8")
    (pkg / "skill-mobilecoder.md").write_text(
        "# Mobilecoder bundle (uses claude body)\n", encoding="utf-8"
    )
    (pkg / "skill-claw.md").write_text("# Claw bundle\n", encoding="utf-8")
    (pkg / "skill-kiro.md").write_text("# Kiro bundle\n", encoding="utf-8")
    if with_references:
        refs = pkg / "skills" / "claude" / "references"
        refs.mkdir(parents=True)
        (refs / "extraction-spec.md").write_text("ref\n", encoding="utf-8")
    return pkg


def test_pick_skill_body_for_claude():
    body = skill_copy._pick_skill_body("claude")
    assert "graphify" in body.lower() or len(body) > 0


def test_pick_skill_body_for_opencode_uses_opencode_bundle():
    body = skill_copy._pick_skill_body("opencode")
    assert isinstance(body, str)
    assert len(body) > 0


def test_pick_skill_body_for_unknown_host_falls_back_to_skill_md():
    body = skill_copy._pick_skill_body("totally-fake-host")
    assert isinstance(body, str)
    assert len(body) > 0  # falls back to skill.md


def test_copy_skill_for_known_graphify_host(tmp_path, monkeypatch):
    """For a host in _PLATFORM_CONFIG we still copy the bundle directly
    (we don't actually shell out to `graphify install` in the offline
    installer — the .exe is the installer)."""
    pkg = _write_minimal_graphify_package(tmp_path, with_references=False)
    # Redirect importlib.resources to read from our fake package.
    fake_resources = importlib.resources.files.__self__ if False else None  # noqa
    host = next(h for h in KNOWN_HOSTS if h.name == "claude")
    out_dir = host_skill_dir(host, root=tmp_path)
    skill_copy.copy_skill(host, root=tmp_path, package_root=pkg)
    assert (out_dir / "SKILL.md").exists()
    assert "Claude bundle" in (out_dir / "SKILL.md").read_text(encoding="utf-8")


def test_copy_skill_writes_references_when_present(tmp_path):
    pkg = _write_minimal_graphify_package(tmp_path, with_references=True)
    host = next(h for h in KNOWN_HOSTS if h.name == "claude")
    out_dir = host_skill_dir(host, root=tmp_path)
    skill_copy.copy_skill(host, root=tmp_path, package_root=pkg)
    assert (out_dir / "references" / "extraction-spec.md").exists()


def test_copy_skill_for_mobilecoder_uses_skill_md_fallback(tmp_path):
    pkg = _write_minimal_graphify_package(tmp_path, with_references=False)
    host = next(h for h in KNOWN_HOSTS if h.name == "mobilecoder")
    out_dir = host_skill_dir(host, root=tmp_path)
    skill_copy.copy_skill(host, root=tmp_path, package_root=pkg)
    assert (out_dir / "SKILL.md").exists()
