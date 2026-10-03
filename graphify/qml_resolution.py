"""Project QML lookup results through source-owned sites in Graphify's simple graph."""

from __future__ import annotations

import hashlib
import json
import posixpath
from pathlib import Path

from graphify.qml_resolution_types import Resolution, answer, fact_edge, fact_node, qml_metadata, relative_reference
from graphify.qml_scope import QmlProjectIndex


def build_qml_index(nodes, edges, *, root: Path, import_roots=None) -> QmlProjectIndex:
    """Indexes have one run lifetime and never discover or execute additional files."""
    return QmlProjectIndex(nodes, edges, root=Path(root), import_roots=import_roots)


def _import_target(index: QmlProjectIndex, node: dict, file: str):
    md = qml_metadata(node)
    kind, value = md.get("import_kind"), md.get("value") or ""
    if kind == "module":
        return index.module_import(value, md.get("major"), md.get("minor")), None
    path = relative_reference(file, value)
    if path is None:
        return Resolution("unavailable", reason="import_outside_corpus"), None
    if kind == "script":
        candidates = [nid for nid in index.by_file.get(path, [])
                      if index.nodes[nid].get("type") == "file" or
                      index.nodes[nid].get("label") == posixpath.basename(path)]
        return answer(candidates, reason="script_outside_corpus"), None
    if kind == "directory":
        known = any(posixpath.dirname(accepted) == path for accepted in index.by_file)
        if not known:
            return Resolution("unavailable", reason="directory_outside_corpus"), None
        namespace = fact_node(file, "directory_namespace", path, value,
                              md.get("span", {}).get("start_row", 0) + 1,
                              directory=path, span=md.get("span", {}))
        return Resolution("resolved", namespace["id"]), namespace
    return Resolution("unsupported", reason="unsupported_import_kind"), None


def resolve_qml_project(per_file, all_nodes: list[dict], all_edges: list[dict], *,
                        root: Path, import_roots=None) -> None:
    """Append derived facts only for fresh sources; borrowed context stays immutable.

    Resolved imports/types use independent sites so parallel source mechanisms
    cannot overwrite each other in a simple graph. Unresolved sites retain a
    bounded reason/candidate set and never receive a guessed target edge.
    """
    index = build_qml_index(all_nodes, all_edges, root=root, import_roots=import_roots)
    fresh = {node["id"] for result in per_file.values() for node in result.get("nodes", [])}
    known_nodes = {node["id"] for node in all_nodes}
    known_edges = {(edge["source"], edge["target"], edge["relation"], edge.get("context"))
                   for edge in all_edges}

    def append_node(node):
        if node["id"] not in known_nodes:
            all_nodes.append(node)
            known_nodes.add(node["id"])

    def append_edge(edge):
        key = (edge["source"], edge["target"], edge["relation"], edge.get("context"))
        if key not in known_edges:
            all_edges.append(edge)
            known_edges.add(key)

    for node_id in sorted(fresh):
        node = index.nodes.get(node_id)
        if node is None:
            continue
        md, file = qml_metadata(node), index.paths[node_id]
        kind = md.get("kind")
        namespace = None
        if kind == "import":
            result, namespace = _import_target(index, node, file)
            site_kind, relation, label = "import_resolution", "imports", md.get("value") or "import"
        elif kind == "object":
            label = md.get("type_name") or md.get("raw_type") or ""
            result = index.resolve_type(file, md.get("component_key") or "", label)
            site_kind, relation = "type_use", "uses"
        else:
            continue
        if namespace is not None:
            append_node(namespace)
        span = md.get("span", {})
        line = span.get("start_row", 0) + 1
        # Hash a bounded semantic key; the owner edge retains the full declaration ID.
        key = hashlib.sha256(json.dumps([node_id, site_kind], ensure_ascii=False).encode()).hexdigest()
        site = fact_node(file, site_kind, key, label, line, span=span,
                         status=result.status, reason=result.reason,
                         diagnostic_code="QML-RESOLVE-001" if result.status != "resolved" else "",
                         evidence=list(result.evidence[:50]), candidates=list(result.candidates[:50]))
        append_node(site)
        owner = {"source_file": file, "source_location": node.get("source_location", f"L{line}")}
        append_edge(fact_edge(node_id, site["id"], "contains", owner, "qml_resolution_site", span=span))
        if result.target_id is not None:
            append_edge(fact_edge(site["id"], result.target_id, relation, owner,
                                  "qml_import_resolution" if kind == "import" else "qml_type_resolution",
                                  confidence="INFERRED", span=span, evidence=list(result.evidence[:50])))
