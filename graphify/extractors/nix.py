"""Dependency-free structural extraction for Nix expressions."""
from __future__ import annotations

import re
from pathlib import Path

from graphify.extractors.base import _file_stem, _make_id

_BINDING_RE = re.compile(r"(?m)^\s*([A-Za-z_][A-Za-z0-9_'-]*)\s*=\s*")
_FUNCTION_RE = re.compile(
    r"(?m)^\s*([A-Za-z_][A-Za-z0-9_'-]*)\s*=\s*(?:\([^\n]*\)|[A-Za-z_][A-Za-z0-9_'-]*)\s*:\s*"
)
_IMPORT_RE = re.compile(r"(?<![A-Za-z0-9_.])((?:\.\.?/)[A-Za-z0-9_./'-]+\.nix)(?![A-Za-z0-9_])")
_INTERPOLATION_RE = re.compile(r"\$\{\s*([A-Za-z_][A-Za-z0-9_'-]*)")
_INHERIT_RE = re.compile(r"(?m)\binherit(?:From)?\s+([^;\n}]+)")


def extract_nix(path: Path) -> dict:
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
    bindings: dict[str, str] = {}

    def line(match: re.Match) -> int:
        return source.count("\n", 0, match.start()) + 1

    def add_node(name: str, at: int, kind: str = "binding") -> str:
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

    for match in _BINDING_RE.finditer(source):
        name = match.group(1)
        if name in {"let", "in", "with", "inherit", "assert", "rec"}:
            continue
        kind = "function" if _FUNCTION_RE.match(source, match.start()) else "binding"
        binding_id = add_node(name, line(match), kind)
        bindings.setdefault(name, binding_id)
        add_edge(file_id, binding_id, "contains", line(match))

    for match in _IMPORT_RE.finditer(source):
        target = match.group(1)
        target_id = _make_id(_file_stem(path.parent / target))
        if target_id not in seen:
            seen.add(target_id)
            nodes.append({"id": target_id, "label": Path(target).name, "file_type": "concept",
                          "source_file": source_file, "source_location": f"L{line(match)}",
                          "kind": "relative-import"})
        add_edge(file_id, target_id, "imports", line(match), "literal-relative-path")

    for match in _INTERPOLATION_RE.finditer(source):
        target = bindings.get(match.group(1))
        if target:
            add_edge(file_id, target, "references", line(match), "interpolation")
    for match in _INHERIT_RE.finditer(source):
        for name in re.findall(r"[A-Za-z_][A-Za-z0-9_'-]*", match.group(1)):
            target = bindings.get(name)
            if target:
                add_edge(file_id, target, "references", line(match), "inherit")
    return {"nodes": nodes, "edges": edges}
