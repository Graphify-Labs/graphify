"""Explicit legacy meta-object connections across established C++/QML handles."""
from __future__ import annotations

import re

from graphify.extractors.qt_cpp_facts import qt_metadata, update_qt
from graphify.qml_resolution_types import Resolution, qml_metadata
from graphify.qt_event_index import QtEventIndex, value_type
from graphify.qt_event_resolution import _role


def _qml_endpoint(index, metadata, prefix):
    expression = metadata.get("signal" if prefix == "sender" else "receiver", {})
    if expression.get("form") != "legacy":
        return Resolution("unsupported", reason="qml_endpoint_requires_literal_meta_signature")
    handle = index.handle({**metadata, "receiver_reference": metadata.get(prefix + "_reference"),
                           "receiver_declaration_id": metadata.get(prefix + "_declaration_id"),
                           "receiver_assignment_byte": metadata.get(prefix + "_assignment_byte", -1)})
    if not handle.target_id:
        return handle
    result = index.member(handle.target_id, expression.get("member_name", ""), "invokeMethod")
    if not result.target_id:
        return result
    declaration = qml_metadata(index.nodes[result.target_id])
    if prefix == "sender" and declaration.get("kind") != "signal":
        return Resolution("unavailable", reason="qml_sender_is_not_signal")
    signature = declaration.get("signature", "").strip().strip("()")
    parameters = []
    names = {"int": "int", "real": "double", "double": "double", "bool": "bool", "string": "QString", "var": "QVariant"}
    for value in signature.split(",") if signature else []:
        match = re.fullmatch(r"\s*(\w+)\s+\w+\s*", value)
        annotation = re.fullmatch(r"\s*\w+\s*:\s*(\w+)\s*", value)
        untyped = re.fullmatch(r"\s*\w+\s*", value)
        raw_type = match[1] if match else annotation[1] if annotation else "var" if untyped and declaration.get("kind") == "function" else ""
        if raw_type not in names:
            return Resolution("unsupported", reason="qml_meta_signature_unestablished")
        parameters.append(names[raw_type])
    if parameters != expression.get("parameter_types", []):
        return Resolution("unavailable", reason="qml_meta_signature_mismatch")
    return result


def resolve_qml_event_access(results, index, all_nodes, all_edges):
    native = QtEventIndex(all_nodes)
    for result in results:
        if not result:
            continue
        additions, edges = [], []
        for site in result.get("nodes", []):
            metadata = qt_metadata(site)
            if metadata.get("kind") not in {"connect", "disconnect"} or metadata.get("status") == "resolved":
                continue
            qml_sender = _qml_endpoint(index, metadata, "sender")
            qml_receiver = _qml_endpoint(index, metadata, "receiver")
            signal = qml_sender if qml_sender.target_id else native.member(metadata.get("signal", {}), metadata.get("sender_type", ""), role="signal", owner_class=metadata.get("owner_class", ""))
            receiver = qml_receiver if qml_receiver.target_id else native.member(metadata.get("receiver", {}), metadata.get("receiver_type", ""), role=metadata.get("receiver", {}).get("role") or None, owner_class=metadata.get("owner_class", ""))
            if not qml_sender.target_id and not qml_receiver.target_id:
                continue
            if not signal.target_id or not receiver.target_id:
                update_qt(site, status="unavailable", reason="cross_language_endpoint_unestablished")
                continue
            offered = metadata.get("signal", {}).get("parameter_types", []) if qml_sender.target_id else qt_metadata(native.nodes[signal.target_id]).get("parameter_types", [])
            required = metadata.get("receiver", {}).get("parameter_types", []) if qml_receiver.target_id else qt_metadata(native.nodes[receiver.target_id]).get("parameter_types", [])
            if len(required) > len(offered) or [value_type(v) for v in offered[:len(required)]] != [value_type(v) for v in required]:
                update_qt(site, status="unavailable", reason="cross_language_signature_mismatch")
                continue
            direction = "qml_to_cpp" if qml_sender.target_id else "cpp_to_qml"
            update_qt(site, status="resolved", reason="", signal_target_id=signal.target_id, receiver_target_id=receiver.target_id, bridge_direction=direction)
            # Each occurrence owns its endpoint annotation. Revisiting earlier
            # accumulated edges changes their operation/direction and recursively
            # encodes raw literal transport; update_qt retains only semantic values.
            site_nodes, site_edges = [], []
            _role(site, signal.target_id, "signal", signal, site_nodes, site_edges)
            _role(site, receiver.target_id, "receiver", receiver, site_nodes, site_edges)
            for node in site_nodes:
                update_qt(node, bridge_direction=direction)
            for edge in site_edges:
                values = qt_metadata(edge)
                update_qt(edge, bridge_direction=direction)
                if edge.get("relation") == "references":
                    edge["context"] = "qt_qml_" + metadata["kind"] + "_" + values.get("role", "")
                    # Upgrade only the same occurrence's partial native role
                    # edge. Leaving both contexts lets raw pair deduplication
                    # retain the older incomplete bridge instead of this proof.
                    old_context = "qt_" + metadata["kind"] + "_" + values.get("role", "")
                    for previous in result.get("edges", []):
                        if (previous.get("context") == old_context
                                and previous.get("relation") == "references"
                                and previous.get("source") == edge["source"]
                                and previous.get("target") == edge["target"]
                                and previous.get("source_file") == site["source_file"]):
                            previous["context"] = edge["context"]
            additions.extend(site_nodes)
            edges.extend(site_edges)
        # The native pass may already own one endpoint of this fresh occurrence.
        # Reuse that canonical role ID and annotate its source-owned dictionary;
        # a duplicate filtered below must not leave the native placeholder stale.
        owned = {node["id"]: node for node in result.get("nodes", [])}
        for node in additions:
            if node["id"] in owned:
                update_qt(owned[node["id"]], bridge_direction=qt_metadata(node)["bridge_direction"])
        known = set(owned)
        fresh = [node for node in additions if node["id"] not in known]
        result.setdefault("nodes", []).extend(fresh)
        all_nodes.extend(fresh)
        edge_keys = {(edge["source"], edge["target"], edge.get("context")) for edge in result.get("edges", [])}
        owned_edges = {(edge["source"], edge["target"], edge.get("context")): edge
                       for edge in result.get("edges", [])}
        for edge in edges:
            previous = owned_edges.get((edge["source"], edge["target"], edge.get("context")))
            if previous is not None:
                update_qt(previous, bridge_direction=qt_metadata(edge)["bridge_direction"])
        fresh_edges = [edge for edge in edges if (edge["source"], edge["target"], edge.get("context")) not in edge_keys]
        result.setdefault("edges", []).extend(fresh_edges)
        all_edges.extend(fresh_edges)
