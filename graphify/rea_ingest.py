"""rea_ingest.py — ingest REA's JavaScript Application Graph into Graphify.

REA (https://github.com/morluto/rea, "Reverse Engineer Anything") analyzes
shipped application bytes — native binaries, JavaScript/Electron bundles, .NET,
WASM — and emits a provider-neutral **JavaScript Application Graph** (JAG): a
canonical JSON graph of the application's structure with evidence attached to
every node and edge. Graphify turns code you *have source for* into a queryable
knowledge graph; this ingester lets you do the same for code you *don't* — feed
a JAG export in and `graphify query` / `path` / `explain` over a reverse-
engineered app.

Entry point:
  ingest_rea_jag(doc: object, source_file: str = "") -> {"nodes": [...], "edges": [...]}

The result is endpoint-safe (every edge endpoint is a real node or a minted
``rea_external`` stub) so ``build_from_json`` keeps every edge.

Grounded in REA's documented JAG contract (docs/javascript-application-graph.md):
top-level ``nodes`` / ``edges`` / ``coverage`` / ``limitations``; each node has a
``kind``, display ``label``, and one or more ``observations``; each edge has
``source_node_id`` / ``target_node_id``, a ``relation`` from REA's fixed relation
vocabulary, and an epistemic state (``observed`` / ``inferred`` / ``unknown`` /
``unavailable``). Field-name aliases are accepted where the prose contract leaves
a name slightly ambiguous, so a minor schema revision degrades gracefully rather
than dropping the whole graph. REA is MIT-licensed; this consumes its JSON
*contract*, not its code.

NOTE: validated against a synthetic fixture built from the documented schema;
should be checked against a real ``rea ... --json`` export before release.
"""

from __future__ import annotations

from typing import Any

from graphify.extractors.base import _make_id
from graphify.security import sanitize_metadata

# REA node kinds that are structural code artifacts vs. conceptual boundaries.
# Everything not listed as a concept defaults to "code".
_REA_CONCEPT_KINDS = frozenset({
    "package", "installer", "artifact", "asar entry", "asar_entry",
    "browserwindow", "frame", "target", "contextbridge api",
    "contextbridge_api", "ipc channel", "ipc_channel", "endpoint", "storage",
})

# REA's directed relation vocabulary -> Graphify's known relation set, so the
# analysis/affected passes understand the edges. The original REA relation is
# preserved verbatim in the edge ``context`` ("rea:<relation>").
_REA_RELATION_MAP = {
    "contains": "contains",
    "loads": "imports",
    "imports": "imports",
    "calls": "calls",
    "invokes": "calls",
    "sends": "calls",
    "handles": "references",
    "exposes": "references",
    "maps_to": "references",
    "persists_to": "references",
    "observed_as": "references",
    "changed_from": "references",
}

# REA confidence term -> a Graphify confidence_score.
_REA_CONFIDENCE_SCORE = {
    "exact": 1.0, "high": 0.9, "medium": 0.7, "low": 0.5, "unknown": 0.3,
}


def _s(value: object, default: str = "") -> str:
    return value if isinstance(value, str) and value else default


def _rea_node_id(raw_id: str) -> str:
    """Namespaced, build-safe Graphify id for a REA node (ids must be [a-z0-9_])."""
    return _make_id("rea", raw_id)


def _node_kind(node: dict) -> str:
    return _s(node.get("kind") or node.get("node_kind") or node.get("type"), "unknown")


def _node_label(node: dict, kind: str, raw_id: str) -> str:
    return _s(node.get("label") or node.get("name"), f"{kind}:{raw_id.rsplit('_', 1)[-1]}")


def _edge_endpoints(edge: dict) -> tuple[str, str]:
    src = _s(edge.get("source_node_id") or edge.get("source") or edge.get("from"))
    tgt = _s(edge.get("target_node_id") or edge.get("target") or edge.get("to"))
    return src, tgt


def _epistemic_state(entity: dict) -> str:
    """Strongest epistemic state of an entity (edge, or node via its observations)."""
    direct = _s(entity.get("epistemic_state")).lower()
    if direct:
        return direct
    best = ""
    rank = {"observed": 3, "inferred": 2, "unknown": 1, "unavailable": 0}
    for obs in entity.get("observations", []) or []:
        if not isinstance(obs, dict):
            continue
        st = _s(obs.get("epistemic_state")).lower()
        if st and rank.get(st, -1) > rank.get(best, -1):
            best = st
    return best


def _confidence(entity: dict, state: str) -> tuple[str, float]:
    """Map an epistemic state + REA confidence term to Graphify (confidence, score)."""
    term = _s(entity.get("confidence")).lower()
    for obs in entity.get("observations", []) or []:
        if isinstance(obs, dict) and not term:
            term = _s(obs.get("confidence")).lower()
    # Only a directly observed fact earns EXTRACTED; everything else is INFERRED.
    confidence = "EXTRACTED" if state == "observed" else "INFERRED"
    default = 1.0 if state == "observed" else 0.7
    score = _REA_CONFIDENCE_SCORE.get(term, default)
    if confidence == "INFERRED":
        score = min(score, 0.9)  # inferred facts never claim certainty
    return confidence, score


def _file_type(kind: str) -> str:
    return "concept" if kind.lower() in _REA_CONCEPT_KINDS else "code"


def ingest_rea_jag(doc: object, source_file: str = "") -> dict[str, Any]:
    """Convert a REA JavaScript Application Graph into Graphify nodes and edges.

    ``doc`` is ``object`` because it arrives as arbitrary deserialized JSON from an
    external tool; anything that is not the expected dict shape yields an empty
    result rather than raising.
    """
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    if not isinstance(doc, dict):
        return {"nodes": nodes, "edges": edges}

    raw_nodes = doc.get("nodes")
    raw_edges = doc.get("edges")
    if not isinstance(raw_nodes, list):
        return {"nodes": nodes, "edges": edges}

    host = _s(source_file) or f"rea:{_s(doc.get('graph_id'), 'graph')}"
    # Graph-wide coverage/limitations are attached to the root nodes' metadata
    # (the ingester contract is node/edge only, with no graph-level slot).
    root_ids = {_s(r) for r in (doc.get("root_node_ids") or []) if isinstance(r, str)}
    graph_coverage = _s(doc.get("coverage"))
    graph_limitations = doc.get("limitations") if isinstance(doc.get("limitations"), list) else []

    id_map: dict[str, str] = {}
    seen_ids: set[str] = set()

    # ---- pass 1: emit a node per REA entity ---------------------------------
    for node in raw_nodes:
        if not isinstance(node, dict):
            continue
        raw_id = _s(node.get("id") or node.get("node_id"))
        if not raw_id:
            continue
        nid = _rea_node_id(raw_id)
        id_map[raw_id] = nid
        if nid in seen_ids:
            continue
        seen_ids.add(nid)
        kind = _node_kind(node)
        state = _epistemic_state(node)
        meta: dict[str, Any] = {
            "rea_kind": kind,
            "rea_id": raw_id,
            "rea_epistemic_state": state or "unknown",
        }
        authorities = [
            _s(o.get("authority")) for o in (node.get("observations") or [])
            if isinstance(o, dict) and _s(o.get("authority"))
        ]
        if authorities:
            meta["rea_authorities"] = sorted(set(authorities))
        if raw_id in root_ids:
            meta["rea_root"] = True
            if graph_coverage:
                meta["rea_coverage"] = graph_coverage
            if graph_limitations:
                meta["rea_limitations"] = graph_limitations
        nodes.append({
            "id": nid,
            "label": _node_label(node, kind, raw_id),
            "file_type": _file_type(kind),
            "source_file": host,
            "source_location": "",
            "metadata": sanitize_metadata(meta),
        })

    # ---- pass 2: emit edges, minting external stubs so none dangle ----------
    seen_edges: set[tuple[str, str, str]] = set()
    for edge in raw_edges if isinstance(raw_edges, list) else []:
        if not isinstance(edge, dict):
            continue
        raw_src, raw_tgt = _edge_endpoints(edge)
        rea_rel = _s(edge.get("relation") or edge.get("kind"))
        if not raw_src or not raw_tgt or not rea_rel:
            continue
        state = _epistemic_state(edge)
        if state == "unavailable":
            continue  # an unavailable fact is not a relationship
        src = id_map.get(raw_src)
        tgt = id_map.get(raw_tgt)
        # Endpoint-safety: mint a stub for an endpoint REA referenced but did not
        # list as a node, so build_from_json keeps the edge.
        for raw_ep, resolved in ((raw_src, src), (raw_tgt, tgt)):
            if resolved is None:
                stub = _rea_node_id(raw_ep)
                id_map[raw_ep] = stub
                if stub not in seen_ids:
                    seen_ids.add(stub)
                    nodes.append({
                        "id": stub,
                        "label": raw_ep.rsplit("_", 1)[-1] or raw_ep,
                        "file_type": "code",
                        "source_file": "",
                        "source_location": "",
                        "metadata": sanitize_metadata({"rea_external": True, "rea_id": raw_ep}),
                    })
        src = id_map[raw_src]
        tgt = id_map[raw_tgt]
        if src == tgt:
            continue  # REA rejects self-edges; don't fabricate one
        relation = _REA_RELATION_MAP.get(rea_rel.lower(), "references")
        key = (src, tgt, relation)
        if key in seen_edges:
            continue
        seen_edges.add(key)
        confidence, score = _confidence(edge, state)
        edges.append({
            "source": src,
            "target": tgt,
            "relation": relation,
            "confidence": confidence,
            "confidence_score": score,
            "source_file": host,
            "source_location": "",
            "weight": 1.0,
            "context": f"rea:{rea_rel}",
            "metadata": sanitize_metadata({
                "rea_relation": rea_rel,
                "rea_epistemic_state": state or "unknown",
            }),
        })

    return {"nodes": nodes, "edges": edges}
