from __future__ import annotations

from pathlib import Path

from .base import BasePlatformInstaller
from .registry import register

_DEVIN_RULES_PATH = Path(".windsurf") / "rules" / "graphify.md"
_DEVIN_RULES = """\
## graphify

This project has a graphify knowledge graph at graphify-out/.

Rules:
- For codebase or architecture questions, when `graphify-out/graph.json` exists, first run `graphify query "<question>"` (or `graphify path "<A>" "<B>"` / `graphify explain "<concept>"`). These return a scoped subgraph, usually much smaller than `GRAPH_REPORT.md` or raw grep output.
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context
- After modifying code files in this session, run `graphify update .` to keep the graph current (AST-only, no API cost)
"""


@register("devin")
class DevinInstaller(BasePlatformInstaller):
    name = "devin"

    def install(self, project_dir: Path | None = None, *, project: bool = False) -> None:
        project_dir = project_dir or Path(".")
        rules_path = project_dir / _DEVIN_RULES_PATH
        rules_path.parent.mkdir(parents=True, exist_ok=True)
        if rules_path.exists() and rules_path.read_text(encoding="utf-8") == _DEVIN_RULES:
            print(f"  {rules_path}  ->  already configured (no change)")
            return
        action = "updated" if rules_path.exists() else "written"
        rules_path.write_text(_DEVIN_RULES, encoding="utf-8")
        print(f"  rules {action}  ->  {rules_path}")

    def uninstall(self, project_dir: Path | None = None, *, project: bool = False) -> None:
        project_dir = project_dir or Path(".")
        rules_path = project_dir / _DEVIN_RULES_PATH
        if not rules_path.exists():
            return
        rules_path.unlink()
        print(f"  rules removed  ->  {rules_path}")
