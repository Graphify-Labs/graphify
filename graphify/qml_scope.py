"""Component/object/member lookup; dynamic instance ancestry is intentionally absent."""

from __future__ import annotations

import posixpath

from graphify.qml_module_index import QmlModuleIndex, combine
from graphify.qml_resolution_types import Resolution, answer, qml_metadata, relative_reference


class QmlProjectIndex(QmlModuleIndex):
    """Module imports and lexical declarations share one bounded, per-run owner."""

    def __init__(self, nodes, edges, **kwargs):
        super().__init__(nodes, edges, **kwargs)
        self.objects, self.members, self.inline = {}, {}, {}
        for nid, node in self.nodes.items():
            md, path = qml_metadata(node), self.paths[nid]
            component = md.get("component_key", "")
            scope = md.get("object_scope_key", "")
            if md.get("kind") == "object":
                self.objects.setdefault((path, component, scope), []).append(nid)
            elif md.get("kind") in {"property", "function", "signal", "enum"}:
                self.members.setdefault((path, component, scope, md.get("raw_name")), []).append(nid)
            elif md.get("kind") == "inline_component":
                enclosing = md.get("enclosing_component_key") or md.get("parent_component_key")
                if enclosing is None:
                    owners = [qml_metadata(self.nodes[parent]).get("component_key")
                              for parent in self.parents.get(nid, ()) if parent in self.nodes]
                    enclosing = owners[0] if len(set(owners)) == 1 else None
                self.inline.setdefault((path, enclosing, md.get("raw_name")), []).append(nid)

    def module_import(self, uri, major=None, minor=None):
        results = [super().module_import(uri, major, minor)]
        if self.native_index:
            results.append(self.native_index.module_import(uri, major, minor))
        if self.project_index:
            results.append(self.project_index.module_import(uri, major, minor))
        # One build namespace and its native registrations describe the same
        # module when the exact context node is carried in native evidence.
        resolved = [result for result in results if result.target_id]
        if len(resolved) > 1:
            namespaces = [result for result in resolved if any(result.target_id in other.evidence
                          for other in resolved if other is not result)]
            if len(namespaces) == 1:
                return Resolution("resolved", namespaces[0].target_id,
                                  evidence=tuple(sorted({item for result in resolved for item in result.evidence})))
        return combine(results)

    def module_type(self, uri, major, minor, name, *, importer, **kwargs):
        results = [super().module_type(uri, major, minor, name, importer=importer, **kwargs)]
        if kwargs.get("_export_kind", "type") == "type":
            if self.native_index:
                results.append(self.native_index.module_type(uri, major, minor, name, importer=importer))
            if self.project_index:
                results.append(self.project_index.resolve_component(uri, name, major, minor))
        return combine(results)

    def resolve_type(self, file: str, component_key: str, name: str) -> Resolution:
        """Inline names shadow imports; an import qualifier is document-local."""
        parts = name.split(".")
        local = self.inline.get((file, component_key, name), [])
        if local:
            return answer(local)
        results = []
        for import_id in self.imports.get(file, []):
            md = qml_metadata(self.nodes[import_id])
            qualifier = md.get("qualifier") or ""
            if qualifier:
                if len(parts) != 2 or parts[0] != qualifier:
                    continue
                wanted = parts[1]
            elif len(parts) == 1:
                wanted = name
            else:
                continue
            value = str(md.get("value") or "")
            kind = md.get("import_kind")
            if kind == "module":
                result = self.module_type(value, md.get("major"), md.get("minor"), wanted, importer=file)
            elif kind == "directory":
                directory = relative_reference(file, value)
                result = (self.directory_type(directory, wanted, importer=file) if directory is not None else
                          Resolution("unavailable", reason="directory_outside_corpus"))
            else:
                continue
            if result.status == "resolved":
                result = Resolution("resolved", result.target_id, evidence=result.evidence + (import_id,))
            results.append(result)
        if len(parts) == 1:
            # Implicit local-directory visibility cannot become global basename search.
            results.append(self.directory_type(posixpath.dirname(file), name, importer=file))
        return combine(results)

    def _root_objects(self, component_id: str) -> list[str]:
        if self.native_index and self.native_index.is_provider(component_id):
            return [component_id]
        md = qml_metadata(self.nodes[component_id])
        component = md.get("component_key")
        file = self.paths[component_id]
        candidates = []
        for (path, key, _), ids in self.objects.items():
            if path != file or key != component:
                continue
            for nid in ids:
                if component_id in self.parents.get(nid, ()) or not qml_metadata(self.nodes[nid]).get("parent_scope_key"):
                    candidates.append(nid)
        return sorted(candidates)

    def _object_member(self, object_id: str, name: str, seen=()) -> Resolution:
        if self.native_index and self.native_index.is_provider(object_id):
            return self.native_index.member(object_id, name)
        if object_id in seen or len(seen) >= 32:
            return Resolution("unsupported", reason="inheritance_cycle_or_limit")
        md = qml_metadata(self.nodes[object_id])
        file, component, scope = self.paths[object_id], md.get("component_key"), md.get("object_scope_key")
        local = self.members.get((file, component, scope, name), [])
        if local:
            visible = [nid for nid in local if not qml_metadata(self.nodes[nid]).get("internal")]
            return answer(visible, reason="member_not_visible")
        type_name = md.get("type_name") or md.get("raw_type")
        if not type_name:
            return Resolution("unavailable", reason="receiver_type_unknown")
        base = self.resolve_type(file, component or "", type_name)
        if base.target_id is None:
            return base
        return combine([self._object_member(nid, name, seen + (object_id,))
                        for nid in self._root_objects(base.target_id)], reason="member_unavailable")

    def resolve_member(self, file: str, component_key: str, object_scope_key: str,
                       name: str, *, lexical_names=()) -> Resolution:
        """IDs precede properties; lexical JS bindings prevent any QML fallback."""
        parts = name.split(".")
        if parts[0] in lexical_names:
            return Resolution("dynamic", reason="javascript_lexical_binding")
        if parts[0] in {"this", "parent"}:
            objects = self.objects.get((file, component_key, object_scope_key), [])
            if parts[0] == "parent":
                scopes = [qml_metadata(self.nodes[nid]).get("static_parent_scope_key") for nid in objects]
                objects = [nid for scope in scopes if scope for nid in
                           self.objects.get((file, component_key, scope), [])]
            owner = answer(objects, reason="runtime_parent_unestablished" if parts[0] == "parent" else
                           "receiver_scope_unavailable")
            return (self.follow_member(owner.target_id, parts[1:]) if owner.target_id is not None and
                    len(parts) > 1 else owner)
        candidates = []
        for (path, component, _), ids in self.objects.items():
            if path == file and component == component_key:
                candidates.extend(nid for nid in ids if qml_metadata(self.nodes[nid]).get("object_id") == parts[0])
        if candidates:
            target = answer(candidates)
            if len(parts) == 1 or target.target_id is None:
                return target
            return self._follow_member(target.target_id, parts[1:])
        if len(parts) > 1:
            # An own/root property precedes a type namespace with the same spelling.
            head = self.resolve_member(file, component_key, object_scope_key, parts[0])
            if head.target_id is not None:
                return self.follow_member(head.target_id, parts[1:])
            if head.status == "ambiguous":
                return head
            target = self.resolve_type(file, component_key, parts[0])
            if target.target_id is not None:
                md = self.md(target.target_id)
                if not md.get("singleton"):
                    return Resolution("unsupported", reason="type_is_not_instance")
                return combine([self._follow_member(nid, parts[1:]) for nid in self._root_objects(target.target_id)])
            # Qualified imported singleton (Alias.State.value).
            if len(parts) > 2:
                target = self.resolve_type(file, component_key, ".".join(parts[:2]))
                if target.target_id is not None and self.md(target.target_id).get("singleton"):
                    return combine([self._follow_member(nid, parts[2:]) for nid in self._root_objects(target.target_id)])
                if target.status == "resolved":
                    return Resolution("unsupported", reason="type_is_not_instance")
            return target
        own_objects = self.objects.get((file, component_key, object_scope_key), [])
        own = combine([self._object_member(nid, name) for nid in own_objects])
        if own.status in {"resolved", "ambiguous"}:
            return own
        roots = [nid for nid, node in self.nodes.items() if self.paths[nid] == file and
                 qml_metadata(node).get("kind") in {"component", "inline_component"} and
                 qml_metadata(node).get("component_key") == component_key]
        return combine([self._object_member(nid, name) for root in roots for nid in self._root_objects(root)],
                       reason="runtime_context_or_member_unavailable")

    def _follow_member(self, object_id: str, parts: list[str]) -> Resolution:
        target = self._object_member(object_id, parts[0])
        if len(parts) == 1 or target.target_id is None:
            return target
        return self.follow_member(target.target_id, parts[1:])

    def follow_member(self, target_id: str, parts) -> Resolution:
        """Continue an established object/typed-property target, without alias execution."""
        parts = list(parts)
        if len(parts) > 32:
            return Resolution("unsupported", reason="member_chain_limit")
        if not parts:
            return answer([target_id])
        if self.native_index and self.native_index.is_provider(target_id):
            return self._follow_member(target_id, parts)
        md = qml_metadata(self.nodes[target_id])
        if md.get("kind") == "object":
            return self._follow_member(target_id, parts)
        provider = self.resolve_type(self.paths[target_id], md.get("component_key") or "",
                                     md.get("raw_type") or "")
        if provider.target_id is None:
            return provider
        return combine([self._follow_member(nid, parts) for nid in self._root_objects(provider.target_id)])
