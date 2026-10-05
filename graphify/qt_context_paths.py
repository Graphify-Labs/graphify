"""Typed context-property chains borrow proven native APIs one hop at a time."""
from __future__ import annotations

from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.qml_resolution_types import Resolution
from graphify.qt_declared_provider import DeclaredProviderIndex


def context_path(bridge, binding, parts):
    """A finite property path is static API evidence, never QObject tree identity."""
    if not parts or len(parts) > 8:
        return Resolution("unsupported", reason="context_type_chain_limit"), {}
    types = DeclaredProviderIndex(bridge.nodes.values())
    if not types.binding_valid(binding):
        return Resolution("unavailable", reason="context_declared_provider_provenance_unavailable"), {}
    current = qt_metadata(binding).get("provider_target_id")
    visited, chain = {current}, []
    resolution = bridge.context_member(binding, parts[0])
    for name in parts[1:]:
        previous = bridge.nodes.get(resolution.target_id)
        if previous is None or qt_metadata(previous).get("kind") != "property":
            return Resolution("unavailable", reason="context_child_property_unavailable"), {}
        target, evidence = types.property_type(previous)
        if not target or target in visited:
            return Resolution("unsupported", reason="context_child_type_unavailable_or_cycle"), {}
        chain.append({"property_id": previous["id"], "class_id": current,
                      "target_class_id": target, "evidence": evidence})
        current = target
        visited.add(current)
        bridge.provider_records[binding["id"]] = {"class_id": current,
            "raw_name": qt_metadata(binding).get("exposed_name"),
            "evidence": tuple(qt_metadata(binding).get("evidence", [])) + tuple(
                item for hop in chain for item in hop["evidence"]) + (binding["id"],)}
        resolution = bridge.member(binding["id"], name)
    proof = bridge.endpoint_proof(resolution.target_id, resolution.evidence) if resolution.target_id else {}
    if proof:
        proof["type_chain"] = chain
    return resolution, proof


def valid_context_chain(binding, proof, nodes):
    """Every consumer repeats authoritative hop validation after serialization."""
    chain = proof.get("type_chain", [])
    if not isinstance(chain, list) or len(chain) > 8:
        return False
    current = binding.get("provider_target_id")
    types = DeclaredProviderIndex(nodes)
    binding_node = types.nodes.get(proof.get("provider_id"))
    if binding_node is None or qt_metadata(binding_node) != binding or not types.binding_valid(binding_node):
        return False
    visited = {current}
    for hop in chain:
        if not isinstance(hop, dict) or hop.get("class_id") != current:
            return False
        property_node = types.nodes.get(hop.get("property_id"))
        if property_node is None or qt_metadata(property_node).get("class_id") != current:
            return False
        target, evidence = types.property_type(property_node)
        if not target or target in visited or target != hop.get("target_class_id"):
            return False
        if not isinstance(hop.get("evidence"), list) or not set(evidence) <= set(hop["evidence"]):
            return False
        current = target
        visited.add(current)
    return proof.get("class_id") == current


def valid_context_endpoint(proof, nodes):
    """A serialized role label cannot turn a private/ordinary method into a signal."""
    member = nodes.get(proof.get("member_fact_id"))
    target = nodes.get(proof.get("canonical_target_id"))
    if member is None or target is None:
        return False
    md = qt_metadata(member)
    types = DeclaredProviderIndex(nodes)
    if not types.source_owned(member):
        return False
    if md.get("kind") == "property":
        return proof.get("kind") == "property" and proof.get("member_fact_id") == proof.get("canonical_target_id")
    roles = set(md.get("roles", []))
    kind = "signal" if "signal" in roles else "function" if roles & {"invokable", "slot"} else ""
    if proof.get("notify_property_id"):
        prop = types.nodes.get(proof["notify_property_id"])
        pmd = qt_metadata(prop) if prop is not None else {}
        accessors = [node for node in types.nodes.values() if qt_metadata(node).get("kind") == "property_accessor"
                     and qt_metadata(node).get("property_id") == proof["notify_property_id"]
                     and qt_metadata(node).get("accessor_role") == "notify"]
        if (pmd.get("kind") != "property" or pmd.get("class_id") != md.get("class_id")
                or pmd.get("status") != "resolved" or pmd.get("constant")
                or pmd.get("notify") != md.get("raw_name") or len(accessors) != 1
                or not types.accessor_owned(accessors[0], prop, "notify")
                or qt_metadata(accessors[0]).get("generic_target_id") != proof.get("canonical_target_id")):
            return False
    return bool(kind and proof.get("kind") == kind and md.get("kind") == "member"
                and md.get("access") == "public" and md.get("generic_target_id") == proof.get("canonical_target_id")
                and target.get("_callable") is True and target.get("_callable_class") is not True)
