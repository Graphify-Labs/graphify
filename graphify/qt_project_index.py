"""Per-run literal Qt build/module/resource index over the accepted corpus only."""
from __future__ import annotations

import posixpath
from pathlib import Path

from graphify.extractors.qml_project_read import literal_path
from graphify.extractors.qml_resources import resource_url
from graphify.qml_module_index import QmlModuleIndex
from graphify.qml_resolution_types import Resolution, answer, qml_metadata, source_path
from graphify.qt_generated_conflicts import generated_conflicts
from graphify.qt_resource_index import QtResourceIndex, normalize_url


class QtProjectIndex:
    """Borrow all source dictionaries read-only; derived lookup records stay local."""
    def __init__(self, nodes, edges, *, root: Path, import_roots=None):
        self.root = Path(root).resolve()
        self.nodes, self.paths, self.modules, self.sources = {}, {}, {}, {}
        for node in nodes:
            path = source_path(node, self.root)
            if path is not None and node.get("id"):
                self.nodes[node["id"]], self.paths[node["id"]] = node, path
                md = qml_metadata(node)
                if md.get("kind") == "qt_module":
                    self.modules.setdefault(md.get("module_key"), []).append(node["id"])
                elif md.get("kind") == "qt_source":
                    self.sources.setdefault(md.get("module_key"), []).append(node["id"])
        self.module_index = QmlModuleIndex(nodes, edges, root=self.root, import_roots=import_roots)
        self.resource_index = QtResourceIndex(nodes, root=self.root)
        self.memberships, self.qml_files = {}, {}
        for key, records in self.sources.items():
            for nid in records:
                md = qml_metadata(self.nodes[nid])
                path = literal_path(self.paths[nid], md.get("value", ""))
                if path is None or path not in self.module_index.by_file:
                    continue
                self.memberships.setdefault(path, []).extend(self.modules.get(key, []))
                if md.get("source_kind") == "qml":
                    self.qml_files.setdefault(key, []).append((path, nid))
                elif md.get("source_kind") == "qrc":
                    for aid in self.module_index.by_file[path]:
                        alias = qml_metadata(self.nodes[aid])
                        if alias.get("kind") == "resource_alias":
                            target = alias.get("target_path")
                            if target in self.module_index.components:
                                self.qml_files.setdefault(key, []).append((target, aid))
        self.diagnostics = generated_conflicts(self)

    def module_metadata(self, module_id: str) -> dict:
        return dict(qml_metadata(self.nodes[module_id]))

    def module_context(self, source_file: str) -> Resolution:
        normalized = source_path({"source_file": source_file}, self.root)
        ids = self.memberships.get(normalized, [])
        result = answer(ids, reason="source_module_context_unavailable", evidence=ids)
        return Resolution(result.status, result.target_id, result.reason,
                          tuple(sorted(set(ids))[:50]), result.candidates)

    def _eligible(self, md, major, minor):
        if major is None:
            return True
        if major != md.get("major"):
            return False
        return minor is None or (isinstance(md.get("minor"), int) and minor <= md["minor"])

    def module_import(self, uri: str, major=None, minor=None) -> Resolution:
        """Build-declared namespaces require exact URI/version/provider evidence."""
        groups = {}
        for ids in self.modules.values():
            for mid in ids:
                md = qml_metadata(self.nodes[mid])
                if md.get("uri") == uri and self._eligible(md, major, minor):
                    key = (md.get("target_name"), md.get("uri"), md.get("major"), md.get("minor"))
                    groups.setdefault(key, []).append(mid)
        evidence = tuple(sorted({mid for ids in groups.values() for mid in ids})[:50])
        if len(groups) > 1:
            return Resolution("ambiguous", reason="duplicate_module_provider",
                              candidates=tuple(sorted(ids[0] for ids in groups.values())[:50]),
                              evidence=evidence)
        if groups:
            return Resolution("resolved", sorted(next(iter(groups.values())))[0], evidence=evidence)
        return Resolution("unavailable", reason="module_or_version_unavailable")

    def module_type(self, uri, major, minor, name, *, importer="", **kwargs) -> Resolution:
        """Match the established QML index seam without adding runtime visibility."""
        return self.resolve_component(uri, name, major, minor)

    def resolve_component(self, uri: str, type_name: str, major=None, minor=None) -> Resolution:
        """Resolve declared module QML sources, plus established qmldir visibility."""
        namespace = self.module_import(uri, major, minor)
        if namespace.status == "ambiguous":
            return namespace
        candidates, evidence, providers = [], [], []
        for key, ids in self.modules.items():
            for mid in ids:
                md = qml_metadata(self.nodes[mid])
                if md.get("uri") != uri:
                    continue
                providers.append(mid)
                if not self._eligible(md, major, minor):
                    continue
                for path, sid in self.qml_files.get(key, []):
                    name = posixpath.basename(path).removesuffix(".ui.qml").removesuffix(".qml")
                    if name == type_name and name[:1].isupper():
                        candidates.extend(self.module_index.components.get(path, []))
                        evidence.extend((mid, sid))
        declared = answer(candidates, reason="module_type_unavailable", evidence=evidence)
        existing = self.module_index.module_type(uri, major, minor, type_name, importer="")
        if existing.status in {"ambiguous", "unsupported"}:
            return existing
        if existing.target_id:
            return answer(candidates + [existing.target_id], evidence=evidence + list(existing.evidence))
        if declared.target_id or declared.status == "ambiguous":
            return declared
        if providers:
            return Resolution("unavailable", reason="module_type_or_version_unavailable", evidence=tuple(providers[:50]))
        return existing

    def resolve_url(self, literal_url: str, base_url: str | None = None) -> Resolution:
        # CMake-generated aliases exist only when the prefix is explicit; policy
        # defaults and source-property aliases are never guessed.
        result = self.resource_index.resolve_url(literal_url, base_url)
        if result.reason != "resource_alias_unavailable":
            return result
        logical = normalize_url(literal_url, base_url)
        if isinstance(logical, Resolution):
            return logical
        matches, evidence = [], []
        for key, ids in self.modules.items():
            for mid in ids:
                md = qml_metadata(self.nodes[mid])
                prefix = md.get("resource_prefix")
                if not isinstance(prefix, str):
                    continue
                prefix = prefix.rstrip("/")
                if not md.get("no_resource_target_path"):
                    prefix += "/" + md["uri"].replace(".", "/")
                for path, sid in self.qml_files.get(key, []):
                    smd = qml_metadata(self.nodes[sid])
                    if resource_url(prefix, smd.get("value", "")) == logical:
                        matches.extend(self.module_index.components.get(path, []))
                        evidence.extend((mid, sid))
        return answer(matches, reason="resource_alias_unavailable", evidence=evidence)
