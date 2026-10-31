"""Bounded accepted-source status counts for Qt/QML reports, without source I/O."""
from __future__ import annotations

from graphify.extractors.qml_facts import qml_metadata
from graphify.extractors.qt_cpp_facts import qt_metadata

STATUSES = ("resolved", "ambiguous", "dynamic", "unsupported", "unavailable", "error")


def _source_fact(node, raw):
    """Version and original span establish a fact; labels never infer coverage."""
    if not isinstance(raw, dict) or type(raw.get("contract_version")) is not int or raw["contract_version"] != 1:
        return False
    span = raw.get("span")
    return (isinstance(node.get("source_file"), str) and bool(node["source_file"])
            and isinstance(raw.get("kind"), str) and bool(raw["kind"])
            and isinstance(span, dict) and type(span.get("start_byte")) is int
            and type(span.get("end_byte")) is int and 0 <= span["start_byte"] <= span["end_byte"])


def source_coverage(graph):
    """Count each source-owned node once per contract, keeping unknown states explicit."""
    counts = {}
    for _, node in graph.nodes(data=True):
        metadata = node.get("metadata")
        if not isinstance(metadata, dict):
            continue
        for name, decode in (("qml", qml_metadata), ("qt", qt_metadata)):
            if not _source_fact(node, metadata.get(name)):
                continue
            row = counts.setdefault(name, {**dict.fromkeys(STATUSES, 0), "other": 0, "facts": 0, "invalid_metadata": 0})
            row["facts"] += 1
            try:
                status = decode(node).get("status")
            except (ValueError, TypeError, UnicodeError):
                status = "error"
                row["invalid_metadata"] += 1
            row[status if status in STATUSES else "other"] += 1
    return counts


def coverage_lines(graph):
    """Do not equate accepted-fact resolution with complete Qt runtime coverage."""
    counts = source_coverage(graph)
    if not counts:
        return []
    lines = ["", "## Qt/QML source coverage", "",
             "Counts describe accepted source facts, not a percentage of supported language syntax.", "",
             "| Contract | Facts | Resolved | Ambiguous | Dynamic | Unsupported | Unavailable | Error | Other / no status |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for name in ("qml", "qt"):
        if name not in counts:
            continue
        row = counts[name]
        cells = [name.upper(), row["facts"], *(row[status] for status in STATUSES), row["other"]]
        lines.append("| " + " | ".join(str(cell) for cell in cells) + " |")
    invalid = sum(row["invalid_metadata"] for row in counts.values())
    if invalid:
        lines.append(f"- {invalid} source fact(s) have invalid semantic metadata; counted as errors.")
    lines += ["", "Static resolution does not prove runtime object creation, binding values, signal delivery, ordering, or thread safety.",
              "Parse and graph-write failures belong to their owning diagnostics; their absence from this graph is not proof of successful extraction."]
    return lines
