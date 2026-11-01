"""Optional source-relationship storage, independent of resolution authority.

Legacy graphs retain their simple projection. A typed local-function fact needs
both containment and calls on one pair; this profile stores logical arcs by
direction and relation without treating their storage keys as source evidence.
"""
from __future__ import annotations

import base64
import binascii
from collections.abc import Mapping
import hashlib
import json
import math
import re
from typing import TypeGuard

import networkx as nx
from graphify.graph_direction import logical_endpoints as accepted_endpoints
from graphify.source_relationship_evidence import validate_observations, validate_parent_cohort, validate_transport_cohort

FIELD = "graphify_source_relationships"
_CONTRACT = {"contract_version": 1}
_SPAN = ("start_byte", "end_byte", "start_row", "end_row", "start_column", "end_column")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


def _span(value):
    return (isinstance(value, dict) and set(value) == set(_SPAN)
            and all(type(value[key]) is int and value[key] >= 0 for key in _SPAN)
            and value["start_byte"] < value["end_byte"]
            and (value["start_row"], value["start_column"]) <= (value["end_row"], value["end_column"]))


def _local_fact(node):
    metadata = node.get("metadata")
    if not isinstance(metadata, dict) or "csharp_local_function" not in metadata:
        return False
    fact = metadata["csharp_local_function"]
    # This only admits a storage profile, never a callable/global/native target.
    # Reject a promised but malformed transport instead of silently collapsing it.
    valid = (isinstance(fact, dict) and type(fact.get("contract_version")) is int
             and fact.get("contract_version") == 1 and node.get("_callable") is True
             and not node.get("is_class") and not node.get("_callable_class")
             and isinstance(node.get("source_file"), str) and bool(node["source_file"])
             and isinstance(fact.get("role"), str) and fact["role"] in {"definition", "declaration"}
             and all(type(fact.get(key)) is bool for key in ("conditional", "ambiguous", "partial"))
             and type(fact.get("type_arity")) is int and fact["type_arity"] >= 0
             and all(isinstance(fact.get(key), str) and _DIGEST.fullmatch(fact[key])
                     for key in ("signature", "scope_fingerprint"))
             and _span(fact.get("span")) and _span(fact.get("scope_span")))
    if valid:
        span, scope = fact["span"], fact["scope_span"]
        valid = (scope["start_byte"] <= span["start_byte"] < span["end_byte"] <= scope["end_byte"]
                 and (scope["start_row"], scope["start_column"]) <= (span["start_row"], span["start_column"])
                 and (span["end_row"], span["end_column"]) <= (scope["end_row"], scope["end_column"])
                 and node.get("source_location") == f"L{span['start_row'] + 1}")
    raw = fact.get("raw_name_b64") if isinstance(fact, dict) else None
    if valid and fact.get("name_status") == "available" and isinstance(raw, str) and len(raw) <= 512:
        try:
            decoded = base64.b64decode(raw, validate=True)
            valid = 0 < len(decoded) <= 384 and bool(decoded.decode("utf-8"))
        except (ValueError, binascii.Error, UnicodeError):
            valid = False
    else:
        valid = valid and fact.get("name_status") == "oversize" and raw == ""
    if not valid:
        raise ValueError("SOURCE_RELATIONSHIPS_INVALID: invalid C# local-function source relationship contract")
    return True


def source_profile(nodes, graph_metadata=None):
    """Validate typed activation or the persisted storage-only marker."""
    # Inspect the envelope before iteration only when storage is promised.
    # Otherwise preserve successful legacy empty carriers and skipped records;
    # a genuine typed peer makes those recorded shape errors reject below.
    promised = isinstance(graph_metadata, dict) and FIELD in graph_metadata
    invalid_collection = isinstance(nodes, (Mapping, str, bytes, bytearray))
    if promised and invalid_collection:
        raise ValueError("SOURCE_RELATIONSHIPS_INVALID: invalid node collection")
    try:
        records = iter(nodes)
    except TypeError as error:
        if promised:
            raise ValueError("SOURCE_RELATIONSHIPS_INVALID: invalid node collection") from error
        raise
    # Visit all promised facts even after activation; a valid peer cannot mask
    # malformed metadata or records. Invalid tuples still expose their existing
    # attribute slot, so its typed promise cannot disappear as legacy absence.
    typed = invalid_records = False
    for item in records:
        if isinstance(item, tuple):
            invalid_records |= len(item) != 2
            node = item[1] if len(item) > 1 else None
        else:
            node = item
        if isinstance(node, dict):
            typed = _local_fact(node) or typed
        else:
            invalid_records = True
    # Legacy falsy carriers represented absence before this optional contract.
    # A typed promise still requires a valid carrier before mutable adoption.
    if graph_metadata is not None and not isinstance(graph_metadata, dict):
        if typed or graph_metadata:
            raise ValueError("SOURCE_RELATIONSHIPS_INVALID: invalid graph metadata")
        return False
    metadata = graph_metadata or {}
    marker = metadata.get(FIELD)
    if FIELD in metadata and (not isinstance(marker, dict) or marker != _CONTRACT
                              or type(marker.get("contract_version")) is not int):
        raise ValueError("SOURCE_RELATIONSHIPS_INVALID: invalid source relationship storage profile")
    if (marker is not None or typed) and (invalid_collection or invalid_records):
        raise ValueError("SOURCE_RELATIONSHIPS_INVALID: invalid node collection")
    return marker is not None or typed


def make_source_graph(nodes=(), *, directed=False, graph_metadata=None):
    """Choose storage once at assembly, retaining the ordinary legacy classes."""
    profile = source_profile(nodes, graph_metadata)
    graph = (nx.MultiDiGraph() if directed else nx.MultiGraph()) if profile else (nx.DiGraph() if directed else nx.Graph())
    graph.graph.update(graph_metadata or {})
    if profile:
        graph.graph[FIELD] = dict(_CONTRACT)
    return graph


def source_identity_ids(nodes):
    """Keep typed source identities out of label-only semantic ghost matching."""
    return frozenset(identity for identity, attributes in nodes if _local_fact(attributes))


def is_source_graph(graph: nx.Graph) -> TypeGuard[nx.MultiGraph | nx.MultiDiGraph]:
    """Constant-time storage-mode query; callers validate transport at adoption."""
    marker = graph.graph.get(FIELD)
    return (graph.is_multigraph() and isinstance(marker, dict) and marker == _CONTRACT
            and type(marker.get("contract_version")) is int)


def logical_endpoints(graph, source, target, attributes):
    """Return logical direction, rejecting partial or foreign explicit markers."""
    pair = accepted_endpoints(source, target, attributes, directed=graph.is_directed())
    if pair is None:
        raise ValueError("SOURCE_RELATIONSHIPS_INVALID: invalid source relationship direction")
    return pair


def storage_key(source, target, relation):
    """A bounded identity key, recomputed after remapping; never resolution proof."""
    return hashlib.sha256(json.dumps([source, target, relation], ensure_ascii=True, separators=(",", ":")).encode()).hexdigest()


def merge_evidence(existing, incoming, *, rank, fold, evidence_keys):
    """Apply the existing simple-graph same-relation evidence precedence once."""
    old_rank, new_rank = rank.get(existing.get("confidence"), 0), rank.get(incoming.get("confidence"), 0)
    keep = old_rank > new_rank
    if old_rank == new_rank:
        keep |= bool(existing.get("source_location") and not incoming.get("source_location"))
        old_score, new_score = existing.get("confidence_score"), incoming.get("confidence_score")
        keep |= old_score is not None and new_score is not None and old_score > new_score
    if keep:
        fold(existing, incoming)
        return False
    fold(incoming, existing)
    for key in (*evidence_keys, "also_seen"):
        if key not in incoming:
            existing.pop(key, None)
    return True


def adopt_transport(data: dict) -> dict:
    """Validate source storage before NetworkX can collapse malformed links.

    Raw extraction writers can omit the profile marker; typed producer facts
    select it on adoption. An explicit persisted marker promises multigraph
    storage and cannot be silently repaired from a contradictory flag.
    """
    metadata = data.get("graph")
    if isinstance(metadata, dict) and FIELD in metadata and not isinstance(data.get("nodes", []), list):
        raise ValueError("SOURCE_RELATIONSHIPS_INVALID: invalid node collection")
    if not source_profile(data.get("nodes", ()), metadata):
        return data
    edges = validate_transport_cohort(data, identity=_identity)
    from graphify.extractors.cpp_type_references import validate_type_reference_transport
    validate_type_reference_transport(data, directed=data.get("directed", False))
    metadata = dict(data.get("graph") or {})
    if FIELD in metadata and data.get("multigraph") is not True:
        raise ValueError("SOURCE_RELATIONSHIPS_INVALID: source relationship profile requires multigraph storage")
    metadata[FIELD] = dict(_CONTRACT)
    links, seen, pairs = [], set(), set()
    for edge in edges:
        endpoints = (edge["source"], edge["target"])
        pair_key = endpoints if data.get("directed") else frozenset(endpoints)
        if data.get("multigraph") is False and pair_key in pairs:
            raise ValueError("SOURCE_RELATIONSHIPS_INVALID: parallel source links contradict simple storage")
        pairs.add(pair_key)
        pair = accepted_endpoints(edge["source"], edge["target"], edge, directed=bool(data.get("directed")))
        if pair is None:
            raise ValueError("SOURCE_RELATIONSHIPS_INVALID: invalid source relationship direction")
        identity = storage_key(*pair, edge.get("relation"))
        if identity in seen:
            raise ValueError("SOURCE_RELATIONSHIPS_INVALID: duplicate source relationship storage identity")
        seen.add(identity)
        links.append({**edge, "source": pair[0], "target": pair[1], "_src": pair[0], "_tgt": pair[1], "key": identity})
    result = dict(data, graph=metadata, links=links, multigraph=True)
    if "edges" in data:
        result["edges"] = links
    return result


def prepare_source_links(graph, original_links, *, add):
    """Compose one accepted logical arc per key before accounting or publication."""
    nodes = [{**data, "id": key} for key, data in graph.nodes(data=True)]
    current = [{**data, "source": source, "target": target} for source, target, data in graph.edges(data=True)]
    validate_parent_cohort(nodes, current, directed=graph.is_directed(), identity=_identity)
    identities = [storage_key(*logical_endpoints(graph, edge["source"], edge["target"], edge), edge["relation"]) for edge in current]
    if len(identities) != len(set(identities)):
        raise ValueError("SOURCE_RELATIONSHIPS_INVALID: duplicate source relationship storage identity")
    if original_links is None:
        return None
    if not isinstance(original_links, (list, tuple)):
        raise ValueError("SOURCE_RELATIONSHIPS_INVALID: invalid original source links")
    selected = list(original_links)
    validate_parent_cohort(nodes, selected, directed=graph.is_directed(), identity=_identity, allow_missing=True)
    return prepare_source_edges([edge for edge in selected if edge["source"] in graph and edge["target"] in graph],
                                directed=graph.is_directed(), add=add)


def validate_source_transport(data):
    """Autoactivation cannot hide malformed unused aliases or coerce mode flags."""
    if source_profile(data.get("nodes", ()), data.get("graph")):
        validate_transport_cohort(data, identity=_identity, raw=True)


def prepare_source_edges(edges, *, directed, add):
    """An explicit raw publisher composes observations before strict adoption."""
    if type(directed) is not bool:
        raise ValueError("SOURCE_RELATIONSHIPS_INVALID: invalid graph mode flag")
    graph = make_source_graph(directed=directed, graph_metadata={FIELD: dict(_CONTRACT)})
    for edge in edges:
        if (not isinstance(edge, dict) or not all(_identity(edge.get(key)) for key in ("source", "target"))
                or not isinstance(edge.get("relation"), str) or not edge["relation"].strip()):
            raise ValueError("SOURCE_RELATIONSHIPS_INVALID: invalid source relationship link")
        validate_observations([edge])
        add(graph, edge["source"], edge["target"], edge)
    return [{**data, "source": source, "target": target} for source, target, data in graph.edges(data=True)]


def inherit_source_profile(data, policy):
    """Retain accepted storage after its last activating declaration is removed."""
    if policy.get("source_profile"):
        source_profile(data.get("nodes", ()), data.get("graph"))
        data["graph"] = {**(data.get("graph") or {}), FIELD: dict(_CONTRACT)}
        data.setdefault("directed", policy["source_directed"])
        data.setdefault("multigraph", True)


def inherit_source_snapshot(data, previous):
    """Borrow only validated persisted storage intent from the caller's snapshot."""
    if previous is not None:
        accepted = adopt_transport(previous)
        inherit_source_profile(data, {"source_profile": source_profile(accepted.get("nodes", ()), accepted.get("graph")),
                                      "source_directed": accepted.get("directed", False)})


def _identity(value):
    """JSON scalar identities must not exploit Python bool/int/float coercion."""
    return (type(value) in (str, int, float) and value != ""
            and (type(value) is not float or math.isfinite(value)))


def canonicalize_keys(graph):
    """Rekey an adopted/remapped source graph without discarding logical arcs."""
    if not is_source_graph(graph):
        return graph
    edges = list(graph.edges(keys=True, data=True))
    for source, target, key, data in edges:
        src, tgt = logical_endpoints(graph, source, target, data)
        expected = storage_key(src, tgt, data.get("relation"))
        if key != expected:
            graph.remove_edge(source, target, key)
            if graph.has_edge(source, target, expected):
                raise ValueError("SOURCE_RELATIONSHIPS_INVALID: duplicate source relationship storage identity")
            graph.add_edge(src, tgt, key=expected, **{k: v for k, v in data.items() if k != "key"})
    return graph
