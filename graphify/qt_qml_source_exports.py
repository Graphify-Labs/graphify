"""Per-run build-declared QML type exports over accepted source facts only.

The project index owns these immutable views. Export names/revisions/internal
visibility are independent from resource URLs, physical filenames and native
registrations. No files are discovered and no generated build output executes.
"""
from __future__ import annotations

import posixpath
import re
from typing import TypeGuard

from graphify.extractors.qml_project_read import MAX_PROJECT_BYTES, literal_path
from graphify.qml_resolution_types import Resolution, answer, qml_metadata


def valid_export_identity(value):
    """Transported lookup keys must be bounded text before any dictionary use."""
    if not isinstance(value, str) or not value:
        return False
    try:
        return len(value.encode("utf-8")) <= 384
    except UnicodeError:
        return False


def _valid_span(value) -> TypeGuard[dict[str, int]]:
    keys = {"start_byte", "end_byte", "start_row", "end_row", "start_column", "end_column"}
    return (isinstance(value, dict) and value.keys() == keys
            and all(type(item) is int and 0 <= item <= MAX_PROJECT_BYTES for item in value.values())
            and value["start_byte"] <= value["end_byte"] and value["start_row"] <= value["end_row"]
            and (value["start_row"] != value["end_row"] or value["start_column"] <= value["end_column"]))


def validate_source_export(metadata):
    """Validate new source fields before the project index hashes or joins them."""
    count, name, value = (metadata.get(key) for key in ("qml_export_count", "qml_export_name", "value"))
    if metadata.get("qml_export_contract") != 1 or type(metadata.get("qml_export_contract")) is not int or (
            metadata.get("source_kind") != "qml" or type(count) is not int or not 0 <= count <= 10_000
            or not isinstance(name, str) or (name and not valid_export_identity(name))
            or not isinstance(value, str) or (value and not valid_export_identity(value))
            or not valid_export_identity(metadata.get("module_key"))):
        raise ValueError("QML_METADATA: invalid build export source contract")
    return count, name, value


def export_ownership(nodes, edges):
    """Validate only the actual new export chains, leaving legacy IDs untouched."""
    required, endpoints = set(), set()
    for eid, node in nodes.items():
        metadata = qml_metadata(node)
        if metadata.get("kind") != "qt_qml_export":
            continue
        sid, mid, key = (metadata.get(field) for field in ("source_id", "module_id", "module_key"))
        if not all(valid_export_identity(value) for value in (sid, mid, key)):
            raise ValueError("QML_METADATA: invalid build type export identity")
        required.update(((mid, sid), (sid, eid)))
        endpoints.update((sid, eid))
    if not required:
        return {}
    ownership = {}
    for edge in edges:
        if edge.get("relation") != "contains" or edge.get("context") != "qt_metadata_declaration":
            continue
        source, target = edge.get("source"), edge.get("target")
        if not isinstance(source, str) or not isinstance(target, str):
            if (isinstance(source, str) and source in endpoints) or (isinstance(target, str) and target in endpoints):
                raise ValueError("QML_METADATA: invalid build export ownership")
            continue
        if (source, target) in required:
            ownership.setdefault((source, target), []).append(edge)
    if required - ownership.keys():
        raise ValueError("QML_METADATA: incomplete build export ownership")
    return ownership


class QmlSourceExports:
    """Validate individual transport facts, then answer source-owned type lookups."""
    def __init__(self, nodes, paths, modules, sources, memberships, components, edges):
        self.nodes, self.memberships, self.components = nodes, memberships, components
        self.rows, self.controlled, self.imports = [], {}, {}
        for nid, node in nodes.items():
            md = qml_metadata(node)
            if md.get("kind") == "import" and md.get("import_kind") == "module" and not md.get("qualifier"):
                self.imports.setdefault(paths[nid], []).append(md)
        source_ids = {sid for ids in sources.values() for sid in ids}
        for sid in source_ids:
            md = qml_metadata(nodes[sid])
            if "qml_export_contract" not in md:
                continue
            count, name, value = validate_source_export(md)
            self.controlled[sid] = {"path": literal_path(paths[sid], value),
                                    "name": name, "count": count, "module_key": md.get("module_key")}
        # Metadata claims alone do not own an export. Retain the actual immutable
        # edge snapshot and require module→source→export declaration provenance.
        ownership = export_ownership(nodes, edges)
        counts = {}
        for eid, node in nodes.items():
            md = qml_metadata(node)
            if md.get("kind") != "qt_qml_export":
                continue
            sid, mid, key = md.get("source_id"), md.get("module_id"), md.get("module_key")
            if not all(valid_export_identity(value) for value in (sid, mid, key)):
                raise ValueError("QML_METADATA: invalid build type export identity")
            source = self.controlled.get(sid)
            major, minor, name = md.get("major"), md.get("minor"), md.get("raw_name")
            valid_version = (major is minor is None) or (type(major) is int and type(minor) is int
                             and 0 <= major <= 999_999 and 0 <= minor <= 999_999)
            if (not source or mid not in modules.get(key, []) or source["module_key"] != key
                    or node.get("source_file") != nodes[sid].get("source_file")
                    or not isinstance(name, str) or re.fullmatch(r"[A-Z][A-Za-z0-9_]*", name) is None
                    or name != source["name"] or not valid_version
                    or type(md.get("internal")) is not bool or type(md.get("singleton")) is not bool
                    or (md["internal"] and (major is not None or md["singleton"]))):
                raise ValueError("QML_METADATA: invalid build type export")
            self._check_ownership(nodes, ownership, mid, sid, eid)
            self.rows.append({**md, "id": eid, "path": source["path"]})
            counts[sid] = counts.get(sid, 0) + 1
        if any(counts.get(sid, 0) != source["count"] for sid, source in self.controlled.items()):
            raise ValueError("QML_METADATA: incomplete build type exports")

    @staticmethod
    def _check_ownership(nodes, ownership, mid, sid, eid):
        """Each source-owned edge carries its child's same-file original span."""
        for parent, child in ((mid, sid), (sid, eid)):
            parent_node, child_node = nodes[parent], nodes[child]
            parent_span, child_span = qml_metadata(parent_node).get("span"), qml_metadata(child_node).get("span")
            owned = ownership.get((parent, child), [])
            if (not owned or not _valid_span(parent_span) or not _valid_span(child_span)
                    or parent_node.get("source_file") != child_node.get("source_file")
                    or not parent_span["start_byte"] <= child_span["start_byte"] <= child_span["end_byte"] <= parent_span["end_byte"]
                    or any(edge.get("source_file") != child_node.get("source_file")
                           or qml_metadata(edge).get("span") != child_span for edge in owned)):
                raise ValueError("QML_METADATA: invalid build export ownership")
        if qml_metadata(nodes[sid])["span"] != qml_metadata(nodes[eid])["span"]:
            raise ValueError("QML_METADATA: build export lost its source token span")

    def module_available(self, metadata, major, minor):
        """Explicit source export versions supplement observed module availability."""
        if major is None:
            return True
        versions = [(metadata.get("major"), metadata.get("minor"))]
        versions.extend((row["major"], row["minor"]) for row in self.rows
                        if row["module_key"] == metadata.get("module_key") and row["major"] is not None)
        return any(ma == major and (minor is None or isinstance(mi, int) and minor <= mi)
                   for ma, mi in versions)

    def _select(self, rows, major, minor, importer):
        if not rows:
            return Resolution("unavailable", reason="module_type_unavailable")
        context = set(self.memberships.get(importer, []))
        visible = [r for r in rows if not r["internal"] or context == {r["module_id"]}]
        if not visible:
            return Resolution("unavailable", reason="internal_export",
                              evidence=tuple(r["id"] for r in rows[:50]))
        matching = [r for r in visible if r["major"] is None or major is None or
                    r["major"] == major and (minor is None or r["minor"] <= minor)]
        if not matching:
            return Resolution("unavailable", reason="type_version_unavailable")
        # Preserve internal declarations alongside the best public revision;
        # distinct same-named sources remain ambiguous instead of first-wins.
        public = [r for r in matching if not r["internal"]]
        best = max(((r["major"], r["minor"]) if r["major"] is not None else (-1, -1)
                    for r in public), default=None)
        selected = [r for r in matching if r["internal"] or
                    ((r["major"], r["minor"]) if r["major"] is not None else (-1, -1)) == best]
        evidence = tuple(sorted({value for r in selected for value in
                                 (r["id"], r["source_id"], r["module_id"])}))[:50]
        targets = sorted({nid for r in selected for nid in self.components.get(r["path"], [])})
        if len({r["source_id"] for r in selected}) > 1:
            return Resolution("ambiguous", reason="duplicate_type_export", evidence=evidence,
                              candidates=tuple(targets[:50]))
        if not targets:
            return Resolution("unavailable", reason="type_target_outside_corpus", evidence=evidence)
        if selected[0]["singleton"] and not all(qml_metadata(self.nodes[nid]).get("singleton") for nid in targets):
            return Resolution("unavailable", reason="singleton_pragma_missing", evidence=evidence)
        return answer(targets, reason="component_unavailable", evidence=evidence)

    def module_type(self, key, name, major, minor, importer):
        return self._select([r for r in self.rows if r["module_key"] == key and r["raw_name"] == name],
                            major, minor, importer)

    def directory_type(self, directory, name, importer):
        """Return None only when no build declaration controls this local spelling."""
        context = set(self.memberships.get(importer, []))
        rows = [r for r in self.rows if r["raw_name"] == name and context == {r["module_id"]}]
        if rows:
            # Module membership establishes an implicit namespace, not a way to
            # bypass an explicit versioned import of that same namespace.
            uri = qml_metadata(self.nodes[rows[0]["module_id"]]).get("uri")
            imports = [md for md in self.imports.get(importer, []) if md.get("value") == uri]
            versions = {(md.get("major"), md.get("minor")) for md in imports}
            if len(versions) > 1:
                return Resolution("ambiguous", reason="duplicate_module_import")
            major, minor = next(iter(versions), (None, None))
            return self._select(rows, major, minor, importer)
        for record in self.controlled.values():
            path = record["path"]
            if path and posixpath.dirname(path) == directory and (
                    posixpath.basename(path).removesuffix(".ui.qml").removesuffix(".qml") == name):
                return Resolution("unavailable", reason="exported_type_name_mismatch")
        return None
