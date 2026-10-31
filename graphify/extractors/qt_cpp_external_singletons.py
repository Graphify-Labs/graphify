"""Source occurrences of Qt6.12 engine-specific external-singleton setup.

SDK declarations, actual receiver syntax and later source-load checkpoints own
identity. This collector never creates registrations or executes an instance.
"""
from __future__ import annotations

import re

from graphify.extractors.qt_cpp_calls import conditional_at, literal_string
from graphify.extractors.qt_cpp_api_shape import api_shape
from graphify.extractors.qt_cpp_facts import owner_scope, qt_metadata, update_qt
from graphify.extractors.qt_cpp_identity import source_reference_key
from graphify.extractors.qt_cpp_loaders import declared_sdk_type
from graphify.extractors.qt_cpp_provider_expression import provider_expression
from graphify.extractors.qt_cpp_syntax import walk
from graphify.extractors.qt_cpp_variables import type_name, variables_at
from graphify.extractors.qt_cpp_external_state import engine_escaped, executable_context


def _identity(identities, name, position, role):
    value = identities.resolve(name, position)
    return {role + "_declaration_id": value["declaration_id"],
            role + "_identity_status": value["status"], role + "_identity_reason": value["reason"],
            **({"provider_scope_end": value["scope_span"].get("end_byte", -1)} if role == "provider" else {})}


def _engine_calls(unit, mapping, identities, types):
    """Only a direct SDK receiver can own this API; chained text is insufficient."""
    for syntax in walk(unit.tree):
        if syntax.type != "call_expression":
            continue
        function = syntax.child_by_field_name("function")
        if function is None or function.type != "field_expression":
            continue
        receiver = function.child_by_field_name("argument")
        member = function.child_by_field_name("field")
        name = unit.field(member, "name") if member is not None and member.type == "template_method" else unit.text(member)
        if name not in {"setExternalSingletonInstance", "singletonInstance", "clearSingletons"} or receiver is None or receiver.type != "identifier":
            continue
        reference, position = unit.text(receiver), syntax.start_byte
        owner = mapping.owner_at(position)
        if owner is None or owner.get("body") is None:
            continue
        spelling, declared_at = identities.type_binding(reference, position)
        receiver_type = types.resolve(type_name(spelling), declared_at) if spelling else ""
        if receiver_type not in {"QQmlEngine", "QQmlApplicationEngine"} or not declared_sdk_type(
                identities, types, reference, position, receiver_type):
            continue
        arguments = syntax.child_by_field_name("arguments")
        args = [unit.text(item) for item in arguments.named_children if item.type != "comment"] if arguments else []
        executable = executable_context(syntax, owner["body"], nonpolymorphic_result=True)
        # Assertions do not prove unique argument execution (retry forms may
        # repeat). Retain occurrences without singleton setup/use/reset authority.
        executable = executable and not any(item["kind"] == "test_assertion"
            and item["start"] <= position < item["end"] for item in unit.qt_test_macros)
        declared_spelling, _ = identities.declared_type_binding(reference, position)
        shape = api_shape(declared_spelling, allow_value=True)
        operator = unit.field(function, "operator")
        yield {"syntax": syntax, "name": name, "receiver": reference, "receiver_type": receiver_type,
               "owner": owner, "args": args, "executable": executable,
               "template_call": member is not None and member.type == "template_method",
               "receiver_shape_supported": shape is not None and operator == ("->" if shape[1] == "pointer" else "."),
               "receiver_potential_declaration_id": identities.potential_declaration(reference, position)["declaration_id"],
               **_identity(identities, reference, position, "receiver")}


def _literal_name(value, identities, types, position):
    """Source-defined wrappers cannot lend authority to a seemingly literal name."""
    for wrapper in re.findall(r"\b([A-Za-z_]\w*)\s*\(", value):
        if (wrapper not in {"QStringLiteral", "QString", "QLatin1String"}
                or not types.sdk_type(wrapper, position, wrapper)
                or types.callable_shadow(wrapper, position)
                or identities.resolve(wrapper, position)["status"] in {"resolved", "dynamic", "ambiguous"}):
            return None
    return literal_string(value)


def collect_external_singletons(unit, mapping, facts, identities, types):
    """Use already-collected loads to bind source checkpoints without global state."""
    calls = list(_engine_calls(unit, mapping, identities, types))
    setups = []
    for call in calls:
        if call["name"] != "setExternalSingletonInstance":
            continue
        syntax, args = call["syntax"], call["args"]
        position = syntax.start_byte
        expression = args[2] if len(args) == 3 else ""
        declared = provider_expression(expression, identities, types, position)
        provider = declared.pop("provider_reference", "")
        variables = variables_at(unit, mapping, position, type_scope=types)
        uri = _literal_name(args[0], identities, types, position) if len(args) == 3 else None
        name = _literal_name(args[1], identities, types, position) if len(args) == 3 else None
        supported = len(args) == 3 and call["executable"] and not call["template_call"] and call["receiver_shape_supported"]
        node = facts.add("external_singleton_setup", call["name"], syntax, call["owner"].get("node_id"),
                         owner_scope_key=owner_scope(unit, call["owner"]), operation=call["name"],
                         receiver_reference=call["receiver"], receiver_type=call["receiver_type"],
                         **{key: value for key, value in call.items() if key.startswith("receiver_") and key not in {"receiver_type"}},
                         **_identity(identities, provider, position, "provider"), **declared,
                         provider_reference=provider, provider_type=variables.get(provider, ""),
                         module_uri=uri, type_name=name, api_supported=supported,
                         conditional=conditional_at(unit, position), status="pending", reason="",
                         runtime_success="unverified", lifetime_status="unverified", ownership_transfer=False,
                         bridge_direction="cpp_to_qml")
        earlier = [other for other in calls if other["name"] == "singletonInstance"
                   and other["syntax"].start_byte < position
                   and other["receiver_potential_declaration_id"] == call["receiver_potential_declaration_id"]
                   and bool(call["receiver_potential_declaration_id"]) and other["executable"]
                   and other["owner"] is call["owner"]]
        update_qt(node, prior_singleton_use=bool(earlier))
        setups.append(node)
    loads = [node for node in facts.nodes if qt_metadata(node).get("kind") == "qml_load"]
    for node in setups:
        md = qt_metadata(node)
        key = source_reference_key(md)
        candidates = [load for load in loads if key is not None and key in {
            source_reference_key(qt_metadata(load), role) for role in ("receiver", "engine")}]
        if len(candidates) != 1:
            continue
        load = candidates[0]
        checkpoint = identities.resolve(md["provider_reference"], qt_metadata(load)["span"]["start_byte"])
        reset = any(other["name"] == "clearSingletons" and other["receiver_potential_declaration_id"] == md["receiver_declaration_id"]
                    and other["executable"]
                    and md["span"]["end_byte"] < other["syntax"].start_byte < qt_metadata(load)["span"]["start_byte"]
                    for other in calls)
        update_qt(node, checkpoint_load_id=load["id"], provider_at_load_declaration_id=checkpoint["declaration_id"],
                  provider_at_load_status=checkpoint["status"], provider_at_load_reason=checkpoint["reason"],
                  singleton_state_reset=reset,
                  engine_escaped=engine_escaped(unit, mapping, identities, mapping.owner_at(md["span"]["start_byte"]),
                                                md["receiver_declaration_id"], qt_metadata(load)["span"]["start_byte"],
                                                setup_end=md["span"]["end_byte"], module_uri=md["module_uri"], type_name=md["type_name"],
                                                component_declaration_id=qt_metadata(load).get("receiver_declaration_id", "")
                                                if qt_metadata(load).get("receiver_type") == "QQmlComponent" and
                                                qt_metadata(load).get("engine_declaration_id") == md["receiver_declaration_id"] else ""))
