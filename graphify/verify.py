"""Basic formal verification: check dependency/architectural invariants against a built graph.

Rules describe forbidden dependencies between parts of the codebase as glob patterns
over `source_file`. A rule fires when an edge's source node file matches `from` and
its target node file matches `to` - i.e. the forbidden dependency actually exists in
the live graph, not just in theory.
"""

from __future__ import annotations

import fnmatch
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class Violation:
    rule: str
    source: str
    target: str
    source_file: str
    target_file: str
    relation: str
    source_location: str


def load_rules(path: Path) -> list[dict[str, str]]:
    data: Any = json.loads(Path(path).read_text(encoding="utf-8"))
    rules = data.get("rules") if isinstance(data, dict) else data
    if not isinstance(rules, list):
        raise ValueError(f"{path}: expected a 'rules' list")
    out: list[dict[str, str]] = []
    for rule in rules:
        if not isinstance(rule, dict) or "from" not in rule or "to" not in rule:
            raise ValueError(f"{path}: each rule needs 'from' and 'to' glob patterns")
        out.append(
            {
                "name": str(rule.get("name", f"{rule['from']} -> {rule['to']}")),
                "from": str(rule["from"]),
                "to": str(rule["to"]),
            }
        )
    return out


def verify_graph(graph_path: Path, rules: list[dict[str, str]]) -> list[Violation]:
    graph: dict[str, Any] = json.loads(Path(graph_path).read_text(encoding="utf-8"))
    nodes_by_id = {
        str(n["id"]): n
        for n in graph.get("nodes", [])
        if isinstance(n, dict) and "id" in n
    }
    edges = graph.get("links") or graph.get("edges") or []

    violations: list[Violation] = []
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        source_id = str(edge.get("source", ""))
        target_id = str(edge.get("target", ""))
        src_node = nodes_by_id.get(source_id)
        tgt_node = nodes_by_id.get(target_id)
        if not src_node or not tgt_node:
            continue
        src_file = str(src_node.get("source_file", ""))
        tgt_file = str(tgt_node.get("source_file", ""))
        if not src_file or not tgt_file:
            continue
        for rule in rules:
            if fnmatch.fnmatch(src_file, rule["from"]) and fnmatch.fnmatch(tgt_file, rule["to"]):
                violations.append(
                    Violation(
                        rule=rule["name"],
                        source=source_id,
                        target=target_id,
                        source_file=src_file,
                        target_file=tgt_file,
                        relation=str(edge.get("relation", "")),
                        source_location=str(edge.get("source_location", "")),
                    )
                )
    return violations


def format_report(violations: list[Violation]) -> str:
    if not violations:
        return "Verify: OK - no forbidden dependencies found."
    lines = [f"Verify: {len(violations)} violation(s) found."]
    for v in violations:
        loc = f" ({v.source_location})" if v.source_location else ""
        lines.append(
            f"  [{v.rule}] {v.source_file}{loc} -> {v.target_file} "
            f"({v.source} --{v.relation}--> {v.target})"
        )
    return "\n".join(lines)


def format_json(violations: list[Violation]) -> dict[str, Any]:
    return {
        "ok": not violations,
        "violation_count": len(violations),
        "violations": [
            {
                "rule": v.rule,
                "source": v.source,
                "target": v.target,
                "source_file": v.source_file,
                "target_file": v.target_file,
                "relation": v.relation,
                "source_location": v.source_location,
            }
            for v in violations
        ],
    }
