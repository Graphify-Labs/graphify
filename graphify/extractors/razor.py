"""ASP.NET Razor component extractor. Moved verbatim from graphify/extract.py."""
from __future__ import annotations

import re
from pathlib import Path

from graphify.extractors.base import _file_stem, _make_id


def extract_razor(path: Path) -> dict:
    """Extract directives, component refs, and @code methods from .razor/.cshtml."""
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"nodes": [], "edges": [], "error": f"cannot read {path}"}

    file_nid = _make_id(str(path))
    str_path = str(path)
    nodes: list[dict] = [{"id": file_nid, "label": path.name, "file_type": "code",
                          "source_file": str_path, "source_location": None}]
    edges: list[dict] = []
    seen_ids: set[str] = set()
    seen_ids.add(file_nid)

    def _add_ref(target_name: str, relation: str, line: int) -> None:
        tgt_nid = _make_id(target_name)
        if not tgt_nid:
            return
        if tgt_nid not in seen_ids:
            seen_ids.add(tgt_nid)
            nodes.append({"id": tgt_nid, "label": target_name,
                          "file_type": "code", "source_file": str_path,
                          "source_location": f"L{line}"})
        edges.append({"source": file_nid, "target": tgt_nid,
                      "relation": relation, "confidence": "EXTRACTED",
                      "source_file": str_path, "source_location": f"L{line}",
                      "weight": 1.0})

    for i, line in enumerate(src.splitlines(), 1):
        m = re.match(r'@using\s+([\w.]+)', line)
        if m:
            _add_ref(m.group(1), "imports", i)
            continue

        m = re.match(r'@inject\s+([\w.<>\[\]]+)\s+(\w+)', line)
        if m:
            _add_ref(m.group(1), "imports", i)
            continue

        m = re.match(r'@inherits\s+([\w.<>\[\]]+)', line)
        if m:
            _add_ref(m.group(1), "inherits", i)
            continue

        m = re.match(r'@model\s+([\w.<>\[\]]+)', line)
        if m:
            _add_ref(m.group(1), "references", i)
            continue

        m = re.match(r'@page\s+"([^"]+)"', line)
        if m:
            route = m.group(1)
            route_nid = _make_id("route", route)
            if route_nid and route_nid not in seen_ids:
                seen_ids.add(route_nid)
                nodes.append({"id": route_nid, "label": f"route:{route}",
                              "file_type": "concept", "source_file": str_path,
                              "source_location": f"L{i}"})
                edges.append({"source": file_nid, "target": route_nid,
                              "relation": "references", "confidence": "EXTRACTED",
                              "source_file": str_path, "weight": 1.0})
            continue

    _COMPONENT_RE = re.compile(r'<([A-Z][A-Za-z0-9]+)[\s/>]')
    _HTML_TAGS = frozenset({
        "DOCTYPE", "Html", "Head", "Body", "Div", "Span", "Table", "Form",
        "Input", "Button", "Select", "Option", "Label", "Textarea",
        "Script", "Style", "Link", "Meta", "Title", "Header", "Footer",
        "Nav", "Main", "Section", "Article", "Aside",
    })
    for m in _COMPONENT_RE.finditer(src):
        comp_name = m.group(1)
        if comp_name in _HTML_TAGS:
            continue
        line_num = src[:m.start()].count("\n") + 1
        _add_ref(comp_name, "calls", line_num)

    _CODE_BLOCK_RE = re.compile(r'@code\s*\{', re.MULTILINE)
    for m in _CODE_BLOCK_RE.finditer(src):
        block_start = m.end()
        depth = 1
        pos = block_start
        while pos < len(src) and depth > 0:
            if src[pos] == '{':
                depth += 1
            elif src[pos] == '}':
                depth -= 1
            pos += 1
        code_block = src[block_start:pos - 1] if depth == 0 else ""

        _METHOD_RE = re.compile(
            r'(?:public|private|protected|internal|static|async|override|virtual|abstract)\s+'
            r'[\w<>\[\],\s]+\s+(\w+)\s*\('
        )
        for mm in _METHOD_RE.finditer(code_block):
            method_name = mm.group(1)
            abs_pos = block_start + mm.start()
            method_line = src[:abs_pos].count("\n") + 1
            method_nid = _make_id(_file_stem(path), method_name)
            if method_nid and method_nid not in seen_ids:
                seen_ids.add(method_nid)
                nodes.append({"id": method_nid, "label": method_name,
                              "file_type": "code", "source_file": str_path,
                              "source_location": f"L{method_line}"})
                edges.append({"source": file_nid, "target": method_nid,
                              "relation": "contains", "confidence": "EXTRACTED",
                              "source_file": str_path, "weight": 1.0})

    return {"nodes": nodes, "edges": edges}
