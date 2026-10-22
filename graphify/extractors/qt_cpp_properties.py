"""Source-backed Q_PROPERTY declarations and narrowly evidenced accessor links."""
from __future__ import annotations

import re

from graphify.extractors.qt_cpp_mapping import normalize_type
from graphify.extractors.qt_cpp_registration import conditional_offset
from graphify.extractors.qt_cpp_api_types import api_type_fields

_ATTRIBUTE = re.compile(r"\b(READ|WRITE|MEMBER|RESET|NOTIFY|REVISION|DESIGNABLE|SCRIPTABLE|STORED|USER|BINDABLE|CONSTANT|FINAL|REQUIRED)\b")


def property_fields(macro):
    """Keep unsupported expressions literal; never expand a preprocessor wrapper."""
    text = macro["args"][0] if len(macro["args"]) == 1 else ""
    tokens = list(_ATTRIBUTE.finditer(text))
    head = text[:tokens[0].start()] if tokens else text
    match = re.fullmatch(r"\s*(.+?)(?:\s+|(?<=[*&]))([A-Za-z_]\w*)\s*", head)
    if not match:
        return {"status": "unsupported", "reason": "property_declaration_unsupported", "raw_name": ""}
    fields = {"raw_name": match[2], "raw_type": normalize_type(match[1]), "status": "resolved", "reason": ""}
    for index, token in enumerate(tokens):
        value = text[token.end():tokens[index + 1].start() if index + 1 < len(tokens) else len(text)].strip()
        key = token[1].lower()
        if key in fields:
            fields.update(status="unsupported", reason="duplicate_property_attribute")
        fields[key] = value or True
    if not fields.get("read") and not fields.get("member"):
        fields.update(status="unsupported", reason="property_read_or_member_missing")
    return fields


def add_properties(unit, mapping, facts, class_record, *, types=None):
    """Properties are independent Qt facts; generic accessor IDs are borrowed."""
    for macro in class_record["macros"]:
        if macro["name"] != "Q_PROPERTY" or mapping.class_at(macro["start_byte"]) is not class_record:
            continue
        fields = property_fields(macro)
        if conditional_offset(unit, macro["start_byte"]):
            fields.update(status="dynamic", reason="conditional_property_declaration")
        name = fields.pop("raw_name")
        if types is not None:
            fields.update(api_type_fields(types, fields.get("raw_type", ""), macro["start_byte"],
                                          conditional=conditional_offset(unit, macro["start_byte"])))
        site = facts.add("property", name, macro["span"], owner=class_record["node_id"] or None,
                         class_id=class_record["node_id"], class_name=class_record["qualified_name"],
                         generic_target_id="", **fields)
        for role in ("read", "write", "reset", "notify"):
            accessor = fields.get(role)
            if not isinstance(accessor, str):
                continue
            candidates = [item for item in mapping.functions if item["class_id"] == class_record["node_id"]
                          and item["name"] == accessor and item["node_id"]]
            if role == "notify":
                candidates = [item for item in candidates if "signal" in item["roles"]
                              and item["return_type"] == "void" and item["parameter_types"] in
                              ([], [fields.get("raw_type")])]
            elif role in {"read", "reset"}:
                candidates = [item for item in candidates if not item["parameter_types"]]
            elif role == "write":
                candidates = [item for item in candidates if len(item["parameter_types"]) == 1]
            signatures = {item["signature"] for item in candidates}
            ids = {item["node_id"] for item in candidates}
            status = "resolved" if len(ids) == len(signatures) == 1 else "ambiguous" if candidates else "unavailable"
            link = facts.add("property_accessor", accessor, macro["span"], owner=site["id"],
                             semantic_key=[site["id"], role], property_id=site["id"], accessor_role=role,
                             status=status, reason="" if status == "resolved" else "accessor_not_unique_or_unavailable",
                             generic_target_id=next(iter(ids)) if status == "resolved" else "")
            if status == "resolved":
                facts.edge(link["id"], next(iter(ids)), "references", macro["span"],
                           context="qt_property_accessor", property_id=site["id"], accessor_role=role)
