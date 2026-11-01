"""Typed, bounded QML tooling descriptions; metadata never grants source authority.

Field ownership follows the Qt6.12 qmltyperegistrar producer, while retaining
earlier accepted tooling flags. File/line values are navigation hints only. The
existing QML fact transport owns lossless string encoding and the fact ceiling.
"""
from __future__ import annotations

from typing import NoReturn

from graphify.extractors.qml_project_read import MetadataError

COMPONENT_FIELDS = {"name", "prototype", "file", "exports", "exportMetaObjectRevisions",
                    "isSingleton", "isCreatable", "isComposite", "defaultProperty", "attachedType",
                    "extension", "accessSemantics", "interfaces", "isStructured", "isValueType",
                    "isSequence", "sequenceValueType", "isRoot", "isCustomParser", "deferredNames",
                    "immediateNames", "isScript", "isExtendedTypeNamespace", "extensionIsJavaScript",
                    "hasCustomParser", "enforcesScopedEnums", "valueType", "aliases",
                    "extensionIsNamespace", "isJavaScriptBuiltin", "isSelfExtension", "isTypeOpaque",
                    "lineNumber", "resolvedFile", "lineNumberInResolvedFile", "parentProperty"}
# Qt6.8 writeType emits isConstant for every type-bearing member. Its Property
# spelling also covered property constness, so retain it as raw tooling evidence
# without aliasing modern isTypeConstant/isMethodConstant/isPropertyConstant.
_TYPE_FIELDS = {"type", "isList", "isPointer", "isTypeConstant", "isConst", "isConstant"}
_PROPERTY_FIELDS = {"isReadonly", "isRequired", "isFinal", "index", "read", "write", "notify",
                    "bindable", "isVirtual", "isOverride", "isPropertyConstant", "privateClass",
                    "reset", "isEnum", "isUnderlyingType", "underlyingType"}
_METHOD_FIELDS = {"isConstructor", "isJavaScriptFunction", "isCloned", "isMethodConstant"}
_ENUM_FIELDS = {"values", "alias", "isFlag", "isScoped", "isEnum", "isUnderlyingType", "underlyingType"}
_COMMON_MEMBER = _TYPE_FIELDS | {"name", "revision", "lineNumber"}
MEMBER_FIELDS = _COMMON_MEMBER | _PROPERTY_FIELDS | _METHOD_FIELDS | _ENUM_FIELDS
_OWNED_FIELDS = {"Module": {"dependencies"}, "Component": COMPONENT_FIELDS,
                 "Property": _COMMON_MEMBER | _PROPERTY_FIELDS,
                 "Method": _COMMON_MEMBER | _METHOD_FIELDS,
                 "Signal": _COMMON_MEMBER | _METHOD_FIELDS,
                 "Enum": _COMMON_MEMBER | _ENUM_FIELDS,
                 "Parameter": _TYPE_FIELDS | {"name"}}
_STRING_LISTS = {"dependencies", "exports", "interfaces", "deferredNames", "immediateNames", "aliases"}
_INTEGERS = {"lineNumber": (0, 2**31 - 1), "lineNumberInResolvedFile": (0, 2**31 - 1),
             "index": (0, 2**31 - 1), "revision": (0, 65535)}
_BOOLEAN_FIELDS = {name for name in COMPONENT_FIELDS | MEMBER_FIELDS
                   if name.startswith(("is", "has", "enforces", "extensionIs"))}
# A 384-byte UTF-8 literal occupies at most 512 base64 bytes, matching the
# established lossless transport. Validate before encoding to retain a typed
# metadata diagnostic rather than a generic read failure.
_MAX_LITERAL_BYTES = 384
_MAX_ENTRIES = 10_000


def _unsupported(reason: str) -> NoReturn:
    raise MetadataError("QML_TYPES_UNSUPPORTED", reason)


def _string(value):
    if not isinstance(value, str):
        _unsupported("invalid_string_description_field")
    try:
        encoded = value.encode("utf-8")
    except UnicodeError:
        _unsupported("invalid_string_description_field")
    if any(ord(char) < 32 for char in value):
        _unsupported("invalid_string_description_field")
    if len(encoded) > _MAX_LITERAL_BYTES:
        raise MetadataError("QML_PROJECT_LIMIT", "type_description_string_limit")


def _integer(value, minimum, maximum):
    # bool is an int subclass; neither it nor an integral float proves a source
    # line, encoded revision, property index or enum's literal integer value.
    if type(value) is not int or not minimum <= value <= maximum:
        _unsupported("invalid_integer_description_field")


def _entries(value):
    if len(value) > _MAX_ENTRIES:
        raise MetadataError("QML_PROJECT_LIMIT", "type_field_entry_limit")


def validate_description(values, kind):
    """Reject corrupt fields before publishing any facts for a tooling file."""
    allowed = _OWNED_FIELDS[kind]
    if values.keys() - allowed:
        _unsupported("invalid_description_field_owner")
    for name, value in values.items():
        if name in _BOOLEAN_FIELDS:
            if not isinstance(value, bool):
                _unsupported("invalid_boolean_description_field")
        elif name in _INTEGERS:
            _integer(value, *_INTEGERS[name])
        elif name in _STRING_LISTS or name == "exportMetaObjectRevisions":
            if not isinstance(value, list):
                _unsupported("invalid_list_description_field")
            _entries(value)
            for entry in value:
                _integer(entry, 0, 65535) if name == "exportMetaObjectRevisions" else _string(entry)
        elif name == "values":
            if not isinstance(value, (list, dict)):
                _unsupported("invalid_enum_description_values")
            _entries(value)
            if isinstance(value, dict):
                for key, entry in value.items():
                    _string(key)
                    _integer(entry, -(2**63), 2**64 - 1)
            else:
                for entry in value:
                    _string(entry)
        else:
            _string(value)
    if "accessSemantics" in values and values["accessSemantics"] not in {"reference", "value", "sequence", "none"}:
        _unsupported("invalid_access_semantics")
    # Qt6.12 emits opaque descriptions for unregistered types referenced by
    # registered APIs. Retain their members and hints without accepting forged
    # exports, creation or extension claims that contradict that producer role.
    if values.get("isTypeOpaque") and (values.get("exports") or values.get("isCreatable")
            or values.get("isSingleton") or values.get("isComposite") or values.get("extension")
            or values.get("isSelfExtension") or values.get("isJavaScriptBuiltin")
            or values.get("isRoot") or values.get("extensionIsNamespace")
            or values.get("extensionIsJavaScript")):
        _unsupported("opaque_type_authority_conflict")
    if kind == "Property" and values.get("isPropertyConstant") and (
            values.get("write") or values.get("notify") or values.get("isReadonly") is False):
        _unsupported("conflicting_constant_property_fields")
