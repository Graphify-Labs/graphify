"""Bounded semantic search views for Qt/QML facts; identities stay opaque."""
from __future__ import annotations

from graphify.extractors.qml_facts import qml_metadata
from graphify.extractors.qt_cpp_facts import qt_metadata

SEARCH_NAMESPACE = "graphify_qt_qml"
_FIELDS = {"kind", "raw_name", "raw_type", "type_name", "class_name", "signature", "uri",
           "qualifier", "import_kind", "mechanism", "status", "reason", "metadata_format", "target_name",
           "declared_type", "callable_form", "operation", "bridge_direction"}
_FLAGS = {"singleton", "creatable", "anonymous", "internal", "required", "readonly", "source_q_object"}
_LISTS = {"roles", "flags"}
MAX_TEXT = 384
MAX_ROLES = 16


def _text(value):
    return value if isinstance(value, str) and len(value) <= MAX_TEXT else None


def _view(values):
    if values.get("contract_version") != 1:
        return {}
    result: dict[str, object] = {key: text for key in sorted(_FIELDS) if (text := _text(values.get(key))) is not None and text}
    for key in sorted(_LISTS):
        values_list = values.get(key)
        if isinstance(values_list, list) and len(values_list) <= MAX_ROLES:
            result[key] = [value for value in values_list if _text(value)]
    result.update({key: values[key] for key in sorted(_FLAGS) if isinstance(values.get(key), bool)})
    if values.get("kind") in {"import", "module_import", "script_import"}:
        value = _text(values.get("value"))
        if value:
            result["import_value"] = value
    major, minor = values.get("major"), values.get("minor")
    if type(major) is int and 0 <= major <= 1_000_000:
        result["major"] = major
    if type(minor) is int and 0 <= minor <= 1_000_000:
        result["minor"] = minor
    return result


def _decode_view(name, raw, decode):
    """Decode only bounded search fields, never copy unrelated payload trees."""
    selected = {key: value for key in _FIELDS | _FLAGS | {"major", "minor", "value"}
                if (value := raw.get(key)) is not None and
                (isinstance(value, (bool, int)) or _text(value) is not None)}
    for key in _LISTS:
        values = raw.get(key)
        if isinstance(values, list) and len(values) <= MAX_ROLES and all(_text(value) is not None for value in values):
            selected[key] = list(values)
    literals = raw.get("raw_values", {})
    if not isinstance(literals, dict) or len(literals) > 100:
        return {}
    selected["contract_version"] = 1
    encoded = {}
    for key, value in literals.items():
        if not isinstance(key, str) or len(key) > 128:
            return {}
        if key not in selected and not any(key.startswith(name + "/") and name in selected for name in _LISTS):
            continue
        # Validate before the Qt decoder copies the packet through JSON. A
        # nested malformed value must never reach that recursive copy.
        if not isinstance(value, str) or len(value) > 512:
            return {}
        encoded[key] = value
    selected["raw_values"] = encoded
    return _view(decode({"metadata": {name: selected}}))


def search_attributes(node):
    """Return a new attribute view without editing source nodes or old attributes.

    Only public semantic fields are indexed. Source IDs, opaque scope keys,
    transport copies, expression bodies and supplied literal data are excluded.
    Existing use of the reserved namespace wins instead of being overwritten.
    Malformed/future metadata cannot make ordinary graph search fail.
    """
    attrs = node.get("attributes")
    result = dict(attrs) if isinstance(attrs, dict) else {}
    if SEARCH_NAMESPACE in result:
        return result
    metadata = node.get("metadata")
    if not isinstance(metadata, dict):
        return result
    views = {}
    for name, decode in (("qml", qml_metadata), ("qt", qt_metadata)):
        raw = metadata.get(name)
        if not isinstance(raw, dict) or type(raw.get("contract_version")) is not int or raw.get("contract_version") != 1:
            continue
        try:
            values = _decode_view(name, raw, decode)
        except (ValueError, TypeError, UnicodeError):
            continue
        if values:
            views[name] = values
    if views:
        result[SEARCH_NAMESPACE] = views
    return result
