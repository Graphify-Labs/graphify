"""Join accepted Qt/QML facts after canonical C++ identities are finalized."""
from __future__ import annotations

from pathlib import Path

from graphify.qml_resolution_types import source_path


def _diagnostic_source(path: Path, root: Path) -> str:
    """Return a bounded relative label without granting source or target authority."""
    # Match the existing safety display's 160-character bound. Diagnostic
    # fallback must not retry a failed identity operation without a guard, leak
    # a foreign root, or truncate a label into a different apparent source.
    try:
        relative = source_path({"source_file": str(path.resolve())}, Path(root).resolve())
    except (OSError, RuntimeError, ValueError):
        relative = source_path({"source_file": str(path)}, Path(root))
    if (relative is None or len(relative) > 160
            or any(ord(char) < 32 or 127 <= ord(char) < 160 or char in "\u2028\u2029"
                   for char in relative)):
        return ""
    return relative


def resolve_qt_qml(paths, per_file, all_nodes, all_edges, *, root,
                   context_nodes=(), context_edges=(), import_roots=None):
    """Publish successful scratch joins; never annotate borrowed context facts."""
    from graphify.extractors.qt_cpp_access import collect_qt_cpp_access
    from graphify.extractors.qt_cpp_events import collect_qt_cpp_events
    from graphify.extractors.qt_cpp_exposure import enrich_qt_cpp
    from graphify.qt_event_resolution import resolve_qt_events
    from graphify.qt_qml_access_resolution import resolve_qt_qml_access
    from graphify.qt_qml_bridge import build_qt_qml_bridge
    from graphify.qt_project_index import QtProjectIndex
    from graphify.qt_project_membership import resolve_project_memberships
    from graphify.qt_source_containment import attach_qt_file_sites

    fresh_ids = {node["id"] for node in all_nodes}
    nodes = all_nodes + [node for node in context_nodes or () if node.get("id") not in fresh_ids]
    edges = all_edges + list(context_edges or ())
    initial_ids = {node["id"] for node in nodes}
    initial_edges = {id(edge) for edge in edges}
    results = {path: result for path, result in zip(paths, per_file) if result}
    active_paths, active_results = list(results), list(results.values())

    def collect(collector):
        counts = [(len(result.get("nodes", [])), len(result.get("edges", []))) for result in active_results]
        collector(active_paths, active_results, root=root, accepted_nodes=nodes, accepted_edges=edges)
        known = {node["id"] for node in nodes}
        for result, (n0, e0) in zip(active_results, counts):
            for node in result.get("nodes", [])[n0:]:
                if node["id"] not in known:
                    nodes.append(node)
                    known.add(node["id"])
            edges.extend(result.get("edges", [])[e0:])

    try:
        collect(enrich_qt_cpp)
        collect(collect_qt_cpp_events)
        collect(collect_qt_cpp_access)
        project_index = QtProjectIndex(nodes, edges, root=root, import_roots=import_roots)
        # Packaging membership is source evidence independent of QML use/load.
        # Only fresh declarations publish decisions over the accepted corpus.
        membership_nodes, _ = resolve_project_memberships(
            results, nodes, edges, root=root, project_index=project_index,
            fresh_ast_ids=fresh_ids)
        native_index = build_qt_qml_bridge(nodes, edges, root=root, project_index=project_index)
        if any(node.get("metadata", {}).get("qml") for node in nodes):
            from graphify.qml_relationships import resolve_qml_relationships
            from graphify.qml_resolution import resolve_qml_project
            resolve_qml_project(results, nodes, edges, root=root, import_roots=import_roots, native_index=native_index, project_index=project_index)
            resolve_qml_relationships(results, nodes, edges, root=root, import_roots=import_roots, native_index=native_index, project_index=project_index)
        resolve_qt_events(results, nodes, edges, root=root)
        resolve_qt_qml_access(results, nodes, edges, root=root, project_index=project_index)
        # Unresolved callable/class identity does not erase observed membership
        # in a uniquely accepted source file; this grants no native target role.
        edges.extend(attach_qt_file_sites(results, nodes, edges, root=root, fresh_ast_ids=fresh_ids))
        for diagnostic in project_index.diagnostics:
            for path, result in results.items():
                if Path(path).resolve().relative_to(root).as_posix() == diagnostic["source_file"]:
                    result.setdefault("diagnostics", []).append(dict(diagnostic))
                    break
    except Exception:
        # Do not expose backend errors or let partial joins reach a graph writer.
        for path, result in results.items():
            path = Path(path)
            if path.suffix.lower() not in {".qml", ".js", ".mjs", ".cpp", ".cc", ".cxx", ".h", ".hpp", ".hh", ".hxx", ".qmltypes", ".cmake", ".pro", ".pri", ".qrc"} and path.name not in {"qmldir", "CMakeLists.txt"}:
                continue
            # A join can fail because this same input no longer resolves. Its
            # diagnostic label is display context only; unavailable context is
            # explicit and cannot interrupt annotation of the remaining files.
            relative = _diagnostic_source(path, root)
            result.setdefault("qml_failures", []).append({"code": "QML_RESOLUTION_FAILED", "source_file": relative})
            result.setdefault("diagnostics", []).append({"code": "QML_RESOLUTION_FAILED", "severity": "error",
                "owner": "qt_qml_resolution", "source_file": relative, "message": "Qt/QML project join failed",
                "recovery": "Correct the join failure and retry; prior graph is preserved."})
    else:
        # Derived membership decisions can replace borrowed same-ID sites.
        # Publish fresh facts by identity, so removal of stale context cannot
        # shift list offsets or leak unrelated borrowed nodes into this result.
        membership_ids = {node["id"] for node in membership_nodes}
        all_nodes.extend(node for node in nodes if node["id"] not in initial_ids
                         or (node["id"] in membership_ids and node["id"] not in fresh_ids))
        all_edges.extend(edge for edge in edges if id(edge) not in initial_edges)

    return [str(path) for path, result in results.items() if result.get("qml_failures") or result.get("qt_failures")]
