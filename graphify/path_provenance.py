"""Readable, bounded source evidence shared by CLI and MCP path rendering."""
from __future__ import annotations

from graphify.security import sanitize_label


def path_provenance(nodes, edges) -> str:
    """Render actual declaration and relationship sources without metadata dumps.

    Path traversal owns ordering and direction. Missing locations stay absent;
    this view never substitutes a target declaration for an edge's call site.
    """
    lines = []
    for data in nodes:
        if source := _source(data):
            label = sanitize_label(str(data.get("label") or "node"))
            lines.append(f"  Node {label}: {source}")
    for data in edges:
        if source := _source(data):
            relation = sanitize_label(str(data.get("relation") or "related"))
            confidence = sanitize_label(str(data.get("confidence") or ""))
            context = sanitize_label(str(data.get("context") or ""))
            suffix = f" [{confidence}]" if confidence else ""
            if context:
                suffix += f" ({context})"
            lines.append(f"  Edge {relation}{suffix}: {source}")
    return "\nSource evidence:\n" + "\n".join(dict.fromkeys(lines)) if lines else ""


def _source(data):
    path = data.get("source_file")
    if not isinstance(path, str) or not path:
        return ""
    path = sanitize_label(path[:512])
    location = data.get("source_location")
    location = sanitize_label(location[:128]) if isinstance(location, str) else ""
    return f"{path}:{location}" if location else path
