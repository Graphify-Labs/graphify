"""Offline, deterministic M2 evaluation for Jev candidate selection.

This consumes only M1's retained public historical graph snapshots and records.
It never imports or calls the TypeSafe transport boundary.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import defaultdict
from collections import deque
from pathlib import Path
from typing import Any

from graphify.jev_shadow import JevShadowError, _file_anchors, _nodes_edges, _same_source_file, candidate_selection
try:  # package import in tests; direct sibling import when run as a script
    from tools import jev_shadow_eval as m1
except ModuleNotFoundError:  # pragma: no cover - exercised by the CLI
    import jev_shadow_eval as m1

BUDGETS = (8, 12, 20, 40)
STRATEGIES = ("distance-v2", "ranked-v2")


def _old_hunks(merge_base: str, head: str, path: str) -> list[tuple[int, int]]:
    """Old-side modified/deleted ranges; evaluation-only historical evidence."""
    output = subprocess.run(["git", "diff", "--unified=0", merge_base, head, "--", path], check=True,
                            text=True, stdout=subprocess.PIPE).stdout
    ranges = []
    for start, count in re.findall(r"@@ -(\\d+)(?:,(\\d+))? ", output):
        if int(count or 1):
            ranges.append((int(start), int(count or 1)))
    return ranges


def _source_range(node: dict[str, Any]) -> tuple[int, int] | None:
    value = str(node.get("source_location") or "")
    match = re.search(r"L?(\\d+)(?:\\s*(?:-|–|to)\\s*L?(\\d+))?", value)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2) or match.group(1))


def _reference(graph_path: Path, task: dict[str, Any], *, merge_base: str, head: str) -> tuple[dict[str, set[str]], set[str]]:
    """Independent pre-change anchors, patch ranges, and structural evidence."""
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    nodes, edges = _nodes_edges(graph)
    anchor_ids, _ = _file_anchors(nodes, task["changed_files"])
    patch_ids: set[str] = set()
    for changed in task["changed_files"]:
        for start, count in _old_hunks(merge_base, head, changed):
            end = start + count - 1
            for node in nodes:
                source_range = _source_range(node)
                if _same_source_file(node["source_file"], changed) and source_range and source_range[0] <= end and start <= source_range[1]:
                    patch_ids.add(node["id"])
    seeds = set(anchor_ids) | patch_ids | set(task["seed_nodes"])
    useful = {"calls", "imports", "contains", "defines", "inherits", "implements", "references", "tests"}
    reference_edges = {edge["id"] for edge in edges if (edge["source"] in seeds or edge["target"] in seeds) and edge["relationship"].lower() in useful}
    structural_ids = set(seeds)
    for edge in edges:
        if edge["id"] in reference_edges:
            structural_ids.add(edge["source"]); structural_ids.add(edge["target"])
    return {"file_anchors": set(anchor_ids), "patch_touched_prechange": patch_ids, "structural_consequences": structural_ids}, reference_edges


def _baseline_details(record: dict[str, Any]) -> dict[str, Any]:
    """Persist M1 traversal observations without reconstructing a graph."""
    graph_path, task = Path(record["graph_path"]), record["task"]
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    nodes, edges = _nodes_edges(graph)
    by_id = {node["id"]: node for node in nodes}
    baseline = json.loads(Path(record["payload_path"]).read_text(encoding="utf-8"))["state"]["candidates"]
    selected = [node["id"] for node in baseline["nodes"]]
    seeds = sorted({node["id"] for node in nodes if node["source_file"] in set(task["changed_files"])} | set(task["seed_nodes"]))
    adjacent: dict[str, list[str]] = {node["id"]: [] for node in nodes}
    degree: dict[str, int] = {node["id"]: 0 for node in nodes}
    for edge in edges:
        adjacent[edge["source"]].append(edge["target"]); adjacent[edge["target"]].append(edge["source"])
        degree[edge["source"]] += 1; degree[edge["target"]] += 1
    distance = {seed: 0 for seed in seeds}; queue = deque(seeds)
    while queue:
        current = queue.popleft()
        for neighbor in sorted(adjacent[current]):
            if neighbor not in distance:
                distance[neighbor] = distance[current] + 1; queue.append(neighbor)
    return {"candidate_node_count": len(selected), "candidate_edge_count": len(baseline["edges"]), "seed_nodes": seeds, "distance_from_seed": {node_id: distance.get(node_id) for node_id in selected}, "relation_types": sorted({edge["relationship"] for edge in baseline["edges"]}), "source_files": sorted({by_id[node_id]["source_file"] for node_id in selected if by_id[node_id]["source_file"]}), "node_types": sorted({by_id[node_id]["node_type"] for node_id in selected if by_id[node_id]["node_type"]}), "degree": {node_id: degree[node_id] for node_id in selected}, "community": {node_id: by_id[node_id]["community"] for node_id in selected}, "selection_order": selected, "node_cap_reached": record.get("node_cap_reached", False), "edge_cap_reached": record.get("edge_cap_reached", False)}


def evaluate(cases: list[dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for case in cases:
        record = m1._read_record(case["case_id"])
        if not record or record.get("prepare_status") != "PREPARED":
            continue
        graph_path, task = Path(record["graph_path"]), record["task"]
        references, reference_edges = _reference(graph_path, task, merge_base=record["merge_base_sha"], head=record["head_sha"])
        reference_nodes = set().union(*references.values())
        base = {"case_id": case["case_id"], "pr": case["pr"], "baseline": _baseline_details(record), "reference_provenance": {key: sorted(value) for key, value in references.items()}, "reference_node_count": len(reference_nodes), "reference_edge_count": len(reference_edges), "patch_categories": sorted({"test" if path.startswith("tests/") else "documentation" if path.endswith((".md", ".rst")) else "configuration" if path.endswith((".yml", ".yaml", ".toml", ".json")) else "code" for path in case["changed_files"]}), "runs": []}
        for strategy in STRATEGIES:
            for budget in BUDGETS:
                try:
                    result = candidate_selection(graph_path, task, node_budget=budget, strategy=strategy)
                    selected_nodes = {node["id"] for node in result["nodes"]}
                    selected_edges = {edge["id"] for edge in result["edges"]}
                    recall = lambda key: len(selected_nodes & references[key]) / len(references[key]) if references[key] else None
                    base["runs"].append({"strategy": strategy, "budget": budget, "status": "OK", "candidate_nodes": len(selected_nodes), "candidate_edges": len(selected_edges), "file_anchor_recall": recall("file_anchors"), "patch_touched_prechange_recall": recall("patch_touched_prechange"), "structural_consequence_recall": recall("structural_consequences"), "reference_node_recall": len(selected_nodes & reference_nodes) / len(reference_nodes) if reference_nodes else None, "reference_edge_recall": len(selected_edges & reference_edges) / len(reference_edges) if reference_edges else None, "mandatory_retained": set(result["metadata"]["mandatory_node_ids"]).issubset(selected_nodes), "anchor_unresolved_files": result["metadata"]["anchor_unresolved_files"], "source_file_coverage": len({node["source_file"] for node in result["nodes"] if node["source_file"]}), "test_evidence_retained": any(node["source_file"].startswith("tests/") for node in result["nodes"]), "consumer_evidence_retained": bool(selected_edges & reference_edges), "node_cap_reached": result["metadata"]["node_cap_reached"], "edge_cap_reached": result["metadata"]["edge_cap_reached"], "candidate_fingerprint": result["candidate_fingerprint"]})
                except JevShadowError as exc:
                    base["runs"].append({"strategy": strategy, "budget": budget, "status": str(exc)})
        rows.append(base)
    return {"schema_version": 1, "m1_prepared_cases": len(rows), "m1_unresolved_cases": len(cases) - len(rows), "budgets": list(BUDGETS), "strategies": list(STRATEGIES), "cases": rows}


def report(results: dict[str, Any]) -> Path:
    aggregates: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for case in results["cases"]:
        for run in case["runs"]:
            aggregates[(run["strategy"], run["budget"])].append(run)
    lines = ["# Graphify Jev M2 candidate-slice evaluation", "", "Offline only: this report uses M1's retained public merge-base graphs and deterministic patch/graph evidence. It makes zero TypeSafe calls; selector recall is deliberately reported separately from Jev stability.", "", "| Strategy | Budget | Cases | Mean nodes | Mean edges | File-anchor recall | Patch pre-change recall | Structural recall | Consumer/test cases | Overflow |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for (strategy, budget), runs in sorted(aggregates.items()):
        ok = [run for run in runs if run["status"] == "OK"]
        overflow = len(runs) - len(ok)
        mean = lambda key: sum(run[key] for run in ok) / len(ok) if ok else 0
        recall = lambda key: sum(run[key] for run in ok if run[key] is not None) / max(1, sum(run[key] is not None for run in ok))
        test_consumer = sum(run['consumer_evidence_retained'] and run['test_evidence_retained'] for run in ok)
        lines.append(f"| {strategy} | {budget} | {len(ok)} | {mean('candidate_nodes'):.1f} | {mean('candidate_edges'):.1f} | {recall('file_anchor_recall'):.1%} | {recall('patch_touched_prechange_recall'):.1%} | {recall('structural_consequence_recall'):.1%} | {test_consumer}/{len(ok)} | {overflow} |")
    lines.extend(["", "Reference provenance and per-case source coverage, unresolved anchors, edge recall, consumer evidence, and test evidence are in `m2.json`. Added-only symbols are not pre-change referenceable. A small candidate set alone is not a production-default decision.", ""])
    path = m1._root("state") / "reports" / "m2.md"
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=m1.DEFAULT_MANIFEST)
    parser.add_argument("--json", action="store_true", help="also write inspectable result JSON beside the report")
    args = parser.parse_args(argv)
    results = evaluate(m1.load_manifest(args.manifest))
    path = report(results)
    if args.json:
        (path.parent / "m2.json").write_text(json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
