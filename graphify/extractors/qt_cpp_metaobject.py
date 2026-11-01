"""Source-owned Q_OBJECT occurrences; QObject ancestry does not supply own moc code."""
from __future__ import annotations

from graphify.extractors.qt_cpp_registration import conditional_offset
from graphify.extractors.qt_cpp_syntax import QtCppError


def add_metaobject_declarations(mapping, facts, record, owned):
    """Retain each original marker and summarize absence/conditional/duplicate source evidence.

    This observes declarations only. It neither runs moc nor establishes a Qt
    build/runtime result, and it leaves ordinary class/member authority intact.
    """
    markers = [macro for macro in owned if macro["name"] == "Q_OBJECT"]
    if len(markers) > 50:
        raise QtCppError("QT_CPP_LIMIT", "Qt class exceeds 50 metaobject declarations")
    conditional = [conditional_offset(mapping.unit, item["start_byte"]) for item in markers]
    malformed = any(mapping.unit.source[item["start_byte"]:item["end_byte"]] != b"Q_OBJECT" for item in markers)
    status, reason = "resolved", ""
    if not markers:
        status, reason = "unavailable", "native_metaobject_unavailable"
    elif len(markers) != 1:
        status, reason = "ambiguous", "native_metaobject_ambiguous"
    elif malformed:
        status, reason = "unsupported", "native_metaobject_declaration_unsupported"
    elif any(conditional):
        status, reason = "dynamic", "native_metaobject_conditional"
    elif record["status"] != "resolved":
        status, reason = "unavailable", "native_metaobject_source_unavailable"
    for marker, guarded in zip(markers, conditional):
        facts.add("metaobject", "Q_OBJECT", marker["span"], owner=record["node_id"] or None,
                  class_id=record["node_id"], class_name=record["qualified_name"],
                  metaobject_contract=1, conditional=guarded, status=status, reason=reason)
    return {"metaobject_contract": 1, "metaobject_count": len(markers),
            "metaobject_status": status, "metaobject_reason": reason,
            "metaobject_span": markers[0]["span"] if len(markers) == 1 else {}}
