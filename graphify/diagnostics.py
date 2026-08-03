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


# Relations whose target is legitimately outside the corpus: a Python stdlib or
# third-party module, a Swift system framework, an npm package. The corpus never
# contains a node for them, so the edge cannot resolve and never will. This is an
# expected unresolved EXTERNAL reference, not a broken internal one, and conflating
# the two hid 31 real semantic danglers behind 43 harmless import edges (#2311).
_EXTERNAL_IMPORT_RELATIONS = frozenset({"imports", "imports_from"})


def _classify_dangling(edge: dict[str, str], node_ids: set[str]) -> str:
    """Classify a dangling edge as an expected external ref or an unexpected one.

    Only a MISSING TARGET counts as external: an import edge whose *source* is
    absent is a broken producer, not an outside module. An external module id is
    a bare name — a dangling target carrying path separators is a corpus file the
    extractor failed to emit, which is a real defect.
    """
    source_present = edge["source"] in node_ids
    target = edge["target"]
    if (
        source_present
        and edge["relation"] in _EXTERNAL_IMPORT_RELATIONS
        and "/" not in target
        and "\\" not in target
    ):
        return "external_import"
    return "unexpected"


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

    # Code-typed semantic nodes the extractor could not verify against the source
    # it read (#1949): likely-inferred (or hallucinated) symbols surfaced from a
    # document. Count them so the flag on graph.json nodes is actually surfaced.
    unverified_node_count = sum(
        1 for n in extraction.get("nodes", [])
        if isinstance(n, dict) and n.get("verification") == "unverified"
    )

    exact_counts: Counter[str] = Counter(_exact_signature(edge) for edge in raw_edges)
    directed_pairs: Counter[tuple[str, str]] = Counter()
    undirected_pairs: Counter[tuple[str, str]] = Counter()
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)

    non_object_edges = 0
    missing_endpoint_edges = 0
    dangling_endpoint_edges = 0
    external_import_edges = 0
    unexpected_dangling_edges = 0
    external_import_targets: set[str] = set()
    unexpected_dangling_examples: list[dict[str, str]] = []
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
            if _classify_dangling(edge, node_ids) == "external_import":
                external_import_edges += 1
                external_import_targets.add(target)
            else:
                unexpected_dangling_edges += 1
                if len(unexpected_dangling_examples) < 40:
                    unexpected_dangling_examples.append(
                        {
                            "source": source,
                            "target": target,
                            "missing": (
                                "target" if source in node_ids else
                                "source" if target in node_ids else "both"
                            ),
                            "relation": edge["relation"],
                            "source_file": edge["source_file"],
                            "source_location": edge["source_location"],
                        }
                    )
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
    provenance_edge_count: int | None = None
    try:
        graph_input = deepcopy(extraction)
        graph: nx.Graph = build_from_json(graph_input, directed=directed, root=root)
        graph_type = type(graph).__name__
        post_build_edge_count = graph.number_of_edges()
        post_build_node_count = graph.number_of_nodes()
        # Edges that absorbed more than one observation and therefore carry
        # collapse provenance. Pinning this count is how a caller detects
        # provenance silently disappearing between rebuilds (#2311).
        provenance_edge_count = sum(
            1 for _, _, data in graph.edges(data=True)
            if int(data.get("evidence_count", 1) or 1) > 1
        )
    except Exception as exc:
        build_error = f"{type(exc).__name__}: {exc}"

    suppression_path = (
        Path(extract_path) if extract_path else Path(__file__).with_name("extract.py")
    )

    return {
        "node_count": len(node_ids),
        "unverified_node_count": unverified_node_count,
        "raw_edge_count": len(raw_edges),
        "non_object_edges": non_object_edges,
        "missing_endpoint_edges": missing_endpoint_edges,
        "dangling_endpoint_edges": dangling_endpoint_edges,
        "external_import_edges": external_import_edges,
        "external_import_targets": sorted(external_import_targets),
        "unexpected_dangling_edges": unexpected_dangling_edges,
        "unexpected_dangling_examples": unexpected_dangling_examples,
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
        "provenance_edge_count": provenance_edge_count,
        "post_build_error": build_error,
        "producer_suppression": scan_producer_suppression_sites(suppression_path),
        "examples": examples,
    }


def evaluate_acceptance(
    summary: dict[str, Any],
    *,
    allow_self_loops: bool = False,
    expected_provenance_edges: int | None = None,
) -> dict[str, Any]:
    """Turn a diagnostic summary into a pass/fail acceptance decision.

    The split is the whole point. Some findings mean the graph is WRONG and the
    build should be rejected; others are permanent properties of an honest graph
    over a real corpus and must be reported without failing, or the gate becomes
    noise that everyone learns to skip.

    FAILS on:
      * malformed or missing endpoint fields
      * self-loops (unless ``allow_self_loops``, for corpora where recursion is
        legitimately modelled)
      * unexpected dangling semantic endpoints — every one is a real defect once
        extraction has run under the current prompt
      * unverified code nodes (symbols an extractor could not confirm in source)
      * build errors
      * nondeterministic loss of semantic provenance, when the caller pins the
        expected count via ``expected_provenance_edges``

    REPORTS without failing:
      * verified external imports (stdlib/third-party targets the corpus cannot
        contain)
      * deterministic simple-graph edge consolidation
    """
    failures: list[str] = []
    informational: list[str] = []

    if summary.get("non_object_edges"):
        failures.append(f"{summary['non_object_edges']} malformed (non-object) edges")
    if summary.get("missing_endpoint_edges"):
        failures.append(
            f"{summary['missing_endpoint_edges']} edges with missing endpoint fields"
        )
    if summary.get("unexpected_dangling_edges"):
        failures.append(
            f"{summary['unexpected_dangling_edges']} unexpected dangling semantic endpoints"
        )
    if summary.get("unverified_node_count"):
        failures.append(f"{summary['unverified_node_count']} unverified code nodes")
    if summary.get("post_build_error"):
        failures.append(f"graph build error: {summary['post_build_error']}")
    self_loops = summary.get("self_loop_edges", 0)
    if self_loops and not allow_self_loops:
        failures.append(f"{self_loops} self-loop edges not explicitly allowed")

    provenance_edges = summary.get("provenance_edge_count")
    if expected_provenance_edges is not None and provenance_edges is not None:
        if provenance_edges != expected_provenance_edges:
            failures.append(
                "semantic provenance changed nondeterministically: expected "
                f"{expected_provenance_edges} edges carrying collapse provenance, "
                f"found {provenance_edges}"
            )

    external = summary.get("external_import_edges", 0)
    if external:
        informational.append(
            f"{external} verified external imports "
            f"({len(summary.get('external_import_targets', []))} distinct modules)"
        )
    collapsed = summary.get("undirected_same_endpoint_collapsed_edges", 0)
    if collapsed:
        informational.append(
            f"{collapsed} deterministic simple-graph edge consolidations across "
            f"{summary.get('same_endpoint_group_count', 0)} endpoint groups"
        )
    if self_loops and allow_self_loops:
        informational.append(f"{self_loops} self-loop edges (explicitly allowed)")

    return {
        "passed": not failures,
        "failures": failures,
        "informational": informational,
    }


def format_acceptance_report(verdict: dict[str, Any]) -> str:
    lines = ["[graphify] acceptance policy"]
    for failure in verdict["failures"]:
        lines.append(f"  FAIL  {failure}")
    for note in verdict["informational"]:
        lines.append(f"  info  {note}")
    lines.append("PASS" if verdict["passed"] else "FAIL")
    return "\n".join(lines)


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
            if key not in {
                "examples",
                "producer_suppression",
                "unexpected_dangling_examples",
            }
        },
        "examples": summary.get("examples", []),
        "unexpected_dangling_examples": summary.get("unexpected_dangling_examples", []),
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
        f"unverified_code_nodes: {summary.get('unverified_node_count', 0)}",
        f"raw_edges: {summary['raw_edge_count']}",
        f"valid_candidate_edges: {summary['valid_candidate_edges']}",
        f"missing_endpoint_edges: {summary['missing_endpoint_edges']}",
        f"dangling_endpoint_edges: {summary['dangling_endpoint_edges']}",
        (
            "  expected_external_imports: "
            f"{summary.get('external_import_edges', 0)}"
        ),
        (
            "  unexpected_dangling_edges: "
            f"{summary.get('unexpected_dangling_edges', 0)}"
        ),
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
