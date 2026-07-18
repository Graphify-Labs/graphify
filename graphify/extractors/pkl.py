"""Dependency-free structural extraction for Pkl configuration modules."""
from __future__ import annotations

import re
from pathlib import Path

from graphify.extractors.base import _file_stem, _make_id

_DECL_RE = re.compile(
    r"(?m)^\s*(?:(abstract)\s+)?(module|class|typealias|function|modulemethod)\s+([A-Za-z_][A-Za-z0-9_]*)"
)
_PROPERTY_RE = re.compile(r"(?m)^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*([A-Za-z_][A-Za-z0-9_?.<>\[\]]*)")
_IMPORT_RE = re.compile(r"(?m)^\s*(import|amends|extends)\s+([^\n]+)")


def extract_pkl(path: Path) -> dict:
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"nodes": [], "edges": [], "error": str(exc)}
    source_file = str(path)
    stem = _file_stem(path)
    file_id = _make_id(stem)
    nodes = [{"id": file_id, "label": path.name, "file_type": "code",
              "source_file": source_file, "source_location": "L1"}]
    edges: list[dict] = []
    seen = {file_id}

    def line(match: re.Match) -> int:
        return source.count("\n", 0, match.start()) + 1

    def add_node(name: str, at: int, kind: str) -> str:
        node_id = _make_id(stem, name)
        if node_id not in seen:
            seen.add(node_id)
            nodes.append({"id": node_id, "label": name, "file_type": "code",
                          "source_file": source_file, "source_location": f"L{at}",
                          "kind": kind})
        return node_id

    def add_edge(source: str, target: str, relation: str, at: int, context: str | None = None) -> None:
        if source == target:
            return
        edge = {"source": source, "target": target, "relation": relation,
                "confidence": "EXTRACTED", "source_file": source_file,
                "source_location": f"L{at}", "weight": 1.0}
        if context:
            edge["context"] = context
        edges.append(edge)

    symbols: dict[str, str] = {}
    for match in _DECL_RE.finditer(source):
        name, kind = match.group(3), match.group(2)
        symbol_id = add_node(name, line(match), kind)
        symbols.setdefault(name, symbol_id)
        add_edge(file_id, symbol_id, "contains", line(match))
    for match in _PROPERTY_RE.finditer(source):
        name, type_name = match.group(1), match.group(2)
        if name in {"module", "class", "typealias", "function", "extends", "amends"}:
            continue
        property_id = add_node(name, line(match), "property")
        symbols.setdefault(name, property_id)
        add_edge(file_id, property_id, "contains", line(match))
        type_id = add_node(type_name, line(match), "type")
        add_edge(property_id, type_id, "references", line(match), "type")
    for match in _IMPORT_RE.finditer(source):
        relation, expression = match.group(1), match.group(2).strip()
        target = expression.strip('"')
        target_id = _make_id("pkl", target)
        if target_id not in seen:
            seen.add(target_id)
            nodes.append({"id": target_id, "label": target, "file_type": "concept",
                          "source_file": source_file, "source_location": f"L{line(match)}",
                          "kind": "module-reference"})
        add_edge(file_id, target_id, "imports" if relation == "import" else relation,
                 line(match), "module-reference")
    return {"nodes": nodes, "edges": edges}
