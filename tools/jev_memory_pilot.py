"""Local, offline-first Graphify memory relevance pilot."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

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
