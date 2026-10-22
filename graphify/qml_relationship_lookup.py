"""Bounded alias and imported-script lookup over accepted source facts only."""
from __future__ import annotations

from graphify.qml_resolution_types import Resolution, answer, qml_metadata, relative_reference


class RelationshipLookup:
    """No global labels, value evaluation, runtime IDs or borrowed-node mutation."""

    def __init__(self, index):
        self.index = index
        self.aliases, self.functions, self.exports, self.script_imports = {}, {}, {}, {}
        for nid, node in index.nodes.items():
            md, path = qml_metadata(node), index.paths[nid]
            if md.get("kind") == "alias":
                self.aliases.setdefault(md.get("owner_id"), []).append(nid)
            elif md.get("kind") == "qml_script_function":
                self.functions.setdefault((path, md.get("raw_name")), []).append(nid)
                for name in md.get("export_names", []):
                    self.exports.setdefault((path, name), []).append(nid)
            elif md.get("kind") == "script_import":
                self.script_imports.setdefault((path, md.get("qualifier")), []).append(nid)

    def _script_function(self, file, name, *, external):
        table = self.exports if external else self.functions
        candidates = [nid for nid in table.get((file, name), [])
                      if qml_metadata(self.index.nodes[nid]).get("static_callable") is not False]
        return answer(candidates, reason="script_member_not_exported_or_missing")

    def _script(self, file, reference):
        parts = reference.split(".")
        if len(parts) == 1:
            local = self._script_function(file, reference, external=False)
            if local.status in {"resolved", "ambiguous"}:
                return local
        imports = self.script_imports.get((file, parts[0]), [])
        answers = []
        for nid in imports:
            md = qml_metadata(self.index.nodes[nid])
            target = relative_reference(file, md.get("value") or "")
            if target is None or target not in self.index.by_file:
                answers.append(Resolution("unavailable", reason="script_outside_corpus"))
            elif md.get("import_kind") == "namespace" and len(parts) == 2:
                answers.append(self._script_function(target, parts[1], external=True))
            elif md.get("import_kind") == "named" and len(parts) == 1:
                answers.append(self._script_function(target, md.get("exported_name"), external=True))
            else:
                answers.append(Resolution("dynamic", reason="script_namespace_or_value_is_not_callable"))
        return self._combine(answers, reason="script_runtime_context_unavailable")

    @staticmethod
    def _combine(results, *, reason):
        results = list(results)
        ids, evidence = [], []
        for result in results:
            if result.target_id:
                ids.append(result.target_id)
            ids.extend(result.candidates)
            evidence.extend(result.evidence)
        selected = answer(ids, reason=reason, evidence=evidence)
        if selected.status != "unavailable":
            return selected
        return results[0] if results else selected

    def _qml_script(self, file, component, reference):
        parts, results = reference.split("."), []
        if len(parts) == 2:
            for nid in self.index.imports.get(file, []):
                md = qml_metadata(self.index.nodes[nid])
                if md.get("import_kind") != "script" or md.get("qualifier") != parts[0]:
                    continue
                target = relative_reference(file, md.get("value") or "")
                result = self._script_function(target, parts[1], external=True)
                results.append(Resolution(result.status, result.target_id, result.reason,
                                          result.evidence + (nid,), result.candidates))
        # Script namespaces and object types are distinct qmldir export roles.
        for nid in self.index.imports.get(file, []):
            md = qml_metadata(self.index.nodes[nid])
            qualifier = md.get("qualifier") or ""
            wanted = parts[1:] if qualifier and parts[0] == qualifier else parts if not qualifier else []
            if len(wanted) != 2:
                continue
            if md.get("import_kind") == "module":
                provider = self.index.module_script(md.get("value"), md.get("major"), md.get("minor"), wanted[0], importer=file)
            elif md.get("import_kind") == "directory":
                directory = relative_reference(file, md.get("value") or "")
                provider = self.index.directory_script(directory, wanted[0], importer=file)
            else:
                continue
            if provider.status == "resolved":
                target = self.index.paths[provider.target_id]
                result = self._script_function(target, wanted[1], external=True)
                results.append(Resolution(result.status, result.target_id, result.reason,
                                          result.evidence + provider.evidence + (nid,), result.candidates))
            elif provider.status == "ambiguous":
                results.append(provider)
        return self._combine(results, reason="script_import_not_visible")

    def chase_alias(self, result, seen=()):
        if result.status != "resolved" or result.target_id not in self.aliases:
            return result
        if result.target_id in seen or len(seen) >= 32:
            return Resolution("unsupported", reason="alias_cycle_or_limit")
        sites = self.aliases[result.target_id]
        if len(sites) != 1:
            return Resolution("ambiguous", reason="duplicate_alias_binding", candidates=tuple(sites[:50]))
        site = self.index.nodes[sites[0]]
        md = qml_metadata(site)
        resolved = self.resolve(site, md.get("reference") or "", seen=seen + (result.target_id,))
        return Resolution(resolved.status, resolved.target_id, resolved.reason,
                          tuple(dict.fromkeys(result.evidence + (site["id"],) + resolved.evidence)), resolved.candidates)

    def resolve(self, site, reference, *, seen=()):
        md, file = qml_metadata(site), self.index.paths[site["id"]]
        if not reference:
            return Resolution("dynamic", reason=md.get("reason") or "computed_or_runtime_target")
        parts = reference.split(".")
        lexical = md.get("lexical_names") or []
        if md.get("lexical_shadowed") or parts[0] in lexical:
            target = md.get("lexical_target_id")
            if target and len(parts) == 1 and target in self.index.nodes:
                return answer([target])
            return Resolution("dynamic", reason="javascript_lexical_binding")
        if md.get("script_file"):
            return self._script(file, reference)
        component, scope = md.get("component_key"), md.get("object_scope_key")
        # Local QML names shadow an imported JS qualifier, even when they cannot
        # be continued statically. A computed namespace never bypasses shadowing.
        head = self.index.resolve_member(file, component, scope, parts[0])
        if head.status == "ambiguous":
            return head
        if head.status == "resolved":
            # Follow each established prefix separately so aliases inside a chain
            # can be chased without pretending an alias's raw type is a provider.
            result = self.chase_alias(head, seen)
            for member in parts[1:]:
                if result.status != "resolved":
                    return result
                evidence = result.evidence
                result = self.chase_alias(self.index.follow_member(result.target_id, [member]), seen)
                result = Resolution(result.status, result.target_id, result.reason,
                                    tuple(dict.fromkeys(evidence + result.evidence)), result.candidates)
            return result
        script = self._qml_script(file, component, reference)
        if script.status in {"resolved", "ambiguous"} or script.evidence:
            return script
        result = self.index.resolve_member(file, component, scope, reference, lexical_names=lexical)
        return self.chase_alias(result, seen)
