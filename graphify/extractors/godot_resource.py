"""Godot text resources: scenes (``.tscn``), resources (``.tres``), ``project.godot``.

All three share Godot's INI-like text format: ``[section key="value" …]``
headers followed by ``key = value`` properties. Only the parts that wire a
project together are read, so a plain line parser is enough and no grammar is
needed:

* ``[ext_resource path="res://…"]`` naming a script, scene or resource ->
  ``imports_from`` that file (the scene attaches, instances or uses it).
* ``[connection signal="s" from="A" to="B" method="m"]`` -> ``references`` to
  ``m`` on the script attached to node ``B`` in the same scene.
* ``project.godot`` ``[autoload]`` entries -> an autoload node that
  ``imports_from`` its script; ``run/main_scene`` -> ``references`` the scene.

The autoload nodes are what ``resolve_gdscript_references`` binds a
``GameState.method()`` call through.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from graphify.extractors.base import _file_stem, _make_id
from graphify.extractors.gdscript import godot_project_root, resolve_res_path

# Section kinds are lowercase words; a continuation line of a multi-line array
# value (`[1, 2]`) is not a header.
_SECTION_RE = re.compile(r"^\[([a-z_]+)(\s.*)?\]\s*$")
_ATTR_RE = re.compile(r'(\w+)=("[^"]*"|\w+\([^)]*\)|[^\s\]]+)')
_PROP_RE = re.compile(r"^([\w/]+)\s*=\s*(.+?)\s*$")
_EXT_RESOURCE_RE = re.compile(r'ExtResource\(\s*"?([^")\s]+)"?\s*\)')
_LINKED_SUFFIXES = frozenset({".gd", ".tscn", ".tres"})


def _unquote(value: str) -> str:
    return value[1:-1] if len(value) >= 2 and value[0] == value[-1] == '"' else value


def _sections(text: str) -> list[tuple[str | None, dict[str, str], list[tuple[str, str, int]], int]]:
    """``(kind, header attrs, [(key, value, line)], line)`` per section.

    Properties before the first header (``config_version`` in project.godot)
    land in a leading section of kind None.
    """
    sections: list[tuple[str | None, dict[str, str], list[tuple[str, str, int]], int]] = [
        (None, {}, [], 1)
    ]
    for number, line in enumerate(text.splitlines(), start=1):
        header = _SECTION_RE.match(line)
        if header:
            attrs = {k: _unquote(v) for k, v in _ATTR_RE.findall(header.group(2) or "")}
            sections.append((header.group(1), attrs, [], number))
            continue
        prop = _PROP_RE.match(line)
        if prop:
            sections[-1][2].append((prop.group(1), prop.group(2), number))
    return sections


def extract_godot_resource(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"nodes": [], "edges": [], "error": f"cannot read {path}: {exc}"}

    source_file = str(path)
    file_id = _make_id(source_file)
    project_root = path.parent if path.name == "project.godot" else godot_project_root(path)
    nodes: list[dict[str, Any]] = [{
        "id": file_id,
        "label": path.name,
        "file_type": "code",
        "source_file": source_file,
        "source_location": "L1",
        "metadata": {"language": "godot", "kind": "file"},
    }]
    edges: list[dict[str, Any]] = []

    def add_edge(src: str, tgt: str, relation: str, line: int, context: str | None,
                 target_file: Path | None = None) -> None:
        edge: dict[str, Any] = {
            "source": src,
            "target": tgt,
            "relation": relation,
            "confidence": "EXTRACTED",
            "confidence_score": 1.0,
            "source_file": source_file,
            "source_location": f"L{line}",
            "weight": 1.0,
        }
        if context:
            edge["context"] = context
        if target_file is not None:
            edge["target_file"] = str(target_file)
        edges.append(edge)

    def linked(ref: str) -> Path | None:
        target = resolve_res_path(ref, path, project_root)
        return target if target is not None and target.suffix in _LINKED_SUFFIXES else None

    sections = _sections(text)

    if path.name == "project.godot":
        stem = _file_stem(path)
        for kind, _attrs, props, _line in sections:
            for key, value, line in props:
                if kind == "autoload":
                    autoload_id = _make_id(stem, "autoload", key)
                    nodes.append({
                        "id": autoload_id,
                        "label": key,
                        "file_type": "code",
                        "source_file": source_file,
                        "source_location": f"L{line}",
                        "metadata": {"language": "gdscript", "kind": "autoload", "name": key},
                    })
                    add_edge(file_id, autoload_id, "contains", line, "autoload")
                    target = linked(_unquote(value).lstrip("*"))
                    if target is not None:
                        add_edge(autoload_id, _make_id(str(target)), "imports_from", line,
                                 "autoload", target)
                elif kind == "application" and key == "run/main_scene":
                    target = linked(_unquote(value))
                    if target is not None:
                        add_edge(file_id, _make_id(str(target)), "references", line,
                                 "main_scene", target)
        return {"nodes": nodes, "edges": edges}

    resources: dict[str, Path] = {}     # ext_resource id -> file
    scripts: dict[str, Path] = {}       # scene node path -> attached script
    for kind, attrs, props, line in sections:
        if kind == "ext_resource":
            target = linked(attrs.get("path", ""))
            if target is None:
                continue
            resources[attrs.get("id", "")] = target
            add_edge(file_id, _make_id(str(target)), "imports_from", line,
                     attrs.get("type") or None, target)
        elif kind == "node":
            name = attrs.get("name", "")
            parent = attrs.get("parent")
            node_path = "." if parent is None else name if parent == "." else f"{parent}/{name}"
            for key, value, _ in props:
                ref = _EXT_RESOURCE_RE.search(value) if key == "script" else None
                if ref and ref.group(1) in resources:
                    scripts[node_path] = resources[ref.group(1)]
        elif kind == "connection":
            script = scripts.get(attrs.get("to", ""))
            method = attrs.get("method")
            if script is None or not method or script.suffix != ".gd":
                continue
            add_edge(file_id, _make_id(_file_stem(script), method), "references", line,
                     f"signal {attrs.get('signal', '')}".strip(), script)
    return {"nodes": nodes, "edges": edges}
