"""Project Qt emissions and connection endpoints without propagation calls."""
from __future__ import annotations

from graphify.extractors.qt_cpp_facts import encode_qt, qt_edge, qt_id, qt_metadata, scope_owner, update_qt
from graphify.qt_event_index import QtEventIndex
from graphify.qml_resolution_types import Resolution


def _record(site, prefix, result):
    update_qt(site, **{prefix + "_status": result.status, prefix + "_target_id": result.target_id or "",
                      prefix + "_reason": result.reason, prefix + "_candidates": list(result.candidates)})


def _role(site, target, role, result, additions, edges):
    """Separate role facts retain signal-to-signal and repeated occurrence edges."""
    metadata = qt_metadata(site)
    node = {"id": qt_id(site["source_file"], "event_endpoint", [site["id"], role]),
            "label": "Qt connection " + role, "type": "concept", "file_type": "code", "_origin": "ast",
            "source_file": site["source_file"], "source_location": site["source_location"],
            "metadata": {"qt": encode_qt({"kind": "event_endpoint", "role": role, "owner_id": site["id"],
                                           "span": metadata["span"], "target_id": target,
                                           "status": result.status, "bridge_direction": "cpp_to_cpp"})}}
    additions.append(node)
    # Endpoint role ownership follows the observed connection syntax. The
    # independently resolved declaration edge below remains inferred.
    ownership = qt_edge(site, node["id"], "contains", "qt_connection_endpoint", role=role)
    ownership["confidence"] = "EXTRACTED"
    edges.append(ownership)
    edges.append(qt_edge(node, target, "references", "qt_" + site.get("metadata", {}).get("qt", {}).get("kind", "connect") + "_" + role,
                         role=role, bridge_direction="cpp_to_cpp"))


def resolve_qt_events(per_file, all_nodes, all_edges, *, root, project_index=None):
    """Mutate only fresh source-owned sites; borrowed accepted corpus stays read-only."""
    del root, project_index
    index = QtEventIndex(all_nodes)
    connection_handles = {}
    results = per_file.values() if isinstance(per_file, dict) else per_file
    for result in results:
        if not result:
            continue
        additions, projected = [], []
        for site in list(result.get("nodes", [])):
            metadata = qt_metadata(site)
            kind = metadata.get("kind")
            if kind == "emission":
                resolution = index.emission(metadata)
                update_qt(site, status=resolution.status, target_id=resolution.target_id or "", reason=resolution.reason,
                          candidates=list(resolution.candidates), bridge_direction="cpp_to_cpp")
                if resolution.target_id:
                    projected.append(qt_edge(site, resolution.target_id, "uses", "qt_signal_emit", bridge_direction="cpp_to_cpp"))
                continue
            if kind not in {"connect", "disconnect"}:
                continue
            if kind == "disconnect" and metadata.get("handle_reference"):
                handle = connection_handles.get((scope_owner(metadata), metadata["handle_reference"]))
                if handle and handle[1] == metadata.get("handle_assignment_byte") and not metadata.get("conditional"):
                    update_qt(site, status="resolved", target_id=handle[0], reason="", bridge_direction="cpp_to_cpp")
                    projected.append(qt_edge(site, handle[0], "uses", "qt_disconnect", bridge_direction="cpp_to_cpp"))
                else:
                    update_qt(site, status="dynamic", reason="connection_handle_unestablished")
                continue
            signal = index.member(metadata.get("signal", {}), metadata.get("sender_type", ""), role="signal",
                                  owner_class=metadata.get("owner_class", ""))
            _record(site, "signal", signal)
            receiver_id, reason = "", ""
            if signal.target_id:
                _role(site, signal.target_id, "signal", signal, additions, projected)
            form = metadata.get("callable_form")
            if form in {"member_pointer", "legacy"}:
                endpoint = metadata.get("receiver", {})
                receiver = index.member(endpoint, metadata.get("receiver_type", ""),
                    role=endpoint.get("role") or None, owner_class=metadata.get("owner_class", ""))
                _record(site, "receiver", receiver)
                if receiver.target_id and signal.target_id and index.compatible(signal.target_id, receiver.target_id):
                    receiver_id = receiver.target_id
                    _role(site, receiver_id, "receiver", receiver, additions, projected)
                else:
                    reason = receiver.reason or "incompatible_or_unestablished_signature"
            elif form == "lambda" and metadata.get("lambda_id"):
                receiver_id = metadata["lambda_id"]
                parameters = qt_metadata(index.nodes.get(receiver_id, {})).get("parameter_types", [])
                if not signal.target_id or not index.compatible(signal.target_id, parameters=parameters):
                    receiver_id, reason = "", "incompatible_or_unestablished_lambda_signature"
                else:
                    _role(site, receiver_id, "receiver", Resolution("resolved", receiver_id), additions, projected)
            elif form in {"functor", "function"}:
                callable_result = index.callable(site)
                _record(site, "receiver", callable_result)
                if callable_result.target_id and signal.target_id and index.compatible(signal.target_id, callable_result.target_id):
                    receiver_id = callable_result.target_id
                    _role(site, receiver_id, "receiver", callable_result, additions, projected)
                else:
                    reason = callable_result.reason or "incompatible_callable_signature"
            else:
                reason = "dynamic_callable"
            status = "resolved" if signal.target_id and receiver_id else "ambiguous" if signal.status == "ambiguous" else "dynamic" if form == "dynamic" else "unavailable"
            if kind == "disconnect" and metadata.get("signal_wildcard") and metadata.get("callable_wildcard"):
                status = "resolved" if index.class_name(metadata.get("sender_type", "")) else "unavailable"
                reason = "source_wildcard_disconnect" if status == "resolved" else "sender_type_unestablished"
            update_qt(site, status=status, reason=reason or signal.reason, receiver_target_id=receiver_id,
                      bridge_direction="cpp_to_cpp", unique_connection_effect="not_guaranteed_for_functors" if form in {"lambda", "functor", "function"} else "unverified")
            if kind == "connect" and status == "resolved" and metadata.get("assigned_handle") and not metadata.get("conditional"):
                connection_handles[(scope_owner(metadata), metadata["assigned_handle"])] = (site["id"], metadata.get("assignment_byte"))
        existing = {node["id"] for node in result.get("nodes", [])}
        fresh = [node for node in additions if node["id"] not in existing]
        result.setdefault("nodes", []).extend(fresh)
        if all_nodes is not result["nodes"]:
            all_nodes.extend(node for node in fresh if node["id"] not in index.nodes)
        known = {(edge["source"], edge["target"], edge.get("context")) for edge in result.get("edges", [])}
        new_edges = [edge for edge in projected if (edge["source"], edge["target"], edge.get("context")) not in known]
        result.setdefault("edges", []).extend(new_edges)
        if all_edges is not result["edges"]:
            all_edges.extend(new_edges)
