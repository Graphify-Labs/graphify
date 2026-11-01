"""Source ownership propagation for Qt/QML dependency occurrence nodes."""
from __future__ import annotations

from graphify.extractors.qml_facts import qml_metadata
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.graph_direction import logical_endpoints


def _owned(node):
    try:
        return qml_metadata(node).get("contract_version") == 1 or qt_metadata(node).get("contract_version") == 1
    except (ValueError, TypeError):
        return False


def _owns_source(parent, child, data, owner_id, child_id):
    file = child.get("source_file")
    if not file or data.get("source_file") != file:
        return False
    if parent.get("source_file") == file:
        return True
    # C++ canonical methods point at their header declaration. Their accepted
    # implementation file can own a Qt site only with callable and exact owner,
    # endpoint and original-span evidence from the extracted containment fact.
    if parent.get("_callable") is not True or parent.get("definition_file") != file:
        return False
    child_qt, edge_qt = qt_metadata(child), qt_metadata(data)
    return (child_qt.get("owner_id") == owner_id and edge_qt.get("target_id") == child_id
            and bool(child_qt.get("span")) and child_qt.get("span") == edge_qt.get("span"))


def owned_ancestors(graph, node_id, *, limit=256):
    """Yield actual EXTRACTED contains owners without general forward traversal.

    A dependency points from a source occurrence to its target. Its enclosing
    binding/handler/component is affected through that source ownership, not by
    an inferred signal-delivery call. Ordinary graph nodes retain old behavior.
    """
    pending, seen = [node_id], {node_id}
    while pending and len(seen) <= limit:
        current = pending.pop()
        if current not in graph or not _owned(graph.nodes[current]):
            continue
        edges = graph.in_edges(current, data=True) if graph.is_directed() else graph.edges(current, data=True)
        for source, target, data in edges:
            endpoints = logical_endpoints(source, target, data, directed=graph.is_directed())
            if endpoints is None:
                continue
            source, target = endpoints
            if target != current or source not in graph or source in seen:
                continue
            if data.get("relation") != "contains" or data.get("confidence") != "EXTRACTED":
                continue
            parent, child = graph.nodes[source], graph.nodes[current]
            try:
                if not _owned(data) or not _owns_source(parent, child, data, source, current):
                    continue
            except (ValueError, TypeError):
                continue
            if len(seen) >= limit:
                return
            seen.add(source)
            yield str(source), data
            pending.append(source)
