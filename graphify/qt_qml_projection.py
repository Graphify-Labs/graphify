"""Validate versioned endpoint evidence for explicit Qt/QML language bridges."""
from pathlib import Path

from graphify.extractors.qml_facts import qml_metadata
from graphify.extractors.qt_cpp_facts import qt_metadata

_CPP = {".cpp", ".cc", ".cxx", ".h", ".hpp", ".hh", ".hxx"}


def allows_qt_qml_edge(source, target, edge, *, source_id, target_id, nodes):
    """A context label cannot authorize a bridge to an unrelated declaration."""
    if edge.get("confidence") != "INFERRED" or edge.get("source_file") != source.get("source_file"):
        return False
    src_ext = Path(source.get("source_file") or "").suffix.lower()
    tgt_ext = Path(target.get("source_file") or "").suffix.lower()
    try:
        smd, tmd = qml_metadata(source), qml_metadata(target)
        source_qt = qt_metadata(source)
        if src_ext == ".qml" and tgt_ext in _CPP and source_qt.get("kind") == "context_access":
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
            expected = member_id if member.get("kind") == "property" else member.get("generic_target_id")
            return (source_qt.get("status") == "resolved" and binding.get("kind") == "context_binding"
                    and binding.get("status") == "resolved" and source_qt.get("target_id") == target_id
                    and proof.get("canonical_target_id") == target_id and proof.get("provider_id") == binding_id
                    and proof.get("class_id") == class_id and member.get("class_id") == class_id
                    and expected == target_id and component.get("component_key") == owner.get("component_key")
                    and nodes[component_id].get("source_file") == source.get("source_file")
                    and edge.get("context") == "qt_context_member" and edge.get("relation") in {"uses", "calls"})
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
                return (target_id == provider_id and smd.get("kind") in {"import_resolution", "type_use"}
                        and edge.get("relation") in {"imports", "uses"})
            member_id = proof.get("member_fact_id")
            if member_id not in nodes:
                return False
            member = qt_metadata(nodes[member_id])
            expected = member_id if member.get("kind") == "property" else member.get("generic_target_id")
            return (member.get("class_id") == class_id and expected == target_id
                    and member.get("kind") in {"property", "member"}
                    and smd.get("kind") in {"read", "call", "handler", "alias"}
                    and edge.get("relation") in {"uses", "calls", "references"})
        if src_ext in _CPP and tgt_ext == ".qml" and tmd.get("contract_version") == 1:
            proof = qt_metadata(edge)
            return (source_qt.get("kind") in {"qml_load", "qml_root", "qml_access", "event_endpoint", "context_exposure", "initial_properties"}
                    and source_qt.get("target_id") == target_id and proof.get("target_id") == target_id
                    and proof.get("bridge_direction") in {"cpp_to_qml", "qml_to_cpp"}
                    and source_qt.get("status") == "resolved"
                    and edge.get("context") in {"qt_cpp_qml_load", "qt_cpp_qml_find_child", "qt_cpp_qml_property_read",
                        "qt_cpp_qml_property_write", "qt_cpp_qml_invoke", "qt_qml_connect_signal", "qt_qml_connect_receiver"})
    except (ValueError, TypeError):
        return False
    return False
