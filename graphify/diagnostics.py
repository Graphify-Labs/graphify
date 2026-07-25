"""Read-only diagnostics for MultiDiGraph readiness."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Any

import networkx as nx
from graphify.ids import normalize_id


_SUPPRESSION_DECL_RE = re.compile(r"^\s*(?P<name>seen_[A-Za-z0-9_]+)\s*[:=]")
_TYPE_TUPLE_RE = re.compile(r"set\[tuple\[(?P<inside>[^\]]+)\]\]")


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return json.dumps(value, sort_keys=True, default=str, ensure_ascii=False)


def _edge_list(extraction: dict[str, Any]) -> list[Any]:
    edges = extraction.get("edges")
    if edges is None:
        edges = extraction.get("links")
    return edges if isinstance(edges, list) else []


def _node_ids(extraction: dict[str, Any]) -> set[str]:
    nodes = extraction.get("nodes", [])
    if not isinstance(nodes, list):
        return set()
    return {
        str(node["id"])
        for node in nodes
        if isinstance(node, dict) and "id" in node and node.get("id") is not None
    }


def _canonical_edge(edge: Any) -> dict[str, Any]:
    if not isinstance(edge, dict):
        return {
            "source": "",
            "target": "",
            "relation": "",
            "confidence": "",
            "source_file": "",
            "source_location": "",
            "context": "",
            "external": False,
            "unresolved_internal": False,
            "_invalid": "non_object_edge",
        }
    source = edge.get("source", edge.get("from"))
    target = edge.get("target", edge.get("to"))
    return {
        "source": _safe_text(source),
        "target": _safe_text(target),
        "relation": _safe_text(edge.get("relation")),
        "confidence": _safe_text(edge.get("confidence")),
        "source_file": _safe_text(edge.get("source_file")),
        "source_location": _safe_text(edge.get("source_location")),
        "context": _safe_text(edge.get("context")),
        "external": edge.get("external") is True,
        "unresolved_internal": edge.get("unresolved_internal") is True,
        "_invalid": "",
    }


def _malformed_endpoint(source: str, target: str, root: str | Path | None) -> bool:
    """Detect machine-absolute endpoint ids that escaped canonical remapping."""
    endpoints = (source.replace("\\", "/"), target.replace("\\", "/"))
    if any(
        value.startswith("/")
        or re.match(r"^[A-Za-z]:/", value)
        for value in endpoints
    ):
        return True
    if root is None:
        return False
    try:
        prefix = normalize_id(str(Path(root).resolve()))
    except OSError:
        prefix = normalize_id(str(root))
    return bool(prefix) and any(
        value == prefix or value.startswith(prefix + "_")
        for value in endpoints
    )


def _exact_signature(edge: Any) -> str:
    if not isinstance(edge, dict):
        return "<non-object>"
    normalized = dict(edge)
    if "source" not in normalized and "from" in normalized:
        normalized["source"] = normalized["from"]
    if "target" not in normalized and "to" in normalized:
        normalized["target"] = normalized["to"]
    normalized.pop("from", None)
    normalized.pop("to", None)
    normalized.pop("key", None)
    normalized.pop("occurrence_count", None)
    normalized.pop("_src", None)
    normalized.pop("_tgt", None)
    return json.dumps(
        normalized,
        sort_keys=True,
        default=str,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _count_extra(counter: Counter[Any]) -> int:
    return sum(count - 1 for count in counter.values() if count > 1)


def _variant_group_count(
    grouped_edges: dict[tuple[str, str], list[dict[str, str]]],
    field: str,
    *,
    relation_sensitive: bool = False,
) -> int:
    groups = 0
    for edges in grouped_edges.values():
        if relation_sensitive:
            by_relation: dict[str, set[str]] = defaultdict(set)
            for edge in edges:
                by_relation[edge["relation"]].add(edge[field])
            groups += sum(1 for values in by_relation.values() if len(values) > 1)
        elif len({edge[field] for edge in edges}) > 1:
            groups += 1
    return groups


def _tuple_arity_from_annotation(line: str) -> int:
    match = _TYPE_TUPLE_RE.search(line)
    if not match:
        return 0
    inside = match.group("inside").strip()
    if not inside:
        return 0
    return inside.count(",") + 1


def scan_producer_suppression_sites(path: str | Path) -> dict[str, Any]:
    """Find likely `seen_*` producer-suppression sets in an extractor file."""
    source_path = Path(path)
    if not source_path.exists():
        return {
            "path": str(source_path),
            "total_sites": 0,
            "sites": [],
            "error": "file not found",
        }

    sites: list[dict[str, Any]] = []
    lines = source_path.read_text(encoding="utf-8").splitlines()
    for lineno, line in enumerate(lines, start=1):
        match = _SUPPRESSION_DECL_RE.match(line)
        if not match:
            continue
        sites.append(
            {
                "line": lineno,
                "name": match.group("name"),
                "tuple_arity": _tuple_arity_from_annotation(line),
                "sample": line.strip()[:120],
            }
        )

    return {
        "path": str(source_path),
        "total_sites": len(sites),
        "sites": sites,
        "error": "",
    }


def diagnose_extraction(
    extraction: dict[str, Any],
    *,
    directed: bool = True,
    multigraph: bool = False,
    root: str | Path | None = None,
    max_examples: int = 5,
    extract_path: str | Path | None = None,
) -> dict[str, Any]:
    """Summarize same-endpoint edge-collapse risk for one JSON graph/extraction dict."""
    from graphify.build import build_from_json

    node_ids = _node_ids(extraction)
    raw_edges = _edge_list(extraction)
    canonical_edges = [_canonical_edge(edge) for edge in raw_edges]

    # Code-typed semantic nodes the extractor could not verify against the source
    # it read (#1949): likely-inferred (or hallucinated) symbols surfaced from a
    # document. Count them so the flag on graph.json nodes is actually surfaced.
    unverified_node_count = sum(
        1 for n in extraction.get("nodes", [])
        if isinstance(n, dict) and n.get("verification") == "unverified"
    )

    exact_counts: Counter[str] = Counter()
    directed_pairs: Counter[tuple[str, str]] = Counter()
    undirected_pairs: Counter[tuple[str, str]] = Counter()
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)

    non_object_edges = 0
    missing_endpoint_edges = 0
    dangling_endpoint_edges = 0
    external_endpoint_edges = 0
    unresolved_internal_endpoint_edges = 0
    malformed_endpoint_edges = 0
    unclassified_endpoint_edges = 0
    self_loop_edges = 0
    valid_candidate_edges = 0
    encoded_duplicate_occurrences = 0
    valid_signatures_by_pair: dict[tuple[str, str], set[str]] = defaultdict(set)
    endpoint_examples: dict[str, list[dict[str, str]]] = {
        "external": [],
        "unresolved_internal": [],
        "malformed": [],
        "unclassified": [],
    }

    def _remember(category: str, edge: dict[str, Any]) -> None:
        if max_examples <= 0 or len(endpoint_examples[category]) >= max_examples:
            return
        endpoint_examples[category].append({
            "source": edge["source"],
            "target": edge["target"],
            "relation": edge["relation"],
            "source_file": edge["source_file"],
            "source_location": edge["source_location"],
        })

    for raw_edge, edge in zip(raw_edges, canonical_edges):
        if edge["_invalid"]:
            non_object_edges += 1
            continue
        source = edge["source"]
        target = edge["target"]
        if not source or not target:
            missing_endpoint_edges += 1
            continue
        if source not in node_ids or target not in node_ids:
            dangling_endpoint_edges += 1
            if _malformed_endpoint(source, target, root):
                malformed_endpoint_edges += 1
                _remember("malformed", edge)
            elif edge["external"]:
                external_endpoint_edges += 1
                _remember("external", edge)
            elif edge["unresolved_internal"]:
                unresolved_internal_endpoint_edges += 1
                _remember("unresolved_internal", edge)
            else:
                unclassified_endpoint_edges += 1
                _remember("unclassified", edge)
            continue
        if source == target:
            self_loop_edges += 1
        valid_candidate_edges += 1
        if isinstance(raw_edge, dict):
            try:
                encoded_duplicate_occurrences += max(
                    0, int(raw_edge.get("occurrence_count", 1)) - 1
                )
            except (TypeError, ValueError):
                pass
        signature = _exact_signature(raw_edge)
        exact_counts[signature] += 1
        directed_pair = (source, target)
        undirected_pair = (source, target) if source <= target else (target, source)
        directed_pairs[directed_pair] += 1
        undirected_pairs[undirected_pair] += 1
        grouped[directed_pair].append(edge)
        valid_signatures_by_pair[directed_pair].add(signature)

    canonical_distinct_candidate_edges = len(exact_counts)
    exact_duplicate_occurrences = (
        _count_extra(exact_counts) + encoded_duplicate_occurrences
    )
    distinct_parallel_edge_instances = sum(
        max(0, len(signatures) - 1)
        for signatures in valid_signatures_by_pair.values()
    )
    orientations_by_pair: dict[tuple[str, str], set[tuple[str, str]]] = defaultdict(set)
    for source, target in valid_signatures_by_pair:
        pair = (source, target) if source <= target else (target, source)
        orientations_by_pair[pair].add((source, target))
    opposite_direction_endpoint_pairs = sum(
        1 for orientations in orientations_by_pair.values() if len(orientations) > 1
    )

    examples: list[dict[str, Any]] = []
    if max_examples > 0:
        for (source, target), count in directed_pairs.most_common():
            if count < 2:
                continue
            edges = grouped[(source, target)]
            examples.append(
                {
                    "source": source,
                    "target": target,
                    "edge_count": count,
                    "relations": sorted({edge["relation"] for edge in edges}),
                    "source_files": sorted({edge["source_file"] for edge in edges}),
                    "source_locations": sorted({edge["source_location"] for edge in edges}),
                    "contexts": sorted({edge["context"] for edge in edges}),
                }
            )
            if len(examples) >= max_examples:
                break

    build_error = ""
    graph_type = ""
    post_build_edge_count: int | None = None
    post_build_node_count: int | None = None
    try:
        graph_input = deepcopy(extraction)
        graph: nx.Graph = build_from_json(
            graph_input,
            directed=directed,
            multigraph=multigraph,
            root=root,
        )
        graph_type = type(graph).__name__
        post_build_edge_count = graph.number_of_edges()
        post_build_node_count = graph.number_of_nodes()
    except Exception as exc:
        build_error = f"{type(exc).__name__}: {exc}"

    suppression_path = (
        Path(extract_path) if extract_path else Path(__file__).with_name("extract.py")
    )

    post_build_preserved_parallel_edges = None
    post_build_lost_distinct_edges = None
    if post_build_edge_count is not None:
        if graph_type in {"MultiGraph", "MultiDiGraph"}:
            built_pairs: Counter[tuple[str, str]] = Counter()
            for source, target in graph.edges():
                built_pairs[(str(source), str(target))] += 1
            post_build_preserved_parallel_edges = min(
                distinct_parallel_edge_instances,
                _count_extra(built_pairs),
            )
        else:
            post_build_preserved_parallel_edges = 0
        post_build_lost_distinct_edges = max(
            0, canonical_distinct_candidate_edges - post_build_edge_count
        )

    return {
        "node_count": len(node_ids),
        "unverified_node_count": unverified_node_count,
        "raw_edge_count": len(raw_edges),
        "non_object_edges": non_object_edges,
        "missing_endpoint_edges": missing_endpoint_edges,
        "dangling_endpoint_edges": dangling_endpoint_edges,
        "external_endpoint_edges": external_endpoint_edges,
        "unresolved_internal_endpoint_edges": unresolved_internal_endpoint_edges,
        "malformed_endpoint_edges": malformed_endpoint_edges,
        "unclassified_endpoint_edges": unclassified_endpoint_edges,
        "self_loop_edges": self_loop_edges,
        "valid_candidate_edges": valid_candidate_edges,
        "exact_duplicate_edges": exact_duplicate_occurrences,
        "canonical_distinct_candidate_edges": canonical_distinct_candidate_edges,
        "exact_duplicate_occurrences": exact_duplicate_occurrences,
        "distinct_parallel_edge_instances": distinct_parallel_edge_instances,
        "opposite_direction_endpoint_pairs": opposite_direction_endpoint_pairs,
        "directed_unique_endpoint_pairs": len(directed_pairs),
        "directed_same_endpoint_collapsed_edges": _count_extra(directed_pairs),
        "undirected_unique_endpoint_pairs": len(undirected_pairs),
        "undirected_same_endpoint_collapsed_edges": _count_extra(undirected_pairs),
        "same_endpoint_group_count": sum(1 for count in directed_pairs.values() if count > 1),
        "relation_variant_groups": _variant_group_count(grouped, "relation"),
        "source_file_variant_groups": _variant_group_count(
            grouped, "source_file", relation_sensitive=True
        ),
        "source_location_variant_groups": _variant_group_count(
            grouped, "source_location", relation_sensitive=True
        ),
        "context_variant_groups": _variant_group_count(grouped, "context", relation_sensitive=True),
        "post_build_graph_type": graph_type,
        "post_build_node_count": post_build_node_count,
        "post_build_edge_count": post_build_edge_count,
        "post_build_preserved_parallel_edges": post_build_preserved_parallel_edges,
        "post_build_lost_distinct_edges": post_build_lost_distinct_edges,
        "post_build_error": build_error,
        "producer_suppression": scan_producer_suppression_sites(suppression_path),
        "examples": examples,
        "endpoint_examples": endpoint_examples,
    }


def _read_json_file(path: str | Path) -> dict[str, Any]:
    """Read a JSON graph after applying Graphify's graph-load size cap."""
    from graphify.security import check_graph_file_size_cap

    json_path = Path(path)
    check_graph_file_size_cap(json_path)
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise RuntimeError(
            f"Cannot parse {json_path}: {exc}. "
            "The file may be corrupted — re-run 'graphify extract'."
        ) from exc
    if not isinstance(data, dict):
        raise ValueError("diagnostic input must be a JSON object")
    return data


def diagnose_file(
    path: str | Path,
    *,
    directed: bool | None = None,
    multigraph: bool | None = None,
    root: str | Path | None = None,
    max_examples: int = 5,
    extract_path: str | Path | None = None,
) -> dict[str, Any]:
    """Diagnose a graph/extraction JSON file without mutating it.

    When `directed` is None, the JSON's "directed" flag is honored. Raw
    extraction JSON that has no "directed" flag defaults to directed analysis.
    """
    data = _read_json_file(path)
    if directed is None:
        raw_directed = data.get("directed")
        effective_directed = raw_directed if isinstance(raw_directed, bool) else True
    else:
        effective_directed = directed
    if multigraph is None:
        effective_multigraph = data.get("multigraph") is True
    else:
        effective_multigraph = multigraph
    if effective_multigraph:
        effective_directed = True

    summary = diagnose_extraction(
        data,
        directed=effective_directed,
        multigraph=effective_multigraph,
        root=root,
        max_examples=max_examples,
        extract_path=extract_path,
    )
    summary["input_path"] = str(path)
    summary["effective_directed"] = effective_directed
    summary["effective_multigraph"] = effective_multigraph
    return summary


def format_diagnostic_json(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "summary": {
            key: value
            for key, value in summary.items()
            if key not in {"examples", "endpoint_examples", "producer_suppression"}
        },
        "examples": summary.get("examples", []),
        "endpoint_examples": summary.get("endpoint_examples", {}),
        "producer_suppression": summary.get("producer_suppression", {}),
        "notes": [
            "Diagnostics are read-only.",
            "A normal graph.json is already post-build and cannot recover raw producer edges.",
            "Producer suppression sites are heuristic source-code evidence.",
        ],
    }


def format_diagnostic_report(summary: dict[str, Any]) -> str:
    suppression = summary.get("producer_suppression", {})
    lines = [
        "[graphify] MultiDiGraph edge-collapse diagnostic",
        f"input: {summary.get('input_path', '<in-memory>')}",
        "input_stage: provided JSON (normal graph.json is post-build)",
        f"effective_directed: {summary.get('effective_directed', '<direct-call>')}",
        f"effective_multigraph: {summary.get('effective_multigraph', '<direct-call>')}",
        f"nodes: {summary['node_count']}",
        f"unverified_code_nodes: {summary.get('unverified_node_count', 0)}",
        f"raw_edges: {summary['raw_edge_count']}",
        f"valid_candidate_edges: {summary['valid_candidate_edges']}",
        f"missing_endpoint_edges: {summary['missing_endpoint_edges']}",
        f"dangling_endpoint_edges: {summary['dangling_endpoint_edges']}",
        f"external_endpoint_edges: {summary.get('external_endpoint_edges', 0)}",
        (
            "unresolved_internal_endpoint_edges: "
            f"{summary.get('unresolved_internal_endpoint_edges', 0)}"
        ),
        f"malformed_endpoint_edges: {summary.get('malformed_endpoint_edges', 0)}",
        f"unclassified_endpoint_edges: {summary.get('unclassified_endpoint_edges', 0)}",
        f"self_loop_edges: {summary['self_loop_edges']}",
        f"exact_duplicate_edges: {summary['exact_duplicate_edges']}",
        (
            "canonical_distinct_candidate_edges: "
            f"{summary.get('canonical_distinct_candidate_edges', 0)}"
        ),
        f"exact_duplicate_occurrences: {summary.get('exact_duplicate_occurrences', 0)}",
        (
            "distinct_parallel_edge_instances: "
            f"{summary.get('distinct_parallel_edge_instances', 0)}"
        ),
        (
            "opposite_direction_endpoint_pairs: "
            f"{summary.get('opposite_direction_endpoint_pairs', 0)}"
        ),
        f"directed_unique_endpoint_pairs: {summary['directed_unique_endpoint_pairs']}",
        (
            "directed_same_endpoint_collapsed_edges: "
            f"{summary['directed_same_endpoint_collapsed_edges']}"
        ),
        f"undirected_unique_endpoint_pairs: {summary['undirected_unique_endpoint_pairs']}",
        (
            "undirected_same_endpoint_collapsed_edges: "
            f"{summary['undirected_same_endpoint_collapsed_edges']}"
        ),
        f"same_endpoint_group_count: {summary['same_endpoint_group_count']}",
        f"relation_variant_groups: {summary['relation_variant_groups']}",
        f"source_file_variant_groups: {summary['source_file_variant_groups']}",
        f"source_location_variant_groups: {summary['source_location_variant_groups']}",
        f"context_variant_groups: {summary['context_variant_groups']}",
        f"post_build_graph_type: {summary['post_build_graph_type']}",
        f"post_build_edges: {summary['post_build_edge_count']}",
        (
            "post_build_preserved_parallel_edges: "
            f"{summary.get('post_build_preserved_parallel_edges', 0)}"
        ),
        (
            "post_build_lost_distinct_edges: "
            f"{summary.get('post_build_lost_distinct_edges', 0)}"
        ),
        f"producer_suppression_sites: {suppression.get('total_sites', 0)}",
    ]
    if summary.get("post_build_error"):
        lines.append(f"post_build_error: {summary['post_build_error']}")
    if suppression.get("error"):
        lines.append(f"producer_suppression_error: {suppression['error']}")
    if suppression.get("sites"):
        lines.append("producer_suppression_examples:")
        for site in suppression["sites"][:8]:
            lines.append(
                f"  - L{site['line']} {site['name']} arity={site['tuple_arity'] or 'unknown'}"
            )
    if summary.get("examples"):
        lines.append("examples:")
        for example in summary["examples"]:
            lines.append(
                "  - "
                f"{example['source']} -> {example['target']} "
                f"edges={example['edge_count']} "
                f"relations={example['relations']} "
                f"locations={example['source_locations']} "
                f"contexts={example['contexts']}"
            )
    lines.append(
        "note: normal graph.json is post-build; raw producer loss must be measured earlier."
    )
    return "\n".join(lines)
