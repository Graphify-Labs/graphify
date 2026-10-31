"""Exact C++ call-site scope and data-shadow facts for the free-function owner.

The accepted parser tree supplies lexical ranges. Local variables, parameters and
opaque normalized Qt binders provide shadowing only, never callable/type proof.
"""
from __future__ import annotations

from copy import deepcopy

from graphify.extractors.base import _read_text
from graphify.extractors.cpp_constructors import _span, _walk
from graphify.extractors.cpp_declarators import callable_declarator, member_declarator
from graphify.extractors.cpp_functions import encoded, namespace_scope
from graphify.extractors.field_call_policy import FieldCallPolicy
from graphify.extractors.cpp_member_identity import member_fact
from graphify.extractors.cpp_constructors import _fact


_SCOPES = {"compound_statement", "for_statement", "for_range_loop", "if_statement", "switch_statement", "catch_clause", "lambda_expression"}


def _scope(node, function):
    parent = node.parent
    while parent is not None and parent != function:
        if parent.type in _SCOPES:
            return parent
        parent = parent.parent
    return function.child_by_field_name("body") or function


def _binding_names(declarator, source):
    if declarator.type == "type_identifier":
        return [_read_text(declarator, source)]
    value = member_declarator(declarator, source)
    if value is not None:
        return [value[0]]
    if declarator.type == "structured_binding_declarator":
        return [_read_text(node, source) for node in declarator.named_children if node.type == "identifier"]
    return []


def _bindings(function, source):
    values = []
    for node in _walk(function):
        if node.type in {"declaration", "type_definition", "parameter_declaration", "optional_parameter_declaration", "for_range_loop"}:
            for declarator in node.children_by_field_name("declarator"):
                scope = _scope(node, function)
                for name in _binding_names(declarator, source):
                    values.append((name, declarator.end_byte, scope.start_byte, scope.end_byte))
        elif node.type == "lambda_capture_specifier":
            scope = next((parent for parent in [node.parent] if parent is not None and parent.type == "lambda_expression"), None)
            if scope is not None:
                for child in node.named_children:
                    candidate = child if child.type == "identifier" else child.child_by_field_name("name")
                    if candidate is not None and candidate.type == "identifier":
                        values.append((_read_text(candidate, source), candidate.end_byte, scope.start_byte, scope.end_byte))
        elif node.type == "alias_declaration":
            name = node.child_by_field_name("name")
            if name is not None:
                scope = _scope(node, function)
                values.append((_read_text(name, source), node.end_byte, scope.start_byte, scope.end_byte))
    return values


def call_target(node, source):
    current = node.child_by_field_name("function")
    template = False
    if current is None:
        return None
    if current.type == "template_function":
        template = True
        current = current.child_by_field_name("name")
    if current is None:
        return None
    if current.type == "identifier":
        return _read_text(current, source), "", False, False, template
    if current.type != "qualified_identifier":
        return None
    raw = _read_text(current, source)
    leaf = current.child_by_field_name("name")
    while leaf is not None and leaf.type == "qualified_identifier":
        leaf = leaf.child_by_field_name("name")
    if leaf is not None and leaf.type == "template_function":
        template = True
        leaf = leaf.child_by_field_name("name")
    if leaf is None or leaf.type != "identifier":
        return None
    name = _read_text(leaf, source)
    qualifier = raw[:raw.rfind("::")].removeprefix("::").strip()
    return name, qualifier, True, raw.lstrip().startswith("::"), template


def _visible_using(call, directives):
    """Only parsed using-directives in enclosing lexical scopes block lookup."""
    ancestors, parent = set(), call.parent
    while parent is not None:
        ancestors.add(parent.id)
        parent = parent.parent
    for directive in directives:
        if directive.start_byte >= call.start_byte:
            continue
        parent = directive.parent
        while parent is not None and parent.type.startswith("preproc_"):
            parent = parent.parent
        if parent is not None and parent.id in ancestors:
            return True
    return False


def reconcile_free_call_sites(index, nodes, edges, raw_calls, path):
    """Retire only free-body guesses and defer exact source sites to their owner."""
    by_id = {node["id"]: node for node in nodes}
    free_ids = {node["id"] for node in nodes if "cpp_function" in node.get("metadata", {})}
    storage = FieldCallPolicy(nodes, edges)
    sites, owned_callers = [], set()
    directives = tuple(node for node in _walk(index.root) if node.type == "using_declaration"
                       and any(child.type == "namespace" for child in node.children))
    for function, caller in index.callers.values():
        # A marked partial generic caller has no new scope proof. Keep its
        # established calls/raw transport instead of taking them over and then
        # discarding them. Recorded uncertain scopes remain conservatively owned.
        if function.id not in index.records and not (
                member_fact(by_id.get(caller, {})) or _fact(by_id.get(caller, {}), "cpp_constructor")):
            continue
        owned_callers.add(caller)
        declarator = function.child_by_field_name("declarator")
        function_shape = member_declarator(declarator, index.source) if declarator else None
        parts, _, member = namespace_scope(function, index.source)
        if not all(isinstance(part, str) for part in parts):
            continue
        namespace = "::".join(parts)
        deferred_member = bool(function_shape and "::" in function_shape[0] and function.id not in index.records)
        native = member_fact(by_id.get(caller, {})) or _fact(by_id.get(caller, {}), "cpp_constructor")
        native_family = "member" if member_fact(by_id.get(caller, {})) else "constructor" if native else ""
        body_proof = ({"label": by_id[caller]["label"], "source_location": by_id[caller]["source_location"],
                       "fact": deepcopy(native)} if native_family == "member" and native.get("role") == "definition" else None)
        bindings = _bindings(function, index.source)
        body = function.child_by_field_name("body")
        if body is None:
            continue
        for node in _walk(body):
            if node.type != "call_expression":
                continue
            # A nested class method owns its own call walk and caller ID.
            parent = node.parent
            while parent is not None and parent != function and parent.type != "function_definition":
                parent = parent.parent
            if parent != function:
                continue
            target = call_target(node, index.source)
            if target is None:
                continue
            name, qualifier, qualified, absolute, template = target
            if not qualified and storage.shadows(caller, name):
                continue  # The field owner already rejected this storage invocation.
            arguments = node.child_by_field_name("arguments")
            argc = len([child for child in arguments.named_children if child.type != "comment"]) if arguments is not None else None
            lookup_head = qualifier.split("::", 1)[0] if qualified else name
            shadowed = (not absolute and (not qualified and storage.shadows(caller, name) or any(
                value == lookup_head and declared <= node.start_byte and start <= node.start_byte < end
                for value, declared, start, end in bindings)))
            # Unevaluated contexts retain source facts without a runtime call.
            parent, unevaluated = node.parent, False
            while parent is not None and parent != function:
                unevaluated |= parent.type in {"sizeof_expression", "decltype", "noexcept_expression", "requires_expression"}
                parent = parent.parent
            visible_using = not qualified and _visible_using(node, directives)
            sites.append({"caller_nid": caller, "callee": name, "is_member_call": qualified,
                "class_name": qualifier if qualified else None, "receiver": qualifier if qualified else None,
                "source_file": str(path), "source_location": f"L{node.start_point.row + 1}",
                "cpp_free_call": {"contract_version": 1, "name_b64": encoded(name), "qualifier_b64": encoded(qualifier),
                    "qualified": qualified, "absolute": absolute, "namespace_b64": encoded(namespace), "namespace_status": "available",
                    "context_kind": "deferred_member" if deferred_member else "member" if member else "free",
                    "caller_span": _span(function), "span": _span(node), "argc": argc,
                    "caller_native_signature": native.get("signature", ""), "caller_native_family": native_family,
                    "caller_body_proof": body_proof,
                    "shadowed": shadowed, "template": template, "unevaluated": unevaluated,
                    "using_namespace_unavailable": visible_using}})
    keys = {(site["caller_nid"], site["callee"], site["source_location"]) for site in sites}
    for call in raw_calls:
        if (call.get("caller_nid"), call.get("callee"), call.get("source_location")) in keys:
            call["_cpp_free_deferred"] = True
    edges[:] = [edge for edge in edges if not (edge.get("relation") == "calls" and edge.get("source") in owned_callers
                                              and edge.get("target") in free_ids)]
    raw_calls.extend(sites)
    # Local direct producer consumers receive the same conservative free-owner
    # resolution; the facade repeats it with the complete accepted corpus.
    from graphify.extractors.cpp_free_calls import resolve_free_function_calls
    resolve_free_function_calls(nodes, edges, sites)
