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
from graphify.extractors.qt_cpp_syntax import QtCppError, read_cpp
from graphify.extractors.qt_cpp_variables import simple_reference, variables_at

_METHODS = {"load", "loadFromModule", "setSource", "create", "createWithInitialProperties", "rootObjects", "rootObject",
            "findChild", "property", "setProperty", "invokeMethod", "read", "write", "setContextProperty", "setContextObject", "setInitialProperties"}
_LOADERS = {"QQmlApplicationEngine", "QQmlEngine", "QQmlComponent", "QQuickView"}


def _site(facts, unit, mapping, call):
    args, method = call["args"], call["name"]
    variables = variables_at(unit, mapping, call["start_byte"])
    receiver = call["receiver"]
    receiver_type = variables.get(receiver, "")
    assigned = assigned_handle(unit, call)
    common = {"owner_class": call["owner"].get("class_name") or "", "receiver_reference": receiver,
              "owner_scope_key": owner_scope(unit, call["owner"]),
              "receiver_type": receiver_type, "assigned_handle": assigned_handle(unit, call),
              "assignment_byte": last_assignment(unit, call["owner"], assigned, call["start_byte"]),
              "receiver_assignment_byte": last_assignment(unit, call["owner"], receiver, call["start_byte"]),
              "conditional": conditional_at(unit, call["start_byte"]), "status": "pending", "reason": "",
              "bridge_direction": "cpp_to_qml"}
    if method in {"load", "loadFromModule", "setSource", "create", "createWithInitialProperties", "rootObjects", "rootObject", "setInitialProperties"}:
        if receiver_type.rsplit("::", 1)[-1] not in _LOADERS:
            return
        values = {**common, "operation": method, "literal_url": literal_string(args[0]["text"]) if args and method in {"load", "setSource"} else None,
                  "module_uri": literal_string(args[0]["text"]) if args and method == "loadFromModule" else None,
                  "type_name": literal_string(args[1]["text"]) if len(args) >= 2 and method == "loadFromModule" else None}
        if method == "rootObjects":
            after = unit.code[call["end_byte"]:call["end_byte"] + 40]
            values["single_root_selection"] = bool(re.match(rb"\s*\.\s*(?:first\(\)|at\(0\))", after))
        if method in {"createWithInitialProperties", "setInitialProperties"}:
            values["properties"], values["literal_properties"] = literal_map(args[0]["text"] if args else "")
            if not values["literal_properties"]:
                values.update(status="dynamic", reason="computed_initial_properties")
            for item in values["properties"]:
                item["provider_type"] = variables.get(item["provider_reference"], "")
        facts.add("qml_load" if method in {"load", "loadFromModule", "setSource"} else "qml_root" if method in {"rootObjects", "rootObject", "create", "createWithInitialProperties"} else "initial_properties", method, call["span"], call["owner"].get("node_id"), **values)
    elif method in {"setContextProperty", "setContextObject"}:
        # Only direct engine.rootContext() chains or a typed QQmlContext receiver
        # establish context provenance. Arbitrary factory/context aliases do not.
        before = unit.code[max(0, call["start_byte"] - 120):call["start_byte"]].decode()
        chain = re.search(r"([A-Za-z_]\w*)\s*(?:\.|->)rootContext\(\)\s*->\s*$", before)
        engine = chain[1] if chain else ""
        if not engine and receiver_type != "QQmlContext":
            return
        provider = simple_reference(args[1 if method == "setContextProperty" else 0]["text"]) if len(args) >= (2 if method == "setContextProperty" else 1) else ""
        facts.add("context_exposure", method, call["span"], call["owner"].get("node_id"), **common,
                  engine_reference=engine, engine_type=variables.get(engine, ""),
                  exposed_name=literal_string(args[0]["text"]) if args and method == "setContextProperty" else None,
                  provider_reference=provider, provider_type=variables.get(provider, ""), operation=method)
    elif method in {"findChild", "property", "setProperty", "invokeMethod", "read", "write"}:
        if method == "invokeMethod" or call["callee"] in {"QQmlProperty::read", "QQmlProperty::write"}:
            if method == "invokeMethod" and call["callee"] != "QMetaObject::invokeMethod":
                return
            receiver, role = handle_argument(args[0]["text"] if args else "")
            name = literal_string(args[1]["text"]) if len(args) > 1 else None
        else:
            role, name = "variable", literal_string(args[0]["text"]) if args else None
        facts.add("qml_access", method, call["span"], call["owner"].get("node_id"), **{**common, "receiver_reference": receiver,
                  "receiver_assignment_byte": last_assignment(unit, call["owner"], receiver, call["start_byte"])},
                  operation=method, lookup_name=name, handle_role=role)


def _component_constructors(unit, mapping, facts):
    for match in re.finditer(rb"\bQQmlComponent\s+([A-Za-z_]\w*)\s*\(", unit.code):
        owner = mapping.owner_at(match.start())
        if not owner or owner.get("body") is None:
            continue
        from graphify.extractors.qt_cpp_calls import argument_ranges, closing
        from graphify.extractors.qt_cpp_syntax import source_span
        left, right = match.end() - 1, closing(unit.code, match.end() - 1)
        if right is None:
            continue
        args = argument_ranges(unit.code, left + 1, right)
        facts.add("qml_load", "QQmlComponent", source_span(unit.source, match.start(), right + 1), owner.get("node_id"),
                  receiver_reference=match[1].decode(), receiver_type="QQmlComponent", operation="component_constructor",
                  owner_scope_key=owner_scope(unit, owner),
                  engine_reference=simple_reference(unit.source[args[0][0]:args[0][1]].decode()) if args else "",
                  literal_url=literal_string(unit.source[args[1][0]:args[1][1]].decode()) if len(args) > 1 else None,
                  assigned_handle="", conditional=conditional_at(unit, match.start()), status="pending", reason="", bridge_direction="cpp_to_qml")
    for match in re.finditer(rb"\bQQmlProperty\s+([A-Za-z_]\w*)\s*\(", unit.code):
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
                  receiver_reference=receiver, operation="QQmlProperty", receiver_type="", assigned_handle=match[1].decode(), assignment_byte=-1,
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
            _component_constructors(unit, mapping, facts)
            for call in calls(unit, mapping, _METHODS):
                _site(facts, unit, mapping, call)
            result.setdefault("nodes", []).extend(facts.nodes)
            result.setdefault("edges", []).extend(facts.edges)
        except (QtCppError, ValueError) as error:
            _failure(result, Path(path), Path(root), error)
