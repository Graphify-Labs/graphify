"""Project expression sites to proven scoped endpoints without runtime execution."""
from __future__ import annotations

import hashlib
from pathlib import Path

from graphify.extractors.qml_facts import encode_metadata
from graphify.qml_relationship_lookup import RelationshipLookup
from graphify.qml_resolution import build_qml_index
from graphify.qml_resolution_types import Resolution, fact_edge, fact_node, qml_metadata


def _handler(lookup, site):
    md, index = qml_metadata(site), lookup.index
    if md.get("disabled_reason"):
        return Resolution("unsupported", reason=md["disabled_reason"])
    if md.get("attached_prefix"):
        return Resolution("unsupported", reason="attached_signal_provider_unavailable")
    reference = md.get("reference") or ""
    if md.get("connections"):
        if not md.get("connection_supplied") or not md.get("connection_target"):
            return Resolution("dynamic", reason="connections_runtime_target")
        reference = md["connection_target"] + "." + reference
    result = lookup.resolve(site, reference)
    if result.status == "resolved":
        kind = index.md(result.target_id).get("kind")
        if kind == "signal":
            return result
        return Resolution("unsupported", reason="handler_target_is_not_signal")
    # QML generates a notify signal for an observed source-declared property.
    # Keep that inferred signal distinct from the property and its subscriptions.
    if reference.endswith("Changed"):
        prop = lookup.resolve(site, reference[:-7])
        if prop.status == "resolved" and index.md(prop.target_id).get("kind") == "property" and not index.md(prop.target_id).get("qt_native"):
            return Resolution("resolved", prop.target_id, "property_notify_signal", prop.evidence)
    return result


def _implicit_handler_parameter(lookup, site, cache):
    """Resolve inherited signal binders before any same-name QML member fallback."""
    md, index = qml_metadata(site), lookup.index
    first = (md.get("reference") or "").split(".")[0]
    owner, seen = md.get("owner_id"), set()
    while owner and owner in index.nodes and owner not in seen and len(seen) < 32:
        seen.add(owner)
        node = index.nodes[owner]
        ancestor = qml_metadata(node)
        if ancestor.get("kind") == "handler":
            if owner not in cache:
                signal = _handler(lookup, node)
                cache[owner] = (index.md(signal.target_id).get("parameter_names") or []
                                if signal.status == "resolved" and signal.target_id in index.nodes else [])
            return first in cache[owner]
        owner = ancestor.get("owner_id")
    return False


def resolve_qml_relationships(per_file, all_nodes, all_edges, *, root: Path, native_index=None, project_index=None) -> None:
    """Mutate fresh source-owned sites only; prior graph context is read-only.

    Each occurrence is already a unique fact with its expression span and owner.
    Separate endpoint edges preserve repeated reads/calls through Graph/DiGraph.
    Unsupported/dynamic/ambiguous sites remain explicit and get no guessed edge.
    """
    index = build_qml_index(all_nodes, all_edges, root=root, native_index=native_index, project_index=project_index)
    lookup = RelationshipLookup(index)
    fresh = {node["id"] for result in per_file.values() if result for node in result.get("nodes", [])}
    node_ids = {node["id"] for node in all_nodes}
    edge_keys = {(e["source"], e["target"], e["relation"], e.get("context")) for e in all_edges}
    handler_parameters = {}

    def append_node(node):
        if node["id"] not in node_ids:
            all_nodes.append(node)
            node_ids.add(node["id"])

    def append_edge(edge):
        key = edge["source"], edge["target"], edge["relation"], edge.get("context")
        if key not in edge_keys:
            all_edges.append(edge)
            edge_keys.add(key)

    for nid in sorted(fresh):
        site = index.nodes.get(nid)
        if site is None:
            continue
        md = qml_metadata(site)
        kind = md.get("kind")
        if kind not in {"read", "call", "alias", "handler"}:
            continue
        if kind in {"read", "call"} and not md.get("lexical_shadowed") and _implicit_handler_parameter(lookup, site, handler_parameters):
            md["lexical_shadowed"] = True
            md["lexical_target_id"] = ""
            result = Resolution("dynamic", reason="javascript_lexical_binding")
        else:
            result = _handler(lookup, site) if kind == "handler" else lookup.resolve(site, md.get("reference") or "")
        if result.status == "resolved" and kind == "call":
            target_kind = index.md(result.target_id).get("kind")
            if target_kind not in {"function", "js_function", "qml_script_function", "signal"}:
                result = Resolution("dynamic", reason="runtime_callable_value")
        span = md.get("span", {})
        owner = {"source_file": index.paths[nid], "source_location": site.get("source_location", "L1")}
        target = result.target_id
        if result.reason == "property_notify_signal":
            assert target is not None
            key = hashlib.sha256(f'{target}:notify'.encode()).hexdigest()
            signal = fact_node(index.paths[target], "property_change_signal", key,
                               (qml_metadata(index.nodes[target]).get("raw_name") or "property") + "Changed",
                               qml_metadata(index.nodes[target]).get("span", {}).get("start_row", 0) + 1,
                               property_id=target, status="inferred", span=qml_metadata(index.nodes[target]).get("span", {}))
            append_node(signal)
            append_edge(fact_edge(target, signal["id"], "contains", index.nodes[target], "qml_property_notify_signal"))
            target = signal["id"]
        updated = {k: v for k, v in md.items() if k != "raw_values"}
        updated.update(status=result.status, reason=result.reason, resolved_target_id=target or "",
                       evidence=list(result.evidence[:50]), candidates=list(result.candidates[:50]),
                       diagnostic_code="" if result.status == "resolved" else "QML-EXPRESSION-001")
        site["metadata"]["qml"] = encode_metadata(updated)
        if result.status != "resolved":
            continue
        assert target is not None
        relation, context = "uses", "qml_binding_read"
        if kind == "alias":
            relation, context = "references", "qml_alias_target"
        elif kind == "handler":
            relation, context = "references", "qml_signal_subscription"
        elif kind == "call":
            target_kind = index.md(target).get("kind")
            if target_kind == "signal":
                context = "qml_signal_emit"
            else:
                relation = "calls"
                context = "qml_script_call" if target_kind == "qml_script_function" else "qml_js_call"
        edge = fact_edge(nid, target, relation, owner, context, confidence="INFERRED",
                         span=span, evidence=list(result.evidence[:50]))
        proof = native_index.endpoint_proof(target, result.evidence) if native_index else {}
        if proof:
            from graphify.extractors.qt_cpp_facts import encode_qt
            edge["metadata"]["qt"] = encode_qt({"kind": "qml_bridge", "span": span, "native_endpoint": proof})
        append_edge(edge)
