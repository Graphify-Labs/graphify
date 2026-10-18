"""Architecture rules over the graph: `graphify check`.

A rules file (JSON, default ``graphify-rules.json`` next to the scanned root)
declares dependencies that must not exist and whether import cycles are
allowed::

    {
      "forbid": [
        {"from": "src/ui/*", "to": "src/db/*", "message": "UI must go through the service layer"},
        {"from": "src/core/*", "to": "src/plugins/*", "relations": ["imports_from"]}
      ],
      "no_import_cycles": true,
      "max_cycle_length": 5,
      "include_inferred": false
    }

Heuristic boundaries (documented, not bugs):
- Patterns are ``fnmatch`` globs on repo-relative POSIX paths; ``*`` also
  matches ``/``, so ``src/ui/*`` covers the whole ``src/ui`` tree.
- Only ``EXTRACTED`` edges count by default: a gate must not fail a build on
  a relationship graphify resolved heuristically. ``"include_inferred": true``
  adds ``INFERRED`` edges; ``AMBIGUOUS`` edges never count.
- Only code-to-code edges count; a document mentioning a file is not a
  dependency on it.
- A rule only sees what the graph has: an unindexed file or an unresolved
  call cannot violate anything.
"""
from __future__ import annotations

import json
import re
from fnmatch import fnmatchcase
from pathlib import Path

import networkx as nx

from graphify.affected import DEFAULT_AFFECTED_RELATIONS

DEFAULT_RULES_FILE = "graphify-rules.json"
# `defines` links a file to its own symbols; it is not a dependency between files.
DEFAULT_FORBID_RELATIONS = tuple(r for r in DEFAULT_AFFECTED_RELATIONS if r != "defines")
FORBIDDEN_RULE_ID = "graphify/forbidden-dependency"
CYCLE_RULE_ID = "graphify/import-cycle"
_LINE_RE = re.compile(r"L(\d+)")


def load_rules(path: Path) -> dict:
    """Read and validate a rules file; raises ValueError with a readable reason."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read rules file {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError("rules file must be a JSON object")
    unknown = set(raw) - {"forbid", "no_import_cycles", "max_cycle_length", "include_inferred"}
    if unknown:
        raise ValueError(f"unknown rules key(s): {', '.join(sorted(unknown))}")
    forbid = raw.get("forbid", [])
    if not isinstance(forbid, list):
        raise ValueError("'forbid' must be a list")
    for i, rule in enumerate(forbid):
        if not isinstance(rule, dict) or not isinstance(rule.get("from"), str) or not isinstance(rule.get("to"), str):
            raise ValueError(f"forbid[{i}] needs string 'from' and 'to' globs")
        rels = rule.get("relations", list(DEFAULT_FORBID_RELATIONS))
        if not isinstance(rels, list) or not all(isinstance(r, str) for r in rels):
            raise ValueError(f"forbid[{i}].relations must be a list of strings")
    for key in ("no_import_cycles", "include_inferred"):
        if not isinstance(raw.get(key, False), bool):
            raise ValueError(f"'{key}' must be true or false")
    max_len = raw.get("max_cycle_length", 5)
    if not isinstance(max_len, int) or isinstance(max_len, bool) or max_len < 2:
        raise ValueError("'max_cycle_length' must be an integer >= 2")
    return raw


def _line(location: object) -> int | None:
    m = _LINE_RE.match(str(location or ""))
    return int(m.group(1)) if m else None


def check_rules(G: nx.Graph, rules: dict) -> list[dict]:
    """Every violation, sorted by file then line."""
    violations: list[dict] = []
    allowed = {"EXTRACTED", "INFERRED"} if rules.get("include_inferred") else {"EXTRACTED"}
    for rule in rules.get("forbid", []):
        rels = set(rule.get("relations", DEFAULT_FORBID_RELATIONS))
        for u, v, data in G.edges(data=True):
            if data.get("relation") not in rels or data.get("confidence", "EXTRACTED") not in allowed:
                continue
            if G.nodes[u].get("file_type", "code") != "code" or G.nodes[v].get("file_type", "code") != "code":
                continue
            src = str(G.nodes[u].get("source_file") or "").replace("\\", "/")
            tgt = str(G.nodes[v].get("source_file") or "").replace("\\", "/")
            if not src or not tgt or src == tgt:
                continue
            if fnmatchcase(src, rule["from"]) and fnmatchcase(tgt, rule["to"]):
                why = rule.get("message") or f"{rule['from']} must not depend on {rule['to']}"
                violations.append({
                    "rule": FORBIDDEN_RULE_ID,
                    "file": src,
                    "line": _line(data.get("source_location")),
                    "message": f"{src} -> {tgt} ({data.get('relation')}): {why}",
                })
    if rules.get("no_import_cycles"):
        from graphify.analyze import find_import_cycles

        for c in find_import_cycles(G, max_cycle_length=rules.get("max_cycle_length", 5), top_n=10**6):
            files = c["cycle"]
            violations.append({
                "rule": CYCLE_RULE_ID,
                "file": files[0],
                "line": None,
                "message": "import cycle: " + " -> ".join(files + files[:1]),
            })
    violations.sort(key=lambda x: (x["file"], x["line"] or 0, x["rule"], x["message"]))
    return violations


def format_text(violations: list[dict]) -> str:
    from graphify.security import sanitize_label

    if not violations:
        return "graphify check: no violations"
    lines = [f"graphify check: {len(violations)} violation{'s' if len(violations) != 1 else ''}"]
    for v in violations:
        where = f"{v['file']}:{v['line']}" if v["line"] else v["file"]
        lines.append(f"  {sanitize_label(where)}  [{v['rule']}] {sanitize_label(v['message'])}")
    return "\n".join(lines)


def to_sarif(violations: list[dict], version: str) -> dict:
    """SARIF 2.1.0, uploadable to GitHub code scanning."""
    results = []
    for v in violations:
        loc: dict = {"artifactLocation": {"uri": v["file"], "uriBaseId": "%SRCROOT%"}}
        if v["line"]:
            loc["region"] = {"startLine": v["line"]}
        results.append({
            "ruleId": v["rule"],
            "level": "error",
            "message": {"text": v["message"]},
            "locations": [{"physicalLocation": loc}],
        })
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": {
                "name": "graphify",
                "version": version,
                "informationUri": "https://github.com/Graphify-Labs/graphify",
                "rules": [
                    {"id": FORBIDDEN_RULE_ID, "shortDescription": {"text": "Dependency forbidden by graphify-rules.json"}},
                    {"id": CYCLE_RULE_ID, "shortDescription": {"text": "Circular file-level import"}},
                ],
            }},
            "results": results,
        }],
    }
