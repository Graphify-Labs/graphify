"""Validate source-owned own-metaobject evidence without reconstructing C++ authority."""
from __future__ import annotations

import copy
from typing import NoReturn

from graphify.extractors.qt_cpp_facts import qt_id, qt_metadata
from graphify.qml_resolution_types import Resolution
from graphify.qt_declared_provider import DeclaredProviderIndex

_SPAN = {"start_byte", "end_byte", "start_row", "end_row", "start_column", "end_column"}
_STATUS = {"resolved", "unavailable", "unsupported", "dynamic", "ambiguous"}


def _bad() -> NoReturn:
    raise ValueError("QT_METADATA: malformed source-owned metaobject evidence")


def _identity(value):
    try:
        return isinstance(value, str) and len(value.encode("utf-8")) <= 384
    except UnicodeError:
        return False


def _span(value):
    return (isinstance(value, dict) and set(value) == _SPAN
            and all(type(item) is int and 0 <= item <= 5_000_000 for item in value.values())
            and value["start_byte"] < value["end_byte"]
            and (value["start_row"], value["start_column"]) < (value["end_row"], value["end_column"]))


def validate_metaobject_transport(node):
    """Reject only new-contract malformed keys before any shared kind/ID index hashes them."""
    md = qt_metadata(node)
    if md.get("metaobject_contract") is None:
        return {}
    if (type(md.get("metaobject_contract")) is not int or md["metaobject_contract"] != 1
            or not isinstance(md.get("kind"), str) or md["kind"] not in {"class", "metaobject"}
            or not _identity(md.get("class_id")) or not _identity(md.get("owner_id"))
            or not _identity(node.get("id")) or not node["id"]):
        _bad()
    if md["kind"] == "class":
        if (type(md.get("metaobject_count")) is not int or not 0 <= md["metaobject_count"] <= 50
                or not isinstance(md.get("metaobject_status"), str) or md["metaobject_status"] not in _STATUS
                or not isinstance(md.get("metaobject_reason"), str)
                or type(md.get("source_q_object")) is not bool
                or md["source_q_object"] != (md["metaobject_count"] > 0)):
            _bad()
    elif (type(md.get("conditional")) is not bool or not isinstance(md.get("status"), str)
          or md["status"] not in _STATUS or not _span(md.get("span"))):
        _bad()
    return md


class QtMetaobjectIndex:
    """One analysis owns a read-only marker/ownership snapshot and accepted class view.

    Missing source syntax is an ordinary unavailable API. Broken promised marker
    transport is an integrity error. Edge context is mandatory for positive own
    metaobject authority, including after sanitation/serialization.
    """
    def __init__(self, nodes, edges=None, *, unknown_metaobject_ownership=()):
        values = ([{**node, "id": identity} for identity, node in nodes.items()]
                  if hasattr(nodes, "items") else list(nodes))
        self.context_nodes, self.context_edges = nodes, edges
        self.node_refs = (dict(nodes.items()) if hasattr(nodes, "items") else
                          {node["id"]: node for node in values if isinstance(node.get("id"), str)})
        self.node_positions = ({node["id"]: position for position, node in enumerate(nodes)
                                if isinstance(node.get("id"), str)} if isinstance(nodes, (list, tuple)) else None)
        # Validate new keys before the shared class index hashes them. Legacy
        # records remain subject to their existing owning contracts.
        self.markers = {}
        for node in values:
            md = validate_metaobject_transport(node)
            if not md:
                continue
            if md.get("kind") == "metaobject":
                self.markers.setdefault(md["class_id"], []).append(node)
        self.declared = DeclaredProviderIndex(values)
        # Index only this contract's actual marker targets once. Unrelated
        # legacy ownership IDs/metadata keep their established boundaries.
        marker_ids = {node["id"] for group in self.markers.values() for node in group}
        # Only the owning partial-analysis boundary can name actual borrowed
        # markers with unknown edge context. It cannot weaken source transport
        # or a provided edge, and graph assembly never supplies this exemption.
        if (not isinstance(unknown_metaobject_ownership, (tuple, frozenset))
                or len(unknown_metaobject_ownership) > len(marker_ids)
                or any(not _identity(value) or value not in marker_ids for value in unknown_metaobject_ownership)):
            _bad()
        self.unknown_ownership = frozenset(unknown_metaobject_ownership)
        self.ownership = None
        if edges is not None:
            self.ownership = {}
            for edge in edges:
                target = edge.get("target", edge.get("to"))
                if isinstance(target, str) and target in marker_ids and edge.get("context") == "qt_source_site":
                    self.ownership.setdefault(target, []).append(edge)
        # Context reuse is scoped to this exact assembly. Snapshot only source
        # inputs for each declaring class, not every member/corpus node, so each
        # later check detects mutation/replacement with bounded local work.
        self.inputs, self.snapshots = {}, {}
        for identity in self.declared.classes.keys() | self.markers.keys():
            ids = tuple(dict.fromkeys([identity]
                + [node["id"] for node in self.declared.classes.get(identity, [])]
                + [node["id"] for node in self.markers.get(identity, [])]))
            self.inputs[identity] = ids
            self.snapshots.update({key: copy.deepcopy(self.node_refs[key]) for key in ids if key in self.node_refs})
        # Fresh source facts with malformed positive transport must fail before
        # a name lookup happens to ignore their class or choose another member.
        for identity, records in self.declared.classes.items():
            if any(qt_metadata(node).get("metaobject_contract") == 1 for node in records):
                self.resolve(identity)
        for identity, markers in self.markers.items():
            positive = any(qt_metadata(node).get("status") == "resolved" for node in markers)
            promised = any(qt_metadata(node).get("metaobject_contract") == 1
                           and qt_metadata(node).get("metaobject_status") == "resolved"
                           for node in self.declared.classes.get(identity, []))
            if positive and not promised:
                _bad()

    def resolve(self, identity):
        if not _identity(identity):
            _bad()
        for key in self.inputs.get(identity, ()):
            original = self.node_refs.get(key)
            if hasattr(self.context_nodes, "items"):
                current = self.context_nodes.get(key)
            elif self.node_positions is not None and key in self.node_positions:
                position = self.node_positions[key]
                current = self.context_nodes[position] if position < len(self.context_nodes) else None
            else:
                current = original
            if current is not original or original != self.snapshots.get(key):
                _bad()
        record = self.declared.class_record(identity)
        if record is None:
            if any(qt_metadata(node).get("metaobject_status") == "resolved"
                   for node in self.declared.classes.get(identity, [])) or any(
                       qt_metadata(node).get("status") == "resolved" for node in self.markers.get(identity, [])):
                _bad()
            return Resolution("unavailable", reason="native_metaobject_source_unavailable")
        md = qt_metadata(record)
        if md.get("metaobject_contract") != 1:
            return Resolution("unavailable", reason="native_metaobject_source_unavailable")
        markers = self.markers.get(identity, [])
        count, status = md["metaobject_count"], md["metaobject_status"]
        if len(markers) != count:
            _bad()
        if count == 0:
            if status != "unavailable" or md.get("metaobject_span") != {}:
                _bad()
        elif count == 1:
            if not _span(md.get("metaobject_span")):
                _bad()
        elif status != "ambiguous" or md.get("metaobject_span") != {}:
            _bad()
        ownership_known = True
        for marker in markers:
            ownership_known = self._marker(record, marker, status, count) and ownership_known
        if status == "resolved":
            if count != 1 or not ownership_known:
                result = Resolution("unavailable", reason="native_metaobject_ownership_unavailable")
            else:
                result = Resolution("resolved", markers[0]["id"], evidence=(record["id"], markers[0]["id"]))
        else:
            result = Resolution(status, reason=md["metaobject_reason"])
        return result

    def owns(self, nodes, edges):
        """Only an explicit immutable ownership tuple may reuse this graph's index."""
        return nodes is self.context_nodes and isinstance(edges, tuple) and edges is self.context_edges

    def _marker(self, record, marker, status, count):
        owner, md = qt_metadata(record), qt_metadata(marker)
        span, bounds = md.get("span"), owner["span"]
        if not isinstance(span, dict) or not _span(span):
            _bad()
        if (md.get("kind") != "metaobject" or md.get("raw_name") != "Q_OBJECT"
                or md.get("owner_id") != owner["class_id"] or md.get("class_id") != owner["class_id"]
                or md.get("class_name") != owner.get("class_name") or md.get("status") != status
                or type(md.get("conditional")) is not bool
                or marker.get("source_file") != record.get("source_file")
                or not bounds["start_byte"] < span["start_byte"] < span["end_byte"] < bounds["end_byte"]
                or not (bounds["start_row"], bounds["start_column"]) < (span["start_row"], span["start_column"])
                or not (span["end_row"], span["end_column"]) < (bounds["end_row"], bounds["end_column"])
                or marker.get("source_location") != f"L{span['start_row'] + 1}-L{span['end_row'] + 1}"
                or marker.get("id") != qt_id(marker["source_file"], "metaobject", [owner["class_id"], span["start_byte"], span["end_byte"], "Q_OBJECT"])
                or count == 1 and span != owner.get("metaobject_span")
                or status == "resolved" and (md["conditional"] or span["end_byte"] - span["start_byte"] != 8
                    or span["start_row"] != span["end_row"] or span["end_column"] - span["start_column"] != 8)
                or status == "dynamic" and not md["conditional"]):
            _bad()
        if self.ownership is None:
            return False
        owned = self.ownership.get(marker["id"], [])
        if not owned and marker["id"] in self.unknown_ownership:
            return False
        if len(owned) != 1:
            _bad()
        edge, link = owned[0], qt_metadata(owned[0])
        if (edge.get("source", edge.get("from")) != owner["class_id"]
                or edge.get("target", edge.get("to")) != marker["id"]
                or edge.get("context") != "qt_source_site"
                or edge.get("_src", owner["class_id"]) != owner["class_id"]
                or edge.get("_tgt", marker["id"]) != marker["id"]
                or edge.get("relation") != "contains" or edge.get("confidence") != "EXTRACTED"
                or edge.get("source_file") != marker.get("source_file")
                or edge.get("source_location") != marker.get("source_location") or link.get("span") != span
                or link.get("target_id") != marker["id"]):
            _bad()
        return True


def valid_metaobject_proof(proof, nodes, edges=None, metaobject_index=None):
    """Retained endpoint IDs cannot repair missing declaring-class/marker/edge evidence."""
    if metaobject_index is not None and (not isinstance(metaobject_index, QtMetaobjectIndex)
                                        or not metaobject_index.owns(nodes, edges)):
        return False
    index = metaobject_index if metaobject_index is not None else QtMetaobjectIndex(nodes, edges)
    result = index.resolve(proof.get("class_id"))
    evidence = proof.get("evidence")
    return bool(result.status == "resolved" and result.target_id == proof.get("metaobject_fact_id")
                and isinstance(evidence, list) and all(isinstance(item, str) for item in evidence)
                and set(result.evidence) <= set(evidence))
