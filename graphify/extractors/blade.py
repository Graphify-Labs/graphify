"""Laravel Blade template extractor. Moved verbatim from graphify/extract.py."""
from __future__ import annotations

from pathlib import Path

from graphify.extractors.base import _make_id, _read_source_text


def extract_blade(path: Path) -> dict:
    """Extract @extends, @include, <livewire:> components, and wire:click bindings from Blade templates."""
    import re
    try:
        src = _read_source_text(path)
    except OSError:
        return {"error": f"cannot read {path}"}

    file_nid = _make_id(str(path))
    nodes = [{"id": file_nid, "label": path.name, "file_type": "code",
              "source_file": str(path), "source_location": None}]
    edges = []

    # @extends('layouts.app') — template inheritance: this view renders inside
    # the named parent layout. It is the primary structural relationship in a
    # Blade view (most page templates extend a layout), so dropping it left the
    # child disconnected from its layout in the graph.
    for m in re.finditer(r"@extends\(['\"]([^'\"]+)['\"]", src):
        tgt = m.group(1).replace(".", "/")
        tgt_nid = _make_id(tgt)
        if tgt_nid not in {n["id"] for n in nodes}:
            nodes.append({"id": tgt_nid, "label": m.group(1), "file_type": "code",
                          "source_file": str(path), "source_location": None})
        edges.append({"source": file_nid, "target": tgt_nid, "relation": "extends",
                      "confidence": "EXTRACTED", "confidence_score": 1.0,
                      "source_file": str(path), "source_location": None, "weight": 1.0})

    # @include('path.to.partial') or @include("path.to.partial")
    for m in re.finditer(r"@include\(['\"]([^'\"]+)['\"]", src):
        tgt = m.group(1).replace(".", "/")
        tgt_nid = _make_id(tgt)
        if tgt_nid not in {n["id"] for n in nodes}:
            nodes.append({"id": tgt_nid, "label": m.group(1), "file_type": "code",
                          "source_file": str(path), "source_location": None})
        edges.append({"source": file_nid, "target": tgt_nid, "relation": "includes",
                      "confidence": "EXTRACTED", "confidence_score": 1.0,
                      "source_file": str(path), "source_location": None, "weight": 1.0})

    # <livewire:component.name /> or <livewire:component.name>
    for m in re.finditer(r"<livewire:([\w.\-]+)", src):
        tgt_nid = _make_id(m.group(1))
        if tgt_nid not in {n["id"] for n in nodes}:
            nodes.append({"id": tgt_nid, "label": m.group(1), "file_type": "code",
                          "source_file": str(path), "source_location": None})
        edges.append({"source": file_nid, "target": tgt_nid, "relation": "uses_component",
                      "confidence": "EXTRACTED", "confidence_score": 1.0,
                      "source_file": str(path), "source_location": None, "weight": 1.0})

    # wire:click="methodName" or wire:click="methodName(arg)", with an optional
    # Livewire event modifier (wire:click.prevent=, wire:click.stop=) the bare
    # `wire:click=` pattern never matched at all. A call's own arguments are not
    # part of the method's name and must not end up in the bound id; a magic
    # action ($set, $emit, $toggle, $refresh, ...) is Livewire's own runtime
    # behavior, not a method the component defines, so it is left unbound rather
    # than fabricating an edge to something that does not exist.
    for m in re.finditer(r'wire:click(?:\.\w+)*=["\']([^"\']+)["\']', src):
        raw = m.group(1).strip()
        if raw.startswith("$"):
            continue
        name_match = re.match(r"[A-Za-z_]\w*", raw)
        if not name_match:
            continue
        method_name = name_match.group(0)
        tgt_nid = _make_id(method_name)
        if tgt_nid not in {n["id"] for n in nodes}:
            nodes.append({"id": tgt_nid, "label": method_name, "file_type": "code",
                          "source_file": str(path), "source_location": None})
        edges.append({"source": file_nid, "target": tgt_nid, "relation": "binds_method",
                      "confidence": "EXTRACTED", "confidence_score": 1.0,
                      "source_file": str(path), "source_location": None, "weight": 1.0})

    return {"nodes": nodes, "edges": edges}
