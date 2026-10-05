"""Publish literal Qt metadata membership over accepted, immutable source facts."""
from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath

from graphify.extractors.qml_project_read import literal_path
from graphify.extractors.qml_source_identity import relative_qml_source
from graphify.qml_resolution_types import Resolution, answer, fact_edge, fact_node, qml_metadata, source_path
from graphify.qt_source_file_role import generic_file_role

_CONTEXTS = {"qt_membership_site", "qt_project_source", "qt_resource_membership"}


def _ast(node, fresh_ids):
    origin = node.get("_origin")
    return origin == "ast" or (origin is None and node.get("id") in fresh_ids)


def _location(node, span):
    start, end = span["start_row"] + 1, span["end_row"] + 1
    if node.get("source_location") not in {f"L{start}", f"L{start}-L{end}"}:
        raise ValueError("QML_METADATA: membership declaration location conflicts with span")


def _span(metadata):
    """Invalid transported locations are integrity failures, not guessed spans."""
    value = metadata.get("span")
    fields = ("start_byte", "end_byte", "start_row", "end_row", "start_column", "end_column")
    if (not isinstance(value, dict)
            or any(type(value.get(key)) is not int or value[key] < 0 for key in fields)
            or value["end_byte"] <= value["start_byte"] or value["end_row"] < value["start_row"]
            or (value["start_row"] == value["end_row"]
                and value["end_column"] - value["start_column"] != value["end_byte"] - value["start_byte"])):
        raise ValueError("QML_METADATA: invalid membership source span")
    return dict(value)


def _unsupported(metadata):
    if metadata.get("generated"):
        return "generated_membership_unestablished"
    if metadata.get("conditional"):
        return "conditional_membership_unestablished"
    return ""


def _file_role(node, path, fresh_ids):
    metadata = qml_metadata(node)
    if not _ast(node, fresh_ids) or node.get("_callable") or node.get("_callable_class"):
        return False
    if metadata.get("kind") == "file":
        return node.get("type") == "file" and node.get("label") == PurePosixPath(path).name
    return generic_file_role(node, path, fresh_ids)


def _target(index, path, fresh_ids):
    """A QML component precedes its file node; other sources need an exact file role."""
    components = index.module_index.components.get(path, [])
    if components:
        records = [index.nodes[nid] for nid in components]
        reason = next((_unsupported(qml_metadata(node)) for node in records
                       if _unsupported(qml_metadata(node))), "")
        if reason:
            return Resolution("unsupported", reason=reason)
        accepted = [node["id"] for node in records if _ast(node, fresh_ids)
                    and node.get("type") == "class"]
        return answer(accepted, reason="membership_component_provenance_unavailable")
    files = [nid for nid in index.module_index.by_file.get(path, [])
             if _file_role(index.nodes[nid], path, fresh_ids)]
    return answer(files, reason="membership_target_outside_accepted_corpus")


def _module(index, declaration, metadata, fresh_ids):
    ids = sorted(set(index.modules.get(metadata.get("module_key"), [])))
    if len(ids) != 1:
        return answer(ids, reason="membership_module_unavailable")
    mid = ids[0]
    module = index.nodes[mid]
    md = qml_metadata(module)
    if not _ast(module, fresh_ids) or module.get("type") != "namespace":
        return Resolution("unavailable", reason="membership_module_provenance_unavailable")
    _location(module, _span(md))
    if index.paths[mid] != index.paths[declaration["id"]]:
        return Resolution("unavailable", reason="membership_module_source_conflict")
    if md.get("kind") != "qt_module" or md.get("module_key") != metadata.get("module_key"):
        return Resolution("unavailable", reason="membership_module_unavailable")
    if reason := _unsupported(md):
        return Resolution("unsupported", reason=reason)
    return Resolution("resolved", mid, evidence=(mid,))


def _source(index, declaration, metadata, fresh_ids):
    module = _module(index, declaration, metadata, fresh_ids)
    if module.status != "resolved":
        return module
    path = literal_path(index.paths[declaration["id"]], metadata.get("value") or "")
    if path is None:
        return Resolution("unavailable", reason="membership_path_outside_root", evidence=module.evidence)
    target = _target(index, path, fresh_ids)
    return Resolution(target.status, target.target_id, target.reason,
                      tuple(dict.fromkeys(module.evidence + target.evidence)), target.candidates)


def _resource(index, declaration, metadata, fresh_ids):
    path = literal_path(index.paths[declaration["id"]], metadata.get("value") or "")
    if path is None or path != metadata.get("target_path"):
        return Resolution("unavailable", reason="membership_path_outside_root_or_conflicting")
    result = index.resource_index.resolve_url(metadata.get("logical_url") or "")
    if result.status != "resolved":
        return result
    accepted = _target(index, path, fresh_ids)
    if accepted.target_id != result.target_id:
        return Resolution(accepted.status if accepted.status != "resolved" else "ambiguous",
                          reason=accepted.reason or "membership_resource_target_conflict",
                          evidence=result.evidence, candidates=accepted.candidates)
    return Resolution("resolved", result.target_id, evidence=result.evidence)


def _remove_owned_edges(edges, site_id):
    # Only this resolver's mechanisms are replaced; semantic/user relationships
    # incident on the same accepted identity keep their independent ownership.
    edges[:] = [edge for edge in edges if not (edge.get("context") in _CONTEXTS
                and (edge.get("source") == site_id or edge.get("target") == site_id))]


def _accepted_input_source(path: Path | str, root: Path) -> str | None:
    """Compare the physically admitted walked owner without lending target roles."""
    # Native/root spellings canonicalize, while separately discovered aliases
    # stay distinct. Exact lexical equality rejects facts borrowed from another
    # owner even when those inputs happen to share a contained physical target.
    try:
        return relative_qml_source(Path(path), root)
    except (OSError, RuntimeError, ValueError):
        return None


def resolve_project_memberships(results, nodes, edges, *, root: Path, project_index,
                                fresh_ast_ids=()):
    """Append fresh source-owned sites and replace stale derived scratch records.

    Return fresh nodes/edges explicitly: a replacement of borrowed context may
    occur before a caller's append-count boundary. Input dictionaries stay
    immutable; the caller owns scratch publication and durable failure policy.
    """
    fresh_ids = set(fresh_ast_ids)
    declarations = []
    for path, result in results.items():
        for node in list(result.get("nodes", [])):
            md = qml_metadata(node)
            if md.get("kind") in {"qt_source", "resource_alias"}:
                declarations.append((node["id"], path, result, node, md))
    derived_nodes, derived_edges = [], []
    for _, path, result, declaration, metadata in sorted(declarations, key=lambda item: item[0]):
        file = source_path(declaration, Path(root))
        if (file is None or file != _accepted_input_source(path, root)
                or declaration["id"] not in project_index.nodes):
            raise ValueError("QML_METADATA: membership declaration source is not accepted")
        span = _span(metadata)
        _location(declaration, span)
        if not _ast(declaration, fresh_ids):
            resolution = Resolution("unavailable", reason="membership_declaration_provenance_unavailable")
        elif result.get("qml_failures") or result.get("error") or result.get("partial"):
            resolution = Resolution("unsupported", reason="metadata_source_incomplete")
        elif reason := _unsupported(metadata):
            resolution = Resolution("unsupported", reason=reason)
        elif metadata["kind"] == "qt_source":
            resolution = _source(project_index, declaration, metadata, fresh_ids)
        else:
            resolution = _resource(project_index, declaration, metadata, fresh_ids)
        key = hashlib.sha256(declaration["id"].encode("utf-8")).hexdigest()
        site = fact_node(file, "membership_resolution", key, metadata.get("value") or "membership",
                         span["start_row"] + 1, span=span,
                         declaration_id=declaration["id"], declaration_kind=metadata["kind"],
                         source_kind=metadata.get("source_kind") or "resource",
                         module_key=metadata.get("module_key") or "",
                         logical_url=metadata.get("logical_url") or "", alias=metadata.get("alias") or "",
                         status=resolution.status, reason=resolution.reason,
                         diagnostic_code="QML-RESOLVE-001" if resolution.status != "resolved" else "",
                         evidence=list(resolution.evidence[:50]), candidates=list(resolution.candidates[:50]),
                         target_id=resolution.target_id or "")
        owned = [fact_edge(declaration["id"], site["id"], "contains", declaration,
                           "qt_membership_site", span=span, declaration_id=declaration["id"])]
        if resolution.target_id:
            owned.append(fact_edge(site["id"], resolution.target_id, "references", declaration,
                         "qt_project_source" if metadata["kind"] == "qt_source" else "qt_resource_membership",
                         span=span, declaration_id=declaration["id"], module_key=metadata.get("module_key") or "",
                         logical_url=metadata.get("logical_url") or "", evidence=list(resolution.evidence[:50])))
        # Replacing a dictionary in scratch cannot mutate the previously saved
        # context object. Canonical source declarations are never rewritten.
        nodes[:] = [node for node in nodes if node.get("id") != site["id"]]
        _remove_owned_edges(edges, site["id"])
        nodes.append(site)
        edges.extend(owned)
        result["nodes"] = [node for node in result.get("nodes", []) if node.get("id") != site["id"]] + [site]
        _remove_owned_edges(result.setdefault("edges", []), site["id"])
        result["edges"].extend(owned)
        derived_nodes.append(site)
        derived_edges.extend(owned)
    return derived_nodes, derived_edges
