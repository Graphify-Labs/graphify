"""Accepted component, objectName and source-local handle lookup for Qt access."""
from __future__ import annotations

from graphify.extractors.qt_cpp_facts import scope_owner
from graphify.qml_resolution import build_qml_index
from graphify.qml_resolution_types import Resolution, answer, qml_metadata
from graphify.qt_project_index import QtProjectIndex


class QtQmlAccessIndex:
    def __init__(self, nodes, edges, *, root, project_index=None):
        self.nodes = {node["id"]: node for node in nodes}
        self.qml = build_qml_index(nodes, edges, root=root)
        self.project = project_index or QtProjectIndex(nodes, edges, root=root)
        self.loads, self.handles, self.names = {}, {}, {}
        for node in nodes:
            metadata = qml_metadata(node)
            if metadata.get("kind") in {"property", "binding"} and metadata.get("raw_name") == "objectName" and isinstance(metadata.get("literal_value"), str):
                key = (node["source_file"], metadata.get("component_key"), metadata["literal_value"])
                self.names.setdefault(key, set()).update(self.qml.objects.get((node["source_file"], metadata.get("component_key"), metadata.get("object_scope_key")), []))

    def load(self, metadata):
        if metadata.get("conditional"):
            return Resolution("dynamic", reason="conditional_component_load")
        if metadata.get("operation") == "loadFromModule":
            if not isinstance(metadata.get("module_uri"), str) or not isinstance(metadata.get("type_name"), str):
                return Resolution("dynamic", reason="computed_module_or_type")
            return self.project.resolve_component(metadata["module_uri"], metadata["type_name"])
        if not isinstance(metadata.get("literal_url"), str):
            return Resolution("dynamic", reason="computed_url")
        return self.project.resolve_url(metadata["literal_url"], metadata.get("base_url"))

    def root_object(self, component_id):
        component = self.nodes.get(component_id, {})
        metadata = qml_metadata(component)
        if metadata.get("kind") == "file":
            candidates = [node["id"] for node in self.nodes.values() if node.get("source_file") == component.get("source_file") and qml_metadata(node).get("kind") == "component"]
            result = answer(candidates, reason="component_unavailable")
            return self.root_object(result.target_id) if result.target_id else result
        candidates = [node["id"] for node in self.nodes.values() if node.get("source_file") == component.get("source_file")
                      and qml_metadata(node).get("kind") == "object" and qml_metadata(node).get("component_key") == metadata.get("component_key")
                      and not qml_metadata(node).get("parent_scope_key")]
        return answer(candidates, reason="component_root_unavailable")

    def find_child(self, root_id, name):
        root = self.nodes[root_id]
        metadata = qml_metadata(root)
        candidates = self.names.get((root["source_file"], metadata.get("component_key"), name), set())
        # QObject::findChild searches descendants, not its receiving object.
        return answer([target for target in candidates if target != root_id], reason="object_name_unavailable")

    def member(self, object_id, name, operation):
        node, metadata = self.nodes[object_id], qml_metadata(self.nodes[object_id])
        result = self.qml.resolve_member(node["source_file"], metadata.get("component_key") or "", metadata.get("object_scope_key") or "", name)
        if not result.target_id:
            return result
        kind = qml_metadata(self.nodes[result.target_id]).get("kind")
        supported = {"function", "signal"} if operation == "invokeMethod" else {"property"}
        return result if kind in supported else Resolution("unavailable", reason="member_role_mismatch")

    def handle(self, metadata, reference=None):
        key = (scope_owner(metadata), reference if reference is not None else metadata.get("receiver_reference"))
        entry = self.handles.get(key)
        if entry is None:
            return Resolution("unavailable", reason="qml_handle_unestablished")
        target, assignment, condition = entry
        if condition or assignment != metadata.get("receiver_assignment_byte", -1):
            return Resolution("dynamic", reason="conditional_or_reassigned_handle")
        return Resolution("resolved", target, evidence=("source_handle",))
