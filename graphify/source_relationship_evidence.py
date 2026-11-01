"""Complete observations of one source arc, without competing edge authority.

The parent owns endpoints, relation, direction and storage key. Secondary records
retain their own complete attributes; absent fields never borrow a primary fact.
Legacy non-source callers continue to use their existing four-field evidence.
"""
from __future__ import annotations

from copy import deepcopy
import json

from graphify.graph_direction import logical_endpoints

PARENT_FIELDS = frozenset({"source", "target", "from", "to", "relation", "key", "_src", "_tgt", "also_seen"})


def invalid_evidence():
    raise ValueError("SOURCE_RELATIONSHIPS_INVALID: invalid complete source observation") from None


def _record(value, *, secondary=False):
    """Clone one JSON record; nested lists cannot introduce another observation owner."""
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        invalid_evidence()
    if secondary and PARENT_FIELDS.intersection(value):
        invalid_evidence()
    result = {key: item for key, item in value.items() if key not in PARENT_FIELDS}
    try:
        json.dumps(result, sort_keys=True, ensure_ascii=True, allow_nan=False)
        return deepcopy(result)
    except (TypeError, ValueError, RecursionError):
        invalid_evidence()


def complete_records(attributes):
    """Read primary plus flat complete observations, validating before mutation."""
    primary = _record(attributes)
    also = attributes.get("also_seen", [])
    if not isinstance(also, list):
        invalid_evidence()
    return [primary, *(_record(record, secondary=True) for record in also)]


def fold_observations(winner, loser):
    """Preserve every distinct record while keeping the existing chosen primary."""
    rows = complete_records(winner) + complete_records(loser)
    own = json.dumps(rows[0], sort_keys=True, ensure_ascii=True)
    unique = {json.dumps(row, sort_keys=True, ensure_ascii=True): row for row in rows[1:] if row}
    unique.pop(own, None)
    if unique:
        winner["also_seen"] = [unique[key] for key in sorted(unique)]
    else:
        winner.pop("also_seen", None)


def preserve_execution_observations(existing, incoming, *, execute):
    """Keep original import observations when the existing aggregate clears type_only."""
    originals = (deepcopy(existing), deepcopy(incoming)) if bool(existing.get("type_only")) != bool(incoming.get("type_only")) else None
    execute(existing, incoming)
    if originals is not None:
        fold_observations(existing, originals[0])
        fold_observations(incoming, originals[1])


def validate_observations(edges):
    """The selected source-profile owner validates even unpromised observations."""
    for edge in edges:
        complete_records(edge)


def observation_edges(edge):
    """Expose independent fact promises with only the parent's actual arc fields.

    Unpromised legacy also_seen shape keeps its old owner. Source-profile callers
    additionally run strict complete_records validation before adoption. No
    primary metadata/confidence/source is inherited by a secondary record.
    """
    yield edge
    if not isinstance(edge, dict) or not isinstance(edge.get("also_seen"), list):
        return
    parent = {key: edge[key] for key in ("source", "target", "relation", "_src", "_tgt") if key in edge}
    for record in edge["also_seen"]:
        if not isinstance(record, dict):
            continue
        if PARENT_FIELDS.intersection(record):
            invalid_evidence()
        yield {**parent, **record}


def validate_parent_cohort(nodes, edges, *, directed, identity, unique_nodes=True, allow_missing=False):
    """Validate original parent types/roles before filtering, composition or mutation."""
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise ValueError("SOURCE_RELATIONSHIPS_INVALID: invalid node/link collection")
    ids = {}
    for node in nodes:
        value = node.get("id") if isinstance(node, dict) else None
        if not identity(value) or value in ids and (unique_nodes or ids[value] is not type(value)):
            raise ValueError("SOURCE_RELATIONSHIPS_INVALID: invalid or duplicate node identity")
        ids[value] = type(value)
    for edge in edges:
        if (not isinstance(edge, dict) or not all(identity(edge.get(key)) for key in ("source", "target"))
                or not isinstance(edge.get("relation"), str) or not edge["relation"].strip()):
            raise ValueError("SOURCE_RELATIONSHIPS_INVALID: invalid source relationship link")
        for key in ("source", "target"):
            if edge[key] in ids:
                valid = ids[edge[key]] is type(edge[key])
            else:
                valid = allow_missing
            if not valid:
                raise ValueError("SOURCE_RELATIONSHIPS_INVALID: invalid source relationship link")
        if logical_endpoints(edge["source"], edge["target"], edge, directed=directed) is None:
            raise ValueError("SOURCE_RELATIONSHIPS_INVALID: invalid source relationship direction")
        complete_records(edge)


def validate_transport_cohort(data, *, identity, raw=False):
    """Source-only aliases/modes share the same untouched parent-cohort preflight."""
    for key in ("directed", "multigraph"):
        if key in data and type(data[key]) is not bool:
            raise ValueError("SOURCE_RELATIONSHIPS_INVALID: invalid graph mode flag")
    aliases = [data[key] for key in ("edges", "links") if key in data]
    if not aliases:
        aliases = [[]]
    for edges in aliases:
        validate_parent_cohort(data.get("nodes", []), edges, directed=data.get("directed", False),
                               identity=identity, unique_nodes=not raw, allow_missing=raw)
    if len(aliases) == 2:
        try:
            equal = len(aliases[0]) == len(aliases[1]) and all(
                json.dumps(a, sort_keys=True, allow_nan=False) == json.dumps(b, sort_keys=True, allow_nan=False)
                for a, b in zip(*aliases))
        except (TypeError, ValueError, RecursionError):
            equal = False
        if not equal:
            raise ValueError("SOURCE_RELATIONSHIPS_INVALID: conflicting link collection aliases")
    return data.get("links", data.get("edges", []))
