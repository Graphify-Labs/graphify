"""Resolve free C++ calls only through accepted source scope and signatures.

The shared label map is not a C++ namespace/overload oracle. Prototype and body
identities remain separate; primitive parameter equivalence can establish arity
agreement, while named/opaque types, aliases and templates retain uncertainty.
"""
from __future__ import annotations

from graphify.extractors.cpp_functions import decoded, free_definition_fact, occurrence_suffix, scope_proof_parts, valid_span
from graphify.extractors.cpp_class_proof import class_fact
from graphify.extractors.cpp_class_scopes import CppClassScopes
from graphify.extractors.cpp_constructors import _fact
from graphify.extractors.cpp_member_identity import member_fact, proven_member_pairs
from graphify.extractors.field_call_policy import FieldCallPolicy
from graphify.extractors.cpp_function_signature import valid_parameter_facts
from graphify.extractors.cpp_anonymous_namespaces import AnonymousFunctions
import re
import hashlib
import json
from graphify.extractors.base import _make_id


def _native_member(node):
    """Malformed borrowed/body-proof transport cannot reach legacy set lookups."""
    metadata = node.get("metadata")
    value = metadata.get("cpp_member") if isinstance(metadata, dict) else None
    return member_fact(node) if isinstance(value, dict) and type(value.get("role")) is str else {}


def _prototype(node):
    metadata = node.get("metadata", {})
    fact = metadata.get("cpp_prototype") if isinstance(metadata, dict) else None
    if (not isinstance(fact, dict) or type(fact.get("contract_version")) is not int or fact["contract_version"] != 1
            or fact.get("role") != "declaration" or fact.get("qualified_name_status") != "available"
            or node.get("_callable") is not True or node.get("_callable_class") is True
            or not isinstance(node.get("source_file"), str) or not node["source_file"] or not valid_span(fact.get("span"))
            or fact.get("signature_status") != "normalized"
            or not re.fullmatch(r"[0-9a-f]{64}", str(fact.get("signature", "")))
            or not valid_parameter_facts(fact)
            or any(type(fact.get(key)) is not bool for key in ("template", "static", "conditional", "scope_complete"))
            or fact.get("scope_status") != "named"
            or node.get("source_location") != f"L{fact['span']['start_row'] + 1}"):
        return {}
    qualified = decoded(fact.get("qualified_name_b64"))
    if not qualified:
        return {}
    namespace, parts = decoded(fact.get("namespace_b64")), scope_proof_parts(fact)
    name = qualified.rsplit("::", 1)[-1]
    template = fact.get("template_fingerprint")
    if (node.get("label") != name + "()" or parts is None or namespace is None
            or "::".join(parts) != namespace or "::".join(filter(None, (namespace, name))) != qualified
            or type(template) is not str or template and not re.fullmatch(r"[0-9a-f]{64}", template)
            or fact["template"] != bool(template)):
        return {}
    scope_key = json.dumps(parts, ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256("\0".join((scope_key, name, fact["signature"], template)).encode()).hexdigest()
    identity, occurrence = node.get("id"), occurrence_suffix(fact["span"], "declaration")
    if isinstance(identity, str) and "::declaration-occurrence::" in identity:
        if not identity.endswith(occurrence):
            return {}
        identity = identity[:-len(occurrence)]
    if (hashlib.sha256(scope_key.encode()).hexdigest() != fact.get("scope_fingerprint")
            or not isinstance(identity, str)
            or not identity.endswith("_" + _make_id("cppproto", digest, name[:32]))):
        return {}
    return fact


def _call(call):
    fact = call.get("cpp_free_call")
    if (not isinstance(fact, dict) or type(fact.get("contract_version")) is not int or fact["contract_version"] != 1
            or decoded(fact.get("name_b64")) != call.get("callee") or decoded(fact.get("namespace_b64")) is None
            or decoded(fact.get("qualifier_b64")) is None or fact.get("namespace_status") != "available"
            or not valid_span(fact.get("span")) or not valid_span(fact.get("caller_span"))
            or call.get("source_location") != f"L{fact['span']['start_row'] + 1}"
            or type(fact.get("argc")) is not int or fact["argc"] < 0
            or type(fact.get("caller_native_family")) is not str or fact["caller_native_family"] not in {"", "member", "constructor"}
            or (fact["caller_native_family"] and not re.fullmatch(r"[0-9a-f]{64}", str(fact.get("caller_native_signature", ""))))
            or not fact["caller_native_family"] and fact.get("caller_native_signature") != ""
            or fact.get("caller_body_proof") is not None and not isinstance(fact["caller_body_proof"], dict)
            or any(type(fact.get(key)) is not bool for key in ("qualified", "absolute", "shadowed", "template", "unevaluated", "using_namespace_unavailable"))):
        return {}
    if not (fact["caller_span"]["start_byte"] <= fact["span"]["start_byte"] < fact["span"]["end_byte"] <= fact["caller_span"]["end_byte"]):
        return {}
    return fact


def _caller_scope(caller, call, fact, owners, definitions, class_scopes):
    if caller is None:
        return None
    free = free_definition_fact(caller)
    if free and free["span"] == fact["caller_span"] and caller.get("source_file") == call.get("source_file"):
        namespace = decoded(free.get("namespace_b64")) if free.get("namespace_status") == "available" else None
        return (namespace, ()) if namespace is not None else None
    # Existing class/member proof owns qualified implementations. A namespace
    # string in call transport alone cannot relabel an unknown owner as a class.
    member = _native_member(caller)
    native = member or _fact(caller, "cpp_constructor")
    if not native:
        return None
    if (fact["caller_native_family"] != ("member" if member else "constructor")
            or fact["caller_native_signature"] != native["signature"]):
        return None
    span_matches = (native.get("span") == fact["caller_span"] and caller.get("source_file") == call.get("source_file")
                    or native.get("definition_span") == fact["caller_span"] and caller.get("definition_file") == call.get("source_file"))
    # Canonical ordinary member merges retain the definition's file/location,
    # not its second span. The original call-site producer carries the native
    # signature, while actual file containment independently proves that body.
    if not span_matches:
        line = f"L{fact['caller_span']['start_row'] + 1}"
        record = fact.get("caller_body_proof")
        body_node = {"label": record.get("label"), "source_location": record.get("source_location"),
                     "source_file": call.get("source_file"), "_callable": True,
                     "metadata": {"cpp_member": record.get("fact")}} if isinstance(record, dict) else {}
        body = _native_member(body_node)
        raw_owner = decoded(body.get("owner_b64"))
        possible = {raw_owner} | {scope + "::" + raw_owner for value in body.get("using_b64", ())
                                 if (scope := decoded(value)) is not None} if raw_owner else set()
        span_matches = (fact.get("caller_native_family") == "member" and body.get("role") == "definition"
                        and body.get("ambiguous") is False and body.get("span") == fact["caller_span"]
                        and decoded(native.get("owner_b64")) in possible
                        and fact.get("caller_native_signature") == body.get("signature") == native["signature"]
                        and caller.get("definition_file") == call.get("source_file")
                        and caller.get("definition_location") == line
                        and (call.get("source_file"), line) in definitions.get(caller["id"], ()))
    if not span_matches:
        return None
    accepted_owners = owners.get(caller["id"], {})
    if len(accepted_owners) != 1:
        return None
    owner = decoded(native.get("owner_b64"))
    possible = {owner} | {scope + "::" + owner for value in (member.get("using_b64", ()) if member else ())
                          if (scope := decoded(value))} if owner else set()
    if decoded(next(iter(accepted_owners.values())).get("qualified_name_b64")) not in possible:
        return None  # A damaged method edge cannot relabel the original source owner.
    # Qualified class identity includes lexical parent classes. Only the
    # source-role witness plus actual containment can separate namespace lookup
    # from enclosing-class hiding; a missing parent supplies neither authority.
    return class_scopes.scope(next(iter(accepted_owners)))


def _direct_member_scopes(nodes, edges):
    """Borrow same-file pair ownership for scope, retaining actual body IDs.

    The declaration proxy also owns field/method hiding. This creates no source
    edge, native endpoint, canonical ID, or authority for a foreign-file body.
    """
    choices = {}
    for body, declaration, owner in proven_member_pairs(nodes, edges):
        if body.get("source_file") == declaration.get("source_file"):
            key = (declaration["id"], owner["id"])
            choices.setdefault(body["id"], {})[key] = class_fact(owner)
    return {caller: (*next(iter(values)), next(iter(values.values())))
            for caller, values in choices.items() if len(values) == 1}


def resolve_free_function_calls(nodes, edges, raw_calls):
    """Consume source sites using the complete accepted view, without mutating context."""
    by_id = {node["id"]: node for node in nodes}
    bodies, prototypes, all_names = {}, {}, set()
    anonymous = AnonymousFunctions()
    for node in nodes:
        fact = free_definition_fact(node)
        if fact:
            name = decoded(fact.get("name_b64"))
            all_names.add(name)
            anonymous.add(node, fact, name)
            qualified = decoded(fact.get("qualified_name_b64"))
            if fact.get("namespace_status") == "available" and qualified:
                bodies.setdefault(qualified, []).append((node, fact))
        prototype = _prototype(node)
        if prototype:
            qualified = decoded(prototype["qualified_name_b64"])
            if qualified is not None:
                all_names.add(qualified.rsplit("::", 1)[-1])
                prototypes.setdefault(qualified, []).append({**prototype, "source_file": node["source_file"]})
    known = set(bodies) | set(prototypes)
    direct_scopes = _direct_member_scopes(nodes, edges)
    fields = FieldCallPolicy(nodes, edges)
    class_scopes = CppClassScopes(nodes, edges)
    owners, definitions = {}, {}
    for edge in edges:
        if edge.get("relation") == "contains" and edge.get("confidence") == "EXTRACTED":
            file_node = by_id.get(edge.get("source"), {})
            if (file_node.get("source_file") == edge.get("source_file") and file_node.get("source_location") == "L1"
                    and not file_node.get("_callable") and not file_node.get("_callable_class")):
                definitions.setdefault(edge.get("target"), set()).add((edge.get("source_file"), edge.get("source_location")))
        if edge.get("relation") == "method" and edge.get("confidence") == "EXTRACTED":
            owner = by_id.get(edge.get("source"), {})
            proof = class_fact(owner)
            if proof and proof["is_definition"] and not proof["ambiguous"]:
                owners.setdefault(edge.get("target"), {})[owner["id"]] = proof
    for caller, (_, owner_id, proof) in direct_scopes.items():
        owners.setdefault(caller, {})[owner_id] = proof
    for node in nodes:
        if name := anonymous.add_declaration(node, definitions):
            all_names.add(name)
    existing = {(edge.get("source"), edge.get("target")) for edge in edges if edge.get("relation") == "calls"}
    for call in raw_calls:
        fact = _call(call)
        if not fact or call.get("callee") not in all_names:
            continue
        if not fact["qualified"]:
            call["_cpp_free_handled"] = True
        caller = by_id.get(call.get("caller_nid"))
        scope = _caller_scope(caller, call, fact, owners, definitions, class_scopes)
        if scope is None:
            continue
        namespace, lexical_classes = scope
        name = decoded(fact["name_b64"])
        qualifier = decoded(fact["qualifier_b64"])
        prefixes = [""] if fact["absolute"] else ["::".join(namespace.split("::")[:end]) for end in range(len(namespace.split("::")), -1, -1)]
        choices = ["::".join(filter(None, (prefix, qualifier, name))) if fact["qualified"] else
                   "::".join(filter(None, (prefix, name))) for prefix in prefixes]
        anonymous_choices = {choice: anonymous.at(call.get("source_file"), choice.rsplit("::", 1)[0] if "::" in choice else "",
                                                  name, fact["span"]["start_byte"]) for choice in choices} if not fact["qualified"] else {}
        selected = next((choice for choice in choices if choice in known or any(anonymous_choices.get(choice, ([], False)))), None)
        if selected is None:
            continue
        call["_cpp_free_handled"] = True
        shadow_owner = direct_scopes[call["caller_nid"]][0] if call.get("caller_nid") in direct_scopes else call.get("caller_nid")
        if (fact["shadowed"] or fact["template"] or fact["unevaluated"] or fact["using_namespace_unavailable"]
                or not fact["qualified"] and (fields.has_member(shadow_owner, call.get("callee"))
                    or any(fields.has_member(owner, call.get("callee")) for owner in lexical_classes))):
            continue
        anonymous_bodies, unknown_anonymous = anonymous_choices.get(selected, ([], False))
        if unknown_anonymous or anonymous_bodies and (selected in known or len(anonymous_bodies) != 1):
            continue  # Anonymous and named declarations can make the same lookup ambiguous.
        declarations = prototypes.get(selected, [])
        viable = []
        for node, definition in (anonymous_bodies or bodies.get(selected, [])):
            if anonymous_bodies and (node["source_file"], node["source_location"]) not in definitions.get(node["id"], ()):
                continue  # The target's actual file edge independently owns its same-TU source frame.
            if (definition["ambiguous"] or definition["template"] or definition["conditional"] or definition.get("scope_complete") is not True
                    or definition.get("arity_status") != "available"
                    or definition["signature_status"] != "normalized" or definition["max_args"] is None
                    or definition["static"] and node.get("source_file") != call.get("source_file")):
                continue
            bounds = [(definition["max_args"], definition["max_args"])]
            if node.get("source_file") == call.get("source_file") and definition["span"]["start_byte"] < fact["span"]["start_byte"]:
                bounds.append((definition["min_args"], definition["max_args"]))
            if declarations:
                if definition.get("canonical_status") != "available" or any(
                    value.get("canonical_status") != "available" or value.get("canonical_parameters") != definition.get("canonical_parameters")
                    or value.get("arity_status") != "available"
                    or value["template"] or value["conditional"] or not value["scope_complete"]
                    or value["static"] and value["source_file"] != call.get("source_file")
                    for value in declarations
                ):
                    continue
                bounds.extend((value["min_args"], value["max_args"]) for value in declarations
                              if value["source_file"] == call.get("source_file") and value["span"]["end_byte"] <= fact["span"]["start_byte"])
            if any(type(maximum) is int and minimum <= fact["argc"] <= maximum for minimum, maximum in bounds):
                viable.append(node["id"])
        if len(set(viable)) != 1:
            continue
        target = viable[0]
        pair = (call["caller_nid"], target)
        if pair in existing or pair[0] == pair[1]:
            continue
        existing.add(pair)
        edges.append({"source": pair[0], "target": pair[1], "relation": "calls", "context": "cpp_free_function",
                      "confidence": "EXTRACTED", "source_file": call["source_file"], "source_location": call["source_location"], "weight": 1.0})
    # Legacy receiver-typed call transport describes the same source site. Once
    # this owner proves namespace lookup, it cannot also become a class lookup.
    handled = {(call.get("caller_nid"), call.get("callee"), call.get("source_file"), call.get("source_location"),
                decoded(call["cpp_free_call"].get("qualifier_b64"))) for call in raw_calls
               if call.get("_cpp_free_handled") and _call(call)}
    for call in raw_calls:
        if (call.get("caller_nid"), call.get("callee"), call.get("source_file"), call.get("source_location"),
                call.get("receiver") or "") in handled:
            call["_cpp_free_handled"] = True
