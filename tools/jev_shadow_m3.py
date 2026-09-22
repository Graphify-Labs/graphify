"""Held-out, candidate-bound Jev file-relevance evaluation."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter, defaultdict, deque
from pathlib import Path
from statistics import median
from typing import Any

from graphify.jev_shadow import _nodes_edges, call_typesafe
try:
    from tools import jev_shadow_eval as m1
except ModuleNotFoundError:  # pragma: no cover
    import jev_shadow_eval as m1

BUDGETS = (8, 12, 20)
SCHEMA_VERSION = 2
SELECTION_RULE = "sha256(case identity + normalized path), first three"
SUPERSEDED_COLLECTION = "SUPERSEDED_UNBOUND_CANDIDATE_QUESTIONS"
SUPERSEDED_REASON = "candidate-specific Noul questions were not semantically bound to individual candidate files"


def _sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _path(value: str) -> str:
    return value.replace("\\", "/").lstrip("./")


def project(graph: dict[str, Any]) -> dict[str, Any]:
    nodes, edges = _nodes_edges(graph)
    files: dict[str, dict[str, Any]] = {}
    by_id = {node["id"]: node for node in nodes}
    for node in nodes:
        path = _path(node.get("source_file", ""))
        if not path:
            continue
        item = files.setdefault(path, {"path": path, "basename": path.rsplit("/", 1)[-1],
            "parent": path.rsplit("/", 1)[0] if "/" in path else "", "node_count": 0,
            "communities": set(), "test_like": path.startswith("tests/") or "/test" in path or path.endswith("_test.py")})
        item["node_count"] += 1
        if str(node.get("community", "")):
            item["communities"].add(str(node["community"]))
    relations: dict[tuple[str, str, str, str, str], int] = Counter()
    for edge in edges:
        left, right = by_id.get(edge["source"]), by_id.get(edge["target"])
        if not left or not right:
            continue
        source, target = _path(left["source_file"]), _path(right["source_file"])
        if source and target and source != target:
            relations[(source, target, edge["relationship"].lower(), edge.get("provenance", "EXTRACTED"), "forward")] += 1
    rows = []
    for path in sorted(files):
        row = dict(files[path]); row["communities"] = sorted(row["communities"]); row["community_count"] = len(row["communities"]); rows.append(row)
    value = {"schema_version": 1, "files": rows, "relations": [{"source": s, "target": t, "relation": r, "provenance": p, "direction": d, "count": n} for (s, t, r, p, d), n in sorted(relations.items())]}
    value["fingerprint"] = _sha(value)
    return value


def folds(case: dict[str, Any], projection: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    represented = {item["path"] for item in projection["files"]}
    statuses = {item["path"]: item["status"] for item in case["github_changed_files"]}
    eligible = sorted(_path(path) for path in case["changed_files"] if _path(path) in represented and statuses.get(path) != "added")
    absent = sorted(_path(path) for path in case["changed_files"] if statuses.get(path) == "added" or _path(path) not in represented)
    if len(eligible) < 2:
        return [], absent
    identity = m1._case_identity(case)
    chosen = sorted(eligible, key=lambda path: (_sha({"case": identity, "path": path}), path))[:3]
    return [{"fold_id": _sha({"case": identity, "target": target})[:20], "seed_files": [p for p in eligible if p != target], "hidden_target": target} for target in chosen], absent


def _candidate_details(projection: dict[str, Any], seeds: list[str]) -> list[dict[str, Any]]:
    files = {item["path"]: item for item in projection["files"]}
    adjacent: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for relation in projection["relations"]:
        adjacent[relation["source"]].append(relation); adjacent[relation["target"]].append(relation)
    distance, queue = {seed: 0 for seed in seeds if seed in files}, deque(seed for seed in seeds if seed in files)
    while queue:
        current = queue.popleft()
        if distance[current] == 2: continue
        for rel in adjacent[current]:
            other = rel["target"] if rel["source"] == current else rel["source"]
            if other not in distance: distance[other] = distance[current] + 1; queue.append(other)
    parents = {files[s]["parent"] for s in seeds if s in files}; communities = {c for s in seeds if s in files for c in files[s]["communities"]}
    candidates = []
    for path, original in files.items():
        if path in seeds: continue
        shared_parent = original["parent"] in parents and bool(original["parent"])
        overlap = sorted(set(original["communities"]) & communities)
        if path not in distance and not shared_parent and not overlap: continue
        connections = [r for r in adjacent[path] if (r["source"] if r["target"] == path else r["target"]) in seeds]
        relation_count = sum(r["count"] for r in connections)
        priority = sum({"calls": 7, "imports": 6, "contains": 2, "defines": 2, "references": 4, "tests": 4}.get(r["relation"], 1) * r["count"] for r in connections)
        degree = sum(r["count"] for r in adjacent[path])
        item = dict(original, distance=distance.get(path, 3), relations_to_seed=sorted({r["relation"] for r in connections}), relation_count=relation_count, community_overlap=overlap)
        item["baseline_score"] = 100 - 25 * item["distance"] + 8 * priority + 4 * relation_count + 3 * len(overlap) + (2 if shared_parent else 0) - min(degree, 30)
        candidates.append(item)
    return sorted(candidates, key=lambda item: (-item["baseline_score"], item["distance"], item["path"]))


def candidates(projection: dict[str, Any], seeds: list[str], budget: int) -> list[dict[str, Any]]:
    return _candidate_details(projection, seeds)[:budget]


def _question_id(path: str) -> str:
    return "file_relevant:" + _sha(path)[:16]


def payload(fold: dict[str, Any], objective: str, candidate_rows: list[dict[str, Any]]) -> dict[str, Any]:
    public = [{key: value for key, value in row.items() if key != "baseline_score"} for row in candidate_rows]
    state = {"fold_id": fold["fold_id"], "objective": objective, "seed_files": fold["seed_metadata"], "candidates": public}
    questions = {_question_id(row["path"]): {"type": "noul", "candidate_path": row["path"], "instructions": f"Given `objective` and `seed_files`, is candidate file `{row['path']}` materially relevant to implementing, reviewing, or verifying this task? Judge only this one candidate file; do not answer for any other candidate."} for row in public}
    return {"model": "jev-latest", "state": state, "questions": questions}


def _rank(rows: list[dict[str, Any]], target: str, scores: dict[str, float] | None = None) -> int | None:
    ordered = sorted(rows, key=lambda row: (-(scores[row["path"]] if scores else row["baseline_score"]), row["path"]))
    return next((index for index, row in enumerate(ordered, 1) if row["path"] == target), None)


def metrics(rows: list[dict[str, Any]], field: str) -> dict[str, float | None]:
    ranks = [row[field] for row in rows if isinstance(row.get(field), int)]
    if not ranks: return {"top1": None, "top3": None, "mrr": None, "median_rank": None}
    return {"top1": sum(rank == 1 for rank in ranks) / len(ranks), "top3": sum(rank <= 3 for rank in ranks) / len(ranks), "mrr": sum(1 / rank for rank in ranks) / len(ranks), "median_rank": median(ranks)}


def per_budget_metrics(rows: list[dict[str, Any]], field: str) -> dict[str, dict[str, float | None]]:
    return {str(budget): metrics([row for row in rows if row["candidate_budget"] == budget], field) for budget in BUDGETS}


def per_pr_metrics(rows: list[dict[str, Any]], field: str) -> dict[str, dict[str, float | None]]:
    return {group: metrics([row for row in rows if row["case_group"] == group], field) for group in sorted({row["case_group"] for row in rows})}


def per_pr_budget_metrics(rows: list[dict[str, Any]], field: str) -> dict[str, dict[str, dict[str, float | None]]]:
    return {group: per_budget_metrics([row for row in rows if row["case_group"] == group], field)
            for group in sorted({row["case_group"] for row in rows})}


def corrected_conclusion(viable: bool, live: bool, baseline_by_budget: dict[str, dict[str, float | None]], jev_by_budget: dict[str, dict[str, float | None]], baseline_by_pr: dict[str, dict[str, float | None]], jev_by_pr: dict[str, dict[str, float | None]]) -> str:
    if not viable or not live: return "M3_EVIDENCE_INSUFFICIENT"
    threshold = 0.10
    budget_keys = [key for key in baseline_by_budget if key in jev_by_budget]
    budget = [jev_by_budget[key]["mrr"] - baseline_by_budget[key]["mrr"] for key in budget_keys
              if jev_by_budget[key]["mrr"] is not None and baseline_by_budget[key]["mrr"] is not None]
    prs = [jev_by_pr[key]["mrr"] - baseline_by_pr[key]["mrr"] for key in baseline_by_pr
           if key in jev_by_pr and jev_by_pr[key]["mrr"] is not None and baseline_by_pr[key]["mrr"] is not None]
    top3_regresses = any(jev_by_budget[key]["top3"] < baseline_by_budget[key]["top3"] for key in budget_keys
                         if jev_by_budget[key]["top3"] is not None and baseline_by_budget[key]["top3"] is not None)
    if len(budget) < len(BUDGETS) or len(prs) < 2: return "M3_EVIDENCE_INSUFFICIENT"
    materially_positive = lambda delta: delta >= threshold - 1e-9
    materially_negative = lambda delta: delta <= -threshold + 1e-9
    positive_prs = sum(materially_positive(delta) for delta in prs)
    negative_prs = sum(materially_negative(delta) for delta in prs)
    if (all(materially_positive(delta) for delta in budget) and not top3_regresses
            and positive_prs >= 2 and negative_prs == 0): return "M3_JEV_ADDS_SIGNAL"
    if all(materially_negative(delta) for delta in budget) and negative_prs >= 2 and not any(materially_positive(delta) for delta in prs): return "M3_JEV_HURTS_RANKING"
    return "M3_JEV_NO_CLEAR_GAIN"


def retained_record(case: dict[str, Any]) -> dict[str, Any] | None:
    current = m1._read_record(case["case_id"]); history = m1._root("state") / "history"
    choices = [current] if current else []
    if history.exists(): choices.extend(json.loads(path.read_text(encoding="utf-8")) for path in sorted(history.glob(f"*-{case['case_id']}.json"), reverse=True))
    for record in choices:
        graph = Path(record.get("graph_path", ""))
        if record.get("prepare_status") == "PREPARED" and record.get("case_identity") == m1._case_identity(case) and record.get("source_snapshot_sha") == case["merge_base_sha"] and graph.is_file() and record.get("graph_fingerprint") == hashlib.sha256(graph.read_bytes()).hexdigest(): return record
    return None


def evaluate(cases: list[dict[str, Any]], *, live: bool = False) -> dict[str, Any]:
    records, absent, result_folds = 0, [], []
    for case in cases:
        record = retained_record(case)
        if not record: continue
        records += 1; projection = project(json.loads(Path(record["graph_path"]).read_text(encoding="utf-8"))); case_folds, missing = folds(case, projection); absent.extend(missing)
        files = {item["path"]: item for item in projection["files"]}
        for fold in case_folds:
            fold["seed_metadata"] = [{key: files[path][key] for key in ("path", "basename", "parent", "node_count", "community_count", "test_like")} for path in fold["seed_files"]]
            for budget in BUDGETS:
                rows = candidates(projection, fold["seed_files"], budget); present = any(row["path"] == fold["hidden_target"] for row in rows)
                entry = {"fold_id": fold["fold_id"], "candidate_budget": budget, "candidate_count": len(rows), "candidate_paths": [row["path"] for row in rows], "candidate_fingerprint": _sha([{key: v for key, v in row.items() if key != "baseline_score"} for row in rows]), "target_present": present, "graphify_rank": _rank(rows, fold["hidden_target"]), "projection_fingerprint": projection["fingerprint"], "case_group": _sha(m1._case_identity(case))[:12]}
                if present:
                    outbound = payload(fold, case["title"], rows); encoded = json.dumps(outbound, sort_keys=True); assert "baseline_score" not in encoded and "hidden_target" not in encoded and "changed_files" not in encoded and "head_sha" not in encoded and "github" not in encoded
                    entry["payload_fingerprint"] = _sha(outbound)
                    if live:
                        response = call_typesafe(outbound, os.environ["TYPESAFE_API_KEY"]); score = {row["path"]: response["answers"][_question_id(row["path"])]["noul"] for row in rows}
                        entry.update({"jev_rank": _rank(rows, fold["hidden_target"], score), "jev_target_noul": score[fold["hidden_target"]], "returned_model": response["model"], "usage": response["usage"]})
                result_folds.append(entry)
    present = [row for row in result_folds if row["target_present"]]; independent_prs = len({row["case_group"] for row in present}); viable = independent_prs >= 2 and len(present) >= 4
    gb, jb = per_budget_metrics(present, "graphify_rank"), per_budget_metrics(present, "jev_rank"); gp, jp = per_pr_metrics(present, "graphify_rank"), per_pr_metrics(present, "jev_rank")
    result = {"schema_version": SCHEMA_VERSION, "candidate_budgets": list(BUDGETS), "selection_rule": SELECTION_RULE, "eligible_prs": records, "not_prechange_referenceable": sorted(set(absent)), "folds": result_folds, "target_present_folds": len(present), "target_missing_folds": len(result_folds) - len(present), "target_present_by_budget": {str(b): sum(row["target_present"] for row in result_folds if row["candidate_budget"] == b) for b in BUDGETS}, "target_missing_by_budget": {str(b): sum(not row["target_present"] for row in result_folds if row["candidate_budget"] == b) for b in BUDGETS}, "independent_prs": independent_prs, "viable": viable, "graphify_metrics": metrics(present, "graphify_rank"), "jev_metrics": metrics(present, "jev_rank"), "graphify_metrics_by_budget": gb, "jev_metrics_by_budget": jb, "graphify_metrics_by_pr": gp, "jev_metrics_by_pr": jp, "graphify_metrics_by_pr_budget": per_pr_budget_metrics(present, "graphify_rank"), "jev_metrics_by_pr_budget": per_pr_budget_metrics(present, "jev_rank"), "conclusion": corrected_conclusion(viable, live, gb, jb, gp, jp), "superseded_collection": {"label": SUPERSEDED_COLLECTION, "reason": SUPERSEDED_REASON, "calls": 36, "excluded_from_conclusion": True}, "live_calls": sum("jev_rank" in row for row in result_folds), "tokens": {"input": sum(row.get("usage", {}).get("input_tokens", 0) for row in result_folds), "output": sum(row.get("usage", {}).get("output_tokens", 0) for row in result_folds)}}
    result["population_fingerprint"] = _sha({"folds": [{"fold_id": row["fold_id"], "candidate_budget": row["candidate_budget"], "candidate_paths": row["candidate_paths"], "candidate_fingerprint": row["candidate_fingerprint"]} for row in result_folds]})
    return result


def population_manifest(result: dict[str, Any]) -> dict[str, Any]:
    return {"schema_version": 1, "candidate_budgets": result["candidate_budgets"], "selection_rule": result["selection_rule"], "population_fingerprint": result.get("population_fingerprint"), "folds": result["folds"]}


def report(result: dict[str, Any]) -> Path:
    path = m1._root("state") / "reports" / "m3.md"; path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Graphify Jev M3 held-out file relevance", "", "The first live collection is **SUPERSEDED_UNBOUND_CANDIDATE_QUESTIONS** (36 calls; candidate-specific Noul questions were not semantically bound to individual candidate files). Its Jev ranks are excluded from this repaired conclusion.", "", f"Eligible PRs: {result['eligible_prs']}; folds: {len(result['folds'])}; target present/missing: {result['target_present_folds']}/{result['target_missing_folds']}; independent PRs: {result['independent_prs']}.", f"Target-present by budget: {json.dumps(result['target_present_by_budget'], sort_keys=True)}; target-missing by budget: {json.dumps(result['target_missing_by_budget'], sort_keys=True)}.", f"Population fingerprint: {result.get('population_fingerprint', '-')}", f"Graphify metrics by budget: {json.dumps(result['graphify_metrics_by_budget'], sort_keys=True)}.", f"Jev metrics by budget: {json.dumps(result['jev_metrics_by_budget'], sort_keys=True)}.", f"Per-PR/per-budget Graphify metrics: {json.dumps(result['graphify_metrics_by_pr_budget'], sort_keys=True)}.", f"Per-PR/per-budget Jev metrics: {json.dumps(result['jev_metrics_by_pr_budget'], sort_keys=True)}.", f"Conclusion: **{result['conclusion']}**.", "", "| Fold | Budget | Candidates | Target present | Graphify rank | Jev rank |", "|---|---:|---:|---|---:|---:|"]
    lines.extend(f"| {row['fold_id']} | {row['candidate_budget']} | {row['candidate_count']} | {'yes' if row['target_present'] else 'no'} | {row.get('graphify_rank','-')} | {row.get('jev_rank','-')} |" for row in result["folds"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8"); return path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--live", action="store_true"); parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv); cases = m1.load_manifest(m1.DEFAULT_MANIFEST)
    if args.live and not os.environ.get("TYPESAFE_API_KEY"): raise SystemExit("TYPESAFE_API_KEY is required for --live")
    result = evaluate(cases, live=args.live); output = report(result)
    state = output.with_suffix(".json")
    if args.json: state.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"); state.with_name("m3-population.json").write_text(json.dumps(population_manifest(result), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__": main()
