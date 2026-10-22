"""Source-owned context signal subscriptions and late implicit-parameter binding.

Context providers are established after ordinary QML lookup. This boundary keeps
subscriptions separate from calls and corrects only freshly owned handler uses.
"""
from __future__ import annotations

from graphify.extractors.qml_facts import encode_metadata, qml_metadata
from graphify.extractors.qt_cpp_facts import encode_qt, qt_edge, qt_id, qt_metadata
from graphify.qt_context_paths import context_path


def _binding_paths(source, reference, bindings, index):
    md, matches = qml_metadata(source), []
    parts = reference.split(".")
    if not reference or md.get("lexical_shadowed") or md.get("script_file"):
        return []
    if any(qml_metadata(index.nodes[nid]).get("qualifier") == parts[0]
           for nid in index.imports.get(source["source_file"], [])):
        return []
    local = index.resolve_member(source["source_file"], md.get("component_key", ""),
                                 md.get("object_scope_key", ""), parts[0])
    for binding in bindings:
        provider = qt_metadata(binding)
        component = index.nodes.get(provider.get("component_target_id"), {})
        if (provider.get("status") != "resolved" or component.get("source_file") != source["source_file"]
                or qml_metadata(component).get("component_key") != md.get("component_key")):
            continue
        if local.status in {"resolved", "ambiguous", "unsupported", "dynamic"} and not (
                provider.get("initial_property") and local.target_id == provider.get("declared_property_id")):
            continue
        path = parts if provider.get("context_object") else parts[1:] if parts[0] == provider.get("exposed_name") else []
        if path:
            matches.append((binding, path))
    return matches


def project_context_subscriptions(results, bridge, bindings, nodes, edges, index):
    """Only exact literal callbacks and handlers in a loaded component subscribe."""
    additions, new_edges, implicit = [], [], {}
    # Native Connections handlers establish legacy parameter binders before any
    # nested signal.connect can resolve a provider or a callback of the same name.
    for kind in ("handler", "call"):
        _collect_subscriptions(results, bridge, bindings, index, kind, additions, new_edges, implicit)
        if kind == "handler":
            _suppress_implicit_parameters(results, nodes, edges, implicit)
    nodes.extend(additions)
    edges.extend(new_edges)


def _collect_subscriptions(results, bridge, bindings, index, kind, additions, new_edges, implicit):
    """Each pass borrows run-owned source facts and appends distinct subscription sites."""
    for result in results:
        if not result:
            continue
        for source in list(result.get("nodes", [])):
            md = qml_metadata(source)
            if md.get("kind") != kind:
                continue
            form, reference, handler = "", "", ""
            if (md.get("kind") == "handler" and md.get("connections")
                    and not md.get("disabled_reason") and not md.get("attached_prefix")):
                if md.get("connection_supplied") and md.get("connection_target"):
                    reference, form, handler = md["connection_target"] + "." + md.get("reference", ""), "Connections", source["id"]
            elif md.get("kind") == "call" and md.get("reference", "").endswith(".connect"):
                if md.get("callback_argument_count") != 1 or not md.get("callback_reference"):
                    continue
                callback = md["callback_reference"]
                if md.get("callback_lexical_shadowed"):
                    handler = md.get("callback_lexical_target_id")
                else:
                    handler = index.resolve_member(source["source_file"], md.get("component_key", ""),
                        md.get("object_scope_key", ""), callback).target_id
                if handler not in index.nodes or index.md(handler).get("kind") not in {"function", "js_function"}:
                    continue
                reference, form = md["reference"][:-8], "signal.connect"
            if not form:
                continue
            matches = _binding_paths(source, reference, bindings, index)
            accepted = []
            for binding, path in matches:
                resolved, proof = context_path(bridge, binding, path)
                if form == "Connections" and proof.get("kind") != "signal" and path[-1].endswith("Changed"):
                    # A native property notification retains its real NOTIFY
                    # declaration even when the handler uses property spelling.
                    prop, property_proof = context_path(bridge, binding, path[:-1] + [path[-1][:-7]])
                    if prop.target_id and property_proof.get("kind") == "property":
                        resolved = bridge.property_notify(prop.target_id, binding["id"])
                        proof = bridge.endpoint_proof(resolved.target_id, resolved.evidence) if resolved.target_id else {}
                        if proof:
                            proof.update(type_chain=property_proof.get("type_chain", []), notify_property_id=prop.target_id)
                if resolved.target_id and proof.get("kind") == "signal":
                    accepted.append((binding, resolved, proof))
            if len(accepted) != 1:
                continue
            binding, resolved, proof = accepted[0]
            site = {"id": qt_id(source["source_file"], "context_subscription", [source["id"], binding["id"]]),
                    "label": "Qt context subscription: " + reference, "type": "concept", "file_type": "code", "_origin": "ast",
                    "source_file": source["source_file"], "source_location": source["source_location"],
                    "metadata": {"qt": encode_qt({"kind": "context_subscription", "span": md["span"],
                        "owner_id": source["id"], "binding_id": binding["id"], "status": "resolved",
                        "target_id": resolved.target_id, "handler_target_id": handler, "subscription_form": form,
                        "endpoint_proof": proof, "bridge_direction": "qml_to_cpp"})}}
            if any(node["id"] == site["id"] for node in result.get("nodes", [])):
                continue
            additions.append(site)
            result.setdefault("nodes", []).append(site)
            # A separate handler endpoint avoids opposite relationships sharing
            # one Graph/DiGraph pair when a Connections handler also owns the site.
            endpoint = {**site, "id": qt_id(source["source_file"], "context_handler_endpoint", [site["id"], handler]),
                        "label": "Qt context handler endpoint", "metadata": {"qt": encode_qt({
                            "kind": "context_handler_endpoint", "span": md["span"], "owner_id": site["id"],
                            "target_id": handler, "status": "resolved"})}}
            additions.append(endpoint)
            result["nodes"].append(endpoint)
            owned = [qt_edge(source, site["id"], "contains", "qt_context_subscription_site", span=md["span"]),
                     qt_edge(site, resolved.target_id, "references", "qt_context_subscription",
                             endpoint_proof=proof, bridge_direction="qml_to_cpp"),
                     qt_edge(site, endpoint["id"], "contains", "qt_context_handler_endpoint"),
                     qt_edge(endpoint, handler, "references", "qt_context_handler")]
            new_edges.extend(owned)
            result.setdefault("edges", []).extend(owned)
            if form == "Connections" and md.get("implicit_parameters") is True:
                implicit[source["id"]] = set(bridge.metadata(resolved.target_id).get("parameter_names", []))


def _suppress_implicit_parameters(results, nodes, edges, parameters):
    """Late native binders remove an earlier same-name QML fallback edge."""
    by_id, suppressed = {node["id"]: node for node in nodes}, set()
    for result in results:
        if not result:
            continue
        for source in result.get("nodes", []):
            md = qml_metadata(source)
            if md.get("kind") not in {"read", "call"}:
                continue
            first, owner, seen = md.get("reference", "").split(".")[0], md.get("owner_id"), set()
            callback = md.get("callback_reference", "").split(".")[0]
            updated = {key: value for key, value in md.items() if key != "raw_values"}
            changed = False
            while owner in by_id and owner not in seen and len(seen) < 32:
                seen.add(owner)
                # Explicit JS binders already carry AST authority. A native
                # implicit name must never displace a nearer local declaration.
                if first in parameters.get(owner, set()) and not md.get("lexical_shadowed"):
                    updated.update(lexical_shadowed=True, lexical_target_id="", status="dynamic",
                                   resolved_target_id="", reason="javascript_lexical_binding")
                    suppressed.add(source["id"])
                    changed = True
                if callback in parameters.get(owner, set()) and not md.get("callback_lexical_shadowed"):
                    updated.update(callback_lexical_shadowed=True, callback_lexical_target_id="")
                    changed = True
                owner = qml_metadata(by_id[owner]).get("owner_id")
            if changed:
                source["metadata"]["qml"] = encode_metadata(updated)
    def kept(edge):
        return not (edge.get("source") in suppressed and edge.get("context", "").startswith("qml_")
                    and edge.get("relation") in {"uses", "calls"})
    edges[:] = [edge for edge in edges if kept(edge)]
    for result in results:
        if result:
            result["edges"][:] = [edge for edge in result.get("edges", []) if kept(edge)]
