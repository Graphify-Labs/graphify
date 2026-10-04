"""Qt C++ event occurrences; event delivery is never an ordinary calls edge."""
from __future__ import annotations

import re
from pathlib import Path

from graphify.extractors.qt_cpp_calls import calls, conditional_at
from graphify.extractors.qt_cpp_access_patterns import assigned_handle, last_assignment
from graphify.extractors.qt_cpp_event_patterns import connection_flags, endpoint, lambda_parameters
from graphify.extractors.qt_cpp_exposure import is_qt_cpp_source
from graphify.extractors.qt_cpp_facts import QtFacts, owner_scope, qt_metadata, update_qt
from graphify.extractors.qt_cpp_mapping import map_cpp
from graphify.extractors.qt_cpp_identity import CppDeclarationIdentity
from graphify.extractors.qt_cpp_syntax import QtCppError, read_cpp
from graphify.extractors.qt_cpp_variables import simple_reference, variables_at
from graphify.extractors.qt_cpp_type_scope import NativeTypeScope


CPP_SUFFIXES = {".cpp", ".cc", ".cxx", ".c++", ".hpp", ".hh", ".hxx", ".h"}


def _failure(result, path, root, error):
    try:
        name = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        name = path.name
    code = error.code if isinstance(error, QtCppError) else "QT_CPP_LIMIT"
    result.setdefault("qt_failures", []).append({"code": code, "source_file": name})
    result.setdefault("diagnostics", []).append({"code": code, "source_file": name, "severity": "error",
        "owner": "qt_cpp", "message": "Qt source analysis could not complete", "recovery": "Correct source and retry; prior graph is preserved."})


def _qt_owner(mapping, owner):
    classes = [record for record in mapping.classes if record.get("node_id") == owner.get("class_id")]
    return any(any(macro["name"] == "Q_OBJECT" for macro in record.get("macros", [])) for record in classes)


def _typed_endpoint(expression, types, call):
    """Member-pointer qualification obeys the same lexical type authority as locals."""
    value = endpoint(expression)
    if value["form"] == "member_pointer":
        raw_name = value["class_name"]
        resolved = types.lookup(raw_name, call["start_byte"], owner=call["owner"])
        value.update(raw_class_name=raw_name, class_name=resolved.name)
        if not resolved.name:
            value.update(form="dynamic", type_reason=resolved.reason)
    return value


def _connection(facts, unit, mapping, call, types, identity):
    owner, args = call["owner"], call["args"]
    if call.get("computed_receiver") or ("::" in call["callee"] and call["callee"] != "QObject::" + call["name"]):
        return
    if call["callee"] != "QObject::" + call["name"] and not _qt_owner(mapping, owner):
        return
    if call["callee"] == call["name"] and any(function["name"] == call["name"] and function.get("class_id") == owner.get("class_id") for function in mapping.functions):
        return
    variables = variables_at(unit, mapping, call["start_byte"], type_scope=types)
    signal = _typed_endpoint(args[1]["text"], types, call) if len(args) >= 2 else endpoint("")
    receiver, context, callable_arg, flag_arg = "", "", None, ""
    if len(args) in {4, 5}:
        receiver = simple_reference(args[2]["text"])
        context = receiver
        callable_arg = args[3]
        flag_arg = args[4]["text"] if len(args) == 5 else ""
    elif len(args) == 3:
        callable_arg = args[2]
    callable_text = callable_arg["text"] if callable_arg else ""
    parameters = lambda_parameters(callable_text)
    receiver_endpoint = _typed_endpoint(callable_text, types, call)
    form = "lambda" if parameters is not None else receiver_endpoint["form"]
    callable_reference = simple_reference(callable_text)
    if form == "dynamic" and callable_reference:
        form = "functor" if variables.get(callable_reference) else "function"
    sender = simple_reference(args[0]["text"]) if args else ""
    sender_identity = identity.resolve(sender, call["start_byte"])
    receiver_identity = identity.resolve(receiver, call["start_byte"])
    site = facts.add(call["name"], call["name"], call["span"], owner.get("node_id"),
        owner_class=owner.get("class_name") or "", owner_status=owner.get("status") or "unavailable",
        owner_scope_key=owner_scope(unit, owner),
        sender_reference=sender, sender_type=variables.get(sender, ""), signal=signal,
        sender_declaration_id=sender_identity["declaration_id"],
        receiver_reference=receiver, receiver_type=variables.get(receiver, ""), receiver=receiver_endpoint,
        receiver_declaration_id=receiver_identity["declaration_id"],
        context_reference=context, context_type=variables.get(context, ""), callable_form=form,
        callable_reference=callable_reference, callable_type=variables.get(callable_reference, ""),
        assigned_handle=assigned_handle(unit, call),
        assignment_byte=last_assignment(unit, owner, assigned_handle(unit, call), call["start_byte"]),
        handle_reference=simple_reference(args[0]["text"]) if call["name"] == "disconnect" and len(args) == 1 else "",
        handle_assignment_byte=last_assignment(unit, owner, sender, call["start_byte"]),
        sender_assignment_byte=last_assignment(unit, owner, sender, call["start_byte"]),
        receiver_assignment_byte=last_assignment(unit, owner, receiver, call["start_byte"]),
        signal_wildcard=len(args) > 1 and args[1]["text"] in {"nullptr", "0"},
        receiver_wildcard=len(args) > 2 and args[2]["text"] in {"nullptr", "0"},
        callable_wildcard=len(args) > 3 and args[3]["text"] in {"nullptr", "0"},
        conditional=conditional_at(unit, call["start_byte"]),
        status="pending", reason="", runtime_delivery="unverified", **connection_flags(flag_arg))
    if parameters is not None and callable_arg:
        target = facts.add("lambda", "connected lambda", callable_arg["span"], site,
                           parameter_types=parameters, callable_form="lambda")
        update_qt(site, lambda_id=target["id"])


def _emission(facts, unit, mapping, call, types, identity):
    owner = call["owner"]
    variables = variables_at(unit, mapping, call["start_byte"], type_scope=types)
    receiver = call["receiver"] or ("" if call.get("computed_receiver") else "this")
    prefix = unit.code[max(0, call["start_byte"] - 40):call["start_byte"]]
    explicit = bool(re.search(rb"\b(?:emit|Q_EMIT)\s*$", prefix))
    if not explicit and not _qt_owner(mapping, owner) and not variables.get(receiver):
        return
    # Preserve independent typed receivers; an unbound constructor cannot infer
    # a native `this` type solely from its syntactic class qualification.
    receiver_type = variables.get(receiver, "")
    if receiver == "this":
        receiver_type = "" if owner.get("native_owner_unavailable") else receiver_type or owner.get("class_name", "")
    facts.add("emission", call["name"], call["span"], owner.get("node_id"),
              owner_class=owner.get("class_name") or "", receiver_reference=receiver,
              owner_scope_key=owner_scope(unit, owner),
              receiver_declaration_id=identity.resolve(receiver, call["start_byte"])["declaration_id"],
              receiver_type=receiver_type,
              member_name=call["name"], argument_count=len(call["args"]), explicit_emit=explicit,
              conditional=conditional_at(unit, call["start_byte"]), status="pending", reason="")


def collect_qt_cpp_events(paths, per_file, *, root: Path, accepted_nodes=None, accepted_edges=None):
    """Enrich admitted results after canonicalization; never regenerate C++ definitions."""
    nodes = accepted_nodes if accepted_nodes is not None else [n for r in per_file if r for n in r.get("nodes", [])]
    edges = accepted_edges if accepted_edges is not None else [e for r in per_file if r for e in r.get("edges", [])]
    signals = {qt_metadata(node).get("raw_name") for node in nodes if "signal" in qt_metadata(node).get("roles", [])}
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
            types = NativeTypeScope(unit, mapping)
            identity = CppDeclarationIdentity(unit, mapping)
            local_signals = {f["name"] for f in mapping.functions if "signal" in f.get("roles", [])}
            for function in mapping.functions:
                if not function.get("class_name") and function.get("node_id"):
                    facts.add("callable", function["qualified_name"], function["span"], function["node_id"],
                              generic_target_id=function["node_id"], parameter_types=function["parameter_types"],
                              callable_name=function["qualified_name"], status="resolved")
            for call in calls(unit, mapping, {"connect", "disconnect"} | signals | local_signals):
                if call["name"] in {"connect", "disconnect"}:
                    _connection(facts, unit, mapping, call, types, identity)
                else:
                    _emission(facts, unit, mapping, call, types, identity)
            known = {node["id"] for node in result.get("nodes", [])}
            result.setdefault("nodes", []).extend(node for node in facts.nodes if node["id"] not in known)
            result.setdefault("edges", []).extend(facts.edges)
        except (QtCppError, ValueError) as error:
            _failure(result, Path(path), Path(root), error)
