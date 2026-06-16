"""Read-only diagnostics for MultiDiGraph readiness."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Any

import networkx as nx


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


def _canonical_edge(edge: Any) -> dict[str, str]:
    if not isinstance(edge, dict):
        return {
            "source": "",
            "target": "",
            "relation": "",
            "confidence": "",
            "source_file": "",
            "source_location": "",
            "context": "",
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
        "_invalid": "",
    }


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
    root: str | Path | None = None,
    max_examples: int = 5,
    extract_path: str | Path | None = None,
) -> dict[str, Any]:
    """Summarize same-endpoint edge-collapse risk for one JSON graph/extraction dict."""
    from graphify.build import build_from_json

    node_ids = _node_ids(extraction)
    raw_edges = _edge_list(extraction)
    canonical_edges = [_canonical_edge(edge) for edge in raw_edges]

    exact_counts: Counter[str] = Counter(_exact_signature(edge) for edge in raw_edges)
    directed_pairs: Counter[tuple[str, str]] = Counter()
    undirected_pairs: Counter[tuple[str, str]] = Counter()
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)

    non_object_edges = 0
    missing_endpoint_edges = 0
    dangling_endpoint_edges = 0
    self_loop_edges = 0
    valid_candidate_edges = 0

    for edge in canonical_edges:
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
            continue
        if source == target:
            self_loop_edges += 1
        valid_candidate_edges += 1
        directed_pair = (source, target)
        undirected_pair = (source, target) if source <= target else (target, source)
        directed_pairs[directed_pair] += 1
        undirected_pairs[undirected_pair] += 1
        grouped[directed_pair].append(edge)

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
        graph: nx.Graph = build_from_json(graph_input, directed=directed, root=root)
        graph_type = type(graph).__name__
        post_build_edge_count = graph.number_of_edges()
        post_build_node_count = graph.number_of_nodes()
    except Exception as exc:
        build_error = f"{type(exc).__name__}: {exc}"

    suppression_path = (
        Path(extract_path) if extract_path else Path(__file__).with_name("extract.py")
    )

    return {
        "node_count": len(node_ids),
        "raw_edge_count": len(raw_edges),
        "non_object_edges": non_object_edges,
        "missing_endpoint_edges": missing_endpoint_edges,
        "dangling_endpoint_edges": dangling_endpoint_edges,
        "self_loop_edges": self_loop_edges,
        "valid_candidate_edges": valid_candidate_edges,
        "exact_duplicate_edges": _count_extra(exact_counts),
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
        "post_build_error": build_error,
        "producer_suppression": scan_producer_suppression_sites(suppression_path),
        "examples": examples,
    }


def _read_json_file(path: str | Path) -> dict[str, Any]:
    """Read a JSON graph after applying Graphify's graph-load size cap."""
    from graphify.security import check_graph_file_size_cap

    json_path = Path(path)
    check_graph_file_size_cap(json_path)
    data = json.loads(json_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("diagnostic input must be a JSON object")
    return data


def diagnose_file(
    path: str | Path,
    *,
    directed: bool | None = None,
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

    summary = diagnose_extraction(
        data,
        directed=effective_directed,
        root=root,
        max_examples=max_examples,
        extract_path=extract_path,
    )
    summary["input_path"] = str(path)
    summary["effective_directed"] = effective_directed
    return summary


def format_diagnostic_json(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "summary": {
            key: value
            for key, value in summary.items()
            if key not in {"examples", "producer_suppression"}
        },
        "examples": summary.get("examples", []),
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
        f"nodes: {summary['node_count']}",
        f"raw_edges: {summary['raw_edge_count']}",
        f"valid_candidate_edges: {summary['valid_candidate_edges']}",
        f"missing_endpoint_edges: {summary['missing_endpoint_edges']}",
        f"dangling_endpoint_edges: {summary['dangling_endpoint_edges']}",
        f"self_loop_edges: {summary['self_loop_edges']}",
        f"exact_duplicate_edges: {summary['exact_duplicate_edges']}",
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


_QUALITY_GENERIC_SYMBOLS = {
    "str",
    "Any",
    "int",
    "bool",
    "float",
    "Path",
    "Connection",
    "Namespace",
    "main()",
    "Check",
    "Report",
    "HealthReport",
}
_QUALITY_RELATIONS = {
    "calls",
    "uses",
    "references",
    "depends_on",
    "imports",
    "implements",
}


def _quality_score(edge: dict[str, Any]) -> float:
    try:
        return float(edge.get("confidence_score", 1.0))
    except (TypeError, ValueError):
        return 1.0


def _quality_label(node: dict[str, Any]) -> str:
    return str(node.get("label") or node.get("id") or "")


def diagnose_quality(
    data: dict[str, Any],
    *,
    low_confidence_threshold: float = 0.5,
    generic_degree_threshold: int = 10,
    generic_source_threshold: int = 3,
    max_examples: int = 10,
) -> dict[str, Any]:
    """Read-only quality diagnostics for graph navigation safety."""
    raw_nodes = data.get("nodes", [])
    nodes = [
        node
        for node in raw_nodes
        if isinstance(node, dict) and node.get("id") is not None
    ] if isinstance(raw_nodes, list) else []
    by_id = {str(node["id"]): node for node in nodes}
    labels = {node_id: _quality_label(node) for node_id, node in by_id.items()}
    edges = _edge_list(data)

    dangling_examples: list[dict[str, Any]] = []
    low_conf_examples: list[dict[str, Any]] = []
    low_conf_generic_examples: list[dict[str, Any]] = []
    degree: Counter[str] = Counter()
    source_files_by_node: dict[str, set[str]] = defaultdict(set)
    dangling_count = 0
    low_conf_count = 0
    low_conf_generic_count = 0

    for edge in edges:
        if not isinstance(edge, dict):
            continue
        source = str(edge.get("source", edge.get("from", "")))
        target = str(edge.get("target", edge.get("to", "")))
        if source not in by_id or target not in by_id:
            dangling_count += 1
            if len(dangling_examples) < max_examples:
                dangling_examples.append({"source": source, "target": target})
            continue

        degree[source] += 1
        degree[target] += 1
        source_file = str(edge.get("source_file") or "")
        if source_file:
            source_files_by_node[source].add(source_file)
            source_files_by_node[target].add(source_file)

        is_low = (
            str(edge.get("confidence", "")).upper() == "INFERRED"
            and _quality_score(edge) <= low_confidence_threshold
        )
        if not is_low:
            continue

        low_conf_count += 1
        example = {
            "source": source,
            "target": target,
            "source_label": labels[source],
            "target_label": labels[target],
            "relation": edge.get("relation"),
            "confidence_score": edge.get("confidence_score"),
            "source_file": edge.get("source_file"),
        }
        if len(low_conf_examples) < max_examples:
            low_conf_examples.append(example)

        source_generic = labels[source] in _QUALITY_GENERIC_SYMBOLS
        target_generic = labels[target] in _QUALITY_GENERIC_SYMBOLS
        if (source_generic or target_generic) and str(edge.get("relation", "")) in _QUALITY_RELATIONS:
            low_conf_generic_count += 1
            if len(low_conf_generic_examples) < max_examples:
                low_conf_generic_examples.append(example)

    generic_bridges = []
    for node_id, label in labels.items():
        if label not in _QUALITY_GENERIC_SYMBOLS:
            continue
        if (
            degree[node_id] >= generic_degree_threshold
            and len(source_files_by_node[node_id]) >= generic_source_threshold
        ):
            generic_bridges.append({
                "id": node_id,
                "label": label,
                "degree": degree[node_id],
                "source_file_count": len(source_files_by_node[node_id]),
            })
    generic_bridges.sort(key=lambda item: (-item["degree"], item["label"]))

    passed = not dangling_count and not low_conf_count and not low_conf_generic_count and not generic_bridges
    return {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "dangling_edge_count": dangling_count,
        "low_confidence_inferred_count": low_conf_count,
        "low_confidence_generic_edge_count": low_conf_generic_count,
        "generic_bridge_count": len(generic_bridges),
        "pass": passed,
        "examples": {
            "dangling_edges": dangling_examples,
            "low_confidence_inferred_edges": low_conf_examples,
            "low_confidence_generic_edges": low_conf_generic_examples,
            "generic_bridges": generic_bridges[:max_examples],
        },
    }


def diagnose_quality_file(
    path: str | Path,
    *,
    low_confidence_threshold: float = 0.5,
    generic_degree_threshold: int = 10,
    generic_source_threshold: int = 3,
    max_examples: int = 10,
) -> dict[str, Any]:
    data = _read_json_file(path)
    summary = diagnose_quality(
        data,
        low_confidence_threshold=low_confidence_threshold,
        generic_degree_threshold=generic_degree_threshold,
        generic_source_threshold=generic_source_threshold,
        max_examples=max_examples,
    )
    graph_path = Path(path)
    report_path = graph_path.parent / "GRAPH_REPORT.md"
    html_path = graph_path.parent / "graph.html"
    graph_mtime = graph_path.stat().st_mtime
    summary["input_path"] = str(path)
    summary["report_stale"] = report_path.exists() and report_path.stat().st_mtime < graph_mtime
    summary["html_stale"] = html_path.exists() and html_path.stat().st_mtime < graph_mtime
    summary["pass"] = summary["pass"] and not summary["report_stale"] and not summary["html_stale"]
    return summary


def format_quality_report(summary: dict[str, Any]) -> str:
    status = "PASS" if summary.get("pass") else "FAIL"
    lines = [
        f"[graphify] Quality diagnostic: {status}",
        f"input: {summary.get('input_path', '<in-memory>')}",
        f"nodes: {summary['node_count']}",
        f"edges: {summary['edge_count']}",
        f"dangling_edges: {summary['dangling_edge_count']}",
        f"low_confidence_inferred_edges: {summary['low_confidence_inferred_count']}",
        f"low_confidence_generic_edges: {summary['low_confidence_generic_edge_count']}",
        f"generic_bridges: {summary['generic_bridge_count']}",
        f"report_stale: {summary.get('report_stale', False)}",
        f"html_stale: {summary.get('html_stale', False)}",
    ]
    examples = summary.get("examples", {})
    for key, rows in examples.items():
        if not rows:
            continue
        lines.append(f"{key}:")
        for row in rows:
            lines.append(f"  - {json.dumps(row, ensure_ascii=False, sort_keys=True)}")
    return "\n".join(lines)
