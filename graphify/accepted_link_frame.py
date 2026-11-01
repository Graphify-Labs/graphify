"""Adopt the builder's accepted publication frame without a second resolver.

One instance belongs to one build invocation. It remembers borrowed mutable
containers, stages complete accepted records before storage folding, and adopts
them only after the owning builder's final validations succeed.
"""
from __future__ import annotations

from collections import deque
from copy import deepcopy

from graphify.graph_direction import logical_endpoints
from graphify.source_relationships import FIELD, source_profile, storage_key

BUILD_PROJECTION_VERSION = 4


class AcceptedLinkFrame:
    """Keep caller-owned lists/dicts coherent across existing compatibility copies."""

    def __init__(self, raw: dict):
        self.owner = raw
        self.primary = "edges" if "edges" in raw else "links"
        values = raw.get(self.primary)
        self.original = list(values) if isinstance(values, list) else None
        self.aliases = {}
        self.positions = {}
        self.accepted = {}
        self.source = source_profile(raw.get("nodes", ()), raw.get("graph"))
        self.explicit_profile = (self.source and isinstance(raw.get("graph"), dict)
                                 and FIELD in raw["graph"])
        if self.original is None:
            return
        # A conflicting ordinary legacy view remains independent. Source-mode
        # aliases were already checked by the builder's transport preflight.
        for name in ("edges", "links"):
            candidate = raw.get(name)
            if isinstance(candidate, list) and (candidate is values or self.source or candidate == values):
                self.aliases[name] = (candidate, list(candidate))

    def bind(self, working: dict) -> None:
        """Bind ordered adapter copies before any normalization can remove rows."""
        if self.original is None:
            return
        rows = working.get("edges", working.get("links", []))
        if len(rows) != len(self.original):
            raise ValueError("SOURCE_RELATIONSHIPS_INVALID: caller frame lost edge correspondence")
        for index, edge in enumerate(rows):
            self.positions.setdefault(id(edge), []).append(index)

    @staticmethod
    def seed_external_targets(graph, edges, node_ids, normalized, *, normalize, mint, prepare, admit, relations) -> None:
        """Admit each import once when its exact source gains existing authority.

        A source-indexed queue closes the complete import cohort without an
        input-order dependency or repeated corpus scans. The existing builder
        supplies preparation/admission; call-only facts and unanchored cycles
        cannot mint targets (#3156), and rejected imports enqueue nothing.
        """
        pending = {}
        for position, edge in enumerate(edges):
            if not isinstance(edge, dict) or edge.get("relation") not in relations:
                continue
            if not (("source" in edge or "from" in edge) and ("target" in edge or "to" in edge)):
                continue
            source, target = edge.get("source", edge.get("from")), edge.get("target", edge.get("to"))
            try:
                hash(source)
                hash(target)
            except TypeError:
                continue
            if source not in node_ids and isinstance(source, str):
                source = normalized.get(normalize(source), source)
            if isinstance(target, str) and target not in node_ids:
                target = normalized.get(normalize(target), target)
            if isinstance(target, str):
                pending.setdefault(source, []).append((str(target), str(edge.get("relation")), position, edge, target))
        queue, visited = deque(sorted(node_ids, key=str)), set()
        while queue:
            source = queue.popleft()
            if source in visited:
                continue
            visited.add(source)
            for _, _, _, edge, target in sorted(pending.get(source, ()), key=lambda row: row[:3]):
                if target in node_ids:
                    continue
                mint(graph, node_ids, target)
                try:
                    attributes = prepare(edge, source, target)
                    accepted = admit(source, target, attributes)
                except Exception:
                    graph.remove_node(target)
                    node_ids.discard(target)
                    raise
                if accepted:
                    queue.append(target)
                else:
                    graph.remove_node(target)
                    node_ids.discard(target)

    def accept(self, edge: dict, source, target, attributes: dict, *,
               directed: bool, already_logical: bool = False) -> None:
        """Capture before graph composition; peers keep their own full attributes."""
        if self.original is None:
            return
        choices = self.positions.get(id(edge), ())
        position = next((item for item in choices if item not in self.accepted), None)
        if position is None:
            raise ValueError("SOURCE_RELATIONSHIPS_INVALID: accepted edge lost caller correspondence")
        record = {**deepcopy(attributes), "source": source, "target": target}
        # Storage-only direction and inferred provenance must not expand an
        # ordinary caller's schema merely through source autoactivation. Explicit
        # persisted profiles stay canonical; present fields retain owning repairs.
        if not self.explicit_profile:
            for name in ("_src", "_tgt", "source_file"):
                if name not in edge:
                    record.pop(name, None)
        # Existing legacy exporter rejection must not be bypassed by repairing
        # an invalid explicit pair. Valid pairs follow accepted ID conversion.
        if "_src" in edge or "_tgt" in edge:
            old_source, old_target = edge.get("source"), edge.get("target")
            pair = logical_endpoints(old_source, old_target, edge, directed=directed)
            if pair is None:
                for name in ("_src", "_tgt"):
                    if name in edge:
                        record[name] = deepcopy(edge[name])
                    else:
                        record.pop(name, None)
            else:
                # The builder alone vouches that its arguments already use
                # this validated logical basis; preserve raw physical direction.
                basis = pair if already_logical else (old_source, old_target)
                converted = {basis[0]: source, basis[1]: target}
                if already_logical:
                    record["source"], record["target"] = converted[old_source], converted[old_target]
                record["_src"], record["_tgt"] = converted[pair[0]], converted[pair[1]]
        for name, value in (("from", record["source"]), ("to", record["target"])):
            if name in record:
                record[name] = value
        if self.source and "key" in record:
            pair = logical_endpoints(record["source"], record["target"], record, directed=directed)
            if pair is None:
                raise ValueError("SOURCE_RELATIONSHIPS_INVALID: accepted edge lost logical direction")
            record["key"] = storage_key(*pair, record["relation"])
        self.accepted[position] = record

    def commit(self, working: dict, *, directed: bool, validate=None) -> None:
        """Validate the detached projection before new caller-frame mutations.

        Earlier legacy builder repairs retain their existing mutation behavior;
        this step does not claim transactional rollback of those older repairs.
        """
        if self.original is None:
            return
        ordered = sorted(self.accepted)
        records = [self.accepted[index] for index in ordered]
        candidate = dict(working, edges=records)
        if "links" in candidate:
            candidate["links"] = records
        if validate is not None:
            validate(candidate, directed=directed)
        # Compute every replacement before touching borrowed dictionaries. A
        # shared alias has one authoritative owner, while held list references
        # still receive the same accepted content in place.
        adopted = []
        for values, originals in self.aliases.values():
            selected = []
            for index in ordered:
                original = originals[index]
                if not isinstance(original, dict):
                    raise ValueError("SOURCE_RELATIONSHIPS_INVALID: accepted caller edge is not a record")
                selected.append((original, deepcopy(self.accepted[index])))
            adopted.append((values, selected))
        for values, selected in adopted:
            for original, record in selected:
                original.clear()
                original.update(record)
            values[:] = [original for original, _ in selected]
        primary = self.aliases[self.primary][0]
        self.owner["nodes"] = working["nodes"]
        for name in self.aliases:
            self.owner[name] = primary
