from __future__ import annotations

import json
import re
from pathlib import Path

from .base import BasePlatformInstaller
from .registry import register

_KIRO_STEERING_MARKER = "graphify: A knowledge graph of this project"

_KILO_PLUGIN_JS = """\
// graphify Kilo plugin
// Injects a knowledge graph reminder before bash tool calls when the graph exists.
import { existsSync } from "fs";
import { join } from "path";

export const GraphifyPlugin = async ({ directory }) => {
  let reminded = false;

  return {
    "tool.execute.before": async (input, output) => {
      if (reminded) return;
      if (!existsSync(join(directory, "graphify-out", "graph.json"))) return;

      if (input.tool === "bash") {
        output.args.command =
          'echo "[graphify] Knowledge graph available. Read graphify-out/GRAPH_REPORT.md for god nodes and architecture context before searching files." && ' +
          output.args.command;
        reminded = true;
      }
    },
  };
};
"""

_KILO_PLUGIN_PATH = Path(".kilo") / "plugins" / "graphify.js"
_KILO_CONFIG_JSON_PATH = Path(".kilo") / "kilo.json"
_KILO_CONFIG_JSONC_PATH = Path(".kilo") / "kilo.jsonc"


def _strip_json_comments(raw: str) -> str:
    result: list[str] = []
    in_string = False
    escaped = False
    line_comment = False
    block_comment = False
    i = 0

    while i < len(raw):
        ch = raw[i]
        nxt = raw[i + 1] if i + 1 < len(raw) else ""

        if line_comment:
            if ch == "\n":
                line_comment = False
                result.append(ch)
            i += 1
            continue

        if block_comment:
            if ch == "*" and nxt == "/":
                block_comment = False
                i += 2
            else:
                i += 1
            continue

        if in_string:
            result.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            i += 1
            continue

        if ch == "/" and nxt == "/":
            line_comment = True
            i += 2
            continue
        if ch == "/" and nxt == "*":
            block_comment = True
            i += 2
            continue

        result.append(ch)
        if ch == '"':
            in_string = True
        i += 1

    return re.sub(r",(\s*[}\]])", r"\1", "".join(result))


def _load_json_like(config_file: Path) -> dict:
    if not config_file.exists():
        return {}
    try:
        raw = config_file.read_text(encoding="utf-8")
        if config_file.suffix == ".jsonc":
            raw = _strip_json_comments(raw)
        loaded = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _kilo_config_path(project_dir: Path) -> Path:
    kilo_dir = (project_dir or Path(".")) / ".kilo"
    json_path = kilo_dir / _KILO_CONFIG_JSON_PATH.name
    if json_path.exists():
        return json_path
    jsonc_path = kilo_dir / _KILO_CONFIG_JSONC_PATH.name
    if jsonc_path.exists():
        return jsonc_path
    return json_path


def _kilo_config_write_path(project_dir: Path) -> Path:
    kilo_dir = (project_dir or Path(".")) / ".kilo"
    return kilo_dir / _KILO_CONFIG_JSON_PATH.name


def _install_kilo_plugin(project_dir: Path) -> None:
    plugin_file = project_dir / _KILO_PLUGIN_PATH
    plugin_file.parent.mkdir(parents=True, exist_ok=True)
    plugin_file.write_text(_KILO_PLUGIN_JS, encoding="utf-8")
    print(f"  {_KILO_PLUGIN_PATH}  ->  tool.execute.before hook written")

    config_file = _kilo_config_path(project_dir)
    write_config_file = _kilo_config_write_path(project_dir)
    write_config_file.parent.mkdir(parents=True, exist_ok=True)
    config = _load_json_like(config_file)
    plugins = config.get("plugin")
    if not isinstance(plugins, list):
        plugins = []
        config["plugin"] = plugins
    entry = plugin_file.resolve().as_uri()
    if entry not in plugins:
        plugins.append(entry)
        write_config_file.write_text(json.dumps(config, indent=2), encoding="utf-8")
        print(f"  {write_config_file.relative_to(project_dir)}  ->  plugin registered")
    else:
        print(
            f"  {config_file.relative_to(project_dir)}  ->  plugin already registered (no change)"
        )


def _uninstall_kilo_plugin(project_dir: Path) -> None:
    plugin_file = project_dir / _KILO_PLUGIN_PATH
    if plugin_file.exists():
        plugin_file.unlink()
        print(f"  {_KILO_PLUGIN_PATH}  ->  removed")

    config_file = _kilo_config_path(project_dir)
    if not config_file.exists():
        return
    write_config_file = _kilo_config_write_path(project_dir)
    config = _load_json_like(config_file)
    plugins = config.get("plugin", [])
    if not isinstance(plugins, list):
        plugins = []
    entry = plugin_file.resolve().as_uri()
    if entry in plugins:
        config["plugin"] = [plugin for plugin in plugins if plugin != entry]
        if not config["plugin"]:
            config.pop("plugin")
        write_config_file.parent.mkdir(parents=True, exist_ok=True)
        write_config_file.write_text(json.dumps(config, indent=2), encoding="utf-8")
        print(f"  {write_config_file.relative_to(project_dir)}  ->  plugin deregistered")


@register("kilo")
class KiloInstaller(BasePlatformInstaller):
    name = "kilo"

    def install(self, project_dir: Path | None = None, *, project: bool = False) -> None:
        from graphify.__main__ import _agents_install, install

        install(platform="kilo")
        _agents_install(project_dir or Path("."), "kilo")

    def uninstall(self, project_dir: Path | None = None, *, project: bool = False) -> None:
        from graphify.__main__ import (
            _AGENTS_MD_MARKER,
            _PLATFORM_CONFIG,
            _agents_uninstall,
            _remove_skill_file,
        )

        project_dir = project_dir or Path(".")
        _agents_uninstall(project_dir, platform="kilo")
        removed = []

        command_dst = Path.home() / ".config" / "kilo" / "command" / "graphify.md"
        if command_dst.exists():
            command_dst.unlink()
            removed.append(f"command removed: {command_dst}")
        try:
            command_dst.parent.rmdir()
        except OSError:
            pass

        skill_dst = Path.home() / _PLATFORM_CONFIG["kilo"]["skill_dst"]
        if skill_dst.exists():
            skill_dst.unlink()
            removed.append(f"skill removed: {skill_dst}")
        version_file = skill_dst.parent / ".graphify_version"
        if version_file.exists():
            version_file.unlink()
        for d in (
            skill_dst.parent,
            skill_dst.parent.parent,
            skill_dst.parent.parent.parent,
        ):
            try:
                d.rmdir()
            except OSError:
                break

        print("; ".join(removed) if removed else "nothing to remove")
