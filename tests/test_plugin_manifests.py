"""Validation and version-sync tests for native Claude Code and Codex plugin manifests (#5500)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.sync_plugin_manifests import read_package_version, sync_manifests  # noqa: E402


def test_plugin_manifests_exist_and_pin_package_version():
    version = read_package_version(REPO_ROOT / "pyproject.toml")
    expected_pkg = f"graphifyy[sql,mcp]=={version}"

    marketplace = json.loads((REPO_ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    assert marketplace["name"] == "graphify"
    assert marketplace["metadata"]["version"] == version
    plugin_entries = [p for p in marketplace["plugins"] if p["name"] == "graphify"]
    assert len(plugin_entries) == 1
    assert plugin_entries[0]["version"] == version
    assert plugin_entries[0]["source"] == "./"

    for rel in (".claude-plugin/plugin.json", ".codex-plugin/plugin.json"):
        manifest = json.loads((REPO_ROOT / rel).read_text(encoding="utf-8"))
        assert manifest["name"] == "graphify"
        assert manifest["version"] == version
        assert manifest["skills"] == "./skills/"
        assert manifest["hooks"] == "./hooks/hooks.json"
        mcp = manifest["mcpServers"]["graphify"]
        assert mcp["type"] == "stdio"
        assert mcp["command"] == "uvx"
        assert mcp["args"] == ["--from", expected_pkg, "graphify-mcp"]


def test_plugin_hooks_json_matches_expected_matchers_and_version():
    version = read_package_version(REPO_ROOT / "pyproject.toml")
    expected_pkg = f"graphifyy[sql,mcp]=={version}"
    hooks_doc = json.loads((REPO_ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    hooks = hooks_doc["hooks"]

    pre_matchers = {entry["matcher"]: entry["hooks"][0] for entry in hooks["PreToolUse"]}
    assert set(pre_matchers) == {"Bash|Grep", "Read|Glob"}
    assert pre_matchers["Bash|Grep"]["command"] == f"uvx --from {expected_pkg} graphify hook-guard search"
    assert pre_matchers["Read|Glob"]["command"] == f"uvx --from {expected_pkg} graphify hook-guard read"
    assert pre_matchers["Bash|Grep"]["timeout"] == 10
    assert pre_matchers["Read|Glob"]["timeout"] == 10

    session_matchers = {entry["matcher"]: entry["hooks"][0] for entry in hooks["SessionStart"]}
    assert set(session_matchers) == {"compact"}
    assert session_matchers["compact"]["command"] == f"uvx --from {expected_pkg} graphify hook-guard compact"
    assert session_matchers["compact"]["timeout"] == 10


def test_bundled_plugin_skills_match_packaged_claude_skill():
    pkg_skill = (REPO_ROOT / "graphify" / "skill.md").read_text(encoding="utf-8")
    plugin_skill = (REPO_ROOT / "skills" / "graphify" / "SKILL.md").read_text(encoding="utf-8")
    assert plugin_skill == pkg_skill

    src_refs = sorted((REPO_ROOT / "graphify" / "skills" / "claude" / "references").glob("*.md"))
    dst_refs = sorted((REPO_ROOT / "skills" / "graphify" / "references").glob("*.md"))
    assert [p.name for p in dst_refs] == [p.name for p in src_refs]
    for src, dst in zip(src_refs, dst_refs):
        assert dst.read_text(encoding="utf-8") == src.read_text(encoding="utf-8")


def test_sync_manifests_bumps_versions_in_isolated_copy(tmp_path):
    import shutil

    for rel in (".claude-plugin", ".codex-plugin", "hooks"):
        shutil.copytree(REPO_ROOT / rel, tmp_path / rel)
    (tmp_path / "graphify" / "skills" / "claude" / "references").mkdir(parents=True)
    shutil.copyfile(REPO_ROOT / "graphify" / "skill.md", tmp_path / "graphify" / "skill.md")
    for ref in (REPO_ROOT / "graphify" / "skills" / "claude" / "references").glob("*.md"):
        shutil.copyfile(ref, tmp_path / "graphify" / "skills" / "claude" / "references" / ref.name)

    sync_manifests(version="9.9.9", root=tmp_path)

    assert json.loads((tmp_path / ".claude-plugin" / "marketplace.json").read_text())["metadata"]["version"] == "9.9.9"
    assert json.loads((tmp_path / ".claude-plugin" / "plugin.json").read_text())["mcpServers"]["graphify"]["args"] == [
        "--from", "graphifyy[sql,mcp]==9.9.9", "graphify-mcp"
    ]
    assert json.loads((tmp_path / ".codex-plugin" / "plugin.json").read_text())["version"] == "9.9.9"
    hooks_text = (tmp_path / "hooks" / "hooks.json").read_text()
    assert "graphifyy[sql,mcp]==9.9.9" in hooks_text
    assert (tmp_path / "skills" / "graphify" / "SKILL.md").exists()
