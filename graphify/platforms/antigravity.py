from __future__ import annotations

import shutil
from pathlib import Path

from .base import BasePlatformInstaller
from .registry import register

_ANTIGRAVITY_RULES_PATH = Path(".agents") / "rules" / "graphify.md"
_ANTIGRAVITY_WORKFLOW_PATH = Path(".agents") / "workflows" / "graphify.md"

_ANTIGRAVITY_WORKFLOW = """\
---
name: graphify
description: Turn any folder of files into a navigable knowledge graph
---

# Workflow: graphify

Follow the graphify skill installed at ~/.gemini/config/skills/graphify/SKILL.md to run the full pipeline.

If no path argument is given, use `.` (current directory).
"""


def _always_on(basename: str) -> str:
    from graphify.__main__ import _always_on as _main_always_on

    return _main_always_on(basename)


def _platform_skill_destination(
    platform_name: str, *, project: bool = False, project_dir: Path | None = None
) -> Path:
    from graphify.__main__ import _platform_skill_destination as _main_dest

    return _main_dest(platform_name, project=project, project_dir=project_dir)


def _install_platform(
    platform: str, *, project: bool = False, project_dir: Path | None = None
) -> None:
    from graphify.__main__ import install as _main_install

    _main_install(platform=platform, project=project, project_dir=project_dir)


@register("antigravity")
class AntigravityInstaller(BasePlatformInstaller):
    name = "antigravity"

    def install(self, project_dir: Path | None = None, *, project: bool = False) -> None:
        project_dir = project_dir or Path(".")
        _install_platform("antigravity")
        self._finalize(_platform_skill_destination("antigravity"), project_dir)

        print()
        print("Antigravity will now check the knowledge graph before answering")
        print("codebase questions. Run /graphify first to build the graph.")
        print()
        print(
            "To enable full MCP architecture navigation, add this to ~/.gemini/antigravity/mcp_config.json:"
        )
        print('  "graphify": {')
        print('    "command": "uv",')
        print(
            '    "args": ["run", "--with", "graphifyy", "--with", "mcp", "-m", "graphify.serve", "${workspace.path}/graphify-out/graph.json"]'
        )
        print("  }")

    def uninstall(self, project_dir: Path | None = None, *, project: bool = False) -> None:
        project_dir = project_dir or Path(".")
        rules_path = project_dir / _ANTIGRAVITY_RULES_PATH
        if rules_path.exists():
            rules_path.unlink()
            print(f"graphify rule removed from {rules_path.resolve()}")
        else:
            print("No graphify Antigravity rule found - nothing to do")

        wf_path = project_dir / _ANTIGRAVITY_WORKFLOW_PATH
        if wf_path.exists():
            wf_path.unlink()
            print(f"graphify workflow removed from {wf_path.resolve()}")

        skill_dst = _platform_skill_destination(
            "antigravity", project=project, project_dir=project_dir
        )
        if skill_dst.exists():
            skill_dst.unlink()
            print(f"graphify skill removed from {skill_dst}")
        version_file = skill_dst.parent / ".graphify_version"
        if version_file.exists():
            version_file.unlink()
        refs_dir = skill_dst.parent / "references"
        if refs_dir.exists():
            shutil.rmtree(refs_dir)
        for d in (
            skill_dst.parent,
            skill_dst.parent.parent,
            skill_dst.parent.parent.parent,
        ):
            try:
                d.rmdir()
            except OSError:
                break

    def _finalize(self, skill_dst: Path, project_dir: Path) -> None:
        if skill_dst.exists():
            content = skill_dst.read_text(encoding="utf-8")
            if not content.startswith("---\n"):
                frontmatter = "---\nname: graphify-manager\ndescription: Rebuild the code graph or perform manual CLI queries when MCP server is offline.\n---\n\n"
                skill_dst.write_text(frontmatter + content, encoding="utf-8")

        rules_path = project_dir / _ANTIGRAVITY_RULES_PATH
        rules_path.parent.mkdir(parents=True, exist_ok=True)
        if rules_path.exists():
            existing = rules_path.read_text(encoding="utf-8")
            if _always_on("antigravity-rules").strip() != existing.strip():
                rules_path.write_text(_always_on("antigravity-rules"), encoding="utf-8")
                print(f"graphify rule updated at {rules_path.resolve()}")
            else:
                print(f"graphify rule already configured at {rules_path.resolve()} (no change)")
        else:
            rules_path.write_text(_always_on("antigravity-rules"), encoding="utf-8")
            print(f"graphify rule written to {rules_path.resolve()}")

        wf_path = project_dir / _ANTIGRAVITY_WORKFLOW_PATH
        wf_path.parent.mkdir(parents=True, exist_ok=True)
        if wf_path.exists():
            existing = wf_path.read_text(encoding="utf-8")
            if _ANTIGRAVITY_WORKFLOW.strip() != existing.strip():
                wf_path.write_text(_ANTIGRAVITY_WORKFLOW, encoding="utf-8")
                print(f"graphify workflow updated at {wf_path.resolve()}")
            else:
                print(f"graphify workflow already configured at {wf_path.resolve()} (no change)")
        else:
            wf_path.write_text(_ANTIGRAVITY_WORKFLOW, encoding="utf-8")
            print(f"graphify workflow written to {wf_path.resolve()}")
