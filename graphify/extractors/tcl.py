"""Tcl extractor for graphify.

Extracts proc definitions, namespace evals, and package requires from .tcl
files using regex — there is no tree-sitter-tcl package on PyPI yet.

Handles both flat proc names and namespace-qualified names (e.g. `::ns::proc`).
"""
from __future__ import annotations

import re
from pathlib import Path

from graphify.extractors.base import _file_stem, _make_id


def extract_tcl(path: Path) -> dict:
    """Extract procs, namespaces, and package imports from a .tcl file."""
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    stem = _file_stem(path)
    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()

    def add_node(nid: str, label: str, line: int) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({
                "id": nid, "label": label, "file_type": "code",
                "source_file": str_path, "source_location": f"L{line}",
                "confidence_score": 1.0,
            })

    def add_edge(src: str, tgt: str, relation: str, line: int,
                 confidence: str = "EXTRACTED", score: float = 1.0) -> None:
        edges.append({
            "source": src, "target": tgt, "relation": relation,
            "confidence": confidence, "confidence_score": score,
            "source_file": str_path, "source_location": f"L{line}",
            "weight": 1.0,
        })

    file_nid = _make_id(str(path))
    add_node(file_nid, path.name, 1)

    # proc definitions — flat and namespace-qualified (::ns::name or ns::name)
    for m in re.finditer(r'^\s*proc\s+([\w:]+)', source, re.MULTILINE):
        name = m.group(1)
        line = source[: m.start()].count("\n") + 1
        nid = _make_id(stem, name)
        add_node(nid, name, line)
        add_edge(file_nid, nid, "defines", line)

    # namespace eval blocks
    for m in re.finditer(r'^\s*namespace\s+eval\s+([\w:]+)', source, re.MULTILINE):
        ns = m.group(1)
        line = source[: m.start()].count("\n") + 1
        nid = _make_id(stem, ns)
        if nid not in seen_ids:
            add_node(nid, ns, line)
            add_edge(file_nid, nid, "contains", line, "INFERRED", 0.8)

    # package require → import edge
    for m in re.finditer(r'^\s*package\s+require\s+([\w:]+)', source, re.MULTILINE):
        pkg = m.group(1)
        line = source[: m.start()].count("\n") + 1
        tgt = _make_id(pkg)
        add_node(tgt, pkg, line)
        add_edge(file_nid, tgt, "imports_from", line)

    # source <file> → import edge (quotes/braces optional)
    for m in re.finditer(r'^\s*source\s+\{?"?([\w./\\-]+\.tcl)"?\}?', source, re.MULTILINE):
        filename = m.group(1)
        line = source[: m.start()].count("\n") + 1
        tgt = _make_id(filename)
        add_node(tgt, filename, line)
        add_edge(file_nid, tgt, "imports_from", line)

    return {"nodes": nodes, "edges": edges}
