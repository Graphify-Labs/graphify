"""Optional graph-first retrieval sidecar for hybrid queries.

The canonical graph remains the source of truth. This module only writes query-time
indexes and debug artifacts; retrieval scores never become edge confidence.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import networkx as nx

TOKEN_RE = re.compile(r"\w+")
SCHEMA_VERSION = "1"
DEFAULT_EMBEDDING_MODEL = "tfidf-local"


def graph_hash(graph_path: Path) -> str:
    return hashlib.sha256(graph_path.read_bytes()).hexdigest()


def _tokens(text: str) -> list[str]:
    terms: list[str] = []
    for raw in TOKEN_RE.findall(text or ""):
        parts = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", raw).split()
        for part in parts + [raw]:
            token = part.lower()
            if len(token) > 1:
                terms.append(token)
    return terms


def _node_text(node_id: str, data: dict) -> str:
    parts = [
        str(data.get("label") or node_id),
        str(data.get("kind") or ""),
        str(data.get("file_type") or ""),
        str(data.get("source_file") or ""),
        str(data.get("community_name") or data.get("community") or ""),
        str(data.get("summary") or ""),
    ]
    return " ".join(p for p in parts if p)


def _edge_iter(G: nx.Graph) -> Iterable[tuple[str, str, dict]]:
    if isinstance(G, (nx.MultiGraph, nx.MultiDiGraph)):
        for u, v, _key, data in G.edges(keys=True, data=True):
            yield str(u), str(v), dict(data)
    else:
        for u, v, data in G.edges(data=True):
            yield str(u), str(v), dict(data)


def _edge_text(G: nx.Graph, source: str, target: str, data: dict) -> str:
    source_label = G.nodes[source].get("label", source) if source in G.nodes else source
    target_label = G.nodes[target].get("label", target) if target in G.nodes else target
    parts = [
        str(source_label),
        str(data.get("relation") or ""),
        str(target_label),
        str(data.get("context") or ""),
        str(data.get("source_file") or ""),
    ]
    return " ".join(p for p in parts if p)


def _idf(documents: list[Counter[str]]) -> dict[str, float]:
    df: Counter[str] = Counter()
    for doc in documents:
        df.update(doc.keys())
    total = len(documents) or 1
    return {term: math.log(1 + total / (1 + count)) for term, count in df.items()}


def _score(query_terms: Counter[str], doc_terms: Counter[str], idf: dict[str, float]) -> float:
    if not query_terms or not doc_terms:
        return 0.0
    dot = 0.0
    q_norm = 0.0
    d_norm = 0.0
    for term, q_tf in query_terms.items():
        q_weight = q_tf * idf.get(term, 1.0)
        q_norm += q_weight * q_weight
        d_tf = doc_terms.get(term, 0)
        if d_tf:
            d_weight = d_tf * idf.get(term, 1.0)
            dot += q_weight * d_weight
    for term, d_tf in doc_terms.items():
        d_weight = d_tf * idf.get(term, 1.0)
        d_norm += d_weight * d_weight
    if not dot or not q_norm or not d_norm:
        return 0.0
    return dot / math.sqrt(q_norm * d_norm)


def _out_dir_for_graph(graph_path: Path) -> Path:
    return graph_path.parent if graph_path.name == "graph.json" else graph_path.parent / "graphify-out"


def build_vector_index(G: nx.Graph, graph_path: Path, out_dir: Path | None = None, *, embedding_model: str = DEFAULT_EMBEDDING_MODEL) -> Path:
    """Build a lightweight local sidecar index for nodes and relations.

    The MVP uses TF-IDF term vectors so it has no new runtime dependency. The
    manifest is shaped so a future dense embedding backend can replace the index
    without changing the query contract.
    """
    out = out_dir or _out_dir_for_graph(graph_path)
    index_dir = out / "vector-index"
    index_dir.mkdir(parents=True, exist_ok=True)

    node_rows: list[dict] = []
    node_docs: list[Counter[str]] = []
    for node_id, data in G.nodes(data=True):
        text = _node_text(str(node_id), dict(data))
        terms = Counter(_tokens(text))
        node_docs.append(terms)
        node_rows.append({"id": str(node_id), "text": text, "terms": dict(terms)})

    relation_rows: list[dict] = []
    relation_docs: list[Counter[str]] = []
    for source, target, data in _edge_iter(G):
        text = _edge_text(G, source, target, data)
        terms = Counter(_tokens(text))
        relation_docs.append(terms)
        relation_rows.append({
            "source": source,
            "target": target,
            "relation": str(data.get("relation") or ""),
            "text": text,
            "terms": dict(terms),
        })

    node_idf = _idf(node_docs)
    relation_idf = _idf(relation_docs)
    (index_dir / "nodes.jsonl").write_text("\n".join(json.dumps(r, sort_keys=True) for r in node_rows) + ("\n" if node_rows else ""), encoding="utf-8")
    (index_dir / "relations.jsonl").write_text("\n".join(json.dumps(r, sort_keys=True) for r in relation_rows) + ("\n" if relation_rows else ""), encoding="utf-8")
    (index_dir / "idf.json").write_text(json.dumps({"nodes": node_idf, "relations": relation_idf}, indent=2, sort_keys=True), encoding="utf-8")

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "graph_hash": graph_hash(graph_path),
        "embedding_model": embedding_model,
        "embedding_dim": None,
        "backend": "tfidf-local",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "node_count": G.number_of_nodes(),
        "relation_count": G.number_of_edges(),
    }
    (index_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return index_dir


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def load_index(graph_path: Path, out_dir: Path | None = None) -> dict | None:
    out = out_dir or _out_dir_for_graph(graph_path)
    index_dir = out / "vector-index"
    manifest_path = index_dir / "manifest.json"
    idf_path = index_dir / "idf.json"
    nodes_path = index_dir / "nodes.jsonl"
    relations_path = index_dir / "relations.jsonl"
    if not all(path.exists() for path in (manifest_path, idf_path, nodes_path, relations_path)):
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("schema_version") != SCHEMA_VERSION:
            return None
        if manifest.get("graph_hash") != graph_hash(graph_path):
            return None
        idf = json.loads(idf_path.read_text(encoding="utf-8"))
        nodes = _load_jsonl(nodes_path)
        relations = _load_jsonl(relations_path)
    except (OSError, json.JSONDecodeError):
        return None
    return {
        "dir": index_dir,
        "manifest": manifest,
        "nodes": nodes,
        "relations": relations,
        "idf": idf,
    }


def search_index(index: dict, question: str, *, k: int = 10) -> dict[str, list[dict]]:
    q = Counter(_tokens(question))
    node_hits = []
    for row in index.get("nodes", []):
        score = _score(q, Counter(row.get("terms", {})), index.get("idf", {}).get("nodes", {}))
        if score > 0:
            node_hits.append({"node_id": row["id"], "retrieval_score": score})
    node_hits.sort(key=lambda r: r["retrieval_score"], reverse=True)

    relation_hits = []
    for row in index.get("relations", []):
        score = _score(q, Counter(row.get("terms", {})), index.get("idf", {}).get("relations", {}))
        if score > 0:
            relation_hits.append({
                "source": row["source"],
                "target": row["target"],
                "relation": row.get("relation", ""),
                "retrieval_score": score,
            })
    relation_hits.sort(key=lambda r: r["retrieval_score"], reverse=True)
    return {"nodes": node_hits[:k], "relations": relation_hits[:k]}


def merge_seed_candidates(lexical: list[tuple[float, str]], semantic_hits: dict[str, list[dict]], *, k: int = 5) -> list[str]:
    scores: dict[str, float] = {}
    for rank, (score, node_id) in enumerate(lexical[:k], start=1):
        lexical_score = min(float(score), 1000.0) / 1000.0
        # Keep lexical evidence in the mix, but do not let every weak text match
        # outrank sidecar-only semantic/relation hits.
        scores[node_id] = max(scores.get(node_id, 0.0), 0.6 * lexical_score + 0.05 / rank)
    for rank, hit in enumerate(semantic_hits.get("nodes", [])[:k], start=1):
        node_id = hit["node_id"]
        score = float(hit["retrieval_score"])
        scores[node_id] = max(scores.get(node_id, 0.0), score + 0.1 / rank)
    for rank, hit in enumerate(semantic_hits.get("relations", [])[:k], start=1):
        rel_score = 0.95 * float(hit["retrieval_score"]) + 0.05 / rank
        for node_id in (hit.get("source"), hit.get("target")):
            if node_id:
                scores[node_id] = max(scores.get(node_id, 0.0), rel_score)
    return [node_id for node_id, _ in sorted(scores.items(), key=lambda item: item[1], reverse=True)[:k]]


def write_retrieval_debug(graph_path: Path, question: str, mode: str, lexical: list[tuple[float, str]], semantic_hits: dict[str, list[dict]], seeds: list[str]) -> Path:
    out_dir = _out_dir_for_graph(graph_path)
    debug_dir = out_dir / "retrieval-debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "query": question,
        "mode": mode,
        "graph_hash": graph_hash(graph_path),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "lexical_candidates": [{"node_id": node_id, "score": score} for score, node_id in lexical[:20]],
        "semantic_candidates": semantic_hits,
        "selected_seeds": seeds,
    }
    path = debug_dir / "last-query.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
