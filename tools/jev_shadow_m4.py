"""M4: bounded hybrid and selective Jev evaluation over frozen M3 folds.

This module is intentionally sidecar-only.  ``--live`` is the sole operation
which talks to TypeSafe; analysis of an existing collection is offline.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

from graphify.jev_shadow import call_typesafe
try:
    from tools import jev_shadow_eval as m1
    from tools import jev_shadow_m3 as m3
except ModuleNotFoundError:  # pragma: no cover
    import jev_shadow_eval as m1
    import jev_shadow_m3 as m3


BUDGET = 12
SCHEMA_VERSION = 1
FUSION_WEIGHTS = (0.75, 0.50, 0.25)  # Graphify weight; Jev receives 1 - weight.
GATE_THRESHOLDS = (0.02, 0.05, 0.10, 0.20, 0.30)
ALWAYS_CALL = "ALWAYS_CALL"


def _sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _rank(paths: list[str], scores: dict[str, float], target: str) -> int | None:
    ordered = sorted(paths, key=lambda path: (-scores[path], path))
    return next((index for index, path in enumerate(ordered, 1) if path == target), None)


def _metrics(rows: list[dict[str, Any]], field: str) -> dict[str, float | None]:
    ranks = [row[field] for row in rows if isinstance(row.get(field), int)]
    if not ranks:
        return {"top1": None, "top3": None, "mrr": None, "median_rank": None}
    return {"top1": sum(rank == 1 for rank in ranks) / len(ranks), "top3": sum(rank <= 3 for rank in ranks) / len(ranks), "mrr": sum(1 / rank for rank in ranks) / len(ranks), "median_rank": median(ranks)}


def _rank_scores(scores: dict[str, float]) -> dict[str, float]:
    """Return normalized deterministic rank scores: best=1, worst=0."""
    paths = sorted(scores, key=lambda path: (-scores[path], path))
    if len(paths) <= 1:
        return {path: 1.0 for path in paths}
    denominator = len(paths) - 1
    return {path: 1 - index / denominator for index, path in enumerate(paths)}


def hybrid_scores(baseline: dict[str, float], jev: dict[str, float], graphify_weight: float) -> dict[str, float]:
    if set(baseline) != set(jev):
        raise ValueError("hybrid candidates must match")
    left, right = _rank_scores(baseline), _rank_scores(jev)
    return {path: graphify_weight * left[path] + (1 - graphify_weight) * right[path] for path in baseline}


def uncertainty_margin(baseline: dict[str, float]) -> float | None:
    """A target-free normalized top-two structural score margin.

    ``None`` means structurally decisive (fewer than two candidates), and is
    always skipped by a selective policy.
    """
    if len(baseline) < 2:
        return None
    first, second = sorted(baseline.values(), reverse=True)[:2]
    return (first - second) / max(1, abs(first), abs(second))


def should_call(baseline: dict[str, float], policy: float | str) -> bool:
    if policy == ALWAYS_CALL:
        return True
    margin = uncertainty_margin(baseline)
    return margin is not None and margin <= float(policy)


def _case_group(case: dict[str, Any]) -> str:
    return _sha(m1._case_identity(case))[:12]


def freeze_population(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Freeze all budget-12 folds before any Jev values are observed."""
    folds, eligible, absent = [], 0, []
    for case in cases:
        record = m3.retained_record(case)
        if not record:
            continue
        eligible += 1
        projection = m3.project(json.loads(Path(record["graph_path"]).read_text(encoding="utf-8")))
        case_folds, missing = m3.folds(case, projection)
        absent.extend(missing)
        files = {row["path"]: row for row in projection["files"]}
        for fold in case_folds:
            seed_metadata = [{key: files[path][key] for key in ("path", "basename", "parent", "node_count", "community_count", "test_like")} for path in fold["seed_files"]]
            rows = m3.candidates(projection, fold["seed_files"], BUDGET)
            paths = [row["path"] for row in rows]
            baseline = {row["path"]: row["baseline_score"] for row in rows}
            target = fold["hidden_target"]
            folds.append({"fold_id": fold["fold_id"], "case_group": _case_group(case), "objective": case["title"], "seed_files": fold["seed_files"], "seed_metadata": seed_metadata, "candidate_rows": rows, "candidate_paths": paths, "candidate_fingerprint": _sha([{key: value for key, value in row.items() if key != "baseline_score"} for row in rows]), "target_present": target in baseline, "hidden_target": target, "baseline_scores": baseline, "graphify_rank": _rank(paths, baseline, target), "projection_fingerprint": projection["fingerprint"]})
    inspectable = [{key: row[key] for key in ("fold_id", "case_group", "seed_files", "candidate_paths", "candidate_fingerprint", "target_present", "baseline_scores", "graphify_rank", "projection_fingerprint")} for row in folds]
    return {"schema_version": SCHEMA_VERSION, "candidate_budget": BUDGET, "selection_rule": m3.SELECTION_RULE, "eligible_prs": eligible, "not_prechange_referenceable": sorted(set(absent)), "folds": folds, "population_fingerprint": _sha(inspectable)}


def public_population(population: dict[str, Any]) -> dict[str, Any]:
    """The frozen manifest retains evaluation target status but never payloads."""
    keep = ("fold_id", "case_group", "seed_files", "candidate_paths", "candidate_fingerprint", "target_present", "baseline_scores", "graphify_rank", "projection_fingerprint")
    return {key: population[key] for key in ("schema_version", "candidate_budget", "selection_rule", "eligible_prs", "not_prechange_referenceable", "population_fingerprint")} | {"folds": [{key: row[key] for key in keep} for row in population["folds"]]}


def payload_for(row: dict[str, Any]) -> dict[str, Any]:
    fold = {"fold_id": row["fold_id"], "seed_metadata": row["seed_metadata"]}
    outbound = m3.payload(fold, row["objective"], row["candidate_rows"])
    encoded = json.dumps(outbound, sort_keys=True)
    forbidden = ("baseline_score", "hidden_target", "target_present", "case_group", "changed_files", "head_sha", "github")
    if any(value in encoded for value in forbidden):
        raise ValueError("M4 payload leaked evaluation-only information")
    return outbound


def collect_live(population: dict[str, Any], api_key: str) -> dict[str, Any]:
    """Collect every non-empty fold, deliberately independent of target status."""
    collected = []
    for row in population["folds"]:
        if not row["candidate_paths"]:
            continue
        outbound = payload_for(row)
        response = call_typesafe(outbound, api_key)
        scores = {path: response["answers"][m3._question_id(path)]["noul"] for path in row["candidate_paths"]}
        collected.append({"fold_id": row["fold_id"], "payload_fingerprint": _sha(outbound), "candidate_fingerprint": row["candidate_fingerprint"], "candidate_noul": scores, "returned_model": response["model"], "usage": response["usage"], "collected_at": datetime.now(timezone.utc).isoformat()})
    return {"schema_version": SCHEMA_VERSION, "candidate_budget": BUDGET, "population_fingerprint": population["population_fingerprint"], "collections": collected}


def _join(population: dict[str, Any], collection: dict[str, Any]) -> list[dict[str, Any]]:
    if collection.get("population_fingerprint") != population.get("population_fingerprint"):
        raise ValueError("collection does not match frozen population")
    by_fold = {item["fold_id"]: item for item in collection["collections"]}
    joined = []
    for source in population["folds"]:
        row = dict(source)
        item = by_fold.get(row["fold_id"])
        if item:
            if item["candidate_fingerprint"] != row["candidate_fingerprint"]:
                raise ValueError("collection candidate fingerprint mismatch")
            row.update(item)
            row["jev_rank"] = _rank(row["candidate_paths"], row["candidate_noul"], row["hidden_target"])
        joined.append(row)
    return joined


def _group_metrics(rows: list[dict[str, Any]], field: str) -> dict[str, dict[str, float | None]]:
    return {group: _metrics([row for row in rows if row["case_group"] == group], field) for group in sorted({row["case_group"] for row in rows})}


def _strategy_key(weight: float) -> str:
    return f"rank_fusion_g{weight:.2f}_j{1 - weight:.2f}"


def _choose_fusion(training: list[dict[str, Any]]) -> float:
    # Stable, predeclared selection: MRR, Top-3, then nearest equal-weight.
    ranked = []
    for weight in FUSION_WEIGHTS:
        field = "hybrid_" + _strategy_key(weight)
        values = _metrics(training, field)
        ranked.append((-(values["mrr"] or 0), -(values["top3"] or 0), abs(weight - .5), weight))
    return min(ranked)[-1]


def lopo_hybrid(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, float]]:
    present = [row for row in rows if row["target_present"] and "candidate_noul" in row]
    for row in present:
        for weight in FUSION_WEIGHTS:
            row["hybrid_" + _strategy_key(weight)] = _rank(row["candidate_paths"], hybrid_scores(row["baseline_scores"], row["candidate_noul"], weight), row["hidden_target"])
    choices = {}
    for group in sorted({row["case_group"] for row in present}):
        choices[group] = _choose_fusion([row for row in present if row["case_group"] != group])
    for row in present:
        weight = choices[row["case_group"]]
        row["hybrid_rank"] = row["hybrid_" + _strategy_key(weight)]
        row["hybrid_strategy"] = _strategy_key(weight)
    return present, choices


def _selective_rank(row: dict[str, Any], policy: float | str, ranking: str) -> int | None:
    if not should_call(row["baseline_scores"], policy):
        return row["graphify_rank"]
    return row[ranking]


def _retention(selective: float | None, baseline: float | None, full: float | None) -> float | None:
    if selective is None or baseline is None or full is None or full <= baseline:
        return None
    return (selective - baseline) / (full - baseline)


def _choose_gate(training_all: list[dict[str, Any]], training_present: list[dict[str, Any]]) -> float | str:
    baseline = _metrics(training_present, "graphify_rank")["mrr"]
    full = _metrics(training_present, "jev_rank")["mrr"]
    if baseline is None or full is None or full <= baseline:
        return ALWAYS_CALL
    eligible = []
    for threshold in GATE_THRESHOLDS:
        selective = _metrics([{**row, "candidate": _selective_rank(row, threshold, "jev_rank")} for row in training_present], "candidate")["mrr"]
        retained = _retention(selective, baseline, full)
        if retained is not None and retained >= .90 - 1e-9:
            rate = sum(should_call(row["baseline_scores"], threshold) for row in training_all) / len(training_all) if training_all else 1
            eligible.append((rate, threshold))
    return min(eligible)[1] if eligible else ALWAYS_CALL


def lopo_selective(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, float | str]]:
    all_rows = [row for row in rows if "candidate_noul" in row]
    present = [row for row in all_rows if row["target_present"]]
    policies = {}
    for group in sorted({row["case_group"] for row in all_rows}):
        train_all = [row for row in all_rows if row["case_group"] != group]
        train_present = [row for row in present if row["case_group"] != group]
        policies[group] = _choose_gate(train_all, train_present)
    for row in all_rows:
        policy = policies[row["case_group"]]
        row["gate_policy"] = policy
        row["gate_call"] = should_call(row["baseline_scores"], policy)
        if row["target_present"]:
            row["selective_jev_rank"] = _selective_rank(row, policy, "jev_rank")
            row["selective_hybrid_rank"] = _selective_rank(row, policy, "hybrid_rank")
    return all_rows, policies


def _hybrid_result(rows: list[dict[str, Any]]) -> str:
    if len({row["case_group"] for row in rows}) < 2 or len(rows) < 4:
        return "M4_HYBRID_EVIDENCE_INSUFFICIENT"
    baseline, jev, hybrid = (_metrics(rows, field) for field in ("graphify_rank", "jev_rank", "hybrid_rank"))
    if hybrid["mrr"] > baseline["mrr"] and hybrid["mrr"] > jev["mrr"] and all(_metrics([row for row in rows if row["case_group"] == group], "hybrid_rank")["mrr"] >= _metrics([row for row in rows if row["case_group"] == group], "jev_rank")["mrr"] for group in {row["case_group"] for row in rows}):
        return "M4_HYBRID_ADDS_GAIN"
    if hybrid["mrr"] < baseline["mrr"] and hybrid["mrr"] < jev["mrr"]:
        return "M4_HYBRID_HURTS"
    return "M4_HYBRID_NO_CLEAR_GAIN"


def analyze(population: dict[str, Any], collection: dict[str, Any], *, m3_result: dict[str, Any] | None = None) -> dict[str, Any]:
    rows = _join(population, collection)
    present, fusion_choices = lopo_hybrid(rows)
    all_rows, gate_policies = lopo_selective(rows)
    graphify, jev, hybrid = (_metrics(present, field) for field in ("graphify_rank", "jev_rank", "hybrid_rank"))
    selective_jev, selective_hybrid = (_metrics(present, field) for field in ("selective_jev_rank", "selective_hybrid_rank"))
    calls = sum(row["gate_call"] for row in all_rows)
    drift = []
    old = {(row["fold_id"], row.get("candidate_budget")): row for row in (m3_result or {}).get("folds", [])}
    for row in present:
        prior = old.get((row["fold_id"], BUDGET))
        if prior and prior.get("jev_target_noul") is not None:
            drift.append({"fold_id": row["fold_id"], "same_returned_model": prior.get("returned_model") == row.get("returned_model"), "target_noul_absolute_drift": abs(prior["jev_target_noul"] - row["candidate_noul"][row["hidden_target"]]), "target_rank_changed": prior.get("jev_rank") != row.get("jev_rank")})
    hybrid_result = _hybrid_result(present)
    selective_result = "M4_SELECTIVE_SAVES_CALLS" if calls < len(all_rows) and _retention(selective_jev["mrr"], graphify["mrr"], jev["mrr"]) is not None and _retention(selective_jev["mrr"], graphify["mrr"], jev["mrr"]) >= .90 else "M4_SELECTIVE_NO_SAFE_SAVINGS"
    if len(present) < 4 or len({row["case_group"] for row in present}) < 2:
        selective_result = "M4_SELECTIVE_EVIDENCE_INSUFFICIENT"
    overall = "M4_OPTIMIZATION_FOUND" if hybrid_result == "M4_HYBRID_ADDS_GAIN" or selective_result == "M4_SELECTIVE_SAVES_CALLS" else "M4_JEV_ONLY_REMAINS_BEST"
    return {"schema_version": SCHEMA_VERSION, "candidate_budget": BUDGET, "population_fingerprint": population["population_fingerprint"], "fold_count": len(rows), "target_present_folds": len(present), "target_missing_folds": len(rows) - len(present), "live_calls": len(collection["collections"]), "tokens": {"input": sum(item.get("usage", {}).get("input_tokens", 0) for item in collection["collections"]), "output": sum(item.get("usage", {}).get("output_tokens", 0) for item in collection["collections"])}, "returned_models": sorted({item.get("returned_model") for item in collection["collections"]}), "graphify_metrics": graphify, "jev_metrics": jev, "hybrid_metrics": hybrid, "hybrid_per_pr": _group_metrics(present, "hybrid_rank"), "fusion_choices": fusion_choices, "hybrid_result": hybrid_result, "selective": {"gate_policies": gate_policies, "calls": calls, "skips": len(all_rows) - calls, "call_rate": calls / len(all_rows) if all_rows else None, "calls_saved": len(all_rows) - calls, "jev_metrics": selective_jev, "hybrid_metrics": selective_hybrid, "jev_gain_retained": _retention(selective_jev["mrr"], graphify["mrr"], jev["mrr"]), "hybrid_gain_retained": _retention(selective_hybrid["mrr"], graphify["mrr"], hybrid["mrr"]), "false_skips": sum(not row["gate_call"] and row["target_present"] and row["jev_rank"] < row["graphify_rank"] for row in all_rows), "useful_skips": sum(not row["gate_call"] and row["target_present"] and row["graphify_rank"] <= row["jev_rank"] for row in all_rows), "result": selective_result}, "stability": drift, "overall_result": overall, "folds": [{key: row.get(key) for key in ("fold_id", "case_group", "target_present", "graphify_rank", "jev_rank", "hybrid_rank", "hybrid_strategy", "gate_policy", "gate_call", "selective_jev_rank", "selective_hybrid_rank")} for row in all_rows]}


def _reports() -> Path:
    return m1._root("state") / "reports"


def write_reports(population: dict[str, Any], collection: dict[str, Any], result: dict[str, Any]) -> Path:
    root = _reports(); root.mkdir(parents=True, exist_ok=True)
    (root / "m4-population.json").write_text(json.dumps(public_population(population), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (root / "m4.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (root / "m4-collection.json").write_text(json.dumps(collection, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    selective = result["selective"]
    lines = ["# Graphify Jev M4 hybrid and selective evaluation", "", f"Population fingerprint: `{result['population_fingerprint']}`.", f"Budget: {BUDGET}; folds: {result['fold_count']}; target present/missing: {result['target_present_folds']}/{result['target_missing_folds']}.", f"Live calls: {result['live_calls']}; models: {', '.join(result['returned_models'])}; tokens: {json.dumps(result['tokens'], sort_keys=True)}.", f"Graphify metrics: {json.dumps(result['graphify_metrics'], sort_keys=True)}.", f"Jev metrics: {json.dumps(result['jev_metrics'], sort_keys=True)}.", f"Hybrid LOPO metrics: {json.dumps(result['hybrid_metrics'], sort_keys=True)}; result: **{result['hybrid_result']}**.", f"Selective calls/skips/rate: {selective['calls']}/{selective['skips']}/{selective['call_rate']}; calls saved: {selective['calls_saved']}.", f"Selective Jev metrics: {json.dumps(selective['jev_metrics'], sort_keys=True)}; gain retained: {selective['jev_gain_retained']}; result: **{selective['result']}**.", f"Overall result: **{result['overall_result']}**."]
    path = root / "m4.md"; path.write_text("\n\n".join(lines) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--live", action="store_true"); parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    population = freeze_population(m1.load_manifest(m1.DEFAULT_MANIFEST))
    root = _reports(); collection_path = root / "m4-collection.json"
    if args.live:
        key = os.environ.get("TYPESAFE_API_KEY")
        if not key: raise SystemExit("TYPESAFE_API_KEY is required for --live")
        collection = collect_live(population, key)
    elif collection_path.is_file():
        collection = json.loads(collection_path.read_text(encoding="utf-8"))
    else:
        raise SystemExit("no M4 collection exists; use --live")
    m3_path = root / "m3.json"; m3_result = json.loads(m3_path.read_text(encoding="utf-8")) if m3_path.is_file() else None
    result = analyze(population, collection, m3_result=m3_result); path = write_reports(population, collection, result)
    if args.json: print(json.dumps(result, indent=2, sort_keys=True))
    print(path)


if __name__ == "__main__": main()
