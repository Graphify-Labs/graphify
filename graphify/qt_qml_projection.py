"""Validate versioned endpoint evidence for explicit Qt/QML language bridges."""
from pathlib import Path

from graphify.extractors.qml_facts import qml_metadata
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.qt_context_paths import valid_context_chain, valid_context_endpoint
from graphify.qt_qml_callback_proof import valid_subscription_callback

_CPP = {".cpp", ".cc", ".cxx", ".h", ".hpp", ".hh", ".hxx"}


def is_typed_qt_qml_edge(source, target, edge):
    """Select existing bridge producers independently of their relation/context/confidence.

    Classification grants no authority: even malformed transport selected here
    must pass the full consumer proof. Context-binding ownership/exposure remains
    under its separate contract rather than being reclassified as member access.
    """
    src = Path(source.get("source_file") or "").suffix.lower()
    tgt = Path(target.get("source_file") or "").suffix.lower()
    if not (src == ".qml" and tgt in _CPP or src in _CPP and tgt == ".qml"):
        return False
    source_metadata, edge_metadata = source.get("metadata"), edge.get("metadata")
    target_metadata = target.get("metadata")
    source_qt = source_metadata.get("qt", {}) if isinstance(source_metadata, dict) else {}
    target_qt = target_metadata.get("qt", {}) if isinstance(target_metadata, dict) else {}
    edge_qt = edge_metadata.get("qt", {}) if isinstance(edge_metadata, dict) else {}
    producer_kinds = {"context_access", "context_subscription", "qml_load", "qml_root", "qml_access", "event_endpoint"}
    return (isinstance(edge_qt, dict) and (edge_qt.get("kind") == "qml_bridge" or "native_endpoint" in edge_qt)
            or any(isinstance(value, dict) and value.get("kind") in producer_kinds for value in (source_qt, target_qt)))


def _context_mechanism(source, source_qt, owner, proof, edge):
    """A derived context access borrows its original read/call, never a new operation."""
    if source_qt.get("kind") == "context_subscription":
        return edge.get("relation") == "references" and edge.get("context") == "qt_context_subscription"
    md = qml_metadata(owner)
    expected = "calls" if md.get("kind") == "call" and proof.get("kind") == "function" else "uses"
    return (md.get("contract_version") == 1 and md.get("kind") in {"read", "call"}
            and md.get("status") == "unavailable" and not md.get("lexical_shadowed") and not md.get("script_file")
            and owner.get("source_file") == source.get("source_file")
            and owner.get("source_location") == source.get("source_location")
            and md.get("span") == source_qt.get("span")
            and edge.get("context") == "qt_context_member" and edge.get("relation") == expected)


def _native_mechanism(md, proof, member, edge, target_id):
    """Registered native APIs retain source expression roles and endpoint declaration roles."""
    kind, role = md.get("kind"), proof.get("kind")
    if (md.get("status") != "resolved" or kind == "handler" and (
            md.get("disabled_reason") or md.get("attached_prefix")
            or md.get("connections") and (not md.get("connection_supplied") or not md.get("connection_target")))):
        return False
    if role in {"module", "component"}:
        expected = ("import_resolution", "imports", "qml_import_resolution") if role == "module" else (
            "type_use", "uses", "qml_type_resolution")
        return (kind, edge.get("relation"), edge.get("context")) == expected
    roles = set(member.get("roles", []))
    declared = "property" if member.get("kind") == "property" else "signal" if "signal" in roles else (
        "function" if roles & {"invokable", "slot"} else "")
    if (role != declared or md.get("resolved_target_id") != target_id or member.get("status") != "resolved"
            or member.get("kind") == "member" and member.get("access") != "public"):
        return False
    expected = {"read": ("uses", "qml_binding_read"), "alias": ("references", "qml_alias_target"),
                "handler": ("references", "qml_signal_subscription") if role == "signal" else None,
                "call": ("uses", "qml_signal_emit") if role == "signal" else (
                    "calls", "qml_js_call") if role == "function" else None}.get(kind)
    return expected == (edge.get("relation"), edge.get("context"))


def _cpp_mechanism(source, md, target_md, edge, nodes, target_id):
    """Reverse operations and connection endpoints have separate observed mechanisms."""
    kind, operation, target_kind = md.get("kind"), md.get("operation"), target_md.get("kind")
    if (md.get("conditional") or md.get("status") != "resolved"
            or md.get("loader_supported") is False or md.get("reflection_supported") is False):
        return False
    if kind == "event_endpoint":
        owner = nodes.get(md.get("owner_id"), {})
        parent = qt_metadata(owner)
        role = md.get("role")
        return (role in {"signal", "receiver"} and parent.get("kind") in {"connect", "disconnect"}
                and parent.get("status") == "resolved" and not parent.get("conditional")
                and md.get("bridge_direction") == parent.get("bridge_direction")
                == ("qml_to_cpp" if role == "signal" else "cpp_to_qml")
                and parent.get(role + "_target_id") == target_id
                and md.get("span") == parent.get("span")
                and owner.get("source_file") == source.get("source_file")
                and owner.get("source_location") == source.get("source_location")
                and target_kind in ({"signal"} if role == "signal" else {"signal", "function"})
                and edge.get("relation") == "references"
                and edge.get("context") == "qt_qml_" + parent["kind"] + "_" + role)
    if kind == "qml_load":
        expected = ("uses", "qt_cpp_qml_load") if (target_kind in {"component", "file"}
            and operation in {"load", "loadFromModule", "loadUrl", "setSource", "component_constructor", "engine_url_constructor"}) else None
    elif kind == "qml_root":
        expected = ("uses", "qt_cpp_qml_load") if (target_kind == "object"
            and operation in {"rootObject", "rootObjects", "create", "createWithInitialProperties"}) else None
    elif kind == "qml_access":
        if operation == "findChild":
            expected = ("uses", "qt_cpp_qml_find_child") if target_kind == "object" else None
        elif operation == "invokeMethod":
            expected = ("calls" if target_kind == "function" else "uses", "qt_cpp_qml_invoke") if target_kind in {"function", "signal"} else None
        elif operation in {"setProperty", "write", "property", "read", "QQmlProperty"}:
            expected = ("uses", "qt_cpp_qml_property_write" if operation in {"setProperty", "write"} else "qt_cpp_qml_property_read") if target_kind == "property" else None
        else:
            expected = None
    else:
        expected = None
    return md.get("bridge_direction") == "cpp_to_qml" and expected == (edge.get("relation"), edge.get("context"))


def allows_qt_qml_edge(source, target, edge, *, source_id, target_id, nodes):
    """A context label cannot authorize a bridge to an unrelated declaration."""
    if edge.get("confidence") != "INFERRED" or edge.get("source_file") != source.get("source_file"):
        return False
    src_ext = Path(source.get("source_file") or "").suffix.lower()
    tgt_ext = Path(target.get("source_file") or "").suffix.lower()
    try:
        smd, tmd = qml_metadata(source), qml_metadata(target)
        source_qt = qt_metadata(source)
        # A retained endpoint ID cannot repair a changed source span or mechanism.
        source_span = source_qt.get("span") if source_qt else smd.get("span")
        if not source_span or qt_metadata(edge).get("span") != source_span:
            return False
        if src_ext == ".qml" and tgt_ext in _CPP and source_qt.get("kind") in {"context_access", "context_subscription"}:
            proof = qt_metadata(edge).get("endpoint_proof", {})
            binding_id, owner_id = source_qt.get("binding_id"), source_qt.get("owner_id")
            if not isinstance(proof, dict) or binding_id not in nodes or owner_id not in nodes:
                return False
            binding = qt_metadata(nodes[binding_id])
            component_id, class_id = binding.get("component_target_id"), binding.get("provider_target_id")
            member_id = proof.get("member_fact_id")
            if component_id not in nodes or class_id not in nodes or member_id not in nodes:
                return False
            component, owner, member = qml_metadata(nodes[component_id]), qml_metadata(nodes[owner_id]), qt_metadata(nodes[member_id])
            subscription = source_qt.get("kind") == "context_subscription"
            if subscription and (proof.get("kind") != "signal" or source_qt.get("handler_target_id") not in nodes):
                return False
            handler = nodes.get(source_qt.get("handler_target_id"), {}) if subscription else {}
            if subscription and (handler.get("source_file") != source.get("source_file")
                    or qml_metadata(handler).get("kind") not in {"handler", "function", "js_function"}
                    or qml_metadata(handler).get("component_key") != component.get("component_key")
                    or not valid_subscription_callback(source, source_qt, nodes)):
                return False
            expected = member_id if member.get("kind") == "property" else member.get("generic_target_id")
            return (source_qt.get("status") == "resolved" and binding.get("kind") == "context_binding"
                    and source_qt.get("bridge_direction") == qt_metadata(edge).get("bridge_direction") == "qml_to_cpp"
                    and binding.get("status") == "resolved" and source_qt.get("target_id") == target_id
                    and proof.get("canonical_target_id") == target_id and proof.get("provider_id") == binding_id
                    and valid_context_chain(binding, proof, nodes) and valid_context_endpoint(proof, nodes)
                    and member.get("class_id") == proof.get("class_id")
                    and expected == target_id and component.get("component_key") == owner.get("component_key")
                    and nodes[component_id].get("source_file") == source.get("source_file")
                    and _context_mechanism(source, source_qt, nodes[owner_id], proof, edge))
        if smd.get("contract_version") == 1 and src_ext == ".qml" and tgt_ext in _CPP:
            proof = qt_metadata(edge).get("native_endpoint", {})
            if not isinstance(proof, dict) or proof.get("canonical_target_id") != target_id:
                return False
            provider_id, class_id = proof.get("provider_id"), proof.get("class_id")
            if provider_id not in nodes or class_id not in nodes:
                return False
            provider = qt_metadata(nodes[provider_id])
            if provider.get("kind") != "registration" or provider.get("class_id") != class_id:
                return False
            if proof.get("kind") in {"module", "component"}:
                return target_id == provider_id and _native_mechanism(smd, proof, {}, edge, target_id)
            member_id = proof.get("member_fact_id")
            if member_id not in nodes:
                return False
            member = qt_metadata(nodes[member_id])
            expected = member_id if member.get("kind") == "property" else member.get("generic_target_id")
            return (member.get("class_id") == class_id and expected == target_id
                    and member.get("kind") in {"property", "member"}
                    and _native_mechanism(smd, proof, member, edge, target_id))
        if src_ext in _CPP and tgt_ext == ".qml" and tmd.get("contract_version") == 1:
            proof = qt_metadata(edge)
            return (source_qt.get("kind") in {"qml_load", "qml_root", "qml_access", "event_endpoint", "context_exposure", "initial_properties"}
                    and source_qt.get("target_id") == target_id and proof.get("target_id") == target_id
                    and proof.get("bridge_direction") in {"cpp_to_qml", "qml_to_cpp"}
                    and proof.get("bridge_direction") == source_qt.get("bridge_direction")
                    and source_qt.get("status") == "resolved"
                    and _cpp_mechanism(source, source_qt, tmd, edge, nodes, target_id))
    except (ValueError, TypeError):
        return False
    return False
