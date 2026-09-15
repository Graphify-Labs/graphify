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
                 confidence: str = "EXTRACTED", score: float = 1.0,
                 target_file: str | None = None) -> None:
        edge = {
            "source": src, "target": tgt, "relation": relation,
            "confidence": confidence, "confidence_score": score,
            "source_file": str_path, "source_location": f"L{line}",
            "weight": 1.0,
        }
        # Transient resolved-target hint (mirrors bash.py's source-statement
        # resolution) — lets the extract() id-remap pass canonicalize this
        # edge onto the sourced file's real file-node id even when that file
        # isn't in the current extraction batch. Popped before persisting.
        if target_file is not None:
            edge["target_file"] = target_file
        edges.append(edge)

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

    # source <file> → import edge (quotes/braces optional). Resolve against this
    # file's directory so the edge targets the sourced file's real file-node id
    # (_make_id(str(path))) rather than a bare-filename id no file node ever
    # uses — mirrors bash.py's source-statement resolution. Only emit when the
    # target exists on disk, guarding against path-traversal-crafted sources.
    for m in re.finditer(r'^\s*source\s+\{?"?([\w./\\-]+\.tcl)"?\}?', source, re.MULTILINE):
        filename = m.group(1)
        line = source[: m.start()].count("\n") + 1
        resolved = (path.parent / filename).resolve()
        if resolved.exists():
            tgt = _make_id(str(resolved))
            add_edge(file_nid, tgt, "imports_from", line, target_file=str(resolved))

    return {"nodes": nodes, "edges": edges}
