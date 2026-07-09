"""Relevance evals for `graphify query` — does the ranked result actually contain
the nodes that answer the question?

`benchmark.py` measures how many *tokens* a query saves. This module measures
whether the query is *right*: given a fixture of (question -> expected nodes)
cases, it runs the real ranking pipeline (``serve.rank_query_nodes``) and scores
precision@k, recall@k, MRR, and nDCG@k. Metrics are defined once, up front, in
``METRIC_GLOSSARY`` (contract-first) so a number always means the same thing.

A fixture is JSONL, one case per line::

    {"query": "how does community detection work", "expect": ["cluster()", "graphify/cluster.py"]}
    {"query": "what renders the wiki", "expect": ["to_wiki()"], "depth": 2, "mode": "bfs"}

Each ``expect`` string matches a result node when it equals the node's label or
id, or names its ``source_file`` (full path or basename) — so fixtures can be
authored by naming the function or file you expect to surface, no node ids
required.

``--save`` appends the run to ``.graphify-evals/eval-results.jsonl`` (repo-local,
git-trackable); ``--replay`` re-runs the fixture and diffs every metric against
the most recent saved run, flagging regressions. That is the safety net for
tuning the ranking: a change that helps one query but quietly hurts three others
shows up as a negative aggregate delta.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import networkx as nx
from networkx.readwrite import json_graph

from graphify.paths import default_graph_json as _default_graph_json


# Contract-first: every metric is defined here, once. key -> (label, description).
METRIC_GLOSSARY: dict[str, tuple[str, str]] = {
    "p_at_k": (
        "P@k",
        "Fraction of the top-k ranked nodes that match some expected node.",
    ),
    "recall_at_k": (
        "Recall@k",
        "Fraction of expected nodes that appear within the top-k ranked nodes.",
    ),
    "mrr": (
        "MRR",
        "Reciprocal rank (1/r) of the first ranked node matching any expected node.",
    ),
    "ndcg_at_k": (
        "nDCG@k",
        "Binary-relevance normalized discounted cumulative gain over the top-k.",
    ),
    "hit_at_k": (
        "Hit@k",
        "1 if any expected node appears in the top-k, else 0.",
    ),
}

DEFAULT_K = 10
# A saved metric may wobble slightly across runs on identical inputs (it won't,
# since ranking is deterministic — but tolerance guards against float noise and
# lets --replay ignore trivial deltas). Regressions beyond this fail --replay.
REPLAY_TOLERANCE = 1e-9

_RESULTS_DIR = ".graphify-evals"
_RESULTS_FILE = "eval-results.jsonl"


@dataclass
class EvalCase:
    query: str
    expect: list[str]
    mode: str = "bfs"
    depth: int = 2
    context: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "EvalCase":
        query = d.get("query") or d.get("question")
        if not query:
            raise ValueError(f"eval case missing 'query': {d!r}")
        expect = d.get("expect") or d.get("expected") or []
        if isinstance(expect, str):
            expect = [expect]
        if not expect:
            raise ValueError(f"eval case for {query!r} has no 'expect' entries")
        return cls(
            query=str(query),
            expect=[str(e) for e in expect],
            mode=str(d.get("mode", "bfs")),
            depth=int(d.get("depth", 2)),
            context=[str(c) for c in (d.get("context") or [])],
        )


@dataclass
class CaseResult:
    query: str
    expect: list[str]
    matched: dict[str, int]  # expected string -> 1-based rank of first match (absent if unmatched)
    metrics: dict[str, float]


@dataclass
class EvalReport:
    k: int
    cases: list[CaseResult]
    aggregate: dict[str, float]

    def to_dict(self) -> dict:
        return {
            "k": self.k,
            "aggregate": self.aggregate,
            "cases": [
                {
                    "query": c.query,
                    "expect": c.expect,
                    "matched": c.matched,
                    "metrics": c.metrics,
                }
                for c in self.cases
            ],
        }


def load_cases(path: Path) -> list[EvalCase]:
    """Load eval cases from a JSONL file (or a JSON array of cases)."""
    text = path.read_text(encoding="utf-8")
    cases: list[EvalCase] = []
    stripped = text.lstrip()
    if stripped.startswith("["):
        for d in json.loads(text):
            cases.append(EvalCase.from_dict(d))
    else:
        for line_no, line in enumerate(text.splitlines(), start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                cases.append(EvalCase.from_dict(json.loads(line)))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSON ({exc})") from exc
    if not cases:
        raise ValueError(f"no eval cases found in {path}")
    return cases


def _node_matches(G: nx.Graph, node_id: str, expected: str) -> bool:
    """True when `expected` names this node by label, id, or source_file."""
    exp = expected.strip().casefold()
    if not exp:
        return False
    if node_id.casefold() == exp:
        return True
    data = G.nodes[node_id]
    label = str(data.get("label", "")).casefold()
    if label == exp or label.rstrip("()") == exp.rstrip("()"):
        return True
    src = str(data.get("source_file", "")).casefold()
    if src == exp:
        return True
    # Basename / suffix match so "cluster.py" hits "graphify/cluster.py".
    if src and (src.endswith("/" + exp) or Path(src).name == exp):
        return True
    return False


def _score_case(G: nx.Graph, ranked: list[str], expect: list[str], k: int) -> tuple[dict[str, int], dict[str, float]]:
    top = ranked[:k]
    # First rank (1-based, within top-k) at which each expected item matches.
    matched: dict[str, int] = {}
    for exp in expect:
        for rank, nid in enumerate(top, start=1):
            if _node_matches(G, nid, exp):
                matched[exp] = rank
                break
    # A top-k node is "relevant" if it matches any expected item.
    relevant_positions = [
        i for i, nid in enumerate(top, start=1)
        if any(_node_matches(G, nid, exp) for exp in expect)
    ]
    denom_k = max(1, min(k, len(top)))
    p_at_k = len(relevant_positions) / denom_k
    recall_at_k = len(matched) / len(expect) if expect else 0.0
    first_rank = min(matched.values()) if matched else 0
    mrr = 1.0 / first_rank if first_rank else 0.0
    hit_at_k = 1.0 if matched else 0.0
    # Binary-relevance nDCG@k. The ideal ranking puts all `num_relevant` relevant
    # nodes at the top, so IDCG normalizes against how many were actually found
    # (not len(expect) — one expected label can match several nodes, which would
    # otherwise push nDCG above 1.0). Result stays in [0, 1].
    num_relevant = len(relevant_positions)
    dcg = sum(1.0 / math.log2(pos + 1) for pos in relevant_positions)
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, min(num_relevant, k) + 1))
    ndcg = dcg / idcg if idcg else 0.0
    metrics = {
        "p_at_k": round(p_at_k, 4),
        "recall_at_k": round(recall_at_k, 4),
        "mrr": round(mrr, 4),
        "ndcg_at_k": round(ndcg, 4),
        "hit_at_k": hit_at_k,
    }
    return matched, metrics


def run_evals(
    G: nx.Graph,
    cases: list[EvalCase],
    *,
    k: int = DEFAULT_K,
    semantic: bool = False,
    graph_path: str | None = None,
) -> EvalReport:
    """Run every case through the real ranking pipeline and score it."""
    from graphify.serve import rank_query_nodes

    results: list[CaseResult] = []
    for case in cases:
        semantic_scores = None
        if semantic:
            try:
                from graphify.embed import semantic_scores_for_query
                semantic_scores = semantic_scores_for_query(G, case.query, graph_path=graph_path)
            except Exception:
                semantic_scores = None
        ranked = rank_query_nodes(
            G,
            case.query,
            mode=case.mode,
            depth=case.depth,
            context_filters=case.context or None,
            semantic_scores=semantic_scores,
        )
        matched, metrics = _score_case(G, ranked, case.expect, k)
        results.append(CaseResult(case.query, case.expect, matched, metrics))

    aggregate: dict[str, float] = {}
    if results:
        for key in METRIC_GLOSSARY:
            aggregate[key] = round(
                sum(c.metrics[key] for c in results) / len(results), 4
            )
    return EvalReport(k=k, cases=results, aggregate=aggregate)


def load_graph(graph_path: str) -> nx.Graph:
    from graphify.security import check_graph_file_size_cap

    p = Path(graph_path)
    check_graph_file_size_cap(p)
    data = json.loads(p.read_text(encoding="utf-8"))
    if "links" not in data and "edges" in data:
        data = dict(data, links=data["edges"])
    data = {**data, "directed": True}
    try:
        return json_graph.node_link_graph(data, edges="links")
    except TypeError:
        return json_graph.node_link_graph(data)


def results_path(base: Path | None = None) -> Path:
    return (base or Path.cwd()) / _RESULTS_DIR / _RESULTS_FILE


def save_report(report: EvalReport, *, base: Path | None = None, fixture: str | None = None) -> Path:
    """Append the run to the repo-local results log and return its path."""
    path = results_path(base)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = report.to_dict()
    record["fixture"] = fixture
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")
    return path


def load_last_report(*, base: Path | None = None) -> dict | None:
    """The most recent saved run, or None if there is no history."""
    path = results_path(base)
    if not path.exists():
        return None
    last = None
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                last = json.loads(line)
            except json.JSONDecodeError:
                continue
    return last


def diff_aggregates(current: dict[str, float], baseline: dict[str, float]) -> dict[str, float]:
    """current - baseline per metric (only keys present in current)."""
    return {key: round(current.get(key, 0.0) - baseline.get(key, 0.0), 4) for key in current}


def scaffold_fixture(G: nx.Graph, *, limit: int = 12) -> list[dict]:
    """Generate a starter fixture: query each prominent symbol, expect itself.

    A sanity baseline — "searching for X surfaces X near the top" — that a user
    then edits into real cases. Prominent = highest-degree non-file nodes with a
    callable-looking label, so the queries read naturally.
    """
    ranked = sorted(G.nodes(data=True), key=lambda nd: G.degree(nd[0]), reverse=True)
    cases: list[dict] = []
    seen: set[str] = set()
    for nid, data in ranked:
        label = str(data.get("label", "")).strip()
        if not label or label in seen:
            continue
        # Prefer symbol-ish labels (functions/classes) over bare file nodes.
        if str(data.get("source_location", "")) == "L1" and "." in label:
            continue
        seen.add(label)
        cases.append({"query": label.rstrip("()"), "expect": [label]})
        if len(cases) >= limit:
            break
    return cases


def format_report(report: EvalReport, *, baseline: dict | None = None) -> str:
    lines: list[str] = []
    lines.append(f"graphify relevance eval — {len(report.cases)} cases @ k={report.k}")
    lines.append("-" * 56)
    for c in report.cases:
        m = c.metrics
        flag = "ok " if m["hit_at_k"] else "MISS"
        lines.append(
            f"  [{flag}] P@k={m['p_at_k']:.2f} R@k={m['recall_at_k']:.2f} "
            f"MRR={m['mrr']:.2f} nDCG={m['ndcg_at_k']:.2f}  {c.query[:44]}"
        )
    lines.append("-" * 56)
    agg = report.aggregate
    base_agg = (baseline or {}).get("aggregate") if baseline else None
    for key, (label, _desc) in METRIC_GLOSSARY.items():
        cur = agg.get(key, 0.0)
        if base_agg is not None:
            delta = round(cur - base_agg.get(key, 0.0), 4)
            arrow = "▲" if delta > 0 else ("▼" if delta < 0 else "=")
            lines.append(f"  {label:<10} {cur:.4f}   {arrow} {delta:+.4f} vs baseline")
        else:
            lines.append(f"  {label:<10} {cur:.4f}")
    return "\n".join(lines)
