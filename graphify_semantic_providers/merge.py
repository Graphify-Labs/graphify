"""Merge provider fragments into a Graphify graph without replacing AST truth."""

from __future__ import annotations

import copy
from collections import defaultdict
from typing import Any, Iterable

from .contracts import ProviderRun


def merge_runs(base: dict[str, Any], runs: Iterable[ProviderRun]) -> dict[str, Any]:
    """Return a new graph document with semantic evidence additively merged.

    A provider symbol is reconciled to a native AST symbol only when
    ``(source_file, label)`` identifies exactly one native node.  Ambiguity
    leaves the semantic node separate rather than guessing.
    """

    runs = tuple(runs)
    result = copy.deepcopy(base)
    edge_key = "links" if "links" in result and "edges" not in result else "edges"
    result.setdefault("nodes", [])
    result.setdefault(edge_key, [])
    nodes = result["nodes"]
    edges = result[edge_key]
    by_id = {
        str(node.get("id")): node for node in nodes if isinstance(node, dict) and node.get("id")
    }
    native_index: dict[tuple[str, str], list[str]] = defaultdict(list)
    for node_id, node in by_id.items():
        key = _reconciliation_key(node)
        if key:
            native_index[key].append(node_id)

    remap: dict[str, str] = {}
    added_ids: set[str] = set()
    for run in runs:
        for node in run.nodes:
            incoming_id = str(node.get("id", ""))
            if not incoming_id:
                continue
            incoming_key = _reconciliation_key(node)
            candidates = native_index.get(incoming_key, []) if incoming_key is not None else []
            if len(candidates) == 1:
                canonical = candidates[0]
                remap[incoming_id] = canonical
                _record_evidence(by_id[canonical], run, node)
            elif incoming_id not in by_id and incoming_id not in added_ids:
                copied = copy.deepcopy(node)
                _record_evidence(copied, run, node)
                nodes.append(copied)
                by_id[incoming_id] = copied
                added_ids.add(incoming_id)

    seen_edges = {
        (
            str(edge.get("source", "")),
            str(edge.get("target", "")),
            str(edge.get("relation", "")),
            str(edge.get("source_location", "")),
        )
        for edge in edges
        if isinstance(edge, dict)
    }
    for run in runs:
        for edge in run.edges:
            copied = copy.deepcopy(edge)
            copied["source"] = remap.get(str(copied.get("source", "")), copied.get("source"))
            copied["target"] = remap.get(str(copied.get("target", "")), copied.get("target"))
            if copied.get("source") not in by_id or copied.get("target") not in by_id:
                continue
            key = (
                str(copied.get("source", "")),
                str(copied.get("target", "")),
                str(copied.get("relation", "")),
                str(copied.get("source_location", "")),
            )
            if key not in seen_edges:
                seen_edges.add(key)
                edges.append(copied)

    graph_meta = result.setdefault("graph", {})
    if isinstance(graph_meta, dict):
        materialized = [run for run in runs if run.nodes or run.edges]
        semantic = sorted({run.provider for run in materialized})
        graph_meta["semantic_providers"] = semantic
        graph_meta["evidence_provider_contract"] = "graphify-semantic-providers/v1"
        if semantic:
            graph_meta["semantic_provider_contract"] = "graphify-semantic-providers/v1"
    return result


def _reconciliation_key(node: dict[str, Any]) -> tuple[str, str] | None:
    source_file = str(node.get("source_file", "")).replace("\\", "/").lstrip("./")
    label = str(node.get("label", "")).strip().casefold()
    if not source_file or not label:
        return None
    return source_file, label


def _record_evidence(target: dict[str, Any], run: ProviderRun, incoming: dict[str, Any]) -> None:
    evidence = target.setdefault("semantic_evidence", [])
    if not isinstance(evidence, list):
        evidence = []
        target["semantic_evidence"] = evidence
    raw_metadata = incoming.get("metadata")
    metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
    record = {
        "provider": run.provider,
        "provider_kind": run.provider_kind.value,
        "run_id": run.run_id,
        "timestamp": run.timestamp,
        "source_location": str(incoming.get("source_location", "")),
        "kind": str(metadata.get("semantic_kind", "")),
    }
    if record not in evidence and len(evidence) < 16:
        evidence.append(record)
