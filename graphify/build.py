# assemble node+edge dicts into a NetworkX graph, preserving edge direction
from __future__ import annotations
import sys
import networkx as nx
from .validate import REQUIRED_EDGE_FIELDS, validate_extraction

# Older extractions use these keys instead of the canonical "relation". They are
# folded before validation so a legacy edge is not dropped for the wrong reason.
_EDGE_ALIASES = ("relationship", "type")


def _fold_edge_aliases(extraction: dict) -> dict:
    """Copy the extraction, folding legacy edge aliases into "relation".

    The caller's dict is left untouched; only the returned copy is normalized.
    """
    edges = extraction.get("edges")
    if not isinstance(edges, list):
        return extraction
    folded: list = []
    for edge in edges:
        if isinstance(edge, dict) and "relation" not in edge:
            for alias in _EDGE_ALIASES:
                if alias in edge:
                    value = edge[alias]
                    edge = {k: v for k, v in edge.items() if k != alias}
                    edge["relation"] = value
                    break
        folded.append(edge)
    return {**extraction, "edges": folded}


def build_from_json(extraction: dict) -> nx.Graph:
    extraction = _fold_edge_aliases(extraction)
    errors = validate_extraction(extraction)
    # Dangling edges (stdlib/external imports) are expected - only warn about real schema errors.
    real_errors = [e for e in errors if "does not match any node id" not in e]
    if real_errors:
        print(f"[graphify] Extraction warning ({len(real_errors)} issues): {real_errors[0]}", file=sys.stderr)
    G = nx.Graph()
    for node in extraction.get("nodes", []):
        G.add_node(node["id"], **{k: v for k, v in node.items() if k != "id"})
    node_set = set(G.nodes())
    # An edge that is still missing a required field is dropped rather than
    # persisted: guessing a relation would put a schema-invalid edge into
    # graph.json, which every downstream consumer assumes is well formed.
    skipped_edges = 0
    skipped_fields: dict[str, int] = {}
    for edge in extraction.get("edges", []):
        if not isinstance(edge, dict):
            skipped_edges += 1
            continue
        missing = REQUIRED_EDGE_FIELDS - edge.keys()
        if missing:
            skipped_edges += 1
            for field in missing:
                skipped_fields[field] = skipped_fields.get(field, 0) + 1
            continue
        src, tgt = edge["source"], edge["target"]
        if src not in node_set or tgt not in node_set:
            continue  # skip edges to external/stdlib nodes - expected, not an error
        attrs = {k: v for k, v in edge.items() if k not in ("source", "target")}
        # Preserve original edge direction - undirected graphs lose it otherwise,
        # causing display functions to show edges backwards.
        attrs["_src"] = src
        attrs["_tgt"] = tgt
        G.add_edge(src, tgt, **attrs)
    if skipped_edges:
        detail = ", ".join(
            f"'{field}' ({count})" for field, count in sorted(skipped_fields.items())
        )
        reason = f"missing required field(s): {detail}" if detail else "not an edge object"
        print(
            f"[graphify] Dropped {skipped_edges} schema-invalid edge(s) - {reason}",
            file=sys.stderr,
        )
    hyperedges = extraction.get("hyperedges", [])
    if hyperedges:
        G.graph["hyperedges"] = hyperedges
    # Strip degree-0 code nodes — they are bundled/synthetic symbols with no
    # connections and only inflate god-node centrality and clustering noise.
    # Document, paper, and image nodes are kept even when isolated since they
    # may be leaf concepts intentionally referenced by the skill.
    isolated_code = [
        n for n in list(G.nodes())
        if G.degree(n) == 0 and G.nodes[n].get("file_type") == "code"
    ]
    G.remove_nodes_from(isolated_code)
    return G


def build(extractions: list[dict]) -> nx.Graph:
    """Merge multiple extraction results into one graph."""
    combined: dict = {"nodes": [], "edges": [], "input_tokens": 0, "output_tokens": 0}
    for ext in extractions:
        combined["nodes"].extend(ext.get("nodes", []))
        combined["edges"].extend(ext.get("edges", []))
        combined["input_tokens"] += ext.get("input_tokens", 0)
        combined["output_tokens"] += ext.get("output_tokens", 0)
    return build_from_json(combined)
