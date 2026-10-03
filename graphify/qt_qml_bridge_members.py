"""Read-only native member views with overload ambiguity before ID deduplication."""
from __future__ import annotations

from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.qml_resolution_types import Resolution


class QtMemberViews:
    """QML lookups borrow canonical C++ methods and distinct Qt property facts."""
    nodes: dict[str, dict]
    provider_records: dict[str, dict]

    def __init__(self, nodes):
        self.native_members, self.native_views, self.native_proofs = {}, {}, {}
        for node in nodes:
            md = qt_metadata(node)
            if md.get("kind") in {"property", "member"} and md.get("class_id"):
                self.native_members.setdefault((md["class_id"], md.get("raw_name")), []).append(node)

    def member(self, provider_id, name):
        provider = self.provider_records.get(provider_id)
        if provider is None:
            return Resolution("unavailable", reason="native_provider_unknown")
        class_id = provider["class_id"]
        declarations = self.native_members.get((class_id, name), [])
        properties = [node for node in declarations if qt_metadata(node).get("kind") == "property"]
        methods = [node for node in declarations if qt_metadata(node).get("kind") == "member"
                   and qt_metadata(node).get("access") == "public"
                   and set(qt_metadata(node).get("roles", [])) & {"invokable", "signal", "slot"}]
        signatures = {qt_metadata(node).get("signature") for node in methods}
        if len(properties) > 1 or len(signatures) > 1 or (properties and methods):
            return Resolution("ambiguous", reason="native_member_or_overload_ambiguous",
                              candidates=tuple(sorted(node["id"] for node in properties + methods))[:50])
        selected = properties[0] if properties else methods[0] if methods else None
        if selected is None:
            return Resolution("unavailable", reason="native_member_not_qml_visible")
        md = qt_metadata(selected)
        if md.get("revision") or md.get("revisions"):
            return Resolution("unsupported", reason="native_member_revision_requires_supported_version")
        if md.get("status") != "resolved":
            return Resolution(md.get("status") or "unavailable", reason=md.get("reason") or "native_member_unavailable")
        target = selected["id"] if properties else md.get("generic_target_id")
        if not target or target not in self.nodes:
            return Resolution("unavailable", reason="canonical_native_member_unavailable")
        role = "property" if properties else "signal" if "signal" in md.get("roles", []) else "function"
        self.native_views[target] = {"kind": role, "raw_name": name, "raw_type": md.get("raw_type") or md.get("return_type", ""),
                                     "class_id": class_id, "qt_native": True, "span": md["span"],
                                     "source_file": selected["source_file"], "generic_target_id": target,
                                     "provider_id": provider_id}
        if role == "signal":
            self.native_views[target]["parameter_names"] = list(md.get("parameter_names", []))
        evidence = tuple(sorted(set(provider["evidence"] + (provider_id, selected["id"]))))
        self.native_proofs[(target, provider_id)] = {"class_id": class_id, "member_fact_id": selected["id"],
                                      "canonical_target_id": target, "provider_id": provider_id,
                                      "evidence": list(evidence), "kind": role}
        return Resolution("resolved", target, evidence=evidence)

    def endpoint_proof(self, target_id, evidence=(), *, kind=None):
        if target_id in self.provider_records and target_id in evidence:
            provider = self.provider_records[target_id]
            return {"kind": kind or "component", "provider_id": target_id, "canonical_target_id": target_id,
                    "class_id": provider["class_id"], "evidence": list(evidence)}
        proofs = [proof for (target, _), proof in self.native_proofs.items() if target == target_id
                  and proof["member_fact_id"] in evidence and proof["provider_id"] in evidence]
        return dict(proofs[0]) if len(proofs) == 1 else {}

    def metadata(self, target_id):
        if isinstance(target_id, dict):
            target_id = target_id.get("id")
        if target_id in self.provider_records:
            md = self.provider_records[target_id]
            return {"kind": "component", "raw_name": md.get("raw_name"), "singleton": md.get("singleton", False),
                    "class_id": md["class_id"], "qt_native": True, "creatable": md.get("creatable", False)}
        return dict(self.native_views.get(target_id, {}))

    def is_provider(self, target_id):
        return target_id in self.provider_records

    def context_member(self, binding_node, name):
        """A source/engine-scoped context provider does not require a type export."""
        md = qt_metadata(binding_node)
        class_id = md.get("provider_target_id")
        if md.get("kind") != "context_binding" or md.get("status") != "resolved" or class_id not in self.nodes:
            return Resolution("unavailable", reason="context_provider_provenance_unavailable")
        nid = binding_node["id"]
        if nid not in self.nodes or md.get("component_target_id") not in self.nodes:
            return Resolution("unavailable", reason="context_component_provenance_unavailable")
        self.provider_records[nid] = {"class_id": class_id, "raw_name": md.get("exposed_name") or "",
                                      "evidence": tuple(md.get("evidence") or ()) + (nid,)}
        return self.member(nid, name)
