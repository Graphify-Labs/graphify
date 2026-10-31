"""Resolve source-established external singleton setup without runtime injection."""
from __future__ import annotations

import re

from graphify.extractors.qt_cpp_facts import qt_edge, qt_metadata, update_qt
from graphify.extractors.qt_cpp_facts import scope_owner
from graphify.extractors.qt_cpp_identity import source_reference_key
from graphify.qt_declared_provider import DeclaredProviderIndex


def _validate(site):
    """Reject malformed source transport before using it as relationship evidence."""
    md = qt_metadata(site)
    span = md.get("span")
    if (not isinstance(span, dict)
            or not all(type(span.get(key)) is int for key in ("start_byte", "end_byte"))
            or not 0 <= span["start_byte"] < span["end_byte"]
            or md.get("operation") != "setExternalSingletonInstance"
            or type(md.get("api_supported")) is not bool or type(md.get("conditional")) is not bool
            or type(md.get("prior_singleton_use")) is not bool
            or ("singleton_state_reset" in md and type(md["singleton_state_reset"]) is not bool)
            or ("engine_escaped" in md and type(md["engine_escaped"]) is not bool)
            or not isinstance(md.get("receiver_potential_declaration_id"), str)
            or md.get("runtime_success") != "unverified" or md.get("lifetime_status") != "unverified"
            or md.get("ownership_transfer") is not False
            or any(md.get(key) is not None and not isinstance(md[key], str) for key in ("module_uri", "type_name"))
            or any(not isinstance(md.get(key), str) for key in ("receiver_declaration_id", "provider_declaration_id",
                                                               "receiver_identity_status", "provider_identity_status"))):
        raise ValueError("QT_METADATA: external singleton source transport is inconsistent")


def _possible_key(md):
    """This lexical key is only an interference rejection, never positive proof."""
    identity, owner = md.get("receiver_potential_declaration_id"), scope_owner(md)
    return (owner, identity) if isinstance(identity, str) and re.fullmatch(r"[0-9a-f]{64}", identity) and isinstance(owner, str) and owner else None


def _rejection(site, setups, loads, index, declared):
    """One rejected source precondition can never be repaired by a global label."""
    md = qt_metadata(site)
    if md.get("api_supported") is not True:
        return "unsupported", "external_singleton_api_unestablished", None
    if md.get("conditional"):
        return "dynamic", "conditional_external_singleton_setup", None
    for role in ("receiver", "provider"):
        if md.get(role + "_identity_status") != "resolved" or source_reference_key(md, role) is None:
            status = md.get(role + "_identity_status")
            return (status if status in {"dynamic", "ambiguous", "unsupported"} else "unavailable",
                    md.get(role + "_identity_reason") or "external_singleton_declaration_unestablished", None)
    uri, name = md.get("module_uri"), md.get("type_name")
    if (not isinstance(uri, str) or not re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*", uri)
            or not isinstance(name, str) or not re.fullmatch(r"[A-Z]\w*", name)):
        return "dynamic", "external_singleton_literal_names_unavailable", None
    key = source_reference_key(md)
    competing = [other for other in setups if other["id"] != site["id"]
                 and qt_metadata(other).get("api_supported") is True and _possible_key(qt_metadata(other)) == key
                 and all(qt_metadata(other).get(field) in {None, md[field]} for field in ("module_uri", "type_name"))]
    if competing:
        return "ambiguous", "duplicate_external_singleton_setup", None
    if md.get("prior_singleton_use"):
        return "unsupported", "external_singleton_prior_use", None
    if md.get("singleton_state_reset"):
        return "unsupported", "external_singleton_state_reset", None
    if md.get("engine_escaped"):
        return "unavailable", "external_singleton_engine_state_unverified", None
    candidates = loads.get(key, [])
    if len(candidates) != 1:
        return "ambiguous" if candidates else "unavailable", "external_singleton_unique_load_unestablished", None
    load = candidates[0]
    loaded = qt_metadata(load)
    if loaded.get("status") != "resolved" or not loaded.get("target_id"):
        return "unavailable", "external_singleton_source_load_unestablished", None
    if md["span"]["end_byte"] > loaded["span"]["start_byte"]:
        return "unsupported", "external_singleton_setup_after_load", None
    if (md.get("checkpoint_load_id") != load["id"] or md.get("provider_at_load_status") != "resolved"
            or md.get("provider_at_load_declaration_id") != md.get("provider_declaration_id")
            or type(md.get("provider_scope_end")) is not int or md["provider_scope_end"] <= loaded["span"]["end_byte"]):
        return "unavailable", "external_singleton_provider_lifetime_unestablished", None
    registrations = [(nid, item) for nid, item in index.native.provider_records.items()
                     if item.get("uri") == uri and item.get("raw_name") == name]
    if len(registrations) != 1:
        return "ambiguous" if registrations else "unavailable", "external_singleton_registration_unestablished", None
    registration, record = registrations[0]
    if not record.get("singleton") or record.get("mechanism") not in {"QML_ELEMENT", "QML_NAMED_ELEMENT"}:
        return "unsupported", "external_singleton_registration_mechanism_unsupported", None
    provider = declared.provider(md)
    if provider is None or qt_metadata(provider[0]).get("class_id") != record.get("class_id"):
        return "unavailable", "external_singleton_instance_type_unestablished", None
    return "resolved", "", (load, registration, record, provider)


def resolve_external_singletons(results, index, all_nodes, all_edges):
    """Annotate fresh setup sites only; existing global provider selection is borrowed."""
    setups = list({node["id"]: node for node in all_nodes
                   if qt_metadata(node).get("kind") == "external_singleton_setup"}.values())
    for site in setups:
        _validate(site)
    loads = {}
    for load in {node["id"]: node for node in all_nodes if qt_metadata(node).get("kind") == "qml_load"}.values():
        keys = {source_reference_key(qt_metadata(load), role) for role in ("receiver", "engine")}
        for key in keys - {None}:
            loads.setdefault(key, []).append(load)
    declared = DeclaredProviderIndex(all_nodes)
    for result in results:
        for site in result.get("nodes", []) if result else ():
            if qt_metadata(site).get("kind") != "external_singleton_setup":
                continue
            status, reason, accepted = _rejection(site, setups, loads, index, declared)
            update_qt(site, status=status, reason=reason)
            if accepted is None:
                continue
            load, registration, record, provider = accepted
            component = qt_metadata(load)["target_id"]
            evidence = list(dict.fromkeys([site["id"], load["id"], registration, component] + provider[1] + list(record["evidence"])))
            update_qt(site, registration_id=registration, provider_class_id=record["class_id"],
                      component_target_id=component, load_id=load["id"], evidence=evidence,
                      semantic_status="source_relationship")
            edges = [qt_edge(site, target, "uses", "qt_external_singleton_" + role,
                             bridge_direction="cpp_to_qml", evidence=evidence)
                     for role, target in (("registration", registration), ("instance", record["class_id"]), ("component", component))]
            result.setdefault("edges", []).extend(edges)
            if all_edges is not result["edges"]:
                all_edges.extend(edges)
