"""Source-only QtTest data/assertion facts over canonical accepted C++ owners."""
from __future__ import annotations

from graphify.extractors.qt_cpp_facts import owner_scope
from graphify.extractors.qt_cpp_test_syntax import needs_test_recovery
from graphify.extractors.qt_cpp_test_launchers import needs_launcher_recovery, add_test_launcher_facts


def is_qt_test_source(source, code):
    # This is admission only. Unproven typed syntax still reaches the explicit
    # syntax diagnostic; an ordinary clean function spelling gains no facts.
    return needs_test_recovery(code) or needs_launcher_recovery(code)


def opaque_test_declaration(unit, syntax):
    """Exact recovered binders shadow names but carry no synthetic native type."""
    return any(record["kind"] == "test_data" and record.get("parsed_role") != "opaque_statement"
               and record["start"] == syntax.start_byte
               and record["semicolon"] + 1 == syntax.end_byte for record in unit.qt_test_macros)


def add_qt_test_facts(mapping, facts):
    """Data columns and retry syntax do not become native providers or calls."""
    for record in mapping.unit.qt_test_macros:
        owner = mapping.owner_at(record["start"])
        if owner is None or owner.get("body") is None:
            continue
        fields = {"mechanism": record["name"], "status": "source_only", "runtime_status": "unverified",
                  "framework": record["framework"],
                  "sdk_header": record["sdk_header"], "owner_scope_key": owner_scope(mapping.unit, owner),
                  "scope_span": {"start_byte": record["scope_start"], "end_byte": record["scope_end"]}}
        if record.get("include_witnesses"):
            fields["include_witnesses"] = record["include_witnesses"]
        if record.get("build_include_witnesses"):
            fields["build_include_witnesses"] = record["build_include_witnesses"]
        if record["kind"] == "test_data":
            fields.update(raw_type=record["raw_type"], variable_span=record["variable_span"],
                          declaration_span=record["declaration_span"], reason="test_data_type_and_column_match_unverified")
            if record.get("parsed_role") == "opaque_statement":
                fields["parsed_role"] = "opaque_statement"
        else:
            fields.update(argument_spans=record["argument_spans"], evaluation_status="unverified",
                          reason="test_retry_runtime_evaluation_unverified" if record["retry"] else "test_assertion_runtime_evaluation_unverified")
            if record["retry"]:
                fields["repeated_evaluation"] = True
        facts.add(record["kind"], record.get("variable") or record["name"], record["span"],
                  owner=owner.get("node_id") or None, **fields)
    add_test_launcher_facts(mapping, facts)
