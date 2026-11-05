"""Cross-file semantic similarity reconciliation for graphify (#3948).

In parallel chunked extraction, subagents only see their chunk's files, so
relationships between concepts in different chunks cannot be emitted by
construction. This module provides the post-collection reconciliation pass that
identifies cross-file / cross-chunk semantic similarity across concept and
rationale nodes, scoring by TF-IDF cosine and rare-term vocabulary overlap.
"""
from __future__ import annotations

import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

# Standard English stop words to filter out before computing vocabulary overlap
_STOP_WORDS = {
    "a", "about", "above", "after", "again", "against", "all", "also", "am",
    "an", "and", "any", "are", "aren't", "as", "at", "be", "because", "been",
    "before", "being", "below", "between", "both", "but", "by", "can", "cannot",
    "could", "did", "do", "does", "doing", "don't", "down", "during", "each",
    "few", "for", "from", "further", "had", "has", "have", "having", "he",
    "her", "here", "hers", "herself", "him", "himself", "his", "how", "i",
    "if", "in", "into", "is", "isn't", "it", "its", "itself", "just", "me",
    "more", "most", "must", "my", "myself", "no", "nor", "not", "now", "of",
    "off", "on", "once", "only", "or", "other", "ought", "our", "ours",
    "ourselves", "out", "over", "own", "same", "she", "should", "so", "some",
    "such", "than", "that", "the", "their", "theirs", "them", "themselves",
    "then", "there", "these", "they", "this", "those", "through", "to", "too",
    "under", "until", "up", "very", "was", "wasn't", "we", "were", "weren't",
    "what", "when", "where", "which", "while", "who", "whom", "why", "with",
    "won't", "would", "you", "your", "yours", "yourself", "yourselves",
}


def _norm_source(sf: str | None) -> str:
    """Normalize source file paths for comparison across relative/absolute variants."""
    if not sf:
        return ""
    p = str(sf).replace("\\", "/").rstrip("/").lower()
    # Drop leading drive letters or ./
    if len(p) >= 2 and p[1] == ":":
        p = p[2:].lstrip("/")
    if p.startswith("./"):
        p = p[2:]
    return p


def _tokenize(text: str) -> list[str]:
    """Extract lowercased terms of length >= 3, excluding common stop words."""
    words = re.findall(r"\b[a-zA-Z0-9_-]{3,}\b", text.lower())
    return [w for w in words if w not in _STOP_WORDS and not w.isdigit()]


def _node_text(node: dict) -> str:
    """Aggregate meaningful text representation for a node."""
    parts: list[str] = []
    if node.get("rationale"):
        parts.append(str(node["rationale"]))
    if node.get("label"):
        parts.append(str(node["label"]))
    if node.get("description"):
        parts.append(str(node["description"]))
    if node.get("summary"):
        parts.append(str(node["summary"]))
    return " ".join(parts).strip()


def reconcile_semantic_similarity(
    nodes: list[dict],
    edges: list[dict],
    *,
    cosine_threshold: float = 0.65,
    moderate_cosine_threshold: float = 0.35,
    min_rare_terms: int = 5,
    file_types: tuple[str, ...] = ("rationale", "concept"),
    report: bool = True,
) -> list[dict]:
    """Reconcile cross-file semantic similarity across chunks (#3948).

    Compares rationale/concept node text across different source files and
    emits `semantically_similar_to` edges marked INFERRED with a confidence
    score derived from the measured similarity.

    Dual acceptance paths:
    1. Strong TF-IDF cosine similarity (>= cosine_threshold, default 0.65).
    2. Moderate cosine (>= moderate_cosine_threshold, default 0.35) AND high
       rare-term overlap (>= min_rare_terms, default 5 shared low-frequency terms),
       capturing concentrated paraphrase surrounded by file-specific text.

    Returns the updated list of edges (original edges + newly inferred similarity edges).
    """
    if not nodes:
        return list(edges)

    # 1. Filter candidate nodes: must be a dict, have an id, and be a rationale/concept
    # or carry a non-empty rationale attribute.
    candidates: list[dict] = []
    token_lists: list[list[str]] = []
    term_counts: list[Counter[str]] = []

    for n in nodes:
        if not isinstance(n, dict) or not n.get("id"):
            continue
        ft = n.get("file_type")
        if ft in file_types or n.get("rationale"):
            tokens = _tokenize(_node_text(n))
            if len(tokens) >= 2:
                candidates.append(n)
                token_lists.append(tokens)
                term_counts.append(Counter(tokens))

    num_docs = len(candidates)
    if num_docs < 2:
        return list(edges)

    # 2. Compute Document Frequency (DF) and Inverse Document Frequency (IDF)
    df: Counter[str] = Counter()
    for tc in term_counts:
        for term in tc:
            df[term] += 1

    idf: dict[str, float] = {}
    for term, freq in df.items():
        # Standard smoothed IDF
        idf[term] = math.log((num_docs + 1.0) / (freq + 1.0)) + 1.0

    # Rare term threshold: appears in few documents (e.g. <= 8% of corpus or <= 3)
    rare_threshold = max(2, int(0.08 * num_docs))

    # 3. Compute TF-IDF vectors and norms for each candidate
    vectors: list[dict[str, float]] = []
    norms: list[float] = []
    inverted_index: defaultdict[str, list[int]] = defaultdict(list)

    for idx, tc in enumerate(term_counts):
        doc_len = len(token_lists[idx])
        vec: dict[str, float] = {}
        for term, count in tc.items():
            # TF-IDF: normalized TF * IDF
            vec[term] = (count / doc_len) * idf[term]
            inverted_index[term].append(idx)
        norm = math.sqrt(sum(v * v for v in vec.values()))
        vectors.append(vec)
        norms.append(norm)

    # 4. Index existing edges to avoid duplicate / conflicting connections
    existing_undirected: set[frozenset[str]] = set()
    for e in edges:
        if isinstance(e, dict) and e.get("source") and e.get("target"):
            existing_undirected.add(frozenset({str(e["source"]), str(e["target"])}))

    # 5. Evaluate candidate pairs via inverted index (sparse matching)
    new_edges: list[dict] = []
    edge_reports: list[tuple[dict, str]] = []

    for i in range(num_docs):
        if norms[i] <= 0:
            continue
        u = candidates[i]
        u_id = str(u["id"])
        u_sf = _norm_source(u.get("source_file"))

        # Find potential matches sharing at least one term
        potential_matches: set[int] = set()
        for term in vectors[i]:
            for j in inverted_index[term]:
                if j > i:
                    potential_matches.add(j)

        for j in potential_matches:
            if norms[j] <= 0:
                continue
            v = candidates[j]
            v_id = str(v["id"])
            if u_id == v_id:
                continue

            v_sf = _norm_source(v.get("source_file"))
            # Cross-file check: only compare across different source files
            if u_sf and v_sf and u_sf == v_sf:
                continue

            # Existing connection check
            pair_key = frozenset({u_id, v_id})
            if pair_key in existing_undirected:
                continue

            # Compute TF-IDF cosine similarity
            shared_terms = set(vectors[i].keys()) & set(vectors[j].keys())
            dot = sum(vectors[i][t] * vectors[j][t] for t in shared_terms)
            cosine = dot / (norms[i] * norms[j])

            # Count shared rare terms
            shared_rare = [t for t in shared_terms if df[t] <= rare_threshold]
            k = len(shared_rare)

            accepted = False
            reason = ""
            if cosine >= cosine_threshold:
                accepted = True
                reason = f"cosine={cosine:.3f}"
            elif (cosine >= moderate_cosine_threshold and k >= min_rare_terms) or (k >= 6 and cosine >= 0.10):
                accepted = True
                reason = f"rare_terms={k}, cosine={cosine:.3f}"

            if accepted:
                # Discrete confidence scoring conforming to extraction-spec rubric
                if cosine >= 0.85:
                    conf = 0.95
                elif cosine >= 0.75 or (k >= 8 and cosine >= 0.50):
                    conf = 0.85
                elif cosine >= 0.65 or k >= 6:
                    conf = 0.75
                else:
                    conf = 0.65

                edge = {
                    "source": u_id,
                    "target": v_id,
                    "relation": "semantically_similar_to",
                    "confidence": "INFERRED",
                    "confidence_score": conf,
                    "source_file": u.get("source_file"),
                    "weight": conf,
                }
                new_edges.append(edge)
                existing_undirected.add(pair_key)
                edge_reports.append((edge, reason))

    if report and edge_reports:
        print(
            f"[graphify] Reconciled {len(edge_reports)} cross-file semantically_similar_to edge(s):",
            file=sys.stderr,
        )
        for e, reason in edge_reports:
            print(
                f"  • {e['source']} ~ {e['target']} "
                f"(confidence={e['confidence_score']}, {reason})",
                file=sys.stderr,
            )

    return list(edges) + new_edges
