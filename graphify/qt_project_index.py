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
        accepted, declarations = [], {}
        for node in nodes:
            md = qml_metadata(node)
            # Only this index's source-owned providers have declaration-local
            # identity. Generic namespaces intentionally share IDs across files;
            # their ordinary graph identity/provenance policy remains unchanged.
            if node.get("id") and md.get("kind") in {"qt_module", "qt_source", "resource_alias"}:
                previous = declarations.get(node["id"])
                if previous is not None:
                    if previous != node:
                        raise ValueError("QML_METADATA: conflicting records for declaration identity")
                    continue
                declarations[node["id"]] = node
            path = source_path(node, self.root)
            if path is not None and node.get("id"):
                accepted.append(node)
                self.nodes[node["id"]], self.paths[node["id"]] = node, path
                if md.get("kind") == "qt_module":
                    self.modules.setdefault(md.get("module_key"), []).append(node["id"])
                elif md.get("kind") == "qt_source":
                    self.sources.setdefault(md.get("module_key"), []).append(node["id"])
        # Repeated transport copies of one declaration ID do not create another
        # provider. Distinct source declarations retain their separate identities.
        self.module_index = QmlModuleIndex(accepted, edges, root=self.root, import_roots=import_roots)
        self.resource_index = QtResourceIndex(accepted, root=self.root)
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
        providers = []
        for ids in self.modules.values():
            for mid in ids:
                md = qml_metadata(self.nodes[mid])
                if md.get("uri") == uri and self._eligible(md, major, minor):
                    providers.append(mid)
        # A common CMake target spelling does not prove two declarations share
        # build provenance. Only the exact source-owned identity may coalesce.
        evidence = tuple(sorted(set(providers))[:50])
        if len(set(providers)) > 1:
            return Resolution("ambiguous", reason="duplicate_module_provider",
                              candidates=evidence,
                              evidence=evidence)
        if providers:
            return Resolution("resolved", evidence[0], evidence=evidence)
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
        # Explicit QRC/CMake aliases and module-generated mappings compete in
        # the same runtime namespace. Resolve their declarations together before
        # granting any endpoint; an earlier index must not pick the winner.
        logical = normalize_url(literal_url, base_url)
        if isinstance(logical, Resolution):
            return logical
        explicit = self.resource_index.resolve_url(literal_url, base_url)
        explicit = Resolution(explicit.status, explicit.target_id, explicit.reason,
                              tuple(sorted(set(explicit.evidence))[:50]),
                              tuple(sorted(set(explicit.candidates))[:50]))
        providers = self._module_resource_providers(logical)
        if not providers:
            return explicit
        # An unsupported, ambiguous or outside-corpus explicit mapping cannot
        # borrow an otherwise available module mapping to acquire authority.
        if explicit.reason != "resource_alias_unavailable" and explicit.status != "resolved":
            return explicit
        evidence = set(explicit.evidence)
        matches = [explicit.target_id] if explicit.target_id else []
        for (module, source), targets in providers.items():
            evidence.update((module, source))
            matches.extend(targets)
        evidence = tuple(sorted(evidence)[:50])
        if any(not targets for targets in providers.values()):
            return Resolution("unavailable", reason="resource_target_outside_corpus", evidence=evidence)
        if explicit.target_id or len(providers) > 1:
            # Two distinct declarations remain ambiguous even for the same
            # target. Exact repeated declaration copies already coalesced above.
            return Resolution("ambiguous", reason="duplicate_resource_alias", evidence=evidence,
                              candidates=tuple(sorted(set(matches))[:50]))
        return answer(matches, reason="resource_alias_unavailable", evidence=evidence)

    def _module_resource_providers(self, logical):
        """Collect declarations without borrowing accepted endpoints for missing inputs."""
        providers = {}
        for key, ids in self.modules.items():
            for mid in set(ids):
                md = qml_metadata(self.nodes[mid])
                prefix = md.get("resource_prefix")
                if not isinstance(prefix, str):
                    continue
                prefix = prefix.rstrip("/")
                if not md.get("no_resource_target_path"):
                    prefix += "/" + md["uri"].replace(".", "/")
                for sid in set(self.sources.get(key, [])):
                    smd = qml_metadata(self.nodes[sid])
                    if smd.get("source_kind") != "qml":
                        continue
                    alias = smd.get("resource_alias", smd.get("value", ""))
                    if isinstance(alias, str) and resource_url(prefix, alias) == logical:
                        path = literal_path(self.paths[sid], smd.get("value", ""))
                        providers[mid, sid] = tuple(self.module_index.components.get(path, []))
        return providers
