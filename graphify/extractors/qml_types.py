"""Literal generated QML type descriptions, retained separately from source APIs."""
from __future__ import annotations

import json
import re
from pathlib import Path

from graphify.extractors.qml_ast import QmlInputError, load_parser
from graphify.extractors.qml_cmake import uri, version
from graphify.extractors.qml_facts import field, text
from graphify.extractors.qml_project_read import MetadataError, ProjectFacts, extract_project, failure

_COMPONENT_FIELDS = {"name", "prototype", "file", "exports", "exportMetaObjectRevisions",
                     "isSingleton", "isCreatable", "isComposite", "defaultProperty", "attachedType",
                     "extension", "accessSemantics", "interfaces", "isStructured", "isValueType",
                     "isSequence", "sequenceValueType", "isRoot", "isCustomParser", "deferredNames",
                     "immediateNames", "isScript", "isExtendedTypeNamespace", "extensionIsJavaScript",
                     "hasCustomParser", "enforcesScopedEnums", "valueType", "aliases",
                     "extensionIsNamespace", "isJavaScriptBuiltin"}
_MEMBER_FIELDS = {"name", "type", "isReadonly", "isList", "isPointer", "revision", "isRequired",
                  "isFinal", "index", "read", "write", "notify", "bindable", "isConstructor",
                  "isJavaScriptFunction", "isCloned", "isConst", "isMethodConstant", "values",
                  "alias", "isFlag", "isScoped", "isEnum", "isUnderlyingType", "underlyingType",
                  "privateClass", "isConstant", "reset"}


def _literal(node, raw):
    if node.type == "expression_statement" and len(node.named_children) == 1:
        return _literal(node.named_children[0], raw)
    if node.type == "array":
        return [_literal(child, raw) for child in node.named_children if child.type != "comment"]
    if node.type == "object":
        values = {}
        for pair in node.named_children:
            if pair.type == "comment":
                continue
            key, value = pair.child_by_field_name("key"), pair.child_by_field_name("value")
            if pair.type != "pair" or key is None or key.type != "string" or value is None:
                raise MetadataError("QML_TYPES_UNSUPPORTED", "nonliteral_enum_entry")
            name = _literal(key, raw)
            if name in values:
                raise MetadataError("QML_TYPES_UNSUPPORTED", "duplicate_enum_entry")
            values[name] = _literal(value, raw)
        return values
    if node.type in {"string", "number", "true", "false", "null", "unary_expression"}:
        try:
            return json.loads(text(node, raw))
        except ValueError as exc:
            raise MetadataError("QML_TYPES_UNSUPPORTED", "non_json_literal") from exc
    raise MetadataError("QML_TYPES_UNSUPPORTED", "computed_type_description_value")


def _bindings(syntax, facts, allowed):
    initializer = syntax.child_by_field_name("initializer")
    values, nested = {}, []
    for child in initializer.named_children if initializer else []:
        if child.type == "comment":
            continue
        if child.type == "ui_object_definition":
            nested.append(child)
            continue
        if child.type != "ui_binding":
            raise MetadataError("QML_TYPES_UNSUPPORTED", "unsupported_type_description_syntax")
        name = field(child, "name", facts.raw)
        if name not in allowed or name in values:
            raise MetadataError("QML_TYPES_UNSUPPORTED", "unknown_or_duplicate_description_field")
        value = child.child_by_field_name("value")
        if value is None:
            raise MetadataError("QML_TYPES_UNSUPPORTED", "missing_description_value")
        values[name] = _literal(value, facts.raw)
        literal = values[name]
        if name.startswith(("is", "has", "enforces")) and not isinstance(literal, bool):
            raise MetadataError("QML_TYPES_UNSUPPORTED", "invalid_boolean_description_field")
        if name in {"name", "type", "prototype", "file", "notify", "read", "write", "bindable"} and not isinstance(literal, str):
            raise MetadataError("QML_TYPES_UNSUPPORTED", "invalid_string_description_field")
    return values, nested


def _field_records(facts, owner, values, syntax):
    """Keep every accepted tooling field independently, avoiding list sanitation."""
    for name, value in values.items():
        entries = list(value.items()) if isinstance(value, dict) else list(enumerate(value)) if isinstance(value, list) else [(0, value)]
        if len(entries) > 10_000:
            raise MetadataError("QML_PROJECT_LIMIT", "type_field_entry_limit")
        for ordinal, (entry_key, entry) in enumerate(entries):
            if isinstance(entry, (list, dict)):
                raise MetadataError("QML_TYPES_UNSUPPORTED", "nested_type_field_literal")
            facts.add("qmltypes_field", (owner["id"], name, ordinal), name,
                      syntax.start_byte, syntax.end_byte, owner=owner,
                      field_name=name, value=entry, position=ordinal,
                      enum_key=entry_key if isinstance(value, dict) else "", generated=True)


def _component(syntax, facts):
    values, nested = _bindings(syntax, facts, _COMPONENT_FIELDS)
    name = values.get("name")
    if not isinstance(name, str) or not name:
        raise MetadataError("QML_TYPES_UNSUPPORTED", "missing_component_name")
    component = facts.add("qmltypes_component", name, name, syntax.start_byte, syntax.end_byte,
                          raw_name=name, prototype=values.get("prototype", ""),
                          singleton=values.get("isSingleton", False),
                          creatable=values.get("isCreatable", True), generated=True,
                          evidence_role="tooling_description", declared_file=values.get("file", ""))
    _field_records(facts, component, values, syntax)
    exports = values.get("exports", [])
    if not isinstance(exports, list) or len(exports) > 10_000:
        raise MetadataError("QML_PROJECT_LIMIT", "type_export_limit_or_shape")
    for exported in exports:
        match = re.fullmatch(r"([^/\s]+)/([^\s]+)\s+(\d{1,6}\.\d{1,6})", str(exported))
        if not match or not uri(match[1]) or not match[2].isidentifier():
            raise MetadataError("QML_TYPES_UNSUPPORTED", "invalid_type_export")
        ver = version(match[3])
        assert ver is not None
        facts.add("qmltypes_export", (name, exported), match[2], syntax.start_byte, syntax.end_byte,
                  owner=component, cpp_name=name, uri=match[1], raw_name=match[2],
                  major=ver[0], minor=ver[1], generated=True, evidence_role="tooling_description")
    for ordinal, child in enumerate(nested):
        kind = field(child, "type_name", facts.raw)
        if kind not in {"Property", "Method", "Signal", "Enum"}:
            raise MetadataError("QML_TYPES_UNSUPPORTED", "unknown_component_description_object")
        fields, parameters = _bindings(child, facts, _MEMBER_FIELDS)
        member_name = fields.get("name")
        if not isinstance(member_name, str) or not member_name:
            raise MetadataError("QML_TYPES_UNSUPPORTED", "missing_member_name")
        member = facts.add("qmltypes_member", (name, kind, member_name, ordinal), member_name,
                           child.start_byte, child.end_byte, owner=component, raw_name=member_name,
                           member_kind=kind.lower(), raw_type=fields.get("type", ""), cpp_name=name,
                           readonly=fields.get("isReadonly", False), is_list=fields.get("isList", False),
                           revision=fields.get("revision"), notify=fields.get("notify", ""),
                           generated=True, evidence_role="tooling_description")
        _field_records(facts, member, fields, child)
        for position, parameter in enumerate(parameters):
            if field(parameter, "type_name", facts.raw) != "Parameter" or kind not in {"Method", "Signal"}:
                raise MetadataError("QML_TYPES_UNSUPPORTED", "unsupported_member_child")
            param, grandchildren = _bindings(parameter, facts, _MEMBER_FIELDS)
            if grandchildren:
                raise MetadataError("QML_TYPES_UNSUPPORTED", "nested_parameter_object")
            parameter_node = facts.add("qmltypes_parameter", (name, kind, member_name, ordinal, position),
                      str(param.get("name", position)), parameter.start_byte, parameter.end_byte,
                      owner=member, raw_name=param.get("name", ""), raw_type=param.get("type", ""),
                      position=position, generated=True)
            _field_records(facts, parameter_node, param, parameter)


def parse_qmltypes(source: bytes | str, *, relative_file="plugins.qmltypes") -> dict:
    try:
        facts = ProjectFacts(source, relative_file, "qmltypes")
        program = load_parser().parse(facts.raw).root_node
        if program.has_error:
            raise MetadataError("QML_TYPES_SYNTAX", "invalid_type_description_syntax")
        pending = [(program, 0)]
        count = 0
        while pending:
            node, depth = pending.pop()
            count += 1
            if count > 100_000 or depth > 64:
                raise MetadataError("QML_PROJECT_LIMIT", "type_description_ast_limit")
            pending.extend((child, depth + 1) for child in node.named_children)
        roots = []
        for child in program.named_children:
            if child.type == "ui_object_definition":
                roots.append(child)
            elif child.type not in {"comment", "ui_import"}:
                raise MetadataError("QML_TYPES_UNSUPPORTED", "unsupported_top_level_description")
        if len(roots) != 1 or field(roots[0], "type_name", facts.raw) != "Module":
            raise MetadataError("QML_TYPES_UNSUPPORTED", "missing_module_description")
        module_values, components = _bindings(roots[0], facts, {"dependencies"})
        _field_records(facts, facts.file_node, module_values, roots[0])
        for syntax in components:
            if field(syntax, "type_name", facts.raw) != "Component":
                raise MetadataError("QML_TYPES_UNSUPPORTED", "unknown_module_description_object")
            _component(syntax, facts)
        return facts.result()
    except (QmlInputError, UnicodeError, ValueError) as exc:
        return failure(relative_file, "qmltypes", exc)


def extract_qmltypes(path: Path, *, root: Path | None = None) -> dict:
    return extract_project(path, root, "qmltypes", parse_qmltypes)
