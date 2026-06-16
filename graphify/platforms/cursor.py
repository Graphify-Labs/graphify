"""Cursor IDE platform installer."""

from __future__ import annotations

from pathlib import Path

from .base import BasePlatformInstaller
from .registry import register

_CURSOR_RULE_PATH = Path(".cursor") / "rules" / "graphify.mdc"
_CURSOR_RULE = """\
---
description: graphify knowledge graph context
alwaysApply: true
---

This project has a graphify knowledge graph at graphify-out/.

**MANDATORY: Before using Read, Grep, Glob, or Bash to explore the codebase, you MUST run graphify first:**
- `graphify query "<question>"` — scoped subgraph for any codebase or architecture question
- `graphify path "<A>" "<B>"` — dependency path between two symbols
- `graphify explain "<concept>"` — all nodes related to a concept

This applies to YOU and to every subagent you spawn. Include this rule explicitly in every subagent prompt that involves code exploration. Do not skip graphify because files are "already known" or because you are executing a plan — the graph surfaces cross-file dependencies and INFERRED edges that grep and Read cannot find.

Only use Read/Grep/Glob directly when:
1. graphify has already oriented you and you need to modify or debug specific lines
2. `graphify-out/graph.json` does not exist yet

- If `graphify-out/wiki/index.md` exists, navigate it instead of reading raw files
- Read `graphify-out/GRAPH_REPORT.md` only for broad architecture review when query/path/explain do not surface enough context
- After modifying code files, run `graphify update .` to keep the graph current (AST-only, no API cost)
"""


@register("cursor")
class CursorInstaller(BasePlatformInstaller):
    name = "cursor"

    def install(self, project_dir: Path | None = None, *, project: bool = False) -> None:
        rule_path = (project_dir or Path(".")) / _CURSOR_RULE_PATH
        rule_path.parent.mkdir(parents=True, exist_ok=True)
        if rule_path.exists() and rule_path.read_text(encoding="utf-8") == _CURSOR_RULE:
            print(f"graphify rule at {rule_path} already configured (no change)")
            return
        action = "updated" if rule_path.exists() else "written"
        rule_path.write_text(_CURSOR_RULE, encoding="utf-8")
        print(f"graphify rule {action} at {rule_path.resolve()}")
        print()
        print("Cursor will now always include the knowledge graph context.")
        print("Run /graphify . first to build the graph if you haven't already.")

    def uninstall(self, project_dir: Path | None = None, *, project: bool = False) -> None:
        rule_path = (project_dir or Path(".")) / _CURSOR_RULE_PATH
        if not rule_path.exists():
            print("No graphify Cursor rule found - nothing to do")
            return
        rule_path.unlink()
        print(f"graphify Cursor rule removed from {rule_path.resolve()}")
