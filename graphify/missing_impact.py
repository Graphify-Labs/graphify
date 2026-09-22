"""Task-aware, file-level missing-impact candidate discovery.

The deterministic graph projection is deliberately separate from optional Jev
ranking.  Jev findings are hypotheses for source verification, never facts
about required changes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any

from graphify.jev_shadow import JevShadowError, _nodes_edges, call_typesafe

CANDIDATE_BUDGET = 12
SCHEMA_VERSION = 1


class MissingImpactError(ValueError):
    """A fail-closed missing-impact input or semantic evaluation error."""


def _sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _path(value: str) -> str:
    value = value.replace("\\", "/")
    # ``lstrip('./')`` would corrupt dotfiles such as ``.gitignore``.
    while value.startswith("./"):
        value = value[2:]
    return value.lstrip("/")


def load_graph(path: Path) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
        _nodes_edges(value)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, JevShadowError) as exc:
        raise MissingImpactError(f"invalid graph: {exc}") from exc
    return value, hashlib.sha256(raw).hexdigest()


def project_graph(graph: dict[str, Any]) -> dict[str, Any]:
    """Project symbols and only cross-file edges into deterministic file data."""
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
    relations: Counter[tuple[str, str, str, str]] = Counter()
    for edge in edges:
        left, right = by_id.get(edge["source"]), by_id.get(edge["target"])
        if not left or not right:
            continue
        source, target = _path(left["source_file"]), _path(right["source_file"])
        if source and target and source != target:
            relations[(source, target, edge["relationship"].lower(), edge.get("provenance", "EXTRACTED"))] += 1
    rows = []
    for path in sorted(files):
        row = dict(files[path]); row["communities"] = sorted(row["communities"]); row["community_count"] = len(row["communities"]); rows.append(row)
    result = {"schema_version": 1, "files": rows, "relations": [
        {"source": source, "target": target, "relation": relation, "provenance": provenance, "count": count}
        for (source, target, relation, provenance), count in sorted(relations.items())]}
    result["fingerprint"] = _sha(result)
    return result


def normalize_changed(paths: list[str], root: Path) -> list[str]:
    result = []
    for value in paths:
        path = Path(value)
        if path.is_absolute():
            try:
                value = str(path.resolve().relative_to(root.resolve()))
            except ValueError as exc:
                raise MissingImpactError(f"changed path is outside repository: {value}") from exc
        result.append(_path(value))
    return sorted(set(path for path in result if path))


def discover_git_changes(root: Path) -> tuple[list[str], list[str]]:
    """Use Git's NUL-delimited plumbing outputs; ignored files are excluded."""
    def git(*args: str) -> list[str]:
        completed = subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=False)
        if completed.returncode:
            raise MissingImpactError("--repo is not a Git repository; use --changed for explicit paths")
        return [_path(item.decode("utf-8", "surrogateescape")) for item in completed.stdout.split(b"\0") if item]
    tracked = set(git("diff", "--name-only", "-z")) | set(git("diff", "--cached", "--name-only", "-z"))
    untracked = set(git("ls-files", "--others", "--exclude-standard", "-z"))
    deleted = sorted(path for path in tracked if not (root / path).exists())
    active = sorted((tracked - set(deleted)) | untracked)
    return active, deleted


def _resolve_repo_root(requested: Path, *, explicit_changed: bool) -> Path:
    """Resolve a requested path to its Git worktree root when possible."""
    completed = subprocess.run(
        ["git", "-C", str(requested), "rev-parse", "--show-toplevel"],
        capture_output=True,
        check=False,
    )
    if completed.returncode == 0:
        return Path(completed.stdout.decode("utf-8", "surrogateescape").strip()).resolve()
    if explicit_changed:
        return requested
    raise MissingImpactError("--repo is not a Git repository; use --changed for explicit paths")


def classify_seeds(paths: list[str], projection: dict[str, Any], deleted: list[str] = []) -> tuple[list[str], list[str], list[str]]:
    represented = {row["path"] for row in projection["files"]}
    deleted_set = set(deleted)
    return (sorted(path for path in paths if path in represented and path not in deleted_set),
            sorted(path for path in paths if path not in represented and path not in deleted_set), sorted(deleted_set))


def candidates(projection: dict[str, Any], seeds: list[str], budget: int = CANDIDATE_BUDGET) -> list[dict[str, Any]]:
    files = {row["path"]: row for row in projection["files"]}
    adjacent: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for relation in projection["relations"]:
        adjacent[relation["source"]].append(relation); adjacent[relation["target"]].append(relation)
    distance, queue = {seed: 0 for seed in seeds if seed in files}, deque(seed for seed in seeds if seed in files)
    while queue:
        current = queue.popleft()
        if distance[current] == 2:
            continue
        for relation in adjacent[current]:
            other = relation["target"] if relation["source"] == current else relation["source"]
            if other not in distance:
                distance[other] = distance[current] + 1; queue.append(other)
    seed_parents = {files[path]["parent"] for path in seeds if files[path]["parent"]}
    seed_communities = {community for path in seeds for community in files[path]["communities"]}
    output = []
    for path, item in files.items():
        if path in seeds:
            continue
        parent_relation = item["parent"] in seed_parents
        overlap = sorted(set(item["communities"]) & seed_communities)
        if path not in distance and not parent_relation and not overlap:
            continue
        direct = [relation for relation in adjacent[path] if (relation["target"] if relation["source"] == path else relation["source"]) in seeds]
        relation_count = sum(relation["count"] for relation in direct)
        relation_weight = sum({"calls": 7, "imports": 6, "references": 4, "tests": 4}.get(relation["relation"], 1) * relation["count"] for relation in direct)
        degree = sum(relation["count"] for relation in adjacent[path])
        row = dict(item, distance=distance.get(path, 3), relations_to_seed=sorted({relation["relation"] for relation in direct}),
                   relation_count=relation_count, community_overlap=overlap, parent_relation=parent_relation)
        row["baseline_score"] = 100 - 25 * row["distance"] + 8 * relation_weight + 4 * relation_count + 3 * len(overlap) + (2 if parent_relation else 0) - min(degree, 30)
        output.append(row)
    ordered = sorted(output, key=lambda row: (-row["baseline_score"], row["distance"], row["path"]))[:budget]
    for rank, row in enumerate(ordered, 1): row["structural_rank"] = rank
    return ordered


def _question_id(path: str) -> str:
    return "file_relevant:" + hashlib.sha256(path.encode()).hexdigest()[:16]


def jev_payload(objective: str, projection: dict[str, Any], seeds: list[str], rows: list[dict[str, Any]]) -> dict[str, Any]:
    files = {row["path"]: row for row in projection["files"]}
    keep = ("path", "basename", "parent", "node_count", "communities", "community_count", "test_like")
    seed_metadata = [{key: files[path][key] for key in keep} for path in seeds]
    candidate_metadata = [{key: row[key] for key in keep + ("distance", "relations_to_seed", "relation_count", "community_overlap", "parent_relation")} for row in rows]
    questions = {_question_id(row["path"]): {"type": "noul", "candidate_path": row["path"], "instructions": f"Given this task and the files already being changed, is candidate file `{row['path']}` materially relevant enough that it should be source-verified for possible implementation, consumer, test, configuration, contract, or documentation impact? Judge only this candidate."} for row in rows}
    return {"model": "jev-latest", "state": {"objective": objective, "seed_files": seed_metadata, "candidates": candidate_metadata}, "questions": questions}


def build_result(*, objective: str, root: Path, graph_path: Path, graph_fingerprint: str, projection: dict[str, Any], changed: list[str], represented: list[str], unrepresented: list[str], deleted: list[str], rows: list[dict[str, Any]], live: bool) -> dict[str, Any]:
    result = {"schema_version": SCHEMA_VERSION, "objective": objective, "repo_root": str(root), "graph_path": str(graph_path), "graph_fingerprint": graph_fingerprint,
              "projection_fingerprint": projection["fingerprint"], "candidate_budget": CANDIDATE_BUDGET, "live": live, "returned_model": None, "usage": None,
              "changed_files": changed, "represented_seeds": represented, "unrepresented_seeds": unrepresented, "deleted_or_unavailable_seeds": deleted, "candidates": []}
    for row in rows:
        result["candidates"].append({key: row[key] for key in ("path", "structural_rank", "distance", "relations_to_seed", "relation_count", "community_overlap", "test_like", "parent_relation", "node_count")}
                                    | {"provenance": "JEV_INFERRED" if live else None, "semantic_rank": None, "jev_noul": None})
    return result


def prepare_analysis(*, objective: str, repo: str | Path = ".", graph: str | None = None,
                     changed_paths: list[str] | None = None, live: bool = False) -> dict[str, Any]:
    """Build the deterministic Missing Impact analysis shared by related views."""
    if not objective.strip():
        raise MissingImpactError("task objective must be non-empty")
    changed_paths = changed_paths or []
    root = _resolve_repo_root(Path(repo).resolve(), explicit_changed=bool(changed_paths))
    graph_path = (root / graph).resolve() if graph and not Path(graph).is_absolute() else (Path(graph).resolve() if graph else root / "graphify-out" / "graph.json")
    graph_value, graph_fingerprint = load_graph(graph_path)
    projection = project_graph(graph_value)
    changed, deleted = (normalize_changed(changed_paths, root), []) if changed_paths else discover_git_changes(root)
    represented, unrepresented, deleted = classify_seeds(changed, projection, deleted)
    if not changed and not deleted:
        return {"status": "NO_CHANGED_FILES", "result": {"schema_version": SCHEMA_VERSION, "status": "NO_CHANGED_FILES", "objective": objective, "changed_files": []}}
    if not represented:
        return {"status": "NO_GRAPH_REPRESENTED_SEEDS", "result": {"schema_version": SCHEMA_VERSION, "status": "NO_GRAPH_REPRESENTED_SEEDS", "objective": objective, "changed_files": changed, "unrepresented_seeds": unrepresented, "deleted_or_unavailable_seeds": deleted}}
    rows = candidates(projection, represented)
    result = build_result(objective=objective, root=root, graph_path=graph_path, graph_fingerprint=graph_fingerprint, projection=projection, changed=changed, represented=represented, unrepresented=unrepresented, deleted=deleted, rows=rows, live=live)
    status = "NO_MISSING_IMPACT_CANDIDATES" if not rows else None
    if status:
        result["status"] = status
    return {"status": status, "result": result, "projection": projection, "represented": represented, "rows": rows}


def rerank_live(analysis: dict[str, Any]) -> None:
    """Apply Missing Impact's single authorized Jev rerank to prepared rows."""
    result, rows = analysis["result"], analysis.get("rows", [])
    if not rows:
        return
    key = os.environ.get("TYPESAFE_API_KEY")
    if not key:
        raise MissingImpactError("TYPESAFE_API_KEY is required for --live")
    response = call_typesafe(jev_payload(result["objective"], analysis["projection"], analysis["represented"], rows), key)
    scores = {row["path"]: response["answers"][_question_id(row["path"])]["noul"] for row in rows}
    result["returned_model"], result["usage"] = response["model"], response["usage"]
    ranked = sorted(result["candidates"], key=lambda row: (-scores[row["path"]], row["path"]))
    for rank, row in enumerate(ranked, 1):
        row["semantic_rank"], row["jev_noul"], row["provenance"] = rank, scores[row["path"]], "JEV_INFERRED"
    result["candidates"] = ranked


def _human(result: dict[str, Any], status: str | None = None) -> str:
    if status: return status
    lines = ["Missing-impact candidates", f"Task: {result['objective']}", "", "Changed files:"]
    lines += [f"- {path}" for path in result["changed_files"]] or ["- (none)"]
    if result["unrepresented_seeds"]: lines += ["", "Graph-unrepresented changed files:"] + [f"- {path}" for path in result["unrepresented_seeds"]]
    if result["deleted_or_unavailable_seeds"]: lines += ["", "Deleted or unavailable changed files:"] + [f"- {path}" for path in result["deleted_or_unavailable_seeds"]]
    lines += ["", "JEV_INFERRED — source verification required" if result["live"] else "Semantic reranking not run; use --live to request Jev judgments."]
    for index, row in enumerate(result["candidates"], 1):
        lines += ["", f"{index}. {row['path']}", f"   semantic relevance: {row['jev_noul'] if row['jev_noul'] is not None else '-'}", f"   structural rank: {row['structural_rank']}", f"   evidence: {', '.join(row['relations_to_seed']) or 'structural context'}; distance {row['distance']}"]
    lines += ["", "These are hypotheses, not confirmed missing changes."]
    return "\n".join(lines)


def run(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="graphify missing-impact", description="Discover source-verification hypotheses beyond changed files.")
    parser.add_argument("--task", required=True); parser.add_argument("--repo", default="."); parser.add_argument("--graph"); parser.add_argument("--changed", action="append", default=[]); parser.add_argument("--top", type=int, default=5); parser.add_argument("--live", action="store_true"); parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        if not 1 <= args.top <= CANDIDATE_BUDGET: raise MissingImpactError("top must be between 1 and 12")
        analysis = prepare_analysis(objective=args.task, repo=args.repo, graph=args.graph, changed_paths=args.changed, live=args.live)
        status, result = analysis["status"], analysis["result"]
        if args.live:
            rerank_live(analysis)
        if "candidates" in result: result["candidates"] = result["candidates"][:args.top]
        print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) if args.json else _human(result, status))
    except (MissingImpactError, JevShadowError) as exc:
        parser.error(str(exc))
