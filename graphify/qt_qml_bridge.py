"""Scoped Qt native providers for QML indexes; no guessed global class aliases."""
from __future__ import annotations

from pathlib import Path

from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.qml_resolution_types import Resolution, answer, source_path
from graphify.qt_qml_bridge_members import QtMemberViews


class QtQmlBridgeIndex(QtMemberViews):
    """Build one source/provider table over an already accepted corpus."""

    def __init__(self, nodes, edges=(), *, root: Path, project_index=None):
        nodes = list(nodes)
        self.nodes = {node["id"]: node for node in nodes if node.get("id") and source_path(node, Path(root)) is not None}
        self.provider_records, self.modules, self.unresolved, self.module_bounds = {}, {}, {}, {}
        super().__init__(self.nodes.values())
        classes = {}
        for node in self.nodes.values():
            md = qt_metadata(node)
            if md.get("kind") == "class" and md.get("class_id") and md.get("is_definition") is True:
                classes.setdefault(md["class_id"], []).append(md)
        for node in self.nodes.values():
            md = qt_metadata(node)
            if md.get("kind") != "registration":
                continue
            value = dict(md)
            value["evidence"] = (node["id"],)
            if value.get("status") != "resolved" or value.get("class_id") not in self.nodes:
                self.unresolved[node["id"]] = value
                continue
            if value.get("module_required"):
                context = project_index.module_context(value["module_source_file"]) if project_index else None
                if project_index is None or context is None or context.target_id is None:
                    value.update(status=context.status if context else "unavailable",
                                 reason=context.reason if context else "module_metadata_unavailable")
                    self.unresolved[node["id"]] = value
                    continue
                module = project_index.module_metadata(context.target_id)
                value.update(uri=module.get("uri"), major=module.get("major"), minor=module.get("minor"),
                             evidence=value["evidence"] + context.evidence + (context.target_id,))
                if isinstance(value["major"], int) and isinstance(value["minor"], int):
                    self.module_bounds.setdefault(value["uri"], set()).add((value["major"], value["minor"]))
                    value["module_minor"] = value["minor"]
                    added = value.get("added_version") or [value["major"], 0]
                    value["minor"] = added[1] if added[0] == value["major"] else 0
            if not value.get("uri") or not isinstance(value.get("major"), int) or not isinstance(value.get("minor"), int):
                value.update(status="unavailable", reason="literal_module_version_unavailable")
                self.unresolved[node["id"]] = value
                continue
            observed = classes.get(value["class_id"], [])
            if not observed:
                value.update(status="unavailable", reason="native_class_definition_unavailable")
                self.unresolved[node["id"]] = value
                continue
            if not any(item.get("is_qobject") for item in observed):
                value.update(status="unsupported", reason="native_class_metaobject_unavailable")
                self.unresolved[node["id"]] = value
                continue
            self.provider_records[node["id"]] = value
            self.modules.setdefault(value["uri"], []).append(node["id"])

    def _version(self, uri, major, minor):
        ids = self.modules.get(uri, [])
        versions = {(self.provider_records[nid]["major"], self.provider_records[nid]["minor"]) for nid in ids}
        bounds = self.module_bounds.get(uri, set())
        versions |= bounds
        if not versions:
            return None
        if major is None:
            return max(versions)
        if minor is None:
            choices = [version for version in versions if version[0] == major]
            return max(choices) if choices else None
        return (major, minor) if (major, minor) in versions or any(ma == major and minor <= maximum for ma, maximum in bounds) else None

    def module_import(self, uri, major=None, minor=None):
        """Multiple native types in one module provide one namespace, not ambiguity."""
        version = self._version(uri, major, minor)
        if version is None:
            return Resolution("unavailable", reason="native_module_version_unavailable")
        ids = [nid for nid in self.modules[uri] if self.provider_records[nid]["major"] == version[0]]
        evidence = tuple(sorted({item for nid in ids for item in self.provider_records[nid]["evidence"]}))
        # This ID is namespace evidence only; type lookup independently checks exports.
        return Resolution("resolved", sorted(ids)[0], evidence=evidence)

    def module_type(self, uri, major, minor, name, *, importer="", **kwargs):
        version = self._version(uri, major, minor)
        if version is None:
            return Resolution("unavailable", reason="native_module_version_unavailable")
        candidates = []
        for nid in self.modules[uri]:
            md = self.provider_records[nid]
            added = tuple(md.get("added_version") or (md["major"], 0))
            removed = tuple(md["removed_version"]) if md.get("removed_version") else None
            if md.get("raw_name") != name or md.get("anonymous") or md["major"] != version[0]:
                continue
            if md["minor"] > version[1] or added > version or (removed and version >= removed):
                continue
            candidates.append(nid)
        if candidates:
            latest = max(self.provider_records[nid]["minor"] for nid in candidates)
            candidates = [nid for nid in candidates if self.provider_records[nid]["minor"] == latest]
        evidence = tuple(sorted({item for nid in candidates for item in self.provider_records[nid]["evidence"]}))
        return answer(candidates, reason="native_type_unavailable", evidence=evidence)


def build_qt_qml_bridge(nodes, edges=(), *, root, project_index=None):
    return QtQmlBridgeIndex(nodes, edges, root=Path(root), project_index=project_index)
