"""Css extractor. @import targets."""
from __future__ import annotations

import re

from pathlib import Path
from graphify.extractors.base import _make_id
from graphify.extractors.resolution import _resolve_js_import_target

_IMPORT_RE = re.compile(r"""^[ \t]*@import[ \t]+['"]([^'"]+)['"]""", re.MULTILINE)


def extract_css(path: Path) -> dict:
    """The targets a stylesheet's @import statements point at."""
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"nodes": [], "edges": [], "error": f"cannot read {path}"}

    str_path = str(path)
    file_nid = _make_id(str(path))
    nodes: list[dict] = [{"id": file_nid, "label": path.name, "file_type": "code",
                          "source_file": str_path, "source_location": "L1"}]
    edges: list[dict] = []

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
