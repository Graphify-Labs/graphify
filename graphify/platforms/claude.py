"""Claude Code platform installer."""

from __future__ import annotations

import json
import platform
import re
import sys
from pathlib import Path

from .base import BasePlatformInstaller
from .registry import register
from .utils import (
    CLAUDE_MD_MARKER,
    PLATFORM_CONFIG,
    READ_SETTINGS_HOOK,
    SETTINGS_HOOK,
    _always_on,
    _copy_skill_file,
    _print_banner,
    _print_project_git_add_hint,
    _project_scope_root,
    _refresh_all_version_stamps,
    _remove_claude_skill_registration,
    _remove_skill_file,
    _replace_or_append_section,
    _skill_registration,
)


def _install_claude_hook(project_dir: Path) -> None:
    settings_path = project_dir / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            settings = {}
    else:
        settings = {}

    hooks = settings.setdefault("hooks", {})
    pre_tool = hooks.setdefault("PreToolUse", [])

    hooks["PreToolUse"] = [
        h
        for h in pre_tool
        if not (h.get("matcher") in ("Glob|Grep", "Bash", "Read|Glob") and "graphify" in str(h))
    ]
    hooks["PreToolUse"].append(SETTINGS_HOOK)
    hooks["PreToolUse"].append(READ_SETTINGS_HOOK)
    settings_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    print(f"  .claude/settings.json  ->  PreToolUse hooks registered (Bash search + Read/Glob)")


def _uninstall_claude_hook(project_dir: Path) -> None:
    settings_path = project_dir / ".claude" / "settings.json"
    if not settings_path.exists():
        return
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
    pre_tool = settings.get("hooks", {}).get("PreToolUse", [])
    filtered = [
        h
        for h in pre_tool
        if not (h.get("matcher") in ("Glob|Grep", "Bash", "Read|Glob") and "graphify" in str(h))
    ]
    if len(filtered) == len(pre_tool):
        return
    settings["hooks"]["PreToolUse"] = filtered
    settings_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    print(f"  .claude/settings.json  ->  PreToolUse hook removed")


@register("claude")
@register("windows")
class ClaudeInstaller(BasePlatformInstaller):
    name = "claude"

    @property
    def skill_file(self) -> str | None:
        return PLATFORM_CONFIG.get(self.name, {}).get("skill_file")

    def install(self, project_dir: Path | None = None, *, project: bool = False) -> None:
        _print_banner()
        platform_name = self.name

        if platform_name not in PLATFORM_CONFIG:
            print(
                f"error: unknown platform '{platform_name}'. Choose from: {', '.join(PLATFORM_CONFIG)}",
                file=sys.stderr,
            )
            sys.exit(1)

        cfg = PLATFORM_CONFIG[platform_name]
        project_dir = project_dir or Path(".")
        skill_dst = _copy_skill_file(platform_name, project=project, project_dir=project_dir)

        if cfg["claude_md"]:
            claude_md = (
                (project_dir / ".claude" / "CLAUDE.md")
                if project
                else Path.home() / ".claude" / "CLAUDE.md"
            )
            registration = _skill_registration(
                ".claude/skills/graphify/SKILL.md"
                if project
                else "~/.claude/skills/graphify/SKILL.md"
            )
            if claude_md.exists():
                content = claude_md.read_text(encoding="utf-8")
                if "graphify" in content:
                    print(f"  CLAUDE.md        ->  already registered (no change)")
                else:
                    claude_md.write_text(content.rstrip() + registration, encoding="utf-8")
                    print(f"  CLAUDE.md        ->  skill registered in {claude_md}")
            else:
                claude_md.parent.mkdir(parents=True, exist_ok=True)
                claude_md.write_text(registration.lstrip(), encoding="utf-8")
                print(f"  CLAUDE.md        ->  created at {claude_md}")

        if project:
            _print_project_git_add_hint([_project_scope_root(skill_dst, project_dir)])
        else:
            _refresh_all_version_stamps()

        print()
        print("Done. Open your AI coding assistant and type:")
        print()
        print("  /graphify .")
        print()

    def uninstall(self, project_dir: Path | None = None, *, project: bool = False) -> None:
        project_dir = project_dir or Path(".")
        platform_name = self.name

        _remove_skill_file(platform_name, project=project, project_dir=project_dir)
        target = project_dir / "CLAUDE.md"

        if not target.exists():
            print("No CLAUDE.md found in current directory - nothing to do")
            return

        content = target.read_text(encoding="utf-8")
        if CLAUDE_MD_MARKER not in content:
            print("graphify section not found in CLAUDE.md - nothing to do")
            return

        cleaned = re.sub(
            r"\n*## graphify\n.*?(?=\n## |\Z)",
            "",
            content,
            flags=re.DOTALL,
        ).rstrip()
        if cleaned:
            target.write_text(cleaned + "\n", encoding="utf-8")
            print(f"graphify section removed from {target.resolve()}")
        else:
            target.unlink()
            print(f"CLAUDE.md was empty after removal - deleted {target.resolve()}")

        _uninstall_claude_hook(project_dir or Path("."))


def claude_install(project_dir: Path | None = None) -> None:
    target = (project_dir or Path(".")) / "CLAUDE.md"

    if target.exists():
        content = target.read_text(encoding="utf-8")
        new_content = _replace_or_append_section(content, CLAUDE_MD_MARKER, _always_on("claude-md"))
    else:
        new_content = _always_on("claude-md")

    if target.exists() and new_content == target.read_text(encoding="utf-8"):
        print(f"graphify already configured in {target.resolve()} (no change)")
    else:
        target.write_text(new_content, encoding="utf-8")
        print(f"graphify section written to {target.resolve()}")

    _install_claude_hook(project_dir or Path("."))

    print()
    print("Claude Code will now check the knowledge graph before answering")
    print("codebase questions and rebuild it after code changes.")


def claude_uninstall(project_dir: Path | None = None, *, project: bool = False) -> None:
    project_dir = project_dir or Path(".")
    _remove_skill_file("claude", project=project, project_dir=project_dir)
    target = project_dir / "CLAUDE.md"

    if not target.exists():
        print("No CLAUDE.md found in current directory - nothing to do")
        return

    content = target.read_text(encoding="utf-8")
    if CLAUDE_MD_MARKER not in content:
        print("graphify section not found in CLAUDE.md - nothing to do")
        return

    cleaned = re.sub(
        r"\n*## graphify\n.*?(?=\n## |\Z)",
        "",
        content,
        flags=re.DOTALL,
    ).rstrip()
    if cleaned:
        target.write_text(cleaned + "\n", encoding="utf-8")
        print(f"graphify section removed from {target.resolve()}")
    else:
        target.unlink()
        print(f"CLAUDE.md was empty after removal - deleted {target.resolve()}")

    _uninstall_claude_hook(project_dir or Path("."))
