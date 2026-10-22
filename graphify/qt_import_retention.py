"""Graph-owned restrictions on retiring imports with unproved source ownership.

This pure policy never resolves a symbol or authorizes deletion. Callers validate
transport before legacy inference, then carry its immutable IDs through their
existing graph publication. The canonical placeholder predicate remains injected
from its build owner; neither corpus reads nor another state store is introduced.
"""
from __future__ import annotations

from collections import Counter
from pathlib import PurePosixPath

from graphify.ids import normalize_id
from graphify.qt_incremental import QT_CPP_SUFFIXES

FIELD = "qt_import_retention"
MAX_IDS = 100_000
MAX_ID_BYTES = 4096


def _invalid():
    raise ValueError("QT_IMPORT_RETENTION_INVALID: invalid graph cleanup context; restore a valid graph and retry")


def _identity(value):
    if not isinstance(value, str) or not value or normalize_id(value) != value:
        _invalid()
    try:
        if len(value.encode("utf-8")) > MAX_ID_BYTES:
            _invalid()
    except UnicodeError:
        _invalid()


def _graph(payload):
    # The reserved field has exactly one node-link location. A misspelled slot
    # must not disappear during a builder's ordinary top-level projection.
    if FIELD in payload:
        _invalid()
    # Retain the established falsy-absence convention for legacy metadata;
    # none of those values carries a reserved field or grants cleanup authority.
    graph = payload.get("graph") or {}
    if not isinstance(graph, dict):
        _invalid()
    return graph


def _node_index(payload):
    nodes = payload.get("nodes", [])
    if not isinstance(nodes, list):
        _invalid()
    index, counts = {}, Counter()
    for node in nodes:
        if isinstance(node, dict) and isinstance(node.get("id"), str):
            counts[node["id"]] += 1
            index[node["id"]] = node
    return index, counts


def read_import_retention(payload, *, is_placeholder) -> frozenset[str]:
    """Strictly validate a transported node-link graph before inference/mutation.

    A context pointing at an absent, duplicate or noncanonical input node is
    corrupt transport. Only a subsequent accepted producer transition may clear
    a formerly valid restriction when its node disappears or changes role.
    """
    graph = _graph(payload)
    if FIELD not in graph:
        return frozenset()
    context = graph[FIELD]
    if (not isinstance(context, dict) or context.keys() != {"schema", "ids"}
            or type(context["schema"]) is not int or context["schema"] != 1):
        _invalid()
    values = context["ids"]
    if not isinstance(values, list) or len(values) > MAX_IDS:
        _invalid()
    for value in values:
        _identity(value)
    if values != sorted(set(values)):
        _invalid()
    index, counts = _node_index(payload)
    if any(counts[value] != 1 or not is_placeholder(index[value]) for value in values):
        _invalid()
    return frozenset(values)


def apply_import_retention(payload, ids, *, is_placeholder) -> dict:
    """Return a detached policy view after an accepted producer transformation.

    Nodes/edges remain borrowed read-only. The returned payload, graph attributes,
    schema dictionary and ID list are independent. Transport callers must first
    use the strict reader; this producer filter is not a corrupted-input repair.
    """
    values = frozenset(ids)
    if len(values) > MAX_IDS:
        _invalid()
    for value in values:
        _identity(value)
    index, counts = _node_index(payload)
    if any(counts[value] > 1 for value in values):
        _invalid()
    retained = sorted(value for value in values if counts[value] == 1 and is_placeholder(index[value]))
    result, graph = dict(payload), dict(_graph(payload))
    graph.pop(FIELD, None)
    if retained:
        graph[FIELD] = {"schema": 1, "ids": retained}
    if graph:
        result["graph"] = graph
    else:
        result.pop("graph", None)
    return result


def plan_import_retention(prior, *, accepted_import_ids=(), is_placeholder) -> frozenset[str]:
    """Restrict cleanup of raw native-source incident placeholders lacking proof.

    Raw edge incidence and source-backed native roles only justify preservation;
    malformed logical orientation or import provenance never becomes deletion or
    provider evidence. Previously stored IDs keep this restriction after the last
    native source disappears. Unrelated generic legacy orphans still heal.
    """
    retained = set(read_import_retention(prior, is_placeholder=is_placeholder))
    index, counts = _node_index(prior)
    native = {identity for identity, node in index.items()
              if isinstance(node.get("source_file"), str) and node["source_file"]
              and node.get("file_type") == "code" and not node.get("external")
              and PurePosixPath(node["source_file"].replace("\\", "/")).suffix.lower() in QT_CPP_SUFFIXES}
    edges = prior.get("links", prior.get("edges", []))
    if not isinstance(edges, list):
        _invalid()
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        source, target = edge.get("source"), edge.get("target")
        for owner, candidate in ((source, target), (target, source)):
            if not isinstance(owner, str) or not isinstance(candidate, str) or owner not in native:
                continue
            node = index.get(candidate)
            if node is not None and is_placeholder(node):
                if counts[candidate] != 1:
                    _invalid()
                _identity(candidate)
                retained.add(candidate)
    retained.difference_update(accepted_import_ids)
    if len(retained) > MAX_IDS:
        _invalid()
    return frozenset(retained)


def node_link_view(graph):
    """Expose actual NetworkX identities to the same strict node-link policy."""
    return {"graph": graph.graph, "nodes": [{**data, "id": identity}
                                            for identity, data in graph.nodes(data=True)]}
