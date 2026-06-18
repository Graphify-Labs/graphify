"""Retrieval quality evaluation for graphify hybrid queries."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import networkx as nx

from graphify.retrieval import load_index, merge_seed_candidates, search_index
from graphify.serve import _bfs, _dfs, _pick_seeds, _query_terms, _score_nodes


class EvalError(ValueError):
    """Raised when an eval file is malformed or cannot be evaluated."""


def load_queries(path: Path) -> list[dict[str, Any]]:
    """Load JSONL eval queries.

    Each line must include `question` plus at least one expectation field:
    `expected_nodes`, `expected_labels`, or `expected_files`.
    """
    queries: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise EvalError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
        if not isinstance(item, dict):
            raise EvalError(f"{path}:{line_no}: expected a JSON object")
        question = item.get("question")
        if not isinstance(question, str) or not question.strip():
            raise EvalError(f"{path}:{line_no}: `question` must be a non-empty string")
        if not any(item.get(key) for key in ("expected_nodes", "expected_labels", "expected_files")):
            raise EvalError(
                f"{path}:{line_no}: add at least one of expected_nodes, expected_labels, expected_files"
            )
        queries.append(item)
    if not queries:
        raise EvalError(f"{path}: no eval queries found")
    return queries


def _as_strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return value
    raise EvalError("expectation fields must be strings or string arrays")


def _label_matches(data: dict[str, Any], expected: str) -> bool:
    label = str(data.get("label") or "").lower()
    return expected.lower() in label


def _file_matches(data: dict[str, Any], expected: str) -> bool:
    source = str(data.get("source_file") or "").lower()
    return expected.lower() in source


def _expected_node_set(G: nx.Graph, query: dict[str, Any]) -> set[str]:
    expected = set(_as_strings(query.get("expected_nodes")))
    labels = _as_strings(query.get("expected_labels"))
    files = _as_strings(query.get("expected_files"))
    for node_id, data in G.nodes(data=True):
        if any(_label_matches(data, label) for label in labels):
            expected.add(str(node_id))
        if any(_file_matches(data, source) for source in files):
            expected.add(str(node_id))
    return {node for node in expected if node in G}


def _forbidden_node_set(G: nx.Graph, query: dict[str, Any]) -> set[str]:
    forbidden = set(_as_strings(query.get("forbidden_nodes")))
    labels = _as_strings(query.get("forbidden_labels"))
    files = _as_strings(query.get("forbidden_files"))
    for node_id, data in G.nodes(data=True):
        if any(_label_matches(data, label) for label in labels):
            forbidden.add(str(node_id))
        if any(_file_matches(data, source) for source in files):
            forbidden.add(str(node_id))
    return {node for node in forbidden if node in G}


def _rank_candidates(
    G: nx.Graph,
    question: str,
    mode: str,
    *,
    k: int,
    index: dict[str, Any] | None,
) -> tuple[list[str], bool]:
    lexical = _score_nodes(G, _query_terms(question))
    if mode == "hybrid" and index is not None:
        hits = search_index(index, question, k=max(k, 20))
        return merge_seed_candidates(lexical, hits, k=k), True
    return _pick_seeds(lexical, max_k=k), mode != "hybrid"


def evaluate_queries(
    G: nx.Graph,
    graph_path: Path,
    queries: list[dict[str, Any]],
    *,
    mode: str = "hybrid",
    k: int = 5,
    depth: int = 2,
    out_dir: Path | None = None,
) -> dict[str, Any]:
    """Evaluate retrieval seed quality and graph traversal coverage."""
    if mode not in {"bfs", "dfs", "hybrid"}:
        raise EvalError("mode must be one of: bfs, dfs, hybrid")
    if k <= 0:
        raise EvalError("k must be positive")
    index = load_index(graph_path, out_dir) if mode == "hybrid" else None
    if mode == "hybrid" and index is None:
        raise EvalError("hybrid eval requires a fresh vector-index; run `graphify index` first")
    rows: list[dict[str, Any]] = []
    for query in queries:
        query_mode = str(query.get("mode") or mode)
        if query_mode not in {"bfs", "dfs", "hybrid"}:
            raise EvalError("query mode must be one of: bfs, dfs, hybrid")
        expected = _expected_node_set(G, query)
        if not expected:
            raise EvalError(f"query {query['question']!r} matched no expected nodes in graph")
        forbidden = _forbidden_node_set(G, query)
        candidates, used_requested_mode = _rank_candidates(
            G, query["question"], query_mode, k=k, index=index
        )
        traversal_mode = "bfs" if query_mode == "hybrid" else query_mode
        nodes, _edges = _dfs(G, candidates, depth) if traversal_mode == "dfs" else _bfs(G, candidates, depth)
        first_rank = next((idx + 1 for idx, node_id in enumerate(candidates) if node_id in expected), None)
        hit_count = len(set(candidates) & expected)
        reached = set(nodes) & expected
        forbidden_hits = sorted((set(candidates) | set(nodes)) & forbidden)
        rows.append(
            {
                "question": query["question"],
                "mode": query_mode,
                "used_requested_mode": used_requested_mode,
                "expected_count": len(expected),
                "candidate_nodes": candidates,
                "hit": first_rank is not None,
                "first_rank": first_rank,
                "reciprocal_rank": 0.0 if first_rank is None else 1.0 / first_rank,
                "recall_at_k": hit_count / len(expected),
                "path_coverage": len(reached) / len(expected),
                "forbidden_hits": forbidden_hits,
            }
        )
    total = len(rows)
    return {
        "mode": mode,
        "k": k,
        "depth": depth,
        "query_count": total,
        "used_requested_mode": all(row["used_requested_mode"] for row in rows),
        "hit_rate_at_k": sum(1 for row in rows if row["hit"]) / total,
        "mean_recall_at_k": sum(row["recall_at_k"] for row in rows) / total,
        "mrr": sum(row["reciprocal_rank"] for row in rows) / total,
        "mean_path_coverage": sum(row["path_coverage"] for row in rows) / total,
        "forbidden_hit_count": sum(len(row["forbidden_hits"]) for row in rows),
        "queries": rows,
    }


def format_report(result: dict[str, Any]) -> str:
    lines = [
        f"Eval: {result['query_count']} queries | mode={result['mode']} | k={result['k']} | depth={result['depth']}",
        f"hit_rate@{result['k']}: {result['hit_rate_at_k']:.3f}",
        f"mean_recall@{result['k']}: {result['mean_recall_at_k']:.3f}",
        f"MRR: {result['mrr']:.3f}",
        f"path_coverage: {result['mean_path_coverage']:.3f}",
        f"forbidden_hits: {result['forbidden_hit_count']}",
    ]
    if not result.get("used_requested_mode", True):
        lines.append("warning: requested mode was unavailable for at least one query")
    for row in result["queries"]:
        rank = row["first_rank"] if row["first_rank"] is not None else "miss"
        lines.append(
            f"- {row['question']} | rank={rank} | recall={row['recall_at_k']:.3f} | "
            f"path={row['path_coverage']:.3f} | forbidden={len(row['forbidden_hits'])}"
        )
    return "\n".join(lines)
