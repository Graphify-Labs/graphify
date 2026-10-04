"""Resolve literal C++ access to accepted QML source, never instantiate components."""
from __future__ import annotations

from graphify.extractors.qt_cpp_facts import qt_edge, qt_metadata, scope_owner, update_qt
from graphify.qml_resolution_types import Resolution
from graphify.qml_resolution_types import qml_metadata
from graphify.qt_qml_access_index import QtQmlAccessIndex
from graphify.qt_qml_event_access import resolve_qml_event_access
from graphify.qt_context_bindings import project_context_access, resolve_context_bindings
from graphify.qt_qml_bridge import build_qt_qml_bridge


def _annotate(site, resolution):
    update_qt(site, status=resolution.status, target_id=resolution.target_id or "", reason=resolution.reason,
              candidates=list(resolution.candidates), evidence=list(resolution.evidence), bridge_direction="cpp_to_qml")


def resolve_qt_qml_access(per_file, all_nodes, all_edges, *, root, project_index=None):
    """Only fresh facts are annotated; prior accepted dictionaries are lookup context."""
    index = QtQmlAccessIndex(all_nodes, all_edges, root=root, project_index=project_index)
    results = list(per_file.values() if isinstance(per_file, dict) else per_file)
    sites = sorted([(site, result) for result in results if result for site in result.get("nodes", [])
                    if qt_metadata(site).get("kind") in {"qml_load", "qml_root", "qml_access", "qml_parent_mutation", "context_exposure", "initial_properties"}],
                   key=lambda pair: (pair[0]["source_file"], qt_metadata(pair[0]).get("span", {}).get("start_byte", -1)))
    for site, result in sites:
        metadata, edges = qt_metadata(site), []
        owner, receiver = scope_owner(metadata), metadata.get("receiver_reference")
        kind, operation = metadata["kind"], metadata.get("operation")
        key = (owner, receiver)
        context = "qt_cpp_qml_load"
        if kind == "qml_load":
            resolution = index.load(metadata)
            index.loads.setdefault(key, []).append(resolution)
        elif kind == "qml_root":
            loads = index.loads.get(key, [])
            if len(loads) != 1 or not loads[0].target_id:
                resolution = Resolution("ambiguous" if len(loads) > 1 else "unavailable", reason="unique_source_loader_unestablished")
            elif operation == "rootObjects" and not metadata.get("single_root_selection"):
                resolution = Resolution("unsupported", reason="root_list_requires_static_selection")
            else:
                resolution = index.root_object(loads[0].target_id)
        elif kind == "qml_parent_mutation":
            # Only an established QML receiver invalidates its accepted tree;
            # unrelated QObject mutations grant no component identity.
            handle = index.handle(metadata)
            if handle.target_id:
                index.mark_parent_mutation(handle.target_id)
            resolution = Resolution("dynamic", reason="runtime_parent_mutation")
        elif kind == "qml_access":
            if metadata.get("handle_role") == "root":
                loads = index.loads.get(key, [])
                handle = index.root_object(loads[0].target_id) if len(loads) == 1 and loads[0].target_id else Resolution("unavailable", reason="unique_source_loader_unestablished")
            else:
                handle = index.handle(metadata)
            if not handle.target_id:
                resolution = handle
            elif operation in {"read", "write"} and metadata.get("receiver_type") == "QQmlProperty" and qml_metadata(index.nodes[handle.target_id]).get("kind") == "property":
                resolution = handle
                context = "qt_cpp_qml_property_write" if operation == "write" else "qt_cpp_qml_property_read"
            elif not isinstance(metadata.get("lookup_name"), str):
                resolution = Resolution("dynamic", reason="computed_access_name")
            elif operation == "findChild":
                resolution = (index.find_child(handle.target_id, metadata["lookup_name"],
                                               options=metadata.get("find_child_options", "unsupported"))
                              if metadata.get("find_child_type_supported") else
                              Resolution("unsupported", reason="find_child_type_unsupported"))
                context = "qt_cpp_qml_find_child"
            else:
                resolution = index.member(handle.target_id, metadata["lookup_name"], operation)
                context = "qt_cpp_qml_invoke" if operation == "invokeMethod" else "qt_cpp_qml_property_write" if operation in {"setProperty", "write"} else "qt_cpp_qml_property_read"
        else:
            # Provider names alone do not establish a runtime engine/component
            # binding. Preserve the literal exposure for the bridge profile.
            resolution = Resolution("unavailable", reason="provider_component_scope_unestablished")
            context = "qt_context_exposure" if kind == "context_exposure" else "qt_initial_property"
        _annotate(site, resolution)
        if resolution.target_id:
            relation = "calls" if operation == "invokeMethod" and index.qml.md(resolution.target_id).get("kind") == "function" else "uses"
            edges.append(qt_edge(site, resolution.target_id, relation, context, bridge_direction="cpp_to_qml"))
            if metadata.get("assigned_handle") and kind in {"qml_root", "qml_access"}:
                index.handles[(owner, metadata["assigned_handle"])] = (resolution.target_id, metadata.get("assignment_byte", -1), bool(metadata.get("conditional")))
        known = {(edge["source"], edge["target"], edge.get("context")) for edge in result.get("edges", [])}
        additions = [edge for edge in edges if (edge["source"], edge["target"], edge.get("context")) not in known]
        result.setdefault("edges", []).extend(additions)
        if all_edges is not result["edges"]:
            all_edges.extend(additions)
    bindings = resolve_context_bindings(results, index, all_nodes, all_edges)
    bridge = build_qt_qml_bridge(all_nodes, all_edges, root=root, project_index=index.project)
    project_context_access(results, bridge, bindings, all_nodes, all_edges, index.qml)
    resolve_qml_event_access(results, index, all_nodes, all_edges)
