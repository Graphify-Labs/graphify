"""Accepted component, objectName and source-local handle lookup for Qt access."""
from __future__ import annotations

from graphify.extractors.qt_cpp_identity import source_reference_key
from graphify.qml_resolution import build_qml_index
from graphify.qml_resolution_types import Resolution, answer, qml_metadata, source_path
from graphify.qt_project_index import QtProjectIndex
from graphify.qt_qml_bridge import build_qt_qml_bridge


class QtQmlAccessIndex:
    def __init__(self, nodes, edges, *, root, project_index=None):
        self.nodes = {node["id"]: node for node in nodes}
        self.project = project_index or QtProjectIndex(nodes, edges, root=root)
        self.native = build_qt_qml_bridge(nodes, edges, root=root, project_index=self.project)
        self.qml = build_qml_index(nodes, edges, root=root, native_index=self.native, project_index=self.project)
        self.loads, self.handles, self.names = {}, {}, {}
        self.declarations, self.unsafe_parent_components, self.qobject_types = {}, set(), {}
        for edge in edges:
            child = self.qml.nodes.get(edge.get("target"), {})
            md = qml_metadata(edge)
            if (edge.get("relation") == "contains" and edge.get("confidence") == "EXTRACTED"
                    and md.get("kind") == "declaration" and md.get("span") == qml_metadata(child).get("span")
                    and source_path(edge, self.qml.root) == source_path(child, self.qml.root)):
                self.declarations.setdefault(edge["target"], set()).add(edge["source"])
        for node in self.qml.nodes.values():
            metadata = qml_metadata(node)
            if metadata.get("construction_parent_dynamic"):
                self.mark_parent_mutation(node["id"])
            if metadata.get("kind") in {"property", "binding"} and metadata.get("raw_name") == "objectName" and isinstance(metadata.get("literal_value"), str):
                path = self.qml.paths[node["id"]]
                key = (path, metadata.get("component_key"), metadata["literal_value"])
                self.names.setdefault(key, set()).update(self.qml.objects.get((path, metadata.get("component_key"), metadata.get("object_scope_key")), []))

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

    def mark_parent_mutation(self, object_id):
        """Invalidate only the accepted component containing a proved mutation."""
        node = self.qml.nodes.get(object_id)
        if node is not None:
            self.unsafe_parent_components.add((self.qml.paths[object_id], qml_metadata(node).get("component_key")))

    def _qobject_type(self, object_id, seen=()):
        """Admit bounded Qt object types or a unique source-defined base chain.

        An unknown custom class, gadget or widget cannot inherit ownership from
        its spelling. Local providers precede the bounded builtin import view.
        """
        if object_id in seen or len(seen) >= 32:
            return False
        if object_id in self.qobject_types:
            return self.qobject_types[object_id]
        md = qml_metadata(self.qml.nodes[object_id])
        path, name = self.qml.paths[object_id], md.get("type_name") or ""
        result = self.qml.resolve_type(path, md.get("component_key") or "", name)
        if result.target_id:
            if self.native.is_provider(result.target_id):
                # This view admits only complete, accepted QObject definitions
                # with a literal registration and source/build module evidence.
                provider = self.native.metadata(result.target_id)
                accepted = bool(provider.get("creatable") and not provider.get("singleton"))
            else:
                roots = self.qml._root_objects(result.target_id)
                accepted = len(roots) == 1 and self._qobject_type(roots[0], seen + (object_id,))
        elif result.status == "ambiguous":
            accepted = False
        else:
            parts = name.split(".")
            accepted = False
            for import_id in self.qml.imports.get(path, []):
                imp = qml_metadata(self.qml.nodes[import_id])
                qualifier = imp.get("qualifier") or ""
                if imp.get("import_kind") != "module" or qualifier != (parts[0] if len(parts) == 2 else ""):
                    continue
                module, type_name = imp.get("value"), parts[-1]
                accepted |= (module in {"QtQml", "QtQuick"} and type_name in {"QtObject", "Component", "Timer", "Connections"}
                             or module == "QtQuick" and type_name in {"Item", "Rectangle", "Text", "Image", "MouseArea"})
        self.qobject_types[object_id] = accepted
        return accepted

    def _construction_parent(self, child_id):
        child, md = self.qml.nodes[child_id], qml_metadata(self.qml.nodes[child_id])
        scope = md.get("construction_parent_scope_key")
        if "construction_parent_scope_key" not in md:
            return Resolution("unavailable", reason="construction_parent_evidence_missing")
        if not scope:
            return Resolution("unavailable", reason="construction_root")
        path, component = self.qml.paths[child_id], md.get("component_key")
        parents = self.qml.objects.get((path, component, scope), [])
        parent = answer(parents, reason="construction_parent_unavailable")
        if not parent.target_id:
            return parent
        owner_ids = self.declarations.get(child_id, set())
        if len(owner_ids) != 1:
            return Resolution("unavailable", reason="construction_owner_unestablished")
        owner = self.qml.nodes.get(next(iter(owner_ids)), {})
        parent_node = self.qml.nodes[parent.target_id]
        omd, pmd = qml_metadata(owner), qml_metadata(parent_node)
        role = md.get("construction_parent_kind")
        owner_kind = "property" if role == "property" else "object" if role in {"default", "binding"} else ""
        if (child.get("_origin") != "ast" or owner.get("_origin") != "ast" or parent_node.get("_origin") != "ast"
                or omd.get("kind") != owner_kind or omd.get("object_scope_key") != scope
                or omd.get("component_key") != component or source_path(owner, self.qml.root) != path
                or not self._qobject_type(child_id) or not self._qobject_type(parent.target_id)
                or not (omd.get("span", {}).get("start_byte", -1) < md.get("span", {}).get("start_byte", -1)
                        and md.get("span", {}).get("end_byte", -1) <= omd.get("span", {}).get("end_byte", -1))
                or not (pmd.get("span", {}).get("start_byte", -1) < md.get("span", {}).get("start_byte", -1)
                        and md.get("span", {}).get("end_byte", -1) <= pmd.get("span", {}).get("end_byte", -1))):
            return Resolution("unavailable", reason="construction_parent_unestablished")
        return Resolution("resolved", parent.target_id, evidence=(child_id, next(iter(owner_ids)), parent.target_id))

    def _descendant(self, target, receiver, direct):
        seen, evidence = set(), set()
        while target not in seen and len(seen) < 256:
            seen.add(target)
            parent = self._construction_parent(target)
            if parent.reason == "construction_root":
                return False, evidence
            if parent.target_id is None:
                return None, evidence
            evidence.update(parent.evidence)
            if parent.target_id == receiver:
                return True, evidence
            if direct:
                return False, evidence
            target = parent.target_id
        return None, evidence

    def find_child(self, root_id, name, *, options="recursive"):
        """Search the evidenced construction subtree, never component-wide names."""
        if options not in {"recursive", "direct"}:
            return Resolution("unsupported", reason="find_child_options_unsupported")
        if root_id not in self.qml.nodes or qml_metadata(self.qml.nodes[root_id]).get("kind") != "object":
            return Resolution("unavailable", reason="qml_receiver_unestablished")
        md = qml_metadata(self.qml.nodes[root_id])
        key = self.qml.paths[root_id], md.get("component_key")
        candidates = self.names.get((*key, name), set()) - {root_id}
        if candidates and key in self.unsafe_parent_components:
            return Resolution("dynamic", reason="component_parenting_mutated", candidates=tuple(sorted(candidates))[:50])
        resolved, uncertain, evidence = [], [], set()
        for target in sorted(candidates):
            inside, proof = self._descendant(target, root_id, options == "direct")
            evidence.update(proof)
            if inside:
                resolved.append(target)
            elif inside is None:
                uncertain.append(target)
        if uncertain:
            return Resolution("unavailable", reason="object_parenting_unestablished", candidates=tuple(sorted(resolved + uncertain))[:50])
        return answer(resolved, reason="object_name_unavailable", evidence=tuple(sorted(evidence))[:50])

    def member(self, object_id, name, operation):
        if object_id not in self.qml.nodes or qml_metadata(self.qml.nodes[object_id]).get("kind") != "object":
            return Resolution("unavailable", reason="qml_receiver_unestablished")
        result = self.qml.follow_member(object_id, [name])
        if not result.target_id:
            return result
        metadata = self.qml.md(result.target_id)
        kind = metadata.get("kind")
        supported = {"function", "signal"} if operation == "invokeMethod" else {"property"}
        if operation in {"setProperty", "write"} and "readonly" in metadata.get("modifiers", []):
            return Resolution("unsupported", reason="readonly_property")
        return result if kind in supported else Resolution("unavailable", reason="member_role_mismatch")

    def handle(self, metadata, reference=None):
        key = source_reference_key(metadata)
        entry = self.handles.get(key) if key else None
        if entry is None:
            status = metadata.get("receiver_identity_status")
            return Resolution(status if status in {"dynamic", "ambiguous", "unsupported"} else "unavailable",
                              reason=metadata.get("receiver_identity_reason") or "qml_handle_unestablished")
        target, assignment, condition = entry
        if condition or assignment != metadata.get("receiver_assignment_byte", -1):
            return Resolution("dynamic", reason="conditional_or_reassigned_handle")
        return Resolution("resolved", target, evidence=("source_handle",))
