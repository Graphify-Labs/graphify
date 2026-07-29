#!/usr/bin/env python3
"""Normalize and validate curriculum schedule tables in Graphify extraction JSON."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


TIMING_RELATIONS = {
    "proposed_in_week",
    "proposed_start_week",
    "proposed_finish_week",
    "current_release_candidate_week",
    "current_due_week",
}


def slug(value: str) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", value.lower())).strip("_")


def cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def is_separator(line: str) -> bool:
    cs = cells(line)
    return bool(cs) and all(re.fullmatch(r":?-{3,}:?", c.replace(" ", "")) for c in cs)


def title_of(lines: list[str], fallback: str) -> str:
    for line in lines:
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def authority_for(path: Path, lines: list[str]) -> str:
    probe = (str(path) + "\n" + "\n".join(lines[:18])).lower()
    heading = title_of(lines, "").lower()
    if "proposed" in path.name.lower() or "teaching plan" in heading or "future calendar" in heading:
        return "proposed_future"
    if "history" in probe or "historical" in probe or "day-by-day" in probe:
        return "historical"
    if "proposed" in probe or "teaching plan" in probe or "future calendar" in probe:
        return "proposed_future"
    if "release" in probe and ("due date" in probe or "due week" in probe):
        return "current_release"
    return "unspecified_schedule"


@dataclass(frozen=True)
class Fact:
    authority: str
    authority_id: str
    assignment: int
    title: str
    relation: str
    week: int
    source_file: str
    source_line: int
    row_key: str


@dataclass(frozen=True)
class Schedule:
    authority: str
    authority_id: str
    label: str
    source_file: str
    weeks: tuple[int, ...]
    row_keys: tuple[str, ...]


ASSIGNMENT_ITEM = re.compile(
    r"(?i)^\s*(?:(begin|finish)\s+)?(?:assignment\s*)?0*(\d{1,3})\s*[-—:]?\s*(.*)$"
)


def parse_alignment_cell(text: str, week: int) -> list[tuple[int, str, str]]:
    found: list[tuple[int, str, str]] = []
    for item in re.split(r"\s*;\s*", text):
        match = ASSIGNMENT_ITEM.match(item)
        if not match:
            continue
        phase, number, title = match.groups()
        title = re.split(
            r"\s+and\s+(?:array|project|integration|assignment)\b",
            title,
            maxsplit=1,
            flags=re.I,
        )[0]
        relation = {
            "begin": "proposed_start_week",
            "finish": "proposed_finish_week",
            None: "proposed_in_week",
        }[phase.lower() if phase else None]
        found.append((int(number), title.strip(), relation))
    return found


def parse_week_tables(path: Path, rel: str, lines: list[str]) -> tuple[list[Fact], list[Schedule]]:
    facts: list[Fact] = []
    schedules: list[Schedule] = []
    authority = authority_for(path, lines)
    label = title_of(lines, path.stem)
    aid = slug(rel)
    all_weeks: set[int] = set()
    row_keys: set[str] = set()
    i = 0
    while i + 2 < len(lines):
        if "|" not in lines[i] or not is_separator(lines[i + 1]):
            i += 1
            continue
        headers = [slug(h) for h in cells(lines[i])]
        week_idx = next((n for n, h in enumerate(headers) if h in {"week", "weeks"}), None)
        assignment_idx = next((n for n, h in enumerate(headers) if "assignment" in h), None)
        if week_idx is None or assignment_idx is None:
            i += 2
            continue
        j = i + 2
        while j < len(lines) and "|" in lines[j] and lines[j].strip().startswith("|"):
            row = cells(lines[j])
            if max(week_idx, assignment_idx) >= len(row):
                j += 1
                continue
            week_match = re.fullmatch(r"\s*(\d{1,2})\s*", row[week_idx])
            if not week_match:
                j += 1
                continue
            week = int(week_match.group(1))
            all_weeks.add(week)
            row_key = f"{rel}:{j + 1}"
            items = parse_alignment_cell(row[assignment_idx], week)
            if items:
                row_keys.add(row_key)
            for number, assignment_title, relation in items:
                facts.append(
                    Fact(
                        authority=authority,
                        authority_id=aid,
                        assignment=number,
                        title=assignment_title,
                        relation=relation if authority == "proposed_future" else f"{authority}_{relation}",
                        week=week,
                        source_file=rel,
                        source_line=j + 1,
                        row_key=row_key,
                    )
                )
            j += 1
        i = j
    if all_weeks:
        schedules.append(
            Schedule(authority, aid, label, rel, tuple(sorted(all_weeks)), tuple(sorted(row_keys)))
        )
    return facts, schedules


SECTION_HEADING = re.compile(r"^##\s+(?:Assignment\s*)?0*(\d{1,3})\s*[-—:]\s*(.+?)\s*$", re.I)
RELEASE_LINE = re.compile(r"^\*\*(Recommended Release|Release(?: Window)?|Due Date|Due Week):\*\*\s*(.+)", re.I)


def parse_section_schedule(path: Path, rel: str, lines: list[str]) -> tuple[list[Fact], list[Schedule]]:
    authority = authority_for(path, lines)
    if authority != "current_release":
        return [], []
    label = title_of(lines, path.stem)
    aid = slug(rel)
    facts: list[Fact] = []
    all_weeks: set[int] = set()
    row_keys: set[str] = set()
    current: tuple[int, str] | None = None
    for index, line in enumerate(lines, 1):
        heading = SECTION_HEADING.match(line)
        if heading:
            current = (int(heading.group(1)), heading.group(2).strip())
            continue
        timing = RELEASE_LINE.match(line)
        if not current or not timing:
            continue
        kind, value = timing.groups()
        timing_text = value if kind.lower().startswith("due") else value.split(";", 1)[0]
        weeks = sorted({int(x) for x in re.findall(r"\bWeek\s+(\d{1,2})\b", timing_text, re.I)})
        if not weeks:
            continue
        relation = "current_due_week" if kind.lower().startswith("due") else "current_release_candidate_week"
        row_key = f"{rel}:{index}"
        row_keys.add(row_key)
        for week in weeks:
            all_weeks.add(week)
            facts.append(
                Fact(
                    authority=authority,
                    authority_id=aid,
                    assignment=current[0],
                    title=current[1],
                    relation=relation,
                    week=week,
                    source_file=rel,
                    source_line=index,
                    row_key=row_key,
                )
            )
    schedules = []
    if all_weeks:
        schedules.append(
            Schedule(authority, aid, label, rel, tuple(sorted(all_weeks)), tuple(sorted(row_keys)))
        )
    return facts, schedules


def discover(root: Path) -> tuple[list[Fact], list[Schedule]]:
    facts: list[Fact] = []
    schedules: list[Schedule] = []
    for path in sorted(root.rglob("*.md")):
        rel_path = path.relative_to(root)
        if "graphify-out" in rel_path.parts or any(part.startswith(".") for part in rel_path.parts):
            continue
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        rel = rel_path.as_posix()
        table_facts, table_schedules = parse_week_tables(path, rel, lines)
        section_facts, section_schedules = parse_section_schedule(path, rel, lines)
        facts.extend(table_facts)
        schedules.extend(table_schedules)
        facts.extend(section_facts)
        schedules.extend(section_schedules)
    # Only authorities with actual assignment timing facts participate.
    active = {f.authority_id for f in facts}
    schedules = [s for s in schedules if s.authority_id in active]
    return facts, schedules


def assignment_candidates(nodes: list[dict]) -> dict[int, str]:
    choices: dict[int, list[tuple[int, int, str]]] = {}
    for node in nodes:
        label = node.get("label", "")
        match = re.search(r"\bAssignment\s+0*(\d{1,3})\b", label, re.I)
        if not match:
            continue
        number = int(match.group(1))
        source = str(node.get("source_file", ""))
        preference = 0 if "00-AssignmentInstructions" in source else 1
        choices.setdefault(number, []).append((preference, len(source), node["id"]))
    return {number: sorted(options)[0][2] for number, options in choices.items()}


def timing_kind(authority: str, relation: str) -> str:
    if authority == "current_release":
        return "due" if relation == "current_due_week" else "release"
    return "schedule"


def timing_node_id(authority_id: str, authority: str, relation: str, week: int) -> str:
    sid = f"curriculum_schedule_{authority_id}"
    kind = timing_kind(authority, relation)
    return f"{sid}_{kind}_week_{week}" if kind != "schedule" else f"{sid}_week_{week}"


def normalize(root: Path, input_path: Path, output_path: Path, expectations_path: Path) -> dict:
    extraction = json.loads(input_path.read_text(encoding="utf-8"))
    facts, schedules = discover(root)
    nodes = list(extraction.get("nodes", []))
    edges = list(extraction.get("edges", []))
    hyperedges = list(extraction.get("hyperedges", []))
    assignment_ids = assignment_candidates(nodes)
    schedule_files = {s.source_file for s in schedules}

    # Replace prior deterministic output and LLM timing guesses from the same authorities.
    original_node_ids = {n["id"] for n in nodes}
    nodes = [
        n for n in nodes
        if not n.get("curriculum_table")
        and not (
            n.get("source_file") in schedule_files
            and re.fullmatch(r"(?:Proposed|Current Release) Week \d+", n.get("label", ""))
        )
    ]
    node_ids = {n["id"] for n in nodes}
    removed_node_ids = original_node_ids - node_ids
    edges = [
        e for e in edges
        if not e.get("curriculum_table")
        and e.get("source") not in removed_node_ids
        and e.get("target") not in removed_node_ids
        and not (
            e.get("source_file") in schedule_files
            and (
                e.get("relation") in TIMING_RELATIONS
                or "timing_proposed_week" in e.get("relation", "")
            )
        )
    ]

    schedule_by_id = {s.authority_id: s for s in schedules}
    for schedule in schedules:
        sid = f"curriculum_schedule_{schedule.authority_id}"
        if sid not in node_ids:
            nodes.append(
                {
                    "id": sid,
                    "label": schedule.label,
                    "file_type": "concept",
                    "source_file": schedule.source_file,
                    "source_location": "schedule authority",
                    "source_url": None,
                    "captured_at": None,
                    "author": None,
                    "contributor": None,
                    "schedule_authority": schedule.authority,
                    "curriculum_table": True,
                }
            )
            node_ids.add(sid)
        concepts: set[tuple[str, int]] = set()
        if schedule.authority == "proposed_future":
            concepts.update(("schedule", week) for week in schedule.weeks)
        concepts.update(
            (timing_kind(f.authority, f.relation), f.week)
            for f in facts
            if f.authority_id == schedule.authority_id
        )
        for kind, week in sorted(concepts):
            wid = f"{sid}_{kind}_week_{week}" if kind != "schedule" else f"{sid}_week_{week}"
            if wid in node_ids:
                continue
            prefix = {
                "proposed_future": "Proposed",
                "current_release": "Current Release",
                "historical": "Historical",
            }.get(schedule.authority, "Schedule")
            if kind == "due":
                prefix = "Current Due"
            nodes.append(
                {
                    "id": wid,
                    "label": f"{prefix} Week {week}",
                    "file_type": "concept",
                    "source_file": schedule.source_file,
                    "source_location": f"week {week}",
                    "source_url": None,
                    "captured_at": None,
                    "author": None,
                    "contributor": None,
                    "schedule_authority": schedule.authority,
                    "timing_kind": kind,
                    "week": week,
                    "curriculum_table": True,
                }
            )
            node_ids.add(wid)
            edges.append(
                {
                    "source": wid,
                    "target": sid,
                    "relation": "part_of_schedule",
                    "confidence": "EXTRACTED",
                    "confidence_score": 1.0,
                    "source_file": schedule.source_file,
                    "source_location": f"week {week}",
                    "weight": 1.0,
                    "schedule_authority": schedule.authority,
                    "curriculum_table": True,
                }
            )

    for fact in facts:
        assignment_id = assignment_ids.get(fact.assignment)
        if assignment_id is None:
            assignment_id = f"curriculum_assignment_{fact.assignment:02d}_{slug(fact.title) or 'untitled'}"
            if assignment_id not in node_ids:
                nodes.append(
                    {
                        "id": assignment_id,
                        "label": f"Assignment {fact.assignment:02d}: {fact.title}".rstrip(": "),
                        "file_type": "concept",
                        "source_file": fact.source_file,
                        "source_location": f"line {fact.source_line}",
                        "source_url": None,
                        "captured_at": None,
                        "author": None,
                        "contributor": None,
                        "curriculum_table": True,
                    }
                )
                node_ids.add(assignment_id)
            assignment_ids[fact.assignment] = assignment_id
        week_id = timing_node_id(fact.authority_id, fact.authority, fact.relation, fact.week)
        edges.append(
            {
                "source": assignment_id,
                "target": week_id,
                "relation": fact.relation,
                "confidence": "EXTRACTED",
                "confidence_score": 1.0,
                "source_file": fact.source_file,
                "source_location": f"line {fact.source_line}",
                "weight": 1.0,
                "schedule_authority": fact.authority,
                "source_row_key": fact.row_key,
                "assignment_identifier": fact.assignment,
                "week": fact.week,
                "curriculum_table": True,
            }
        )

    result = {
        "nodes": nodes,
        "edges": edges,
        "hyperedges": hyperedges,
        "input_tokens": extraction.get("input_tokens", 0),
        "output_tokens": extraction.get("output_tokens", 0),
    }
    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    expectations = {
        "facts": [asdict(f) for f in facts],
        "schedules": [asdict(s) for s in schedules],
    }
    expectations_path.write_text(json.dumps(expectations, indent=2, ensure_ascii=False), encoding="utf-8")
    return {
        "schedules": len(schedules),
        "facts": len(facts),
        "assignments": len({(f.authority_id, f.assignment) for f in facts}),
        "output": str(output_path),
    }


def validate(root: Path, graph_path: Path, report_path: Path) -> tuple[dict, bool]:
    facts, schedules = discover(root)
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    nodes = {n["id"]: n for n in graph.get("nodes", [])}
    expected = {
        (f.authority_id, f.assignment, f.relation, f.week, f.row_key)
        for f in facts
    }
    actual_edges = [e for e in graph.get("links", graph.get("edges", [])) if e.get("curriculum_table")]
    actual = {
        (
            slug(e.get("source_file", "")),
            int(e["assignment_identifier"]),
            e["relation"],
            int(e["week"]),
            e["source_row_key"],
        )
        for e in actual_edges
        if e.get("relation") in TIMING_RELATIONS
    }
    missing = sorted(expected - actual)
    invented = sorted(actual - expected)
    expected_weeks = set()
    for schedule in schedules:
        if schedule.authority == "proposed_future":
            expected_weeks.update((schedule.authority_id, "schedule", week) for week in schedule.weeks)
    expected_weeks.update(
        (f.authority_id, timing_kind(f.authority, f.relation), f.week)
        for f in facts
    )
    actual_weeks = {
        (slug(n.get("source_file", "")), n.get("timing_kind", "schedule"), int(n["week"]))
        for n in nodes.values()
        if n.get("curriculum_table") and "week" in n
    }
    missing_weeks = sorted(expected_weeks - actual_weeks)
    expected_rows = {f.row_key for f in facts}
    actual_rows = {e.get("source_row_key") for e in actual_edges if e.get("source_row_key")}
    skipped_rows = sorted(expected_rows - actual_rows)
    provenance_missing = sorted(
        (
            e.get("source"),
            e.get("target"),
            e.get("relation"),
        )
        for e in actual_edges
        if e.get("relation") in TIMING_RELATIONS
        and not (e.get("source_file") and e.get("source_location") and e.get("source_row_key"))
    )

    target_authorities: dict[str, set[str]] = {}
    for edge in actual_edges:
        if edge.get("relation") in TIMING_RELATIONS:
            target_authorities.setdefault(edge.get("target", ""), set()).add(
                slug(edge.get("source_file", ""))
            )
    collapsed = {
        target: sorted(authorities)
        for target, authorities in target_authorities.items()
        if target and len(authorities) > 1
    }

    by_authority: dict[str, dict[int, dict[str, set[int]]]] = {}
    for fact in facts:
        by_authority.setdefault(fact.authority, {}).setdefault(fact.assignment, {}).setdefault(
            fact.relation, set()
        ).add(fact.week)
    proposed = by_authority.get("proposed_future", {})
    current = by_authority.get("current_release", {})
    competing = []
    for assignment in sorted(set(proposed) & set(current)):
        proposed_weeks = sorted({w for values in proposed[assignment].values() for w in values})
        release_weeks = sorted(
            current[assignment].get("current_release_candidate_week", set())
        )
        if proposed_weeks != release_weeks:
            competing.append(
                {
                    "assignment": assignment,
                    "proposed_weeks": proposed_weeks,
                    "current_release_weeks": release_weeks,
                    "classification": "competing_planning_schedules",
                }
            )

    assignments_without_timing = []
    for schedule in schedules:
        expected_assignments = {f.assignment for f in facts if f.authority_id == schedule.authority_id}
        actual_assignments = {
            int(e["assignment_identifier"])
            for e in actual_edges
            if slug(e.get("source_file", "")) == schedule.authority_id
            and e.get("relation") in TIMING_RELATIONS
        }
        for assignment in sorted(expected_assignments - actual_assignments):
            assignments_without_timing.append((schedule.authority_id, assignment))

    ok = not any(
        (
            missing,
            invented,
            missing_weeks,
            skipped_rows,
            provenance_missing,
            collapsed,
            assignments_without_timing,
        )
    )
    report = {
        "status": "pass" if ok else "fail",
        "expected_facts": len(expected),
        "actual_facts": len(actual),
        "schedules": [asdict(s) for s in schedules],
        "missing_relationships": missing,
        "invented_relationships": invented,
        "missing_timing_concepts": missing_weeks,
        "skipped_source_rows": skipped_rows,
        "relationships_without_row_provenance": provenance_missing,
        "assignments_without_timing": assignments_without_timing,
        "collapsed_authorities": collapsed,
        "competing_schedules": competing,
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report, ok


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    extract_parser = sub.add_parser("extract")
    extract_parser.add_argument("--root", type=Path, required=True)
    extract_parser.add_argument("--input", type=Path, required=True)
    extract_parser.add_argument("--output", type=Path, required=True)
    extract_parser.add_argument("--expectations", type=Path, required=True)
    validate_parser = sub.add_parser("validate")
    validate_parser.add_argument("--root", type=Path, required=True)
    validate_parser.add_argument("--graph", type=Path, required=True)
    validate_parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "extract":
        print(json.dumps(normalize(args.root.resolve(), args.input, args.output, args.expectations), indent=2))
        return 0
    report, ok = validate(args.root.resolve(), args.graph, args.report)
    print(json.dumps(report, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
