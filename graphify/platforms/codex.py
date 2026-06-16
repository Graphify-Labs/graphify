from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from .base import BasePlatformInstaller
from .registry import register


_CODEX_HOOK = {
    "hooks": {
        "PreToolUse": [
            {
                "matcher": "Bash",
                "hooks": [
                    {
                        "type": "command",
                        "command": "graphify hook-check",
                    }
                ],
            }
        ]
    }
}


def _resolve_graphify_exe() -> str:
    """Return the absolute path to the graphify executable.

    Falls back to bare 'graphify' if resolution fails. Using an absolute path
    ensures the hook works in environments where the venv Scripts/ directory is
    not on PATH (e.g. VS Code Codex extension on Windows).
    """
    found = shutil.which("graphify")
    if found:
        return found
    scripts_dir = Path(sys.executable).parent
    for name in ("graphify.exe", "graphify"):
        candidate = scripts_dir / name
        if candidate.exists():
            return str(candidate)
    return "graphify"


@register("codex")
class CodexInstaller(BasePlatformInstaller):
    name = "codex"

    def install(self, project_dir: Path | None = None, *, project: bool = False) -> None:
        project_dir = project_dir or Path(".")
        hooks_path = project_dir / ".codex" / "hooks.json"
        hooks_path.parent.mkdir(parents=True, exist_ok=True)

        if hooks_path.exists():
            try:
                existing = json.loads(hooks_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                existing = {}
        else:
            existing = {}

        graphify_exe = _resolve_graphify_exe()
        hook_entry = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [{"type": "command", "command": f"{graphify_exe} hook-check"}],
                    }
                ]
            }
        }

        pre_tool = existing.setdefault("hooks", {}).setdefault("PreToolUse", [])
        existing["hooks"]["PreToolUse"] = [h for h in pre_tool if "graphify" not in str(h)]
        existing["hooks"]["PreToolUse"].extend(hook_entry["hooks"]["PreToolUse"])
        hooks_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        print(f"  .codex/hooks.json  ->  PreToolUse hook registered ({graphify_exe} hook-check)")

    def uninstall(self, project_dir: Path | None = None, *, project: bool = False) -> None:
        project_dir = project_dir or Path(".")
        hooks_path = project_dir / ".codex" / "hooks.json"
        if not hooks_path.exists():
            return
        try:
            existing = json.loads(hooks_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return
        pre_tool = existing.get("hooks", {}).get("PreToolUse", [])
        filtered = [h for h in pre_tool if "graphify" not in str(h)]
        existing["hooks"]["PreToolUse"] = filtered
        hooks_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        print(f"  .codex/hooks.json  ->  PreToolUse hook removed")
