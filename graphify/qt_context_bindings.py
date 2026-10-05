"""Source-established engine/component providers; no repository-wide injection."""
from __future__ import annotations

from graphify.extractors.qt_cpp_facts import encode_qt, qt_edge, qt_id, qt_metadata, update_qt
from graphify.extractors.qt_cpp_identity import source_reference_key
from graphify.qml_resolution_types import qml_metadata
from graphify.qt_event_index import QtEventIndex
from graphify.qt_declared_provider import DeclaredProviderIndex
from graphify.qt_context_paths import context_path
from graphify.qt_context_subscriptions import project_context_subscriptions


def _binding(site, item, component, provider, evidence):
    metadata, source = qt_metadata(site), site["source_file"]
    return {"id": qt_id(source, "context_binding", [site["id"], item.get("name"), item.get("ordinal", 0), provider]),
            "label": "Qt provider: " + (item.get("name") or "context object"), "type": "concept", "file_type": "code",
            "source_file": source, "source_location": site["source_location"], "_origin": "ast",
            "metadata": {"qt": encode_qt({"kind": "context_binding", "span": metadata["span"], "owner_id": site["id"],
                "exposed_name": item.get("name") or "", "context_object": metadata.get("operation") == "setContextObject",
                "initial_property": metadata.get("kind") != "context_exposure", "provider_target_id": provider,
                "declared_property_id": item.get("declared_property_id", ""),
                "provider_class_name": item.get("provider_type", ""), "component_target_id": component,
                "engine_reference": metadata.get("engine_reference") or metadata.get("receiver_reference") or "",
                "engine_declaration_id": metadata.get("engine_declaration_id") or metadata.get("receiver_declaration_id") or "",
                "provider_declaration_id": item.get("provider_declaration_id") or "",
                "provider_type_evidence": item.get("provider_type_evidence", []),
                "evidence": evidence,
                "status": "resolved", "bridge_direction": "cpp_to_qml"})}}


def resolve_context_bindings(results, index, all_nodes, all_edges):
    native, loads = QtEventIndex(all_nodes), {}
    declared_types = DeclaredProviderIndex(all_nodes)
    for result in results:
        for site in result.get("nodes", []) if result else []:
            metadata = qt_metadata(site)
            if metadata.get("kind") == "qml_load":
                # Components have their own declaration and an explicit source
                # engine; either role can supply its corresponding provider.
                keys = {key for role in ("receiver", "engine")
                        if (key := source_reference_key(metadata, role)) is not None}
                for key in keys:
                    loads.setdefault(key, []).append(site)
    additions, fresh_ids = [], set()
    for result in results:
        if not result:
            continue
        for site in list(result.get("nodes", [])):
            metadata = qt_metadata(site)
            if metadata.get("kind") not in {"context_exposure", "initial_properties", "qml_root"}:
                continue
            if metadata.get("kind") == "qml_root" and metadata.get("operation") != "createWithInitialProperties":
                continue
            if metadata.get("kind") != "context_exposure" and not metadata.get("literal_properties"):
                update_qt(site, status="dynamic", reason="computed_initial_properties")
                continue
            role = "engine" if metadata.get("kind") == "context_exposure" else "receiver"
            key = source_reference_key(metadata, role)
            candidates = loads.get(key, []) if key is not None else []
            if key is None:
                # Preserve authoritative lexical uncertainty instead of hiding
                # a reassignment or duplicate behind a generic missing loader.
                status = metadata.get(role + "_identity_status")
                update_qt(site, status=status if status in {"dynamic", "ambiguous", "unsupported"} else "unavailable",
                          reason=metadata.get(role + "_identity_reason") or "provider_component_scope_unestablished")
                continue
            # A direct context alias without established engine identity remains
            # unsupported. An old/later repeated load cannot prove one instance.
            if len(candidates) != 1 or metadata.get("conditional"):
                update_qt(site, status="dynamic" if metadata.get("conditional") else "ambiguous" if len(candidates) > 1 else "unavailable", reason="provider_component_scope_unestablished")
                continue
            load = candidates[0]
            component = qt_metadata(load).get("target_id")
            if not component:
                continue
            if metadata.get("kind") == "context_exposure":
                items = [{"name": metadata.get("exposed_name"), "provider_type": metadata.get("provider_type"),
                          "provider_reference": metadata.get("provider_reference"),
                          "provider_declaration_id": metadata.get("provider_declaration_id"),
                          "provider_identity_status": metadata.get("provider_identity_status"),
                          "provider_identity_reason": metadata.get("provider_identity_reason"),
                          "provider_scope_end": metadata.get("provider_scope_end"),
                          "provider_root_type_id": metadata.get("provider_root_type_id"),
                          "provider_root_type_spelling": metadata.get("provider_root_type_spelling"),
                          "provider_root_address_of": metadata.get("provider_root_address_of"),
                          "provider_expression_steps": metadata.get("provider_expression_steps"),
                          "provider_type_status": metadata.get("provider_type_status")}]
                if metadata.get("operation") == "setContextProperty" and not isinstance(metadata.get("exposed_name"), str):
                    update_qt(site, status="dynamic", reason="computed_context_name")
                    continue
            else:
                items = metadata.get("properties", [])
            count = 0
            for item in items:
                # A provider declaration must still belong to this lexical
                # lifetime when its engine loads the component. Names alone and
                # old transport cannot authorize a cross-language relationship.
                provider_key = source_reference_key({**metadata, "provider_declaration_id": item.get("provider_declaration_id")}, "provider")
                scope_end = item.get("provider_scope_end")
                if (provider_key is None or not isinstance(scope_end, int) or isinstance(scope_end, bool)
                        or qt_metadata(load)["span"]["start_byte"] >= scope_end):
                    continue
                if metadata.get("kind") != "context_exposure":
                    root = index.root_object(component)
                    declared_property = index.member(root.target_id, item.get("name", ""), "property") if root.target_id else root
                    if not declared_property.target_id:
                        continue
                    item = {**item, "declared_property_id": declared_property.target_id}
                    if metadata.get("operation") == "setInitialProperties" and metadata["span"]["start_byte"] > qt_metadata(load)["span"]["start_byte"]:
                        continue
                typed = declared_types.provider(item) if item.get("provider_root_type_id") else None
                declared = native.class_name(item.get("provider_type") or "")
                records = ([typed[0]] if typed else [] if item.get("provider_type_status") is not None
                           else native.classes.get(declared, []))
                if len(records) != 1:
                    continue
                provider = qt_metadata(records[0])
                if not provider.get("is_qobject") or not provider.get("generic_target_id"):
                    continue
                item = {**item, "provider_type": provider["class_name"], "provider_type_evidence": typed[1] if typed else [records[0]["id"]]}
                node = _binding(site, item, component, provider["generic_target_id"], [site["id"], load["id"], records[0]["id"], component] + item["provider_type_evidence"])
                existing = next((value for value in result.get("nodes", []) if value["id"] == node["id"]), None)
                if existing is None:
                    result.setdefault("nodes", []).append(node)
                    additions.append(node)
                fresh_ids.add(node["id"])
                edges = [qt_edge(site, node["id"], "contains", "qt_context_binding"),
                         qt_edge(node, component, "uses", "qt_initial_property" if metadata.get("kind") != "context_exposure" else "qt_context_exposure", bridge_direction="cpp_to_qml")]
                known = {(edge["source"], edge["target"], edge.get("context")) for edge in result.get("edges", [])}
                fresh_edges = [edge for edge in edges if (edge["source"], edge["target"], edge.get("context")) not in known]
                result.setdefault("edges", []).extend(fresh_edges)
                all_edges.extend(fresh_edges)
                count += 1
            if count:
                update_qt(site, status="resolved", reason="", component_target_id=component, binding_count=count)
            elif items:
                # Initial-property lists may mix independent failure reasons.
                # Report one provider identity reason only when every rejected
                # item proves that exact failure; other rejections stay generic.
                failures = {(item.get("provider_identity_status"), item.get("provider_identity_reason")) for item in items}
                if len(failures) == 1:
                    status, reason = next(iter(failures))
                    if status in {"dynamic", "ambiguous", "unsupported", "unavailable"} and reason and all(
                        source_reference_key({**metadata, "provider_declaration_id": item.get("provider_declaration_id")}, "provider") is None
                        for item in items
                    ):
                        update_qt(site, status=status, reason=reason)
        all_nodes.extend(additions)
        additions = []
    bindings = list({node["id"]: node for node in all_nodes if qt_metadata(node).get("kind") == "context_binding"}.values())
    groups = {}
    for binding in bindings:
        metadata = qt_metadata(binding)
        groups.setdefault((metadata.get("component_target_id"), metadata.get("exposed_name"), metadata.get("context_object")), []).append(binding)
    blocked = set()
    for group in groups.values():
        if len(group) > 1:
            blocked.update(binding["id"] for binding in group)
            for binding in group:
                if binding["id"] in fresh_ids:
                    update_qt(binding, status="ambiguous", reason="duplicate_context_provider")
    return [binding for binding in bindings if binding["id"] not in blocked]


def project_context_access(results, bridge, bindings, all_nodes, all_edges, qml_index):
    """Join only unresolved source QML sites in the established loaded component."""
    project_context_subscriptions(results, bridge, bindings, all_nodes, all_edges, qml_index)
    by_component = {}
    node_map = {node["id"]: node for node in all_nodes}
    for binding in bindings:
        metadata = qt_metadata(binding)
        if metadata.get("status") != "resolved":
            continue
        component = node_map.get(metadata.get("component_target_id"), {})
        key = (component.get("source_file"), qml_metadata(component).get("component_key"))
        by_component.setdefault(key, []).append(binding)
    for result in results:
        if not result:
            continue
        for source in list(result.get("nodes", [])):
            metadata = qml_metadata(source)
            if metadata.get("kind") not in {"read", "call"} or metadata.get("status") != "unavailable" or metadata.get("lexical_shadowed") or metadata.get("script_file"):
                continue
            reference = metadata.get("reference", "").split(".")
            imports = qml_index.imports.get(source["source_file"], [])
            if any(qml_metadata(qml_index.nodes[nid]).get("qualifier") == reference[0] for nid in imports):
                continue
            matches = []
            for binding in by_component.get((source["source_file"], metadata.get("component_key")), []):
                provider = qt_metadata(binding)
                local = qml_index.resolve_member(source["source_file"], metadata.get("component_key") or "", metadata.get("object_scope_key") or "", reference[0])
                if local.status in {"resolved", "ambiguous", "unsupported", "dynamic"} and not (provider.get("initial_property") and local.target_id == provider.get("declared_property_id")):
                    continue
                path = reference if provider.get("context_object") else reference[1:] if reference[0] == provider.get("exposed_name") else []
                if path:
                    resolution, proof = context_path(bridge, binding, path)
                    if resolution.target_id:
                        matches.append((binding, resolution, proof))
            if len(matches) != 1:
                continue
            binding, resolution, proof = matches[0]
            span = metadata.get("span", {})
            site = {"id": qt_id(source["source_file"], "context_access", [source["id"], binding["id"]]),
                    "label": "Qt context access: " + metadata.get("reference", ""), "type": "concept", "file_type": "code", "_origin": "ast",
                    "source_file": source["source_file"], "source_location": source["source_location"],
                    "metadata": {"qt": encode_qt({"kind": "context_access", "span": span, "owner_id": source["id"],
                        "binding_id": binding["id"], "target_id": resolution.target_id, "status": "resolved", "bridge_direction": "qml_to_cpp"})}}
            update_qt(site, endpoint_proof=proof, evidence=list(resolution.evidence))
            if any(value["id"] == site["id"] for value in result.get("nodes", [])):
                continue
            result.setdefault("nodes", []).append(site)
            all_nodes.append(site)
            edges = [qt_edge(source, site["id"], "contains", "qt_context_access", span=span),
                     qt_edge(site, resolution.target_id, "calls" if metadata.get("kind") == "call" and bridge.metadata(resolution.target_id).get("kind") == "function" else "uses", "qt_context_member", bridge_direction="qml_to_cpp",
                             endpoint_proof=proof, evidence=list(resolution.evidence))]
            result.setdefault("edges", []).extend(edges)
            all_edges.extend(edges)
