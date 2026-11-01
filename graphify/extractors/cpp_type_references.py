"""Keep a source-local C++ lookup rejection on its reference, not its stub.

The dual promise survives generic identity rewriting and graph publication. It
only forbids a guessed target; it grants no type, owner, callable or native proof.
All readers validate a complete supplied cohort before their caller mutates it.
"""
from __future__ import annotations

import base64
import binascii
from collections import Counter
import json
import re
from typing import NoReturn

from graphify.graph_direction import logical_endpoints
from graphify.source_relationship_evidence import observation_edges

FIELD = "cpp_type_reference"
VERSION = "cpp_type_reference_version"
_SPAN = {"start_byte", "end_byte", "start_row", "end_row", "start_column", "end_column"}
_FIELDS = {"contract_version", "resolution", "raw_name_b64", "lexical_scope_b64", "scope_complete", "type_span",
           "lookup_b64", "lookup_complete"}


def invalid_type_reference_context() -> NoReturn:
    """One safe failure is shared by source allocation and transport validation."""
    raise ValueError("CPP_REFERENCE_CONTEXT_INVALID: invalid C++ reference context; re-extract or repair and retry") from None


def _name(value, *, rooted=False):
    return (isinstance(value, str) and bool(value)
            and all(part.isidentifier() for part in (value.removeprefix("::") if rooted else value).split("::")))


def _decode(value, *, rooted=False, allow_empty=False, opaque=False):
    if not isinstance(value, str) or (not value and not allow_empty) or len(value) > 512:
        invalid_type_reference_context()
    try:
        raw = base64.b64decode(value, validate=True)
        text = raw.decode("utf-8")
    except (ValueError, binascii.Error, UnicodeError):
        invalid_type_reference_context()
    if (not (0 if allow_empty else 1) <= len(raw) <= 384 or base64.b64encode(raw).decode("ascii") != value
            or not opaque and not (allow_empty and not text) and not _name(text, rooted=rooted)):
        invalid_type_reference_context()
    return text


def _span(value):
    return (isinstance(value, dict) and set(value) == _SPAN
            and all(type(value[key]) is int and value[key] >= 0 for key in _SPAN)
            and value["start_byte"] < value["end_byte"]
            and (value["start_row"], value["start_column"]) < (value["end_row"], value["end_column"])
            and (value["start_row"] != value["end_row"]
                 or value["end_byte"] - value["start_byte"] == value["end_column"] - value["start_column"]))


def make_type_reference(name, scope, syntax, source, *, lookup=None):
    """Encode an already-proved rejection using original, already-read bytes.

    The producer owns lookup and syntax selection. A type context can contain a
    template, so its span is not represented as an exact leaf-token span.
    """
    if (not _name(name, rooted=True) or len(name.encode("utf-8")) > 384
            or not (scope == "" or _name(scope)) or not isinstance(source, bytes)):
        invalid_type_reference_context()
    start, end = getattr(syntax, "start_byte", None), getattr(syntax, "end_byte", None)
    if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(source):
        invalid_type_reference_context()
    written = name if lookup is None else lookup
    if not isinstance(written, str) or not written:
        invalid_type_reference_context()
    try:
        written_bytes = written.encode("utf-8")
    except UnicodeError:
        invalid_type_reference_context()
    span = {"start_byte": start, "end_byte": end,
            "start_row": source.count(b"\n", 0, start), "end_row": source.count(b"\n", 0, end),
            "start_column": start - source.rfind(b"\n", 0, start) - 1,
            "end_column": end - source.rfind(b"\n", 0, end) - 1}
    complete = len(scope.encode("utf-8")) <= 384
    lookup_complete = len(written_bytes) <= 384
    return {"contract_version": 1, "resolution": "unavailable",
            "raw_name_b64": base64.b64encode(name.encode("utf-8")).decode("ascii"),
            "lexical_scope_b64": base64.b64encode(scope.encode("utf-8")).decode("ascii") if complete else None,
            "scope_complete": complete, "type_span": span, "lookup_complete": lookup_complete,
            "lookup_b64": base64.b64encode(written_bytes).decode("ascii") if lookup_complete else None}


def _fact(edge):
    if not isinstance(edge, dict):
        return None
    metadata = edge.get("metadata")
    nested = isinstance(metadata, dict) and FIELD in metadata
    marked = VERSION in edge
    if not nested and not marked:
        return None
    if (not isinstance(metadata, dict) or not nested or not marked
            or type(edge[VERSION]) is not int or edge[VERSION] != 1):
        invalid_type_reference_context()
    fact = metadata[FIELD]
    if (not isinstance(fact, dict) or set(fact) != _FIELDS
            or type(fact.get("contract_version")) is not int or fact["contract_version"] != 1
            or fact.get("resolution") != "unavailable" or type(fact.get("scope_complete")) is not bool
            or type(fact.get("lookup_complete")) is not bool
            or not _span(fact.get("type_span"))):
        invalid_type_reference_context()
    _decode(fact["raw_name_b64"], rooted=True)
    if fact["scope_complete"]:
        _decode(fact["lexical_scope_b64"], allow_empty=True)
    elif fact["lexical_scope_b64"] is not None:
        invalid_type_reference_context()
    if fact["lookup_complete"]:
        _decode(fact["lookup_b64"], opaque=True)
    elif fact["lookup_b64"] is not None:
        invalid_type_reference_context()
    if (not isinstance(edge.get("relation"), str) or edge["relation"] not in {"references", "inherits"}
            or edge.get("confidence") != "EXTRACTED"
            or not isinstance(edge.get("source_file"), str) or not edge["source_file"]
            or not isinstance(edge.get("source_location"), str)
            or re.fullmatch(r"L[0-9]{1,12}", edge["source_location"]) is None
            or not 1 <= int(edge["source_location"][1:]) <= fact["type_span"]["start_row"] + 1):
        invalid_type_reference_context()
    return fact


def is_type_reference_unavailable(edge):
    """Read only a typed rejection; absence retains legacy reconciliation."""
    if not _promises(edge):
        return False
    facts = [_fact(row) for row in observation_edges(edge)]
    return any(fact is not None for fact in facts)


def _promises(value):
    """Inspect only the reserved edge slots, without interpreting unrelated data."""
    def edge_promises(edge):
        rows = [edge, *edge.get("also_seen", [])] if isinstance(edge, dict) and isinstance(edge.get("also_seen"), list) else [edge]
        return any(isinstance(row, dict) and (VERSION in row
                   or isinstance(row.get("metadata"), dict) and FIELD in row["metadata"]) for row in rows)
    return (any(edge_promises(edge) for edge in value) if isinstance(value, (list, tuple))
            else edge_promises(value))


def _secondary_profile(nodes, edges, metadata):
    """Unsupported legacy evidence cannot silently erase a recognized promise."""
    if isinstance(edges, (list, tuple)) and any(isinstance(edge, dict)
            and isinstance(edge.get("also_seen"), list) and any(_promises(row) for row in edge["also_seen"])
            for edge in edges):
        from graphify.source_relationships import source_profile
        if not source_profile(nodes, metadata):
            invalid_type_reference_context()


def validate_type_reference_transport(payload, *, directed=False):
    """Validate typed raw mode/alias choices before a consumer can select one.

    Both aliases must carry exactly the same ordered evidence, including the
    rejection. Compare individual JSON records to keep memory bounded by one
    edge rather than copying a complete graph. This is not a reconciliation or
    a mode policy for graphs with no C++ rejection promise.
    """
    if not isinstance(payload, dict) or not any(_promises(payload.get(key)) for key in ("edges", "links")):
        return False
    for key in ("edges", "links"):
        _secondary_profile(payload.get("nodes", ()), payload.get(key), payload.get("graph"))
    if type(directed) is not bool or any(key in payload and type(payload[key]) is not bool
                                        for key in ("directed", "multigraph")):
        invalid_type_reference_context()
    for key in ("edges", "links"):
        if key in payload:
            validate_type_references(payload.get("nodes"), payload[key], directed=directed)
    if "edges" in payload and "links" in payload:
        left, right = payload["edges"], payload["links"]
        if type(left) is not type(right) or not isinstance(left, (list, tuple)) or len(left) != len(right):
            invalid_type_reference_context()
        try:
            for first, second in zip(left, right):
                if json.dumps(first, sort_keys=True, ensure_ascii=True, allow_nan=False) != json.dumps(
                        second, sort_keys=True, ensure_ascii=True, allow_nan=False):
                    invalid_type_reference_context()
        except (TypeError, ValueError, RecursionError):
            invalid_type_reference_context()
    return True


def validate_type_references(nodes, edges, *, directed=False):
    """Preflight all promises and their real endpoints without repairing input.

    Legacy unpromised collections keep their old compatibility behavior. Only
    promised endpoints need an index; unrelated malformed legacy facts stay with
    their existing owner rather than becoming a new global schema restriction.
    """
    if not isinstance(edges, (list, tuple)):
        if isinstance(edges, dict) and (VERSION in edges
                or isinstance(edges.get("metadata"), dict) and FIELD in edges["metadata"]):
            invalid_type_reference_context()
        return
    promised = []
    for edge in edges:
        if _promises(edge):
            for row in observation_edges(edge):
                fact = _fact(row)
                if fact is not None:
                    promised.append((row, fact))
    if not promised:
        return
    if not isinstance(nodes, (list, tuple)):
        invalid_type_reference_context()
    needed, pairs = set(), []
    for edge, fact in promised:
        source, target = edge.get("source"), edge.get("target")
        if not all(isinstance(value, str) and value for value in (source, target)):
            invalid_type_reference_context()
        pair = logical_endpoints(source, target, edge, directed=directed)
        if pair is None or pair[0] == pair[1]:
            invalid_type_reference_context()
        needed.update(pair)
        pairs.append((pair, fact, edge))
    by_id, counts = {}, Counter()
    for node in nodes:
        identity = node.get("id") if isinstance(node, dict) else None
        if isinstance(identity, str) and identity in needed:
            by_id[identity] = node
            counts[identity] += 1
    for (source, target), fact, edge in pairs:
        if counts[source] != 1 or counts[target] != 1:
            invalid_type_reference_context()
        owner, stub = by_id[source], by_id[target]
        name = _decode(fact["raw_name_b64"], rooted=True)
        if (not isinstance(owner.get("source_file"), str) or not owner["source_file"]
                or edge["source_file"] != owner["source_file"]
                or stub.get("source_file") != "" or stub.get("source_location") != ""
                or stub.get("file_type") != "code" or stub.get("external")
                or stub.get("_callable") or stub.get("_callable_class")
                or not isinstance(stub.get("label"), str)
                or stub.get("label") not in {name, name.removeprefix("::"), name.rsplit("::", 1)[-1]}):
            invalid_type_reference_context()


def validate_type_reference_graph(graph):
    """Use actual graph identities and accepted logical direction, never iteration order."""
    if not any(_promises(data) for _, _, data in graph.edges(data=True)):
        return
    edges = [{**data, "source": source, "target": target}
             for source, target, data in graph.edges(data=True)]
    nodes = [{**data, "id": identity} for identity, data in graph.nodes(data=True)]
    _secondary_profile(nodes, edges, graph.graph)
    validate_type_references(nodes, edges, directed=graph.is_directed())


def validate_type_reference_export(graph, original_links=None):
    """A raw override must retain every restriction already known by the graph.

    Ordinary simple storage can fold several source observations into one arc.
    Required proof inclusion preserves that retained observation while allowing
    the writer's existing restoration of extra original parallel evidence.
    """
    validate_type_reference_graph(graph)
    if original_links is None:
        return
    known = any(_promises(data) for _, _, data in graph.edges(data=True))
    if not known and not _promises(original_links):
        return
    nodes = [{**data, "id": identity} for identity, data in graph.nodes(data=True)]
    _secondary_profile(nodes, original_links, graph.graph)
    validate_type_references(nodes, original_links, directed=graph.is_directed())
    if not isinstance(original_links, (list, tuple)):
        invalid_type_reference_context()

    def claims(edges):
        result = Counter()
        for source, target, edge in edges:
            if not _promises(edge):
                continue
            pair = logical_endpoints(source, target, edge, directed=graph.is_directed())
            if pair is None:
                invalid_type_reference_context()
            for row in observation_edges(edge):
                fact = _fact(row)
                if fact is not None:
                    key = json.dumps([pair, row["relation"], row["confidence"], row["source_file"],
                                      row["source_location"], fact], sort_keys=True, ensure_ascii=True)
                    result[key] += 1
        return result

    required = claims(graph.edges(data=True))
    supplied = claims((edge.get("source"), edge.get("target"), edge)
                      for edge in original_links if isinstance(edge, dict))
    if required - supplied:
        invalid_type_reference_context()
