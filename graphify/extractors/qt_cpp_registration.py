"""Literal Qt registration facts, retaining unsupported and conditional evidence."""
from __future__ import annotations

import json
import re

from graphify.extractors.qt_cpp_mapping import normalize_type
from graphify.extractors.qt_cpp_syntax import split_arguments, walk

_SUPPORTED = {"qmlRegisterType", "qmlRegisterUncreatableType", "qmlRegisterSingletonType",
              "qmlRegisterSingletonInstance", "qmlRegisterAnonymousType"}
_IDENTIFIER = re.compile(r"[A-Za-z_]\w*")


def literal_string(value):
    if not re.fullmatch(r'"(?:[^"\\]|\\["\\nrt])*"', value):
        return None
    try:
        return json.loads(value)
    except ValueError:
        return None


def conditional(syntax):
    parent = syntax.parent
    while parent:
        if parent.type in {"if_statement", "switch_statement", "for_statement", "while_statement",
                           "do_statement", "conditional_expression", "preproc_if", "preproc_ifdef", "preproc_else"}:
            return True
        parent = parent.parent
    return False


def conditional_offset(unit, byte):
    return any(node.type in {"preproc_if", "preproc_ifdef", "preproc_else"}
               and node.start_byte <= byte < node.end_byte for node in walk(unit.tree))


def _scope(unit, syntax):
    scopes, parent = [], syntax.parent
    while parent:
        if parent.type in {"namespace_definition", "class_specifier", "struct_specifier"}:
            name = unit.field(parent, "name")
            if name:
                scopes.append(name)
        parent = parent.parent
    return list(reversed(scopes))


def class_target(unit, syntax, raw_type, classes):
    """Qualified lexical candidates only, never a corpus-wide basename lookup."""
    raw_type = normalize_type(raw_type).removeprefix("::")
    if not re.fullmatch(r"[A-Za-z_]\w*(?:::[A-Za-z_]\w*)*", raw_type):
        return [], "class_expression_unsupported"
    if "::" in raw_type:
        wanted = [raw_type]
    else:
        scopes = _scope(unit, syntax)
        wanted = ["::".join(scopes[:count] + [raw_type]) for count in range(len(scopes), -1, -1)]
    for qualified in wanted:
        matches = [record for record in classes if record["qualified_name"] == qualified]
        if matches:
            ids = {record["node_id"] for record in matches if record["node_id"]}
            return sorted(ids), "" if len(ids) == 1 else "class_mapping_ambiguous_or_unavailable"
    return [], "class_not_in_corpus"


def add_macro_registration(mapping, facts, record):
    owned = [macro for macro in record["macros"] if mapping.class_at(macro["start_byte"]) is record]
    macros = {macro["name"]: macro for macro in owned}
    named = macros.get("QML_NAMED_ELEMENT") or macros.get("QML_ELEMENT") or macros.get("QML_ANONYMOUS")
    if named is None:
        return
    name = record["name"] if named["name"] == "QML_ELEMENT" else ""
    status, reason = record["status"], "" if record["node_id"] else "class_mapping_unavailable"
    if named["name"] == "QML_NAMED_ELEMENT":
        args = named["args"]
        if len(args) == 1 and _IDENTIFIER.fullmatch(args[0]):
            name = args[0]
        else:
            status, reason = "unsupported", "named_element_requires_identifier"
    flags = {"singleton": "QML_SINGLETON" in macros, "anonymous": "QML_ANONYMOUS" in macros,
             "creatable": "QML_UNCREATABLE" not in macros and "QML_ANONYMOUS" not in macros}
    allowed = {"QML_ELEMENT", "QML_NAMED_ELEMENT", "QML_ANONYMOUS", "QML_SINGLETON", "QML_UNCREATABLE",
               "QML_ADDED_IN_VERSION", "QML_REMOVED_IN_VERSION"}
    unsupported = sorted(name for name in macros if name.startswith("QML_") and name not in allowed)
    if unsupported:
        status, reason = "unsupported", "foreign_extended_or_attached_mapping_unsupported"
    if conditional(record["syntax"]) or conditional_offset(mapping.unit, named["start_byte"]):
        status, reason = "dynamic", "conditional_exposure"
    fields = {"class_id": record["node_id"], "generic_target_id": record["node_id"],
              "class_name": record["qualified_name"], "mechanism": named["name"], "status": status,
              "reason": reason, "module_source_file": mapping.unit.relative_file, "module_required": True,
              "unsupported_macros": unsupported, **flags}
    fields["annotations"] = [{key: macro[key] for key in ("name", "args", "span")}
                             for macro in owned if macro["name"].startswith("QML_")]
    for macro_name, key in (("QML_ADDED_IN_VERSION", "added_version"), ("QML_REMOVED_IN_VERSION", "removed_version")):
        macro = macros.get(macro_name)
        if macro:
            args = macro["args"]
            if len(args) == 2 and all(re.fullmatch(r"\d+", arg) for arg in args):
                fields[key] = [int(arg) for arg in args]
            else:
                fields.update(status="unsupported", reason="exposure_version_expression_unsupported")
    facts.add("registration", name, named["span"], owner=record["node_id"] or None, **fields)


def add_literal_registrations(mapping, facts, classes):
    unit = mapping.unit
    for syntax in walk(unit.tree):
        if syntax.type != "call_expression":
            continue
        function = syntax.child_by_field_name("function")
        name = unit.field(function, "name") if function and function.type == "template_function" else unit.text(function)
        if not re.fullmatch(r"qmlRegister[A-Za-z_]\w*", name):
            continue
        template = function.child_by_field_name("arguments") if function else None
        types = split_arguments(unit.source[template.start_byte + 1:template.end_byte - 1]) if template else []
        arguments = syntax.child_by_field_name("arguments")
        args = split_arguments(unit.source[arguments.start_byte + 1:arguments.end_byte - 1]) if arguments else []
        owner = mapping.owner_at(syntax.start_byte)
        fields = {"mechanism": name, "module_required": False, "status": "unsupported",
                  "reason": "literal_registration_arguments_unsupported", "class_id": "", "generic_target_id": "",
                  "raw_type": types[0] if types else "", "class_name": "", "singleton": "Singleton" in name,
                  "anonymous": name == "qmlRegisterAnonymousType", "creatable": name == "qmlRegisterType"}
        raw_name = ""
        needed = 2 if fields["anonymous"] else 4 if name == "qmlRegisterType" else 5
        if name not in _SUPPORTED:
            fields["reason"] = "registration_mechanism_unsupported"
        supported_template = len(types) == 1 or (len(types) == 2 and bool(re.fullmatch(r"\d+", types[1])))
        if name in _SUPPORTED and supported_template and len(args) == needed:
            if len(types) == 2:
                fields["metaobject_revision"] = int(types[1])
            uri = literal_string(args[0])
            version_args = args[1:2] if fields["anonymous"] else args[1:3]
            raw_name = "" if fields["anonymous"] else literal_string(args[3])
            ids, reason = class_target(unit, syntax, types[0], classes)
            if uri and raw_name is not None and all(re.fullmatch(r"\d+", arg) for arg in version_args):
                fields.update(uri=uri, major=int(version_args[0]), minor=0 if fields["anonymous"] else int(version_args[1]),
                              class_id=ids[0] if len(ids) == 1 else "", generic_target_id=ids[0] if len(ids) == 1 else "",
                              status="resolved" if len(ids) == 1 else "ambiguous" if ids else "unavailable", reason=reason)
                records = [record for record in classes if record["node_id"] == fields["class_id"]]
                fields["class_name"] = records[0]["qualified_name"] if records else ""
        if conditional(syntax):
            fields.update(status="dynamic", reason="conditional_registration")
        facts.add("registration", raw_name or "", syntax, owner=owner["node_id"] if owner and owner["node_id"] else None, **fields)
