# user-owned curation overlay: deny false edges, pin verified ones
"""Durable human corrections to the graph.

Every edge in graph.json is derived from an extractor, so any correction a human
makes to graph.json is transient by construction:

- **Deleted false edges come back.** The semantic cache is keyed by file content,
  not by graph state. An unchanged doc keeps its cached edges forever, so the next
  ``graphify extract`` re-injects a deleted edge and writes it back with
  ``force=True`` — past the shrink guard.
- **Added verified edges are destroyed.** ``build_merge`` replaces per source_file:
  every ``source_file`` present in the new chunks is dropped from the base graph
  before merging. A human-authored edge whose ``source_file`` names a re-extracted
  file is dropped, and no extractor re-emits it. The node count *grows* while this
  happens, so nothing warns.

``save-result --outcome dead_end`` records that an edge is false, but it is advisory
— it informs a future agent through LESSONS.md and never gates extraction. So the
graph and the lessons drift apart: the graph keeps asserting an edge the operator
has already disproved.

This module adds the missing layer: ``graphify-out/curation.json``, a small
user-owned file that is applied at the end of :func:`graphify.build.build_from_json`
— the single funnel through which ``build``, ``build_merge``, ``watch`` and the
skill's agent path all construct the graph. Applying it there (rather than at write
time) means clustering, god-nodes, surprising-connections and GRAPH_REPORT.md all
see the curated graph, so a disproved edge stops being re-advertised.

The overlay is declarative and idempotent: it is re-applied on every build, so it
survives rebuilds that would otherwise erase it. Set ``GRAPHIFY_NO_CURATION=1`` to
disable (mirrors ``GRAPHIFY_NO_BACKUP``).

Schema (``graphify-out/curation.json``)::

    {
      "version": 1,
      "deny_edges": [
        {"source": "a_mod_foo", "target": "b_mod_bar", "relation": "calls",
         "reason": "lexical collision; no call site", "evidence": "b/bar.py:12"}
      ],
      "add_edges": [
        {"source": "a_mod_foo", "target": "b_mod_bar",
         "relation": "shares_data_with", "confidence": "INFERRED",
         "confidence_score": 0.95, "source_file": "a/foo.py",
         "source_location": "L45", "reason": "both read Report.subLoaded"}
      ]
    }

``relation`` is optional on a deny entry; omitting it denies every edge between the
pair. Endpoint order is not significant — an undirected graph canonicalizes it — so
a deny matches the pair in either orientation.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import networkx as nx

CURATION_FILENAME = "curation.json"
CURATION_SCHEMA_VERSION = 1

# Mirrors export._CONFIDENCE_SCORE_DEFAULTS so a pinned edge that omits an explicit
# score still lands with the same default the extractor path would have given it.
_DEFAULT_SCORES = {"EXTRACTED": 1.0, "INFERRED": 0.5, "AMBIGUOUS": 0.2}


def curation_path(out_dir: str | Path | None = None) -> Path:
    """Path to the curation file. Defaults to ``graphify-out/curation.json`` in CWD."""
    return Path(out_dir or "graphify-out") / CURATION_FILENAME


def empty_curation() -> dict[str, Any]:
    return {"version": CURATION_SCHEMA_VERSION, "deny_edges": [], "add_edges": []}


def _pair(entry: dict) -> tuple[str, str] | None:
    src, tgt = entry.get("source"), entry.get("target")
    if not isinstance(src, str) or not isinstance(tgt, str) or not src or not tgt:
        return None
    return (src, tgt)


def _deny_key(src: str, tgt: str, relation: str | None) -> tuple[str, str, str | None]:
    """Order-insensitive key. Undirected storage canonicalizes endpoint order, so a
    deny written as (a, b) must also match an edge stored as (b, a)."""
    lo, hi = sorted((src, tgt))
    return (lo, hi, relation)


def load_curation(out_dir: str | Path | None = None) -> dict[str, Any] | None:
    """Load the curation overlay. Returns None when absent, disabled, or unreadable.

    Never raises: a malformed curation file must not break a build. It warns and is
    ignored, because silently applying half a corrupt overlay is worse than applying
    none of it.
    """
    if os.environ.get("GRAPHIFY_NO_CURATION"):
        return None
    path = curation_path(out_dir)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"[graphify] warning: ignoring unreadable {path}: {exc}")
        return None
    if not isinstance(data, dict):
        print(f"[graphify] warning: ignoring {path}: expected a JSON object")
        return None
    version = data.get("version")
    if version is not None and version != CURATION_SCHEMA_VERSION:
        print(
            f"[graphify] warning: ignoring {path}: schema version {version!r} "
            f"(this graphify understands {CURATION_SCHEMA_VERSION})"
        )
        return None
    for key in ("deny_edges", "add_edges"):
        if not isinstance(data.get(key, []), list):
            print(f"[graphify] warning: ignoring {path}: {key} must be a list")
            return None
    return data


def save_curation(curation: dict[str, Any], out_dir: str | Path | None = None) -> Path:
    """Write the overlay deterministically (sorted keys) so re-runs are byte-identical."""
    path = curation_path(out_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(curation, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def apply_curation(G: nx.Graph, curation: dict[str, Any] | None) -> dict[str, int]:
    """Apply the overlay to a built graph, in place. Returns per-action counts.

    Denies run before adds, so an entry can legitimately deny an extractor's
    mistyped edge and pin the corrected one over the same pair.

    A pinned edge whose endpoints are not both present is skipped, not invented:
    the overlay corrects the graph, it does not fabricate nodes. That also keeps the
    edge from dangling and being silently swallowed by the dangling-edge drop.
    """
    stats = {"denied": 0, "added": 0, "skipped_missing_endpoint": 0}
    if not curation:
        return stats

    denies: set[tuple[str, str, str | None]] = set()
    for entry in curation.get("deny_edges", []):
        if not isinstance(entry, dict):
            continue
        pair = _pair(entry)
        if pair is None:
            continue
        denies.add(_deny_key(pair[0], pair[1], entry.get("relation")))

    if denies:
        doomed = []
        for src, tgt, attrs in G.edges(data=True):
            # Match on the edge's true direction (_src/_tgt) when present — undirected
            # storage may have flipped the stored endpoints (#563).
            e_src = attrs.get("_src", src)
            e_tgt = attrs.get("_tgt", tgt)
            rel = attrs.get("relation")
            if (
                _deny_key(e_src, e_tgt, rel) in denies
                or _deny_key(e_src, e_tgt, None) in denies
            ):
                doomed.append((src, tgt))
        for src, tgt in doomed:
            if G.has_edge(src, tgt):
                G.remove_edge(src, tgt)
                stats["denied"] += 1

    for entry in curation.get("add_edges", []):
        if not isinstance(entry, dict):
            continue
        pair = _pair(entry)
        if pair is None:
            continue
        src, tgt = pair
        if src not in G or tgt not in G:
            stats["skipped_missing_endpoint"] += 1
            continue
        if G.has_edge(src, tgt):
            existing = G.get_edge_data(src, tgt) or {}
            if existing.get("relation") == entry.get("relation"):
                continue  # already present — idempotent re-apply
        confidence = entry.get("confidence", "INFERRED")
        attrs = {
            "relation": entry.get("relation", "references"),
            "confidence": confidence,
            "confidence_score": entry.get(
                "confidence_score", _DEFAULT_SCORES.get(confidence, 1.0)
            ),
            "source_file": entry.get("source_file", ""),
            "source_location": entry.get("source_location"),
            "weight": entry.get("weight", 1.0),
            "curated": True,
            "_src": src,
            "_tgt": tgt,
        }
        G.add_edge(src, tgt, **attrs)
        stats["added"] += 1

    return stats


def apply_curation_to_payload(
    data: dict[str, Any], curation: dict[str, Any] | None
) -> dict[str, int]:
    """Apply the overlay to a raw graph payload, in place.

    For the ``--no-cluster`` write paths, which dump an extraction dict directly and
    never construct a NetworkX graph. Handles both the ``links`` key (node_link_data)
    and ``edges`` (raw extraction).
    """
    stats = {"denied": 0, "added": 0, "skipped_missing_endpoint": 0}
    if not curation:
        return stats

    edge_key = "links" if "links" in data else "edges"
    edges = data.get(edge_key)
    if not isinstance(edges, list):
        return stats

    denies: set[tuple[str, str, str | None]] = set()
    for entry in curation.get("deny_edges", []):
        if isinstance(entry, dict) and (pair := _pair(entry)):
            denies.add(_deny_key(pair[0], pair[1], entry.get("relation")))

    if denies:
        kept = []
        for e in edges:
            src, tgt = e.get("source"), e.get("target")
            if isinstance(src, str) and isinstance(tgt, str) and (
                _deny_key(src, tgt, e.get("relation")) in denies
                or _deny_key(src, tgt, None) in denies
            ):
                stats["denied"] += 1
                continue
            kept.append(e)
        edges = kept

    node_ids = {
        n.get("id") for n in data.get("nodes", []) if isinstance(n, dict)
    }
    present = {
        _deny_key(e["source"], e["target"], e.get("relation"))
        for e in edges
        if isinstance(e.get("source"), str) and isinstance(e.get("target"), str)
    }
    for entry in curation.get("add_edges", []):
        if not isinstance(entry, dict):
            continue
        pair = _pair(entry)
        if pair is None:
            continue
        src, tgt = pair
        if src not in node_ids or tgt not in node_ids:
            stats["skipped_missing_endpoint"] += 1
            continue
        relation = entry.get("relation", "references")
        if _deny_key(src, tgt, relation) in present:
            continue
        confidence = entry.get("confidence", "INFERRED")
        edges.append({
            "source": src,
            "target": tgt,
            "relation": relation,
            "confidence": confidence,
            "confidence_score": entry.get(
                "confidence_score", _DEFAULT_SCORES.get(confidence, 1.0)
            ),
            "source_file": entry.get("source_file", ""),
            "source_location": entry.get("source_location"),
            "weight": entry.get("weight", 1.0),
            "curated": True,
        })
        stats["added"] += 1

    data[edge_key] = edges
    return stats


def format_stats(stats: dict[str, int]) -> str | None:
    """One-line summary for the CLI, or None when the overlay changed nothing."""
    bits = []
    if stats.get("denied"):
        bits.append(f"{stats['denied']} edge(s) denied")
    if stats.get("added"):
        bits.append(f"{stats['added']} edge(s) pinned")
    if stats.get("skipped_missing_endpoint"):
        bits.append(
            f"{stats['skipped_missing_endpoint']} pin(s) skipped (endpoint not in graph)"
        )
    if not bits:
        return None
    return "[graphify] curation: " + ", ".join(bits)
