"""Fail-closed promotion gate for navigation evidence."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from graphify.paths import write_json_atomic, write_text_atomic

REQUIRED_CAPABILITIES = (
    ("internal_import_resolution", "Internal import resolution"),
    ("lexical_inferred_ownership", "Lexical inferred ownership"),
    ("artifact_freshness", "Artifact freshness"),
)
_VALID_STATUSES = frozenset({"PASS", "FAIL"})


def evaluate_navigation_trust(capabilities: Mapping[str, object]) -> dict[str, object]:
    """Evaluate required capability evidence as one atomic trust decision."""
    rows: list[dict[str, str]] = []
    for capability_id, label in REQUIRED_CAPABILITIES:
        raw = capabilities.get(capability_id)
        if not isinstance(raw, Mapping):
            status = "MISSING"
            evidence = ""
        else:
            raw_status = raw.get("status")
            status = str(raw_status).upper() if raw_status is not None else "MISSING"
            if status not in _VALID_STATUSES:
                status = "INVALID"
            raw_evidence = raw.get("evidence", "")
            evidence = str(raw_evidence) if raw_evidence is not None else ""
        rows.append(
            {
                "id": capability_id,
                "label": label,
                "status": status,
                "evidence": evidence,
            }
        )

    trusted = all(row["status"] == "PASS" for row in rows)
    return {
        "schema_version": 1,
        "status": "TRUSTED" if trusted else "UNTRUSTED",
        "capabilities": rows,
    }


def _markdown_cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_markdown(report: Mapping[str, object]) -> str:
    """Render an evaluated trust report without collapsing diagnostic rows."""
    lines = [
        "# Navigation Trust",
        "",
        f"**Overall: {_markdown_cell(report.get('status', 'UNTRUSTED'))}**",
        "",
        "| Capability | Status | Evidence |",
        "| --- | --- | --- |",
    ]
    capabilities = report.get("capabilities", [])
    if isinstance(capabilities, Sequence) and not isinstance(capabilities, (str, bytes)):
        for row in capabilities:
            if not isinstance(row, Mapping):
                continue
            lines.append(
                "| "
                f"{_markdown_cell(row.get('label', ''))} | "
                f"{_markdown_cell(row.get('status', 'MISSING'))} | "
                f"{_markdown_cell(row.get('evidence', ''))} |"
            )
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    """Evaluate an evidence file and return zero only for a trusted artifact."""
    parser = argparse.ArgumentParser(prog="graphify trust")
    parser.add_argument("evidence", type=Path, help="JSON file containing a capabilities object")
    parser.add_argument("--json-out", type=Path, help="write the evaluated JSON report")
    parser.add_argument("--markdown-out", type=Path, help="write the Markdown report")
    args = parser.parse_args(argv)

    try:
        payload: Any = json.loads(args.evidence.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"graphify trust: could not read evidence: {exc}", file=sys.stderr)
        return 2
    if not isinstance(payload, Mapping) or not isinstance(payload.get("capabilities"), Mapping):
        print("graphify trust: evidence must contain a capabilities object", file=sys.stderr)
        return 2

    report = evaluate_navigation_trust(payload["capabilities"])
    provenance = payload.get("provenance")
    if isinstance(provenance, Mapping):
        report["provenance"] = dict(provenance)
    markdown = render_markdown(report)

    if args.json_out is not None:
        write_json_atomic(args.json_out, report, indent=2, ensure_ascii=False)
    if args.markdown_out is not None:
        write_text_atomic(args.markdown_out, markdown)
    print(markdown, end="")
    return 0 if report["status"] == "TRUSTED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
