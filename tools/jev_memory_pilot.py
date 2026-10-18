"""Local, offline-first Graphify memory relevance pilot."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from graphify.paths import write_json_atomic
from graphify.serve import _query_terms, _read_graph, _score_query


def _head(repo: Path) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True,
    ).strip()


def candidate_pool(graph_path: Path, repo: Path, question: str) -> list[dict]:
    """Return up to ten Graphify-ranked nodes from a graph pinned to repo HEAD."""
    graph = _read_graph(str(graph_path))
    if graph.graph.get("_built_at_commit") != _head(repo):
        raise ValueError("graph commit differs from source HEAD; rebuild the graph")
    ranked = _score_query(graph, _query_terms(question), collect_per_term_seeds=False).ranked[:10]
    sources = sorted({source for _, nid in ranked
                      if isinstance(source := graph.nodes[nid].get("source_file"), str)
                      and source})
    for source in sources:
        if subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", source],
            cwd=repo, capture_output=True,
        ).returncode != 0:
            raise ValueError(f"candidate source is not tracked at graph HEAD: {source}")
    if sources and subprocess.run(
        ["git", "diff", "--quiet", "HEAD", "--", *sources], cwd=repo,
    ).returncode != 0:
        raise ValueError("source has uncommitted edits; rebuild the graph")
    return [
        {
            "node_id": nid,
            "label": graph.nodes[nid].get("label", nid),
            "type": graph.nodes[nid].get("type", ""),
            "source_file": graph.nodes[nid].get("source_file", ""),
            "source_location": graph.nodes[nid].get("source_location", ""),
            "baseline_rank": rank,
        }
        for rank, (_, nid) in enumerate(ranked, 1)
    ]


def load_case(path: Path, case_id: str, graph_node_ids: set[str], project: str) -> dict:
    """Select one labeled case and its observations from a local corpus."""
    corpus = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(corpus, dict):
        raise ValueError("corpus needs observation and case lists")
    observations = corpus.get("observations")
    cases = corpus.get("cases")
    if not isinstance(observations, list) or not isinstance(cases, list):
        raise ValueError("corpus needs observation and case lists")
    for records in (observations, cases):
        if any(not isinstance(item, dict) for item in records):
            raise ValueError("corpus records must be objects")
        ids = [item.get("id") for item in records]
        if any(not isinstance(value, str) or not value for value in ids) or len(set(ids)) != len(ids):
            raise ValueError("duplicate or missing IDs")
    matches = [item for item in cases if item["id"] == case_id]
    if len(matches) != 1:
        raise ValueError("case ID not found")
    case = dict(matches[0])
    if not isinstance(case.get("question"), str) or not case["question"].strip():
        raise ValueError("case question is missing")
    gold = case.get("relevant_node_ids")
    pairs = case.get("relevant_pairs")
    selected = case.get("observation_ids")
    if not isinstance(gold, list) or not all(isinstance(nid, str) for nid in gold):
        raise ValueError("relevant node IDs are missing")
    if len(set(gold)) != len(gold) or set(gold) - graph_node_ids:
        raise ValueError("unknown node or duplicate gold node")
    if (not isinstance(selected, list) or len(selected) > 3
            or any(not isinstance(obs_id, str) for obs_id in selected)
            or len(set(selected)) != len(selected)):
        raise ValueError("invalid observation selection")
    by_id = {item["id"]: item for item in observations}
    if any(obs_id not in by_id for obs_id in selected):
        raise ValueError("unknown observation")
    resolved = [by_id[obs_id] for obs_id in selected]
    required = {"id", "project", "date", "summary", "source_ref"}
    if any(not required <= item.keys() or item["project"] != project
           or not all(isinstance(item[field], str) and item[field] for field in required)
           for item in resolved):
        raise ValueError("observation project or fields are invalid")
    if not isinstance(pairs, list) or any(
        not isinstance(pair, list) or len(pair) != 2
        or pair[0] not in gold or pair[1] not in selected for pair in pairs
    ):
        raise ValueError("invalid relevant pair")
    case["observations"] = resolved
    return case


def _answers_valid(
    candidates: list[dict], observations: list[dict], answers: dict,
    eligible_node_ids: set[str],
) -> bool:
    expected = {(item["node_id"], obs["id"]) for item in candidates
                if item["node_id"] in eligible_node_ids for obs in observations}
    return set(answers) == expected and all(
        isinstance(answer, dict)
        and answer.get("choice") in {"relevant", "unrelated", "insufficient_evidence"}
        and not isinstance(answer.get("probability"), bool)
        and isinstance(answer.get("probability"), (int, float))
        and math.isfinite(answer["probability"])
        and 0 <= answer["probability"] <= 1
        for answer in answers.values()
    )


def apply_decisions(
    candidates: list[dict], observations: list[dict],
    answers: dict[tuple[str, str], dict], *, eligible_node_ids: set[str], threshold: float,
) -> tuple[list[dict], list[dict]]:
    """Promote only complete, valid, above-threshold relevant decisions."""
    if not math.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError("threshold must be between zero and one")
    if not answers or not _answers_valid(candidates, observations, answers, eligible_node_ids):
        return candidates, []
    weight = {item["node_id"]: 0.0 for item in candidates}
    suggestions = []
    for candidate in candidates:
        node_id = candidate["node_id"]
        for obs in observations:
            answer = answers.get((node_id, obs["id"]))
            if not answer or answer["choice"] != "relevant":
                continue
            probability = float(answer["probability"])
            if probability < threshold:
                continue
            weight[node_id] = max(weight[node_id], probability)
            suggestions.append({"node_id": node_id, "observation_id": obs["id"],
                                "probability": probability, "status": "suggestion"})
    ordered = sorted(candidates, key=lambda item: (-weight[item["node_id"]], item["baseline_rank"]))
    return ordered, suggestions


def read_sidecar(path: Path, graph_path: Path, head: str) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    digest = hashlib.sha256(graph_path.read_bytes()).hexdigest()
    if (not isinstance(data, dict) or data.get("schema_version") != 1
            or data.get("head") != head or data.get("graph_sha256") != digest):
        raise ValueError("stale Jev memory sidecar")
    return data


def load_decisions(path: Path) -> dict[tuple[str, str], dict]:
    """Read synthetic/offline decisions; the runner validates the full pair set."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("decisions"), list):
        raise ValueError("offline decisions must be a list")
    answers = {}
    for item in data["decisions"]:
        if not isinstance(item, dict) or not all(
            isinstance(item.get(field), str) and item[field]
            for field in ("node_id", "observation_id", "choice")
        ):
            raise ValueError("invalid offline decision")
        key = (item["node_id"], item["observation_id"])
        if key in answers:
            raise ValueError("duplicate offline decision")
        answers[key] = {"choice": item["choice"], "probability": item.get("probability")}
    return answers


def save_private_payload(repo: Path, case_id: str, payload: dict) -> Path:
    """Store exact dry-run bytes outside all Git worktrees with private modes."""
    from tools.jev_memory_pilot_api import serialize_request

    repo_hash = hashlib.sha256(str(repo.resolve()).encode()).hexdigest()[:12]
    private_dir = Path.home() / ".local" / "share" / "jev-memory-pilot" / repo_hash
    private_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    private_dir.chmod(0o700)
    body = serialize_request(payload)
    name = hashlib.sha256(case_id.encode()).hexdigest()[:12]
    digest = hashlib.sha256(body).hexdigest()[:12]
    path = private_dir / f"{name}-{digest}.json"
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if path.is_symlink() or path.stat().st_mode & 0o777 != 0o600 or path.read_bytes() != body:
            raise ValueError("existing dry-run payload differs") from None
    else:
        with os.fdopen(fd, "wb") as handle:
            handle.write(body)
    return path


def query_with_decisions(
    graph_path: Path, repo: Path, case: dict, candidates: list[dict],
    answers: dict[tuple[str, str], dict], *, eligible_node_ids: set[str], threshold: float,
    model_id: str | None = None,
) -> str:
    """Call the original Graphify query, with seeds only when its top three change."""
    observations = case["observations"]
    valid = bool(answers) and _answers_valid(candidates, observations, answers, eligible_node_ids)
    if not answers:
        print("Jev unavailable; using unseeded Graphify query", file=sys.stderr)
    elif not valid:
        print("Invalid or incomplete decisions; using unseeded Graphify query", file=sys.stderr)
    normalized = answers if valid else {}
    ordered, suggestions = apply_decisions(
        candidates, observations, normalized, eligible_node_ids=eligible_node_ids,
        threshold=threshold,
    )
    assisted = [item["node_id"] for item in ordered[:3]] != [item["node_id"] for item in candidates[:3]]
    selected = [item["node_id"] for item in ordered[:3]] if assisted else []
    args = [sys.executable, "-m", "graphify", "query", case["question"],
            "--graph", str(graph_path)]
    if assisted:
        args.extend(part for node_id in selected for part in ("--seed", node_id))
    env = {**os.environ, "GRAPHIFY_QUERY_LOG_DISABLE": "1"}
    answer_text = subprocess.run(args, check=True, capture_output=True, text=True, env=env).stdout
    by_node = {item["node_id"]: item for item in candidates}
    by_obs = {item["id"]: item for item in observations}
    for suggestion in suggestions:
        node = by_node[suggestion["node_id"]]
        obs = by_obs[suggestion["observation_id"]]
        answer_text += (
            f'Suggested memory link: {node["node_id"]} '
            f'({node["source_file"]}:{node["source_location"]}) '
            f'↔ {obs["id"]} [{obs["source_ref"]}] (model-ranked)\n'
        )
    metadata = {
        "schema_version": 1,
        "graph_sha256": hashlib.sha256(graph_path.read_bytes()).hexdigest(),
        "head": _head(repo),
        "model": model_id if valid else None,
        "query_id": case["id"],
        "query_sha256": hashlib.sha256(case["question"].encode()).hexdigest(),
        "candidate_ids": [item["node_id"] for item in candidates],
        "selected_nodes": selected,
        "observation_ids": [item["id"] for item in observations],
        "decisions": [
            {"node_id": node_id, "observation_id": obs_id,
             "choice": answer["choice"], "probability": answer["probability"]}
            for (node_id, obs_id), answer in sorted(normalized.items())
        ],
        "redaction_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    write_json_atomic(graph_path.parent / "jev-memory-decisions.json", metadata, indent=2)
    return answer_text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline Graphify memory pilot")
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--threshold", type=float, default=0.8)
    parser.add_argument("--decisions", type=Path, help="Local offline decision JSON")
    parser.add_argument("--dry-run", action="store_true", help="Save exact Jev payload privately")
    parser.add_argument("--print-synthetic-payload", action="store_true")
    parser.add_argument("--live", action="store_true", help="Opt in to one paid Jev request")
    parser.add_argument("--approved-paid-use", action="store_true")
    parser.add_argument("--max-requests", type=int, default=0)
    args = parser.parse_args(argv)
    if args.live and (args.decisions or args.dry_run):
        parser.error("--live cannot be combined with --decisions or --dry-run")
    if args.print_synthetic_payload and not args.dry_run:
        parser.error("--print-synthetic-payload requires --dry-run")
    graph = _read_graph(str(args.graph))
    case = load_case(args.corpus, args.case_id, set(graph.nodes), args.project)
    candidates = candidate_pool(args.graph, args.repo, case["question"])
    answers = load_decisions(args.decisions) if args.decisions else {}
    eligible_node_ids = {item["node_id"] for item in candidates if item["source_file"]}
    model_id = None
    if args.dry_run or args.live:
        from tools.jev_memory_pilot_api import decide_once, make_request

        payload, pair_map = make_request(args.repo, case["question"], candidates,
                                         case["observations"])
        eligible_node_ids = {node_id for node_id, _ in pair_map.values()}
        if args.dry_run:
            if args.print_synthetic_payload:
                own_repo = Path(__file__).resolve().parents[1]
                fixture = own_repo / "tests" / "fixtures" / "jev_memory_pilot.json"
                if (args.repo.resolve() != own_repo or args.corpus.resolve() != fixture
                        or any(not obs["id"].startswith("synthetic-")
                               for obs in case["observations"])):
                    parser.error("printing is limited to the public synthetic fixture")
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                path = save_private_payload(args.repo, case["id"], payload)
                print(f"Dry-run payload: {path}; pairs: {len(pair_map)}", file=sys.stderr)
            return 0
        if not args.approved_paid_use or args.max_requests < 1:
            parser.error("--live requires --approved-paid-use and --max-requests >= 1")
        # No credential access occurs in default or dry-run mode.
        key = os.environ.get("JEV_MEMORY_PILOT_API_KEY")
        answers, model_id, cost = decide_once(
            payload, pair_map, live=True, approved=True,
            max_requests=args.max_requests, api_key=key,
        )
        if cost is not None:
            print(f"Jev actual cost: USD {cost:.8f}", file=sys.stderr)
    print(query_with_decisions(args.graph, args.repo, case, candidates, answers,
                               eligible_node_ids=eligible_node_ids,
                               threshold=args.threshold, model_id=model_id), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
