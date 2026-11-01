"""Keep original C++ declaration bytes distinct from an aligned parse view.

Compatibility syntax may change an operator to enter the bundled grammar. Type
inference still owns the normalized view; declaration signatures and original
byte spans require this explicit, same-read source input instead of a reread.
"""
from __future__ import annotations

from itertools import zip_longest
from pathlib import Path
import re


def valid_span(value):
    """One typed physical-range contract serves declaration and default proof."""
    keys = ("start_byte", "end_byte", "start_row", "end_row", "start_column", "end_column")
    return (isinstance(value, dict) and all(type(value.get(key)) is int and value[key] >= 0 for key in keys)
            and value["start_byte"] < value["end_byte"] and value["start_row"] <= value["end_row"]
            and (value["start_row"] != value["end_row"]
                 or value["end_byte"] - value["start_byte"] == value["end_column"] - value["start_column"]))


def span_contains(owner, child):
    """Byte and point containment agree wherever the enclosing line is known."""
    if not valid_span(owner) or not valid_span(child):
        return False
    if not (owner["start_byte"] <= child["start_byte"] < child["end_byte"] <= owner["end_byte"]
            and (owner["start_row"], owner["start_column"]) <= (child["start_row"], child["start_column"])
            and (child["end_row"], child["end_column"]) <= (owner["end_row"], owner["end_column"])):
        return False
    return (child["start_row"] != owner["start_row"] or child["start_byte"] - owner["start_byte"] == child["start_column"] - owner["start_column"]) and (
        child["end_row"] != owner["end_row"] or owner["end_byte"] - child["end_byte"] == owner["end_column"] - child["end_column"])


def declaration_source(parsed, original):
    """Reject unaligned source integrity rather than borrow normalized semantics."""
    if original is None:
        return parsed
    if not isinstance(parsed, bytes) or not isinstance(original, bytes) or len(original) != len(parsed):
        raise ValueError("CPP_SOURCE_VIEW_MISMATCH")
    positions = (re.finditer(rb"[\r\n]", view) for view in (parsed, original))
    for left, right in zip_longest(*positions):
        if left is None or right is None or left.start() != right.start() or left[0] != right[0]:
            raise ValueError("CPP_SOURCE_VIEW_MISMATCH")
    return original


def source_view_failure(result, path):
    """A source-integrity rejection must reach accepted-product retention gates."""
    path = Path(path)
    relative = path.as_posix() if not path.is_absolute() else path.name
    if len(relative.encode()) > 160 or any(ord(char) < 32 or 127 <= ord(char) < 160 or char in "\u2028\u2029" for char in relative):
        relative = ""  # Diagnostic display is not source/endpoint authority.
    code = "CPP_SOURCE_VIEW_MISMATCH"
    result.setdefault("qt_failures", []).append({"code": code, "source_file": relative})
    result.setdefault("diagnostics", []).append({"code": code, "severity": "error", "owner": "cpp_source_views",
        "source_file": relative, "message": "C++ compatibility source does not align with the original bytes",
        "recovery": "Correct the analyzer's source-view inputs and retry; prior graph is preserved."})
    return result
