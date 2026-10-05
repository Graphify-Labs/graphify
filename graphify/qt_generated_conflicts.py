"""Report generated tooling/source disagreements while preserving both origins."""
from __future__ import annotations

from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.qml_resolution_types import qml_metadata


def generated_conflicts(index) -> list[dict]:
    diagnostics = []
    native_members = {}
    for node in index.nodes.values():
        md = qt_metadata(node)
        if md.get("kind") in {"property", "member"} and md.get("class_name"):
            native_members.setdefault((md["class_name"], md.get("raw_name")), []).append(node)

    def add(generated, source_id, reason):
        if len(diagnostics) < 50:
            md = qml_metadata(generated)
            diagnostics.append({"code": "QML_TYPES_CONFLICT", "severity": "warning",
                                "owner": "qt_project_index", "source_file": generated["source_file"],
                                "span": md.get("span"), "reason": reason,
                                "generated_id": generated["id"], "source_id": source_id,
                                "message": "Both generated and source declarations are retained",
                                "recovery": "Regenerate tooling metadata or reconcile the source declarations."})

    for node in index.nodes.values():
        md = qml_metadata(node)
        if md.get("kind") == "qmltypes_export":
            source = index.resolve_component(md["uri"], md["raw_name"], md.get("major"), md.get("minor"))
            if source.target_id or source.status == "ambiguous":
                add(node, source.target_id, "generated_and_source_type_origins")
        elif md.get("kind") == "qmltypes_member":
            for source in native_members.get((md.get("cpp_name"), md.get("raw_name")), []):
                native = qt_metadata(source)
                pairs = [(md.get("raw_type"), native.get("raw_type") if native.get("kind") == "property"
                          else native.get("return_type"))]
                if native.get("kind") == "property":
                    pairs.append((md.get("notify"), native.get("notify")))
                if any(a and b and a != b for a, b in pairs):
                    add(node, source["id"], "generated_member_disagrees_with_source")
    return diagnostics
