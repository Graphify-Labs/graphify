"""Source-verification plans over the shared Missing Impact analysis.

This module deliberately makes no completeness verdict.  Its classifications
are deterministic file/path hints; optional Jev ranking remains entirely in
``missing_impact`` and is performed at most once.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from graphify import missing_impact as mi
from graphify.jev_shadow import JevShadowError

SCHEMA_VERSION = 1
DIMENSIONS = ("implementation", "consumers", "tests", "configuration", "migration_or_schema", "documentation")
CONSUMER_RELATIONS = {"calls", "references", "imports", "imports_from", "dynamic_import", "re_exports", "uses", "requires"}
CODE_EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java", ".kt", ".rb", ".php", ".cs", ".c", ".h", ".cpp", ".hpp", ".swift", ".scala", ".sh", ".sql"}
CONFIG_NAMES = {"dockerfile", "makefile", "compose.yml", "compose.yaml", "package.json", "tsconfig.json", "pyproject.toml", "setup.cfg", ".gitignore"}


def file_dimensions(path: str, *, test_like: bool = False) -> set[str]:
    """Return conservative deterministic path-based classification hints."""
    lower = path.lower().replace("\\", "/")
    name = lower.rsplit("/", 1)[-1]
    suffix = Path(name).suffix
    result: set[str] = set()
    if test_like or lower.startswith("tests/") or "/tests/" in lower or "/test/" in lower or "/spec/" in lower or name.startswith(("test_", "spec_")) or name.endswith(("_test.py", ".test.js", ".test.ts", ".spec.js", ".spec.ts")):
        result.add("tests")
    if lower.startswith("docs/") or "/docs/" in lower or suffix in {".md", ".rst", ".adoc"}:
        result.add("documentation")
    if lower.startswith(("config/", ".github/")) or "/config/" in lower or "/.github/" in lower or suffix in {".toml", ".yaml", ".yml"} or name in CONFIG_NAMES:
        result.add("configuration")
    if any(part in {"migrations", "migration", "schema", "alembic", "prisma"} for part in lower.split("/")) or name.startswith(("migration", "schema")) or name.endswith((".schema", ".prisma")):
        result.add("migration_or_schema")
    if suffix in CODE_EXTENSIONS and not result.intersection({"tests", "documentation", "configuration", "migration_or_schema"}):
        result.add("implementation")
    return result


def _changed_consumers(projection: dict[str, Any], changed: set[str]) -> set[str]:
    return {relation["source"] for relation in projection["relations"] if relation["source"] in changed and relation["relation"] in CONSUMER_RELATIONS}


def _candidate_dimensions(candidate: dict[str, Any]) -> set[str]:
    roles = file_dimensions(candidate["path"], test_like=candidate["test_like"])
    if set(candidate["relations_to_seed"]) & CONSUMER_RELATIONS:
        roles.add("consumers")
    return roles


def build_plan(analysis: dict[str, Any]) -> dict[str, Any]:
    """Create a verification plan without changing the shared candidate set."""
    result = analysis["result"]
    if "candidates" not in result:
        return result | {"status": analysis["status"], "dimensions": {}}
    candidates = result["candidates"]
    changed_roles: dict[str, set[str]] = {path: file_dimensions(path) for path in result["changed_files"]}
    projection = analysis["projection"]
    for path in _changed_consumers(projection, set(result["changed_files"])):
        if path in changed_roles:
            changed_roles[path].add("consumers")
    candidate_roles = {candidate["path"]: _candidate_dimensions(candidate) for candidate in candidates}
    dimensions: dict[str, dict[str, Any]] = {}
    for dimension in DIMENSIONS:
        changed = sorted(path for path, roles in changed_roles.items() if dimension in roles)
        verify = [candidate["path"] for candidate in candidates if dimension in candidate_roles[candidate["path"]]]
        state = "CHANGED_EVIDENCE" if changed else "VERIFY_CANDIDATE" if verify else "NO_STRUCTURAL_EVIDENCE"
        dimensions[dimension] = {"state": state, "changed_files": changed, "verify_candidates": verify}
    status = "NEEDS_SOURCE_VERIFICATION" if candidates else "NO_ADDITIONAL_CANDIDATES"
    return result | {"schema_version": SCHEMA_VERSION, "status": status, "dimensions": dimensions}


def _human(plan: dict[str, Any], top: int) -> str:
    if plan["status"] in {"NO_CHANGED_FILES", "NO_GRAPH_REPRESENTED_SEEDS"}:
        return plan["status"]
    labels = {"implementation": "Implementation", "consumers": "Consumers", "tests": "Tests", "configuration": "Configuration", "migration_or_schema": "Migration/schema", "documentation": "Documentation"}
    candidates = {row["path"]: row for row in plan.get("candidates", [])}
    lines = ["Change completeness verification plan", f"Task: {plan['objective']}", ""]
    for dimension in DIMENSIONS:
        item = plan["dimensions"][dimension]
        lines += [labels[dimension], f"  {item['state']}"]
        if item["changed_files"]:
            lines += ["  changed:"] + [f"  - {path}" for path in item["changed_files"]]
        shown = item["verify_candidates"][:top]
        if shown:
            lines += ["  verify:"] + [f"  - {path} [{candidates[path]['provenance'] or 'STRUCTURAL_CANDIDATE'}, {'semantic rank ' + str(candidates[path]['semantic_rank']) if plan['live'] else 'structural rank ' + str(candidates[path]['structural_rank'])}]" for path in shown]
        lines.append("")
    lines += [f"Overall: {plan['status']}", "", "Semantic reranking was not run." if not plan.get("live") else "Jev-ranked candidates are source-verification hypotheses.", "This is a verification plan, not proof that the change is complete."]
    return "\n".join(lines)


def run(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="graphify change-completeness", description="Produce a source-verification plan, not a completeness certification.")
    parser.add_argument("--task", required=True); parser.add_argument("--repo", default="."); parser.add_argument("--graph"); parser.add_argument("--changed", action="append", default=[]); parser.add_argument("--top", type=int, default=5); parser.add_argument("--live", action="store_true"); parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        if not 1 <= args.top <= mi.CANDIDATE_BUDGET:
            raise mi.MissingImpactError("top must be between 1 and 12")
        analysis = mi.prepare_analysis(objective=args.task, repo=args.repo, graph=args.graph, changed_paths=args.changed, live=args.live)
        if args.live:
            mi.rerank_live(analysis)
        plan = build_plan(analysis)
        print(json.dumps(plan, indent=2, sort_keys=True, ensure_ascii=False) if args.json else _human(plan, args.top))
    except (mi.MissingImpactError, JevShadowError) as exc:
        parser.error(str(exc))
