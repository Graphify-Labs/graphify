"""Css extractor. Custom-property definitions and @import targets."""
from __future__ import annotations

import re

from pathlib import Path
from graphify.extractors.base import _file_stem, _make_id
from graphify.extractors.resolution import _resolve_js_import_target

_CUSTOM_PROPERTY_RE = re.compile(r"^[ \t]*(--[A-Za-z0-9_-]+)[ \t]*:", re.MULTILINE)
_VAR_REF_RE = re.compile(r"var\(\s*(--[A-Za-z0-9_-]+)", re.MULTILINE)
_IMPORT_RE = re.compile(r"""^[ \t]*@import[ \t]+['"]([^'"]+)['"]""", re.MULTILINE)


def extract_css(path: Path) -> dict:
    """Custom properties a stylesheet defines, and the targets it imports."""
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"nodes": [], "edges": [], "error": f"cannot read {path}"}

    str_path = str(path)
    stem = _file_stem(path)
    file_nid = _make_id(str(path))
    nodes: list[dict] = [{"id": file_nid, "label": path.name, "file_type": "code",
                          "source_file": str_path, "source_location": "L1"}]
    edges: list[dict] = []
    seen: set[str] = {file_nid}

    declared_names: set[str] = {m.group(1) for m in _CUSTOM_PROPERTY_RE.finditer(source)}

    for m in _CUSTOM_PROPERTY_RE.finditer(source):
        name = m.group(1)
        if name.endswith("-rgb") and name[:-4] in declared_names:
            name = name[:-4]
        nid = _make_id(stem, name)
        if nid in seen:
            continue
        seen.add(nid)
        line = source.count("\n", 0, m.start()) + 1
        nodes.append({"id": nid, "label": name, "file_type": "code",
                      "source_file": str_path, "source_location": f"L{line}"})
        edges.append({"source": file_nid, "target": nid, "relation": "contains",
                      "confidence": "EXTRACTED", "source_file": str_path,
                      "source_location": f"L{line}", "weight": 1.0})

    seen_refs: set[str] = set()
    for m in _VAR_REF_RE.finditer(source):
        name = m.group(1)
        if name.endswith("-rgb") and name[:-4] in declared_names:
            name = name[:-4]
        if name in seen_refs:
            continue
        seen_refs.add(name)
        line = source.count("\n", 0, m.start()) + 1
        target = _make_id(stem, name) if name in declared_names else name
        edges.append({"source": file_nid, "target": target, "relation": "uses_token",
                      "confidence": "EXTRACTED", "source_file": str_path,
                      "source_location": f"L{line}", "weight": 1.0, "token_name": name})

    for m in _IMPORT_RE.finditer(source):
        line = source.count("\n", 0, m.start()) + 1
        raw = m.group(1)
        resolved = _resolve_js_import_target(raw, str_path)
        if resolved is None:
            continue
        target, resolved_path = resolved
        if resolved_path is not None and not resolved_path.is_file():
            target, resolved_path = _make_id("ref", raw), None
        edge = {"source": file_nid, "target": target,
                "relation": "imports", "confidence": "EXTRACTED",
                "source_file": str_path, "source_location": f"L{line}",
                "weight": 1.0}
        if resolved_path is not None:
            edge["target_file"] = str(resolved_path)
        edges.append(edge)

    return {"nodes": nodes, "edges": edges}
