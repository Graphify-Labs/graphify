"""HTML semantic relationship views keep source dependencies distinct from calls."""
from __future__ import annotations

from html import escape

from graphify.extractors.qml_facts import qml_metadata
from graphify.extractors.qt_cpp_facts import qt_metadata

_LABELS = {
    "qt_signal_emit": "signal emission", "qt_connect_signal": "connection signal", "qt_connect_receiver": "connection receiver",
    "qt_disconnect_signal": "disconnect signal", "qt_disconnect_receiver": "disconnect receiver", "qt_disconnect": "disconnect handle",
    "qt_qml_connect_signal": "QML connection signal", "qt_qml_connect_receiver": "QML connection receiver",
    "qt_qml_disconnect_signal": "QML disconnect signal", "qt_qml_disconnect_receiver": "QML disconnect receiver",
    "qml_signal_subscription": "signal subscription", "qml_signal_emit": "QML signal emission",
    "qml_binding_read": "binding read", "qml_alias_target": "alias target", "qml_js_call": "JavaScript call", "qml_script_call": "imported script call",
    "qml_import_resolution": "QML import", "qml_type_resolution": "QML type", "qml_type_base": "QML base type",
    "qt_cpp_qml_load": "component or object access", "qt_cpp_qml_find_child": "objectName lookup",
    "qt_cpp_qml_property_read": "QML property read", "qt_cpp_qml_property_write": "QML property write", "qt_cpp_qml_invoke": "QML method invocation",
    "qt_context_exposure": "context provider", "qt_initial_property": "initial property provider", "qt_context_member": "QML context member",
}
_EVENTS = {key for key in _LABELS if "connect" in key or "signal" in key}
_KINDS = {"type_use", "import_resolution", "read", "call", "handler", "alias", "qml_load", "qml_root", "qml_access", "context_exposure", "initial_properties", "connect", "disconnect", "emission"}


def relationship_label(edge):
    """A free-form context string alone is not versioned source evidence."""
    if edge.get("context") not in _LABELS:
        return None
    try:
        if qml_metadata(edge).get("contract_version") != 1 and qt_metadata(edge).get("contract_version") != 1:
            return None
    except (ValueError, TypeError):
        return None
    return _LABELS[edge["context"]]


def is_event_relationship(edge):
    return edge.get("context") in _EVENTS and relationship_label(edge) is not None


def render_relationship_table(nodes, edges, lang="en"):
    """Render accepted links and explicit unresolved source facts as HTML text."""
    del lang
    by_id = {node["id"]: node for node in nodes}
    rows = []
    for edge in edges:
        label = relationship_label(edge)
        source, target = by_id.get(edge.get("source")), by_id.get(edge.get("target"))
        if not label or not source or not target:
            continue
        location = str(edge.get("source_file") or "") + ":" + str(edge.get("source_location") or "")
        rows.append('<tr data-source-id="' + escape(source["id"], quote=True) + '" data-target-id="' + escape(target["id"], quote=True) + '"><td>'
                    + escape(source.get("label") or source["id"]) + '</td><td>' + escape(label) + '</td><td>' + escape(target.get("label") or target["id"])
                    + '</td><td>' + escape(location) + '</td><td>' + escape(str(edge.get("confidence") or "")) + '</td></tr>')
    for node in nodes:
        try:
            metadata = qml_metadata(node) or qt_metadata(node)
        except (ValueError, TypeError):
            continue
        if metadata.get("kind") not in _KINDS or metadata.get("status") not in {"ambiguous", "dynamic", "unsupported", "unavailable"}:
            continue
        rows.append('<tr data-source-id="' + escape(node["id"], quote=True) + '"><td>' + escape(node.get("label") or node["id"])
                    + '</td><td>' + escape(metadata["status"]) + '</td><td>' + escape(str(metadata.get("reason") or "target unestablished"))
                    + '</td><td>' + escape(str(node.get("source_file") or "") + ':' + str(node.get("source_location") or "")) + '</td><td>source fact</td></tr>')
    if not rows:
        return ""
    return '<section class="qt-qml-relationships"><h3>Qt/QML source relationships</h3><p>Connections and subscriptions describe source facts; runtime delivery is unverified.</p><table><thead><tr><th>Source</th><th>Relationship / status</th><th>Target / reason</th><th>Location</th><th>Evidence</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table></section>'
