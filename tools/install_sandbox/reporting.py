"""Concise manifest and Markdown reporting."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from .models import ScenarioResult


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def summarize(results: Iterable[ScenarioResult]) -> dict[str, int]:
    counts = Counter(result.status for result in results)
    return dict(sorted(counts.items()))


def build_manifest(
    *,
    repo: Path,
    selection: Mapping[str, object],
    package: Mapping[str, object],
    results: list[ScenarioResult],
    purge: Mapping[str, object],
) -> dict[str, object]:
    return {
        "harness": "graphify-install-sandbox-v8",
        "generated_at": utc_now(),
        "repo": str(repo),
        "selection": dict(selection),
        "package": dict(package),
        "summary": summarize(results),
        "scenario_count": len(results),
        "scenarios": [result.as_dict() for result in results],
        "purge": dict(purge),
    }


def render_report(manifest: Mapping[str, Any]) -> str:
    summary = manifest.get("summary", {})
    summary_text = ", ".join(f"{key}={value}" for key, value in summary.items())
    lines = [
        "# Graphify install sandbox",
        "",
        f"Status: {summary_text or 'no scenarios'}; purge={manifest['purge']['status']}",
        "",
        "| Scenario | Status | Uninstall |",
        "|---|---:|---:|",
    ]
    limitations: list[str] = []
    for scenario in manifest.get("scenarios", []):
        phases = scenario.get("phases", [])
        uninstall = next(
            (
                phase.get("status", "UNKNOWN")
                for phase in phases
                if phase.get("name") == "uninstall"
            ),
            "N/A",
        )
        lines.append(
            f"| {scenario['scenario']} | {scenario['status']} | {uninstall} |"
        )
        for limitation in scenario.get("limitations", []):
            if limitation not in limitations:
                limitations.append(limitation)
    if limitations:
        lines.extend(["", "## Runtime limitations", ""])
        lines.extend(f"- {item}" for item in limitations)
    failures = [
        scenario
        for scenario in manifest.get("scenarios", [])
        if scenario.get("status") == "FAIL"
    ]
    if failures:
        lines.extend(["", "## Failed scenarios", ""])
        for scenario in failures:
            failed_phases = [
                phase["name"]
                for phase in scenario.get("phases", [])
                if phase.get("status") == "FAIL"
            ]
            lines.append(
                f"- `{scenario['scenario']}`: {', '.join(failed_phases)} "
                f"([{scenario['artifact_dir']}/result.json]({scenario['artifact_dir']}/result.json))"
            )
    lines.extend(
        [
            "",
            "Detailed command logs and filesystem snapshots are under `scenarios/`.",
            "",
        ]
    )
    return "\n".join(lines)


def write_run_outputs(output: Path, manifest: Mapping[str, Any]) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output / "report.md").write_text(render_report(manifest), encoding="utf-8")
