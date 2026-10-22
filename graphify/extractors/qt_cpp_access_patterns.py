"""Literal handle assignment and initial-property maps; unsupported dataflow is opaque."""
from __future__ import annotations

import re

from graphify.extractors.qt_cpp_calls import literal_string
from graphify.extractors.qt_cpp_syntax import lexical_code, split_arguments


def assigned_handle(unit, call):
    before = unit.code[max(call["owner"]["body"].start_byte, unit.code.rfind(b";", 0, call["start_byte"]) + 1):call["start_byte"]].decode()
    match = re.search(r"\b([A-Za-z_]\w*)\s*=\s*$", before)
    return match[1] if match else ""


def handle_argument(expression):
    value = expression.strip()
    root = re.fullmatch(r"([A-Za-z_]\w*)\s*(?:\.|->)\s*(?:rootObjects\(\)\.(?:first|at)\(0?\)|rootObject\(\))", value)
    return (root[1], "root") if root else (value, "variable") if re.fullmatch(r"[A-Za-z_]\w*", value) else ("", "dynamic")


def literal_map(expression):
    """Recognize direct QVariantMap initializer pairs only; no computed merging."""
    value = re.sub(r"^\s*(?:QVariantMap|QMap\s*<[^>]+>)\s*", "", expression.strip())
    if not value.startswith("{") or not value.endswith("}"):
        return [], False
    pairs = []
    for entry in split_arguments(value[1:-1].encode()):
        if not entry.startswith("{") or not entry.endswith("}"):
            return [], False
        args = split_arguments(entry[1:-1].encode())
        key = literal_string(args[0]) if len(args) == 2 else None
        if key is None:
            return [], False
        reference = args[1].strip().lstrip("&")
        pairs.append({"ordinal": len(pairs), "name": key, "provider_reference": reference if re.fullmatch(r"[A-Za-z_]\w*", reference) else "",
                      "literal_value": literal_string(args[1]), "dynamic_value": not bool(re.fullmatch(r"[A-Za-z_]\w*", reference)) and literal_string(args[1]) is None})
    return pairs, bool(pairs)


def handle_reassigned(unit, owner, name, start, end):
    if not name or end <= start:
        return False
    code = lexical_code(unit.source[start:end]).decode()
    return bool(re.search(r"\b" + re.escape(name) + r"\s*=(?!=)", code))


def last_assignment(unit, owner, name, position):
    if not name or owner.get("body") is None:
        return -1
    start = owner["body"].start_byte
    matches = list(re.finditer(rb"\b" + re.escape(name.encode()) + rb"\s*=(?!=)", unit.code[start:position]))
    return start + matches[-1].start() if matches else -1
