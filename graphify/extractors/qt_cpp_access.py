"""Literal C++ to QML access occurrences, retaining engine and handle provenance."""
from __future__ import annotations

from pathlib import Path
import re

from graphify.extractors.qt_cpp_access_patterns import assigned_handle, handle_argument, last_assignment, literal_map
from graphify.extractors.qt_cpp_calls import calls, conditional_at, literal_string
from graphify.extractors.qt_cpp_events import CPP_SUFFIXES, _failure
from graphify.extractors.qt_cpp_facts import QtFacts, owner_scope
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.extractors.qt_cpp_exposure import is_qt_cpp_source
from graphify.extractors.qt_cpp_mapping import map_cpp
from graphify.extractors.qt_cpp_identity import CppDeclarationIdentity
from graphify.extractors.qt_cpp_loaders import (collect_loader_constructors, declared_sdk_type, literal_creation_arguments,
    literal_loader_arguments, literal_url_expression, loader_operation_owner)
from graphify.extractors.qt_cpp_type_scope import NativeTypeScope
from graphify.extractors.qt_cpp_syntax import QtCppError, read_cpp, source_span
from graphify.extractors.qt_cpp_variables import simple_reference, type_name, variables_at
from graphify.extractors.qt_cpp_provider_expression import provider_expression

_METHODS = {"load", "loadFromModule", "loadUrl", "setSource", "create", "createWithInitialProperties", "rootObjects", "rootObject",
            "findChild", "property", "setProperty", "setParent", "invokeMethod", "read", "write", "setContextProperty", "setContextObject", "setInitialProperties"}


def _identity_fields(identities, name, position, role):
    """Semantic joins use exact declarations; display spellings remain provenance."""
    value = identities.resolve(name, position)
    fields = {role + "_declaration_id": value["declaration_id"],
              role + "_identity_status": value["status"], role + "_identity_reason": value["reason"]}
    if role == "provider":
        fields["provider_scope_end"] = value["scope_span"].get("end_byte", -1)
    return fields


def _site(facts, unit, mapping, call, identities, types, component_engines):
    args, method = call["args"], call["name"]
    variables = variables_at(unit, mapping, call["start_byte"], type_scope=types)
    receiver = call["receiver"]
    receiver_type = variables.get(receiver, "")
    assigned = assigned_handle(unit, call)
    common = {"owner_class": call["owner"].get("class_name") or "", "receiver_reference": receiver,
              "owner_scope_key": owner_scope(unit, call["owner"]),
              "receiver_type": receiver_type, "assigned_handle": assigned_handle(unit, call),
              "assignment_byte": last_assignment(unit, call["owner"], assigned, call["start_byte"]),
              "receiver_assignment_byte": last_assignment(unit, call["owner"], receiver, call["start_byte"]),
              "conditional": conditional_at(unit, call["start_byte"]), "status": "pending", "reason": "",
              "bridge_direction": "cpp_to_qml",
              **_identity_fields(identities, receiver, call["start_byte"], "receiver"),
              **_identity_fields(identities, assigned, call["start_byte"], "assigned")}
    if method in {"load", "loadFromModule", "loadUrl", "setSource", "create", "createWithInitialProperties", "rootObjects", "rootObject", "setInitialProperties"}:
        # A reassignment loses runtime identity, but its declared SDK type still
        # identifies the observed API occurrence. Resolution keeps that uncertainty.
        if not receiver_type:
            spelling, declared_at = identities.type_binding(receiver, call["start_byte"])
            receiver_type = types.resolve(type_name(spelling), declared_at) if spelling else ""
        # Incomplete source declarations are not external SDK authority either.
        if (not loader_operation_owner(receiver_type, method)
                or not declared_sdk_type(identities, types, receiver, call["start_byte"], receiver_type.removeprefix("::"))):
            return
        loading = method in {"load", "loadFromModule", "loadUrl", "setSource"}
        supported = (literal_loader_arguments(receiver_type, method, args, types=types, position=call["start_byte"])
                     if loading else literal_creation_arguments(method, args))
        values = {**common, "receiver_type": receiver_type, "operation": method,
                  "loader_supported": supported, "loader_reason": "" if supported else "loader_overload_unestablished",
                  "literal_url": literal_url_expression(args[0]["text"], types=types, identities=identities, position=call["start_byte"]) if args and method in {"load", "loadUrl", "setSource"} else None,
                  "module_uri": literal_string(args[0]["text"]) if args and method == "loadFromModule" else None,
                  "type_name": literal_string(args[1]["text"]) if len(args) >= 2 and method == "loadFromModule" else None}
        if receiver_type == "QQmlComponent":
            association = component_engines.get(common["receiver_declaration_id"])
            if association is not None:
                values.update(association)
                if association["component_engine_supported"] is False:
                    values.update(loader_supported=False, loader_reason="component_engine_unestablished")
        if method == "rootObjects":
            after = unit.code[call["end_byte"]:call["end_byte"] + 40]
            values["single_root_selection"] = bool(re.match(rb"\s*\.\s*(?:first\(\)|at\(0\))", after))
        if method in {"createWithInitialProperties", "setInitialProperties"}:
            values["properties"], values["literal_properties"] = literal_map(args[0]["text"] if args else "")
            if not values["literal_properties"]:
                values.update(status="dynamic", reason="computed_initial_properties")
            for item in values["properties"]:
                item["provider_type"] = variables.get(item["provider_reference"], "")
                item.update(_identity_fields(identities, item["provider_reference"], call["start_byte"], "provider"))
        facts.add("qml_load" if loading else "qml_root" if method in {"rootObjects", "rootObject", "create", "createWithInitialProperties"} else "initial_properties", method, call["span"], call["owner"].get("node_id"), **values)
    elif method in {"setContextProperty", "setContextObject"}:
        # Only direct engine.rootContext() chains or a typed QQmlContext receiver
        # establish context provenance. Arbitrary factory/context aliases do not.
        before = unit.code[max(0, call["start_byte"] - 120):call["start_byte"]].decode()
        chain = re.search(r"([A-Za-z_]\w*)\s*(?:\.|->)rootContext\(\)\s*->\s*$", before)
        engine = chain[1] if chain else ""
        if not engine and receiver_type != "QQmlContext":
            return
        expression = args[1 if method == "setContextProperty" else 0]["text"] if len(args) >= (2 if method == "setContextProperty" else 1) else ""
        declared = provider_expression(expression, identities, types, call["start_byte"])
        provider = declared.pop("provider_reference", "")
        facts.add("context_exposure", method, call["span"], call["owner"].get("node_id"), **common,
                  engine_reference=engine, engine_type=variables.get(engine, ""),
                  **_identity_fields(identities, engine, call["start_byte"], "engine"),
                  **_identity_fields(identities, provider, call["start_byte"], "provider"),
                  exposed_name=literal_string(args[0]["text"]) if args and method == "setContextProperty" else None,
                  provider_reference=provider, provider_type=variables.get(provider, ""), operation=method, **declared)
    elif method == "setParent":
        # An observed parent mutation cannot establish a static QObject tree.
        # Keep its source occurrence for conservative child-lookup rejection.
        facts.add("qml_parent_mutation", method, call["span"], call["owner"].get("node_id"),
                  **common, operation=method)
    elif method in {"findChild", "property", "setProperty", "invokeMethod", "read", "write"}:
        reflection = {}
        qualifier = call["callee"].rsplit("::", 1)[0] if "::" in call["callee"] else ""
        sdk = "QMetaObject" if method == "invokeMethod" else "QQmlProperty"
        if method == "invokeMethod" or qualifier.rsplit("::", 1)[-1] == "QQmlProperty":
            if qualifier.rsplit("::", 1)[-1] != sdk:
                return
            # The shared call scanner starts at an identifier. Restore an
            # explicit global qualifier before lexical lookup and source proof.
            if unit.code[max(0, call["start_byte"] - 2):call["start_byte"]] == b"::":
                qualifier = "::" + qualifier
                call = {**call, "start_byte": call["start_byte"] - 2,
                        "span": source_span(unit.source, call["start_byte"] - 2, call["end_byte"])}
            reflection = {"reflection_type": qualifier,
                          "reflection_supported": types.sdk_type(qualifier, call["start_byte"], sdk)}
            receiver, role = handle_argument(args[0]["text"] if args else "")
            name = literal_string(args[1]["text"]) if len(args) > 1 else None
        else:
            role, name = "variable", literal_string(args[0]["text"]) if args else None
        # Only the default and exact documented enum options prove lookup depth.
        # Computed flags and unsupported overloads must not silently recurse.
        option = args[1]["text"].strip() if method == "findChild" and len(args) == 2 else "" if len(args) == 1 else "unsupported"
        depth = {"": "recursive", "Qt::FindChildrenRecursively": "recursive", "Qt::FindDirectChildrenOnly": "direct"}.get(option, "unsupported")
        callee = unit.code[call["start_byte"]:call["end_byte"]].split(b"(", 1)[0]
        filter_type = re.search(rb"findChild\s*<\s*((?:::)?QObject)\s*\*\s*>\s*$", callee)
        # The bounded filter is the SDK QObject pointer, not a same-spelled
        # lexical alias or a source-defined class with different ancestry.
        child_type_supported = bool(filter_type and
            types.resolve(filter_type[1].decode(), call["start_byte"]) == "QObject"
            and not types.classes.get("QObject"))
        facts.add("qml_access", method, call["span"], call["owner"].get("node_id"), **{**common, "receiver_reference": receiver,
                  **_identity_fields(identities, receiver, call["start_byte"], "receiver"),
                  "receiver_assignment_byte": last_assignment(unit, call["owner"], receiver, call["start_byte"])},
                  operation=method, lookup_name=name, handle_role=role, **reflection,
                  **({"find_child_options": depth, "find_child_type_supported": child_type_supported} if method == "findChild" else {}))


def _component_constructors(unit, mapping, facts, identities, types):
    # Property wrappers remain separate from component load construction.
    for match in re.finditer(rb"(?<![\w:])((?:::)?(?:[A-Za-z_]\w*::)*QQmlProperty)\s+([A-Za-z_]\w*)\s*\(", unit.code):
        owner = mapping.owner_at(match.start())
        if not owner or owner.get("body") is None:
            continue
        from graphify.extractors.qt_cpp_calls import argument_ranges, closing
        from graphify.extractors.qt_cpp_syntax import source_span
        right = closing(unit.code, match.end() - 1)
        if right is None:
            continue
        args = argument_ranges(unit.code, match.end(), right)
        receiver = simple_reference(unit.source[args[0][0]:args[0][1]].decode()) if args else ""
        facts.add("qml_access", "QQmlProperty", source_span(unit.source, match.start(), right + 1), owner.get("node_id"),
                  receiver_reference=receiver, operation="QQmlProperty", receiver_type="", assigned_handle=match[2].decode(), assignment_byte=-1,
                  **_identity_fields(identities, receiver, match.end() - 1, "receiver"),
                  **_identity_fields(identities, match[2].decode(), match.end() - 1, "assigned"),
                  reflection_type=match[1].decode(),
                  reflection_supported=types.sdk_type(match[1].decode(), match.start(), "QQmlProperty"),
                  owner_scope_key=owner_scope(unit, owner),
                  receiver_assignment_byte=last_assignment(unit, owner, receiver, match.start()),
                  lookup_name=literal_string(unit.source[args[1][0]:args[1][1]].decode()) if len(args) > 1 else None,
                  conditional=conditional_at(unit, match.start()), status="pending", reason="", bridge_direction="cpp_to_qml")


def collect_qt_cpp_access(paths, per_file, *, root: Path, accepted_nodes=None, accepted_edges=None):
    nodes = accepted_nodes if accepted_nodes is not None else [node for result in per_file if result for node in result.get("nodes", [])]
    edges = accepted_edges if accepted_edges is not None else [edge for result in per_file if result for edge in result.get("edges", [])]
    for path, result in zip(paths, per_file):
        if not result or Path(path).suffix.lower() not in CPP_SUFFIXES or result.get("error"):
            continue
        try:
            if not is_qt_cpp_source(path):
                continue
            unit = read_cpp(Path(path), Path(root))
            mapping, facts = map_cpp(unit, nodes, edges, root=Path(root)), QtFacts(unit)
            mapping.bind_classes([{"node_id": md.get("class_id", ""), "qualified_name": md.get("class_name", "")}
                                  for node in nodes if (md := qt_metadata(node)).get("kind") == "class"])
            identities = CppDeclarationIdentity(unit, mapping)
            types = NativeTypeScope(unit, mapping)
            component_engines = collect_loader_constructors(unit, mapping, facts, identities, types)
            _component_constructors(unit, mapping, facts, identities, types)
            for call in calls(unit, mapping, _METHODS):
                _site(facts, unit, mapping, call, identities, types, component_engines)
            result.setdefault("nodes", []).extend(facts.nodes)
            result.setdefault("edges", []).extend(facts.edges)
        except (QtCppError, ValueError) as error:
            _failure(result, Path(path), Path(root), error)
