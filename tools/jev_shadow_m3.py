"""Held-out file relevance evaluation for the opt-in Jev shadow experiment.

M3 only reads M1's merge-base graph snapshots.  It never modifies a graph and
does not contact TypeSafe unless ``--live`` is explicitly supplied after the
offline feasibility gate has passed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter, defaultdict, deque
from pathlib import Path
from statistics import median
from typing import Any

from graphify.jev_shadow import JevShadowError, _nodes_edges, call_typesafe
try:
    from tools import jev_shadow_eval as m1
except ModuleNotFoundError:  # pragma: no cover
    import jev_shadow_eval as m1

BUDGETS = (8, 12, 20)
SCHEMA_VERSION = 1
SELECTION_RULE = "sha256(case identity + normalized path), first three"


def _sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _path(value: str) -> str:
    return value.replace("\\", "/").lstrip("./")


def project(graph: dict[str, Any]) -> dict[str, Any]:
    """Project graph nodes and only supported cross-file edges to files."""
    nodes, edges = _nodes_edges(graph)
    files: dict[str, dict[str, Any]] = {}
    by_id = {node["id"]: node for node in nodes}
    for node in nodes:
        path = _path(node.get("source_file", ""))
        if not path:
            continue
        item = files.setdefault(path, {"path": path, "basename": path.rsplit("/", 1)[-1],
                                      "parent": path.rsplit("/", 1)[0] if "/" in path else "",
                                      "node_count": 0, "communities": set(),
                                      "test_like": path.startswith("tests/") or "/test" in path or path.endswith("_test.py")})
        item["node_count"] += 1
        if str(node.get("community", "")):
            item["communities"].add(str(node["community"]))
    relations: dict[tuple[str, str, str, str, str], int] = Counter()
    for edge in edges:
        left, right = by_id.get(edge["source"]), by_id.get(edge["target"])
        if not left or not right:
            continue
        source, target = _path(left["source_file"]), _path(right["source_file"])
        if not source or not target or source == target:
            continue
        relations[(source, target, edge["relationship"].lower(), edge.get("provenance", "EXTRACTED"), "forward")] += 1
    file_rows = []
    for path in sorted(files):
        row = dict(files[path]); row["communities"] = sorted(row["communities"]); row["community_count"] = len(row["communities"]); file_rows.append(row)
    relation_rows = [{"source": s, "target": t, "relation": r, "provenance": p, "direction": d, "count": count}
                     for (s, t, r, p, d), count in sorted(relations.items())]
    value = {"schema_version": SCHEMA_VERSION, "files": file_rows, "relations": relation_rows}
    value["fingerprint"] = _sha(value)
    return value


def folds(case: dict[str, Any], projection: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    represented = {item["path"] for item in projection["files"]}
    statuses = {item["path"]: item["status"] for item in case["github_changed_files"]}
    eligible = sorted(_path(path) for path in case["changed_files"] if _path(path) in represented and statuses.get(path) != "added")
    absent = sorted(_path(path) for path in case["changed_files"] if statuses.get(path) == "added" or _path(path) not in represented)
    if len(eligible) < 2:
        return [], absent
    case_identity = m1._case_identity(case)
    chosen = sorted(eligible, key=lambda path: (_sha({"case": case_identity, "path": path}), path))[:3]
    result = []
    for target in chosen:
        seeds = [path for path in eligible if path != target]
        opaque = _sha({"case": case_identity, "target": target})[:20]
        result.append({"fold_id": opaque, "seed_files": seeds, "hidden_target": target})
    return result, absent


def _candidate_details(projection: dict[str, Any], seeds: list[str]) -> list[dict[str, Any]]:
    files = {item["path"]: item for item in projection["files"]}
    adjacent: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for relation in projection["relations"]:
        adjacent[relation["source"]].append(relation); adjacent[relation["target"]].append(relation)
    distance, queue = {seed: 0 for seed in seeds if seed in files}, deque(seed for seed in seeds if seed in files)
    while queue:
        current = queue.popleft()
        if distance[current] == 2:
            continue
        for rel in adjacent[current]:
            other = rel["target"] if rel["source"] == current else rel["source"]
            if other not in distance:
                distance[other] = distance[current] + 1; queue.append(other)
    seed_parents = {files[s]["parent"] for s in seeds if s in files}
    seed_communities = {c for s in seeds if s in files for c in files[s]["communities"]}
    candidates = []
    for path, item in files.items():
        if path in seeds:
            continue
        shared_parent = item["parent"] in seed_parents and bool(item["parent"])
        shared_communities = sorted(set(item["communities"]) & seed_communities)
        if path not in distance and not shared_parent and not shared_communities:
            continue
        connections = [rel for rel in adjacent[path] if (rel["source"] if rel["target"] == path else rel["target"]) in seeds]
        relation_count = sum(rel["count"] for rel in connections)
        priority = sum({"calls": 7, "imports": 6, "contains": 2, "defines": 2, "references": 4, "tests": 4}.get(rel["relation"], 1) * rel["count"] for rel in connections)
        degree = sum(rel["count"] for rel in adjacent[path])
        item = dict(item, distance=distance.get(path, 3), relations_to_seed=sorted({rel["relation"] for rel in connections}), relation_count=relation_count, community_overlap=shared_communities)
        # Transparent fixed weights; this is not tuned against hidden labels.
        item["baseline_score"] = 100 - 25 * item["distance"] + 8 * priority + 4 * relation_count + 3 * len(shared_communities) + (2 if shared_parent else 0) - min(degree, 30)
        candidates.append(item)
    return sorted(candidates, key=lambda item: (-item["baseline_score"], item["distance"], item["path"]))


def candidates(projection: dict[str, Any], seeds: list[str], budget: int) -> list[dict[str, Any]]:
    return _candidate_details(projection, seeds)[:budget]


def payload(fold: dict[str, Any], objective: str, candidate_rows: list[dict[str, Any]]) -> dict[str, Any]:
    state = {"fold_id": fold["fold_id"], "objective": objective,
             "seed_files": [{key: value for key, value in item.items() if key != "hidden_target"} for item in candidate_rows if False],
             "candidates": candidate_rows}
    # Seed metadata deliberately comes from projection callers; no historical case fields enter this object.
    state["seed_files"] = fold["seed_metadata"]
    questions = {f"file_relevant:{index}": {"type": "noul", "instructions": "Given `objective`, `seed_files`, and `candidates`, is this candidate file likely materially relevant to implementing, reviewing, or verifying the task?"}
                 for index, _ in enumerate(candidate_rows)}
    return {"model": "jev-latest", "state": state, "questions": questions}


def _rank(rows: list[dict[str, Any]], target: str, scores: dict[str, float] | None = None) -> int | None:
    ordered = sorted(rows, key=lambda row: (-(scores[row["path"]] if scores else row["baseline_score"]), row["path"]))
    for index, row in enumerate(ordered, 1):
        if row["path"] == target:
            return index
    return None


def metrics(rows: list[dict[str, Any]], field: str) -> dict[str, float | None]:
    ranks = [row[field] for row in rows if isinstance(row.get(field), int)]
    if not ranks:
        return {"top1": None, "top3": None, "mrr": None, "median_rank": None}
    return {"top1": sum(rank == 1 for rank in ranks) / len(ranks), "top3": sum(rank <= 3 for rank in ranks) / len(ranks),
            "mrr": sum(1 / rank for rank in ranks) / len(ranks), "median_rank": median(ranks)}


def conclusion(viable: bool, live: bool, baseline: dict[str, float | None], jev: dict[str, float | None]) -> str:
    if not viable or not live:
        return "M3_EVIDENCE_INSUFFICIENT"
    delta = (jev["mrr"] or 0) - (baseline["mrr"] or 0)
    if delta >= 0.10 and (jev["top3"] or 0) >= (baseline["top3"] or 0):
        return "M3_JEV_ADDS_SIGNAL"
    if delta <= -0.10 and (jev["top3"] or 0) <= (baseline["top3"] or 0):
        return "M3_JEV_HURTS_RANKING"
    return "M3_JEV_NO_CLEAR_GAIN"


def retained_record(case: dict[str, Any]) -> dict[str, Any] | None:
    """Find a fingerprint-verified retained M1 snapshot without re-extracting it."""
    current = m1._read_record(case["case_id"])
    history = m1._root("state") / "history"
    choices = [current] if current else []
    if history.exists():
        choices.extend(json.loads(path.read_text(encoding="utf-8")) for path in sorted(history.glob(f"*-{case['case_id']}.json"), reverse=True))
    for record in choices:
        graph = Path(record.get("graph_path", ""))
        if (record.get("prepare_status") == "PREPARED" and record.get("case_identity") == m1._case_identity(case)
                and record.get("source_snapshot_sha") == case["merge_base_sha"] and graph.is_file()
                and record.get("graph_fingerprint") == hashlib.sha256(graph.read_bytes()).hexdigest()):
            return record
    return None


def evaluate(cases: list[dict[str, Any]], *, live: bool = False) -> dict[str, Any]:
    records, not_prechange, result_folds = 0, [], []
    for case in cases:
        record = retained_record(case)
        if not record:
            continue
        records += 1; projection = project(json.loads(Path(record["graph_path"]).read_text(encoding="utf-8")))
        case_folds, absent = folds(case, projection); not_prechange.extend(absent)
        files = {item["path"]: item for item in projection["files"]}
        for fold in case_folds:
            fold["seed_metadata"] = [{key: files[path][key] for key in ("path", "basename", "parent", "node_count", "community_count", "test_like")} for path in fold["seed_files"]]
            for budget in BUDGETS:
                rows = candidates(projection, fold["seed_files"], budget)
                present = any(row["path"] == fold["hidden_target"] for row in rows)
                entry = {"fold_id": fold["fold_id"], "candidate_budget": budget, "candidate_count": len(rows), "target_present": present,
                         "graphify_rank": _rank(rows, fold["hidden_target"]), "projection_fingerprint": projection["fingerprint"], "case_group": _sha(m1._case_identity(case))[:12]}
                if present:
                    outbound = payload(fold, case["title"], rows)
                    encoded = json.dumps(outbound, sort_keys=True)
                    assert "hidden_target" not in encoded and "changed_files" not in encoded and "head_sha" not in encoded and "github" not in encoded
                    entry["payload_fingerprint"] = _sha(outbound)
                    if live:
                        response = call_typesafe(outbound, os.environ["TYPESAFE_API_KEY"])
                        score = {row["path"]: response["answers"][f"file_relevant:{index}"]["noul"] for index, row in enumerate(rows)}
                        entry.update({"jev_rank": _rank(rows, fold["hidden_target"], score), "jev_target_noul": score[fold["hidden_target"]], "returned_model": response["model"], "usage": response["usage"]})
                result_folds.append(entry)
    present = [row for row in result_folds if row["target_present"]]
    independent_prs = len({row["case_group"] for row in present})
    viable = independent_prs >= 2 and len(present) >= 4
    baseline_metrics, jev_metrics = metrics(present, "graphify_rank"), metrics(present, "jev_rank")
    return {"schema_version": SCHEMA_VERSION, "candidate_budgets": list(BUDGETS), "selection_rule": SELECTION_RULE, "eligible_prs": records,
            "not_prechange_referenceable": sorted(set(not_prechange)), "folds": result_folds, "target_present_folds": len(present), "target_missing_folds": len(result_folds) - len(present),
            "independent_prs": independent_prs, "viable": viable, "graphify_metrics": baseline_metrics, "jev_metrics": jev_metrics, "conclusion": conclusion(viable, live, baseline_metrics, jev_metrics),
            "live_calls": sum("jev_rank" in row for row in result_folds), "tokens": {"input": sum(row.get("usage", {}).get("input_tokens", 0) for row in result_folds), "output": sum(row.get("usage", {}).get("output_tokens", 0) for row in result_folds)}}


def report(result: dict[str, Any]) -> Path:
    path = m1._root("state") / "reports" / "m3.md"; path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Graphify Jev M3 held-out file relevance", "", "Shadow-only evaluation over retained M1 merge-base graphs. Hidden changed-file labels are evaluation-only and never included in Jev state.", "",
             f"Eligible PRs: {result['eligible_prs']}; folds: {len(result['folds'])}; target present/missing: {result['target_present_folds']}/{result['target_missing_folds']}; independent PRs: {result['independent_prs']}.",
             f"Candidate budgets: {result['candidate_budgets']}; fold selection: {result['selection_rule']}.",
             f"Graphify metrics: {json.dumps(result['graphify_metrics'], sort_keys=True)}. Jev metrics: {json.dumps(result['jev_metrics'], sort_keys=True)}.",
             f"TypeSafe calls: {result['live_calls']}; tokens: {result['tokens']['input']} input / {result['tokens']['output']} output; M1 comparison: 165402 input / 68058 output.",
             f"Conclusion: **{result['conclusion']}**.", "", "| Fold | Budget | Candidates | Target present | Graphify rank | Jev rank | Jev Noul | Model | Tokens in/out |", "|---|---:|---:|---|---:|---:|---:|---|---|"]
    lines += [f"| {row['fold_id']} | {row['candidate_budget']} | {row['candidate_count']} | {'yes' if row['target_present'] else 'no'} | {row.get('graphify_rank','-')} | {row.get('jev_rank','-')} | {row.get('jev_target_noul','-')} | {row.get('returned_model','-')} | {row.get('usage',{}).get('input_tokens','-')}/{row.get('usage',{}).get('output_tokens','-')} |" for row in result["folds"]]
    lookup = {_sha(m1._case_identity(case))[:12]: case["pr"] for case in m1.load_manifest(m1.DEFAULT_MANIFEST)}
    lines += ["", "## Per-PR aggregation", "", "| PR | Target-present folds | Graphify MRR | Jev MRR |", "|---:|---:|---:|---:|"]
    for group in sorted({row["case_group"] for row in result["folds"]}):
        rows = [row for row in result["folds"] if row["case_group"] == group and row["target_present"]]
        lines.append(f"| {lookup.get(group, 'retained')} | {len(rows)} | {metrics(rows, 'graphify_rank')['mrr']} | {metrics(rows, 'jev_rank')['mrr']} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8"); return path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--live", action="store_true"); parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv); cases = m1.load_manifest(m1.DEFAULT_MANIFEST)
    if args.live and not os.environ.get("TYPESAFE_API_KEY"):
        raise SystemExit("TYPESAFE_API_KEY is required for --live")
    offline = evaluate(cases)
    if args.live and not offline["viable"]:
        result = offline
    else:
        result = evaluate(cases, live=args.live)
    output = report(result)
    if args.json: output.with_suffix(".json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__": main()
