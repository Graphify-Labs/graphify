"""Sync native plugin manifests (.claude-plugin, .codex-plugin, hooks, skills) with pyproject.toml."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def read_package_version(pyproject_path: Path | None = None) -> str:
    """Read the package version string from pyproject.toml."""
    text = (pyproject_path or ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        raise ValueError("Could not find version in pyproject.toml")
    return match.group(1)


def sync_manifests(version: str | None = None, root: Path | None = None) -> list[Path]:
    """Update plugin manifest versions, uvx pin args, and bundled skills/ directory."""
    repo = root or ROOT
    ver = version or read_package_version(repo / "pyproject.toml")
    pkg_spec = f"graphifyy[sql,mcp]=={ver}"
    updated: list[Path] = []

    marketplace_path = repo / ".claude-plugin" / "marketplace.json"
    marketplace = json.loads(marketplace_path.read_text(encoding="utf-8"))
    marketplace["metadata"]["version"] = ver
    for plugin in marketplace.get("plugins", []):
        if plugin.get("name") == "graphify":
            plugin["version"] = ver
    marketplace_path.write_text(json.dumps(marketplace, indent=2) + "\n", encoding="utf-8")
    updated.append(marketplace_path)

    for rel in (".claude-plugin/plugin.json", ".codex-plugin/plugin.json"):
        p = repo / rel
        data = json.loads(p.read_text(encoding="utf-8"))
        data["version"] = ver
        data["mcpServers"]["graphify"]["args"] = ["--from", pkg_spec, "graphify-mcp"]
        p.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        updated.append(p)

    hooks_path = repo / "hooks" / "hooks.json"
    hooks_data = json.loads(hooks_path.read_text(encoding="utf-8"))
    for event_entries in hooks_data.get("hooks", {}).values():
        for entry in event_entries:
            for hook in entry.get("hooks", []):
                cmd = hook.get("command", "")
                hook["command"] = re.sub(
                    r"graphifyy\[sql,mcp\]==\S+",
                    pkg_spec,
                    cmd,
                )
    hooks_path.write_text(json.dumps(hooks_data, indent=2) + "\n", encoding="utf-8")
    updated.append(hooks_path)

    skill_dst = repo / "skills" / "graphify"
    refs_dst = skill_dst / "references"
    refs_dst.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(repo / "graphify" / "skill.md", skill_dst / "SKILL.md")
    updated.append(skill_dst / "SKILL.md")
    for src_ref in sorted((repo / "graphify" / "skills" / "claude" / "references").glob("*.md")):
        dst_ref = refs_dst / src_ref.name
        shutil.copyfile(src_ref, dst_ref)
        updated.append(dst_ref)

    return updated


if __name__ == "__main__":
    paths = sync_manifests()
    print(f"Synced {len(paths)} plugin file(s) to version {read_package_version()}")
