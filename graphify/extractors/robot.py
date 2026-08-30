"""Structural extraction for Robot Framework ``.robot`` and ``.resource`` files.

Robot Framework files are executable test specifications, but they do not have a
Tree-sitter grammar in Graphify's dependency set.  This module deliberately
models their stable document structure rather than attempting to interpret
keyword implementations or variable values.
"""
from __future__ import annotations

import re
from pathlib import Path

from graphify.extractors.base import _file_stem, _make_id

_SECTION_RE = re.compile(r"^\s*\*\*\*\s+(.+?)\s+\*\*\*\s*$", re.IGNORECASE)
_ENTITY_RE = re.compile(r"^\S(?:.*\S)?$")
_SECTION_NAMES = {
    "settings": "settings",
    "variables": "variables",
    "test cases": "test_cases",
    "tasks": "tasks",
    "keywords": "keywords",
    "comments": "comments",
}


def extract_robot(path: Path) -> dict:
    """Extract Robot Framework suite sections and named test/keyword entities.

    The file itself is the root document node.  Section nodes contain named
    tests, tasks, and user keywords; settings and variables are represented as
    leaf nodes because their rows have no nested declaration structure.
    Executable keyword rows are intentionally not emitted as nodes: resolving
    them would require Robot's runtime/library semantics and would create noisy
    edges for built-in keywords.
    """
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return {"nodes": [], "edges": [], "error": str(exc)}

    source_file = str(path)
    stem = _file_stem(path)
    file_id = _make_id(source_file)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen: set[str] = set()

    def add_node(label: str, line: int, kind: str, *id_parts: str) -> str:
        nid = _make_id(stem, *id_parts) if id_parts else file_id
        if nid in seen:
            nid = _make_id(stem, kind, f"L{line}")
        if nid in seen:
            return nid
        seen.add(nid)
        nodes.append({
            "id": nid,
            "label": label,
            "file_type": "document",
            "node_kind": kind,
            "source_file": source_file,
            "source_location": f"L{line}",
        })
        return nid

    def add_edge(parent: str, child: str, line: int) -> None:
        edges.append({
            "source": parent,
            "target": child,
            "relation": "contains",
            "confidence": "EXTRACTED",
            "source_file": source_file,
            "source_location": f"L{line}",
            "weight": 1.0,
        })

    seen.add(file_id)
    nodes.append({
        "id": file_id,
        "label": path.name,
        "file_type": "document",
        "node_kind": "page",
        "source_file": source_file,
        "source_location": "L1",
    })

    current_section: tuple[str, str] | None = None
    for line_number, raw in enumerate(lines, 1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue

        section_match = _SECTION_RE.match(raw)
        if section_match:
            title = section_match.group(1).strip()
            section_key = _SECTION_NAMES.get(title.casefold(), title.casefold().replace(" ", "_"))
            section_id = add_node(title, line_number, "section", section_key)
            add_edge(file_id, section_id, line_number)
            current_section = (section_key, section_id)
            continue

        if current_section is None:
            continue
        section_key, parent_id = current_section
        # Robot declaration rows are unindented.  Indented rows are settings,
        # arguments, or executable keyword calls and are intentionally skipped.
        if raw[:1].isspace() or not _ENTITY_RE.match(raw):
            continue

        if section_key in {"test_cases", "tasks", "keywords"}:
            kind = "test" if section_key == "test_cases" else "task" if section_key == "tasks" else "keyword"
            entity_id = add_node(stripped, line_number, kind, kind, stripped, f"L{line_number}")
            add_edge(parent_id, entity_id, line_number)
        elif section_key in {"settings", "variables"}:
            entity_id = add_node(stripped, line_number, "setting" if section_key == "settings" else "variable", section_key, stripped, f"L{line_number}")
            add_edge(parent_id, entity_id, line_number)

    return {"nodes": nodes, "edges": edges}


__all__ = ["extract_robot"]
