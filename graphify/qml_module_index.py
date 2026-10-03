"""Per-run module/directory indexes over accepted facts; never widen the corpus."""

from __future__ import annotations

import posixpath
from pathlib import Path

from graphify.qml_resolution_types import Resolution, answer, qml_metadata, relative_reference, source_path

MAX_MODULE_RESOLUTION_STEPS = 1024


class QmlModuleIndex:
    """Own lookup tables, borrow declarations read-only, and preserve provider identity."""

    def __init__(self, nodes, edges, *, root: Path, import_roots=None):
        self.root = Path(root).resolve()
        self.import_roots = tuple(import_roots if import_roots is not None else (".",))
        self.nodes = {}
        self.paths = {}
        self.by_file = {}
        self.parents = {}
        for node in nodes:
            path = source_path(node, self.root)
            if path is not None and node.get("id"):
                self.nodes[node["id"]] = node
                self.paths[node["id"]] = path
                self.by_file.setdefault(path, []).append(node["id"])
        for edge in edges:
            if edge.get("relation") == "contains":
                self.parents.setdefault(edge["target"], set()).add(edge["source"])
        self.components = {}
        self.imports = {}
        self.providers = {}
        self.exports = {}
        for nid, node in self.nodes.items():
            md, path = qml_metadata(node), self.paths[nid]
            kind = md.get("kind")
            if kind == "component":
                self.components.setdefault(path, []).append(nid)
            elif kind == "import":
                self.imports.setdefault(path, []).append(nid)
            elif kind == "module" or (kind == "file" and md.get("metadata_format") == "qmldir"):
                self.providers.setdefault(posixpath.dirname(path), []).append(nid)
            elif kind == "export":
                self.exports.setdefault(posixpath.dirname(path), []).append(nid)
        # A module declaration supersedes its containing qmldir file as provider.
        for directory, ids in self.providers.items():
            modules = [nid for nid in ids if qml_metadata(self.nodes[nid]).get("kind") == "module"]
            self.providers[directory] = sorted(modules or ids)

    def _target(self, export: str, *, importer: str) -> Resolution:
        node, md = self.nodes[export], qml_metadata(self.nodes[export])
        source = self.paths[export]
        if md.get("internal") and posixpath.dirname(importer) != posixpath.dirname(source):
            return Resolution("unavailable", reason="internal_export", evidence=(export,))
        target = relative_reference(source, str(md.get("target_path") or ""))
        if target is None or target not in self.by_file:
            return Resolution("unavailable", reason="target_outside_corpus", evidence=(export,))
        candidates = self.components.get(target, [])
        if md.get("export_kind") == "script":
            candidates = [nid for nid in self.by_file[target]
                          if self.nodes[nid].get("label") == posixpath.basename(target)]
        if md.get("singleton") and candidates:
            if not all(qml_metadata(self.nodes[nid]).get("singleton") for nid in candidates):
                return Resolution("unavailable", reason="singleton_pragma_missing", evidence=(export,))
        return answer(candidates, reason="component_unavailable", evidence=(export,))

    def directory_type(self, directory: str, name: str, *, importer: str) -> Resolution:
        exports = self.exports.get(directory)
        if exports is not None:
            matches = [nid for nid in exports if qml_metadata(self.nodes[nid]).get("raw_name") == name and
                       qml_metadata(self.nodes[nid]).get("export_kind") == "type"]
            versions = [(qml_metadata(self.nodes[nid]).get("major"),
                         qml_metadata(self.nodes[nid]).get("minor")) for nid in matches]
            versioned = [version for version in versions if version[0] is not None]
            if versioned:
                latest = max(versioned)
                matches = [nid for nid, version in zip(matches, versions) if version == latest]
            results = [self._target(nid, importer=importer) for nid in matches]
            return combine(results, reason="type_unavailable")
        candidates = []
        for path, ids in self.components.items():
            if posixpath.dirname(path) == directory and posixpath.basename(path) == name + ".qml":
                candidates.extend(ids)
        return answer(candidates, reason="type_unavailable")

    def module_provider(self, uri: str, major=None, minor=None) -> Resolution:
        candidates = []
        for rank, import_root in enumerate(self.import_roots):
            prefix = posixpath.normpath(str(import_root).replace("\\", "/"))
            if prefix.startswith("/") or prefix == ".." or prefix.startswith("../") or ":" in prefix:
                continue
            expected = posixpath.normpath(posixpath.join(prefix, uri.replace(".", "/")))
            for directory, ids in self.providers.items():
                suffix = directory[len(expected):] if directory.startswith(expected) else "invalid"
                if suffix not in {"", f".{major}", f".{major}.{minor}"}:
                    continue
                for nid in ids:
                    if qml_metadata(self.nodes[nid]).get("uri") != uri:
                        continue
                    # Explicit root order and exact versioned layout are evidence.
                    priority = (rank, 0 if minor is not None and suffix == f".{major}.{minor}" else
                                1 if major is not None and suffix == f".{major}" else 2)
                    candidates.append((priority, nid))
        if not candidates:
            return Resolution("unavailable", reason="module_not_in_import_roots")
        priority = min(item[0] for item in candidates)
        return answer([nid for key, nid in candidates if key == priority], reason="module_unavailable")

    def module_import(self, uri: str, major=None, minor=None) -> Resolution:
        """Require an observed available module version before selecting its types."""
        provider = self.module_provider(uri, major, minor)
        if provider.status != "resolved":
            return provider
        selected, _, _ = self._module_version(provider, major, minor)
        return selected

    def _module_version(self, provider: Resolution, major, minor):
        if provider.target_id is None:
            return provider, major, minor
        source = self.paths[provider.target_id]
        directory = posixpath.dirname(source)
        records = self.exports.get(directory, [])
        versions = set()
        for nid in records:
            md = qml_metadata(self.nodes[nid])
            ma, mi = md.get("major"), md.get("minor")
            if isinstance(ma, int) and isinstance(mi, int):
                versions.add((ma, mi))
        if major is not None and not versions:
            return Resolution("unavailable", reason="module_version_unavailable"), major, minor
        if major is None and versions:
            major, minor = max(versions)
        elif major is not None and minor is None:
            minors = [mi for ma, mi in versions if ma == major]
            if not minors:
                return Resolution("unavailable", reason="module_version_unavailable"), major, minor
            minor = max(minors)
        if versions and (major, minor) not in versions:
            return Resolution("unavailable", reason="module_version_unavailable"), major, minor
        return provider, major, minor

    def module_type(self, uri: str, major, minor, name: str, *, importer: str, seen=(), _budget=None,
                    _export_kind="type") -> Resolution:
        # One query owns the work budget across branches, including repeated DAG paths.
        budget = [MAX_MODULE_RESOLUTION_STEPS] if _budget is None else _budget
        budget[0] -= 1
        if budget[0] < 0:
            return Resolution("unsupported", reason="module_resolution_work_limit")
        key = (uri, major, minor)
        if key in seen or len(seen) >= 32:
            return Resolution("unsupported", reason="module_import_cycle_or_limit")
        provider = self.module_import(uri, major, minor)
        if provider.target_id is None:
            return provider
        _, major, minor = self._module_version(provider, major, minor)
        source = self.paths[provider.target_id]
        directory = posixpath.dirname(source)
        records = self.exports.get(directory, [])
        related = [self.nodes[nid] for nid in self.by_file[source]]
        if any(qml_metadata(node).get("kind") == "prefer" for node in related):
            return Resolution("unsupported", reason="preferred_path_requires_resource_index")
        matches = []
        for nid in records:
            md = qml_metadata(self.nodes[nid])
            version = (md.get("major"), md.get("minor"))
            if md.get("export_kind") == _export_kind and md.get("raw_name") == name and (version[0] is None or
                                               (version[0] == major and isinstance(version[1], int) and
                                                isinstance(minor, int) and version[1] <= minor)):
                matches.append(((-1, -1) if version[0] is None else version, nid))
        if matches:
            best = max(version for version, _ in matches)
            result = combine([self._target(nid, importer=importer) for version, nid in matches if version == best])
            return Resolution(result.status, result.target_id, result.reason,
                              tuple(sorted(set(result.evidence + (provider.target_id,)))), result.candidates)
        imports = [qml_metadata(node) for node in related if qml_metadata(node).get("kind") == "module_import"]
        return combine([self.module_type(md["uri"], major if md.get("auto") else md.get("major"),
                                         minor if md.get("auto") else md.get("minor"), name,
                                         importer=importer, seen=seen + (key,), _budget=budget,
                                         _export_kind=_export_kind) for md in imports])

    def module_script(self, uri: str, major, minor, name: str, *, importer: str) -> Resolution:
        """Script namespace exports have a separate lookup role from object types."""
        return self.module_type(uri, major, minor, name, importer=importer, _export_kind="script")


def combine(results, *, reason="type_unavailable") -> Resolution:
    """Preserve ambiguity even when a competing result also has a unique endpoint."""
    results = list(results)
    blocked = [result for result in results if result.status == "unsupported"]
    if blocked:
        return blocked[0]
    ids, evidence = [], []
    for result in results:
        if result.target_id:
            ids.append(result.target_id)
        ids.extend(result.candidates)
        evidence.extend(result.evidence)
    if ids:
        return answer(ids, reason=reason, evidence=evidence)
    if results:
        return results[0]
    return Resolution("unavailable", reason=reason)
