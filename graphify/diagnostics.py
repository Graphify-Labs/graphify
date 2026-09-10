"""Read-only diagnostics for MultiDiGraph readiness."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Any

import networkx as nx

from graphify.validate import validate_extraction

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


# Relations where direction is citer -> citee between whole-file document/paper
# nodes (extraction-spec.md's "references"/"cites" direction rule for docs,
# mirroring the "calls" direction rule for code). Deliberately excludes "calls"
# and other relation types, whose direction semantics differ.
_CITATION_RELATIONS = frozenset({"references", "cites"})
_WHOLE_FILE_TYPES = frozenset({"document", "paper"})


def _find_edge_direction_suspects(
    extraction: dict[str, Any], node_ids: set[str]
) -> list[dict[str, Any]]:
    """Flag references/cites edges whose own source_file matches the TARGET
    node's file rather than the SOURCE node's - the extraction-spec.md
    self-check for a reversed citation edge (the file that made the assertion
    is the target, meaning the target cited the source, not the other way
    round).

    High precision by construction: a node's source_file is where that node
    was authored; an edge's source_file is where the assertion was found. When
    those disagree in exactly this way, the edge was very likely recorded
    backwards - the bug class that inflated a real corpus's ARCHITECTURE.md/
    PRODUCT.md "god node" degree with edges actually asserted by the ADRs
    citing them, not by the docs themselves. Scoped to document/paper whole-
    file nodes on both ends, matching the spec rule this check enforces.
    """
    nodes = extraction.get("nodes", [])
    if not isinstance(nodes, list):
        return []
    file_by_id: dict[str, str] = {}
    type_by_id: dict[str, str] = {}
    ids_by_file: dict[str, set[str]] = defaultdict(set)
    for node in nodes:
        if not isinstance(node, dict):
            continue
        nid = node.get("id")
        sf = node.get("source_file")
        if not isinstance(nid, str) or not isinstance(sf, str) or not sf:
            continue
        file_by_id[nid] = sf
        type_by_id[nid] = node.get("file_type")
        ids_by_file[sf].add(nid)

    suspects: list[dict[str, Any]] = []
    for edge in _edge_list(extraction):
        if not isinstance(edge, dict) or edge.get("relation") not in _CITATION_RELATIONS:
            continue
        source = edge.get("source", edge.get("from"))
        target = edge.get("target", edge.get("to"))
        edge_source_file = edge.get("source_file")
        if not (
            isinstance(source, str) and isinstance(target, str)
            and source in node_ids and target in node_ids
            and source in file_by_id  # source node's own file must be known
            and type_by_id.get(source) in _WHOLE_FILE_TYPES
            and type_by_id.get(target) in _WHOLE_FILE_TYPES
            and isinstance(edge_source_file, str) and edge_source_file
        ):
            continue
        if file_by_id[source] == edge_source_file:
            continue  # matches the source node's own file - direction looks right.
        if target in ids_by_file.get(edge_source_file, ()):
            suspects.append(
                {
                    "source": source,
                    "target": target,
                    "relation": edge["relation"],
                    "edge_source_file": edge_source_file,
                    "source_node_file": file_by_id[source],
                }
            )
    return suspects


def _find_duplicate_whole_file_candidates(
    extraction: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Flag document/paper nodes that probably represent the same real file
    under two different ids - a canonical-identity violation.

    Returns (hard, soft):
      - hard: id B == id A + "_document" (or "_file"/"_page") - the exact
        whole-file-node suffix a subagent must never invent (extraction-spec.md
        "Whole-file nodes"), almost never a coincidence.
      - soft: labels look like the same file (one is the other's exact prefix
        up to a " - "/" -- "/" (" separator, e.g. "ARCHITECTURE.md" vs
        "ARCHITECTURE.md - Avenoria Technical Architecture") on two nodes with
        different source_file - plausible but not certain, kept separate from
        `hard` so it never blocks canonical status on its own.
    """
    nodes = [
        n for n in extraction.get("nodes", [])
        if isinstance(n, dict) and n.get("file_type") in _WHOLE_FILE_TYPES
        and isinstance(n.get("id"), str) and isinstance(n.get("label"), str)
    ]
    by_id = {n["id"]: n for n in nodes}

    hard: list[dict[str, Any]] = []
    hard_pairs: set[tuple[str, str]] = set()
    for n in nodes:
        for suffix in ("_document", "_file", "_page"):
            candidate = n["id"] + suffix
            other = by_id.get(candidate)
            if other is None:
                continue
            pair = tuple(sorted((n["id"], other["id"])))
            if pair in hard_pairs:
                continue
            hard_pairs.add(pair)
            hard.append(
                {"node_a": n["id"], "node_b": other["id"], "reason": f"id suffix {suffix!r}"}
            )

    soft: list[dict[str, Any]] = []
    seen_soft: set[tuple[str, str]] = set()
    separators = (" - ", " -- ", " (")
    for n in nodes:
        for m in nodes:
            if n["id"] >= m["id"]:
                continue
            pair = (n["id"], m["id"])
            if pair in hard_pairs or n.get("source_file") == m.get("source_file"):
                continue  # already caught by the id-suffix check, or same file
                          # (e.g. a heading node) - not a whole-file duplicate.
            shorter, longer = sorted((n["label"], m["label"]), key=len)
            if not longer.startswith(shorter):
                continue
            rest = longer[len(shorter):]
            if not any(rest.startswith(sep) for sep in separators):
                continue
            if pair in seen_soft:
                continue
            seen_soft.add(pair)
            soft.append({"node_a": n["id"], "node_b": m["id"], "reason": "label prefix"})

    return hard, soft


def diagnose_extraction(
    extraction: dict[str, Any],
    *,
    directed: bool = True,
    root: str | Path | None = None,
    max_examples: int = 5,
    extract_path: str | Path | None = None,
) -> dict[str, Any]:
    """Summarize same-endpoint edge-collapse risk for one JSON graph/extraction dict.

    Also runs the graph-validity gate this function's docstring didn't used to
    cover: schema errors, reversed citation edges, and probable duplicate
    whole-file nodes. The `canonical` field is the answer to "can architectural
    metrics (centrality, clustering, dependency analysis) computed from this
    graph be trusted, or are they informational only until the issues below are
    fixed?" A non-canonical graph is not corrupt or unusable - it can still be
    built and browsed - but its structural metrics may not reflect the real
    architecture and should be caveated accordingly.
    """
    from graphify.build import build_from_json

    node_ids = _node_ids(extraction)
    raw_edges = _edge_list(extraction)
    canonical_edges = [_canonical_edge(edge) for edge in raw_edges]
    schema_errors = validate_extraction(extraction)
    edge_direction_suspects = _find_edge_direction_suspects(extraction, node_ids)
    duplicate_node_candidates, duplicate_node_candidates_soft = (
        _find_duplicate_whole_file_candidates(extraction)
    )

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

    # What blocks `canonical`: schema errors, dangling/missing edge endpoints,
    # reversed citation edges, and hard (id-suffix) duplicate whole-file nodes.
    # What does NOT block it (informational only, per the report/warnings
    # below): edge-collapse counts, self-loops, and the soft (label-prefix)
    # duplicate candidates - each has a plausible benign explanation on its
    # own, so they are visibility, not proof.
    canonical_issues: list[str] = []
    if schema_errors:
        canonical_issues.append(f"{len(schema_errors)} schema error(s)")
    if missing_endpoint_edges:
        canonical_issues.append(f"{missing_endpoint_edges} edge(s) with a missing endpoint")
    if dangling_endpoint_edges:
        canonical_issues.append(f"{dangling_endpoint_edges} edge(s) with a dangling endpoint")
    if edge_direction_suspects:
        canonical_issues.append(
            f"{len(edge_direction_suspects)} references/cites edge(s) with a likely-reversed direction"
        )
    if duplicate_node_candidates:
        canonical_issues.append(
            f"{len(duplicate_node_candidates)} probable duplicate whole-file node pair(s)"
        )
    canonical = not canonical_issues

    return {
        "canonical": canonical,
        "canonical_issues": canonical_issues,
        "schema_errors": schema_errors,
        "edge_direction_suspects": edge_direction_suspects,
        "duplicate_node_candidates": duplicate_node_candidates,
        "duplicate_node_candidates_soft": duplicate_node_candidates_soft,
        "node_count": len(node_ids),
        "unverified_node_count": unverified_node_count,
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
    canonical = summary.get("canonical", True)
    verdict = "CANONICAL" if canonical else "NON-CANONICAL"
    lines = [
        "[graphify] MultiDiGraph edge-collapse diagnostic",
        f"verdict: {verdict}"
        + (
            ""
            if canonical
            else " - treat centrality/clustering/dependency metrics as informational "
            "only until the issues below are fixed"
        ),
        f"input: {summary.get('input_path', '<in-memory>')}",
        "input_stage: provided JSON (normal graph.json is post-build)",
        f"effective_directed: {summary.get('effective_directed', '<direct-call>')}",
        f"nodes: {summary['node_count']}",
        f"unverified_code_nodes: {summary.get('unverified_node_count', 0)}",
        f"raw_edges: {summary['raw_edge_count']}",
        f"valid_candidate_edges: {summary['valid_candidate_edges']}",
        f"missing_endpoint_edges: {summary['missing_endpoint_edges']}",
        f"dangling_endpoint_edges: {summary['dangling_endpoint_edges']}",
        f"schema_errors: {len(summary.get('schema_errors', []))}",
        f"edge_direction_suspects: {len(summary.get('edge_direction_suspects', []))}",
        f"duplicate_node_candidates: {len(summary.get('duplicate_node_candidates', []))}"
        f" (+{len(summary.get('duplicate_node_candidates_soft', []))} soft)",
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
    if summary.get("schema_errors"):
        lines.append("schema_errors:")
        for error in summary["schema_errors"][:8]:
            lines.append(f"  - {error}")
    if summary.get("edge_direction_suspects"):
        lines.append("edge_direction_suspects (likely reversed references/cites):")
        for s in summary["edge_direction_suspects"][:8]:
            lines.append(
                f"  - {s['source']} --{s['relation']}--> {s['target']} "
                f"(edge asserted in {s['edge_source_file']!r}, which is {s['target']}'s own file, "
                f"not {s['source']}'s {s['source_node_file']!r})"
            )
    if summary.get("duplicate_node_candidates"):
        lines.append("duplicate_node_candidates (probable same-file split, id suffix):")
        for d in summary["duplicate_node_candidates"][:8]:
            lines.append(f"  - {d['node_a']} <-> {d['node_b']} ({d['reason']})")
    if summary.get("duplicate_node_candidates_soft"):
        lines.append("duplicate_node_candidates_soft (label prefix, needs a human glance):")
        for d in summary["duplicate_node_candidates_soft"][:8]:
            lines.append(f"  - {d['node_a']} <-> {d['node_b']} ({d['reason']})")
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
