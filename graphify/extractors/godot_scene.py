"""Godot scene / resource / project extractor.

Parses Godot's INI-like text formats without a tree-sitter grammar:

* ``.tscn`` (PackedScene) and ``.tres`` (Resource):
    - ``[ext_resource type="Script" path="res://x.gd"]`` -> ``attaches_script`` edge
    - ``[ext_resource type="PackedScene" path="res://y.tscn"]`` -> ``instances`` edge
    - ``[node name="N" type="T" parent="P"]`` -> scene-tree node + ``child_of`` edge
    - ``script = ExtResource("id")`` under a node -> that node's ``attaches_script`` edge
    - ``[connection signal="s" from="A" to="B" method="m"]`` -> ``connects`` edge,
      resolved to the target node's script function when possible

* ``project.godot``:
    - ``[autoload]`` entries -> global singleton node + ``autoload`` edge to the script
    - ``run/main_scene`` -> ``main_scene`` edge

Godot text formats are line-oriented and stable, so a small hand parser is
more robust here than a grammar (and adds no dependency).
"""
from __future__ import annotations

import re

from pathlib import Path

from graphify.extractors.base import _file_stem, _make_id

_SECTION_RE = re.compile(r'^\[(?P<kind>[a-z_]+)(?P<attrs>[^\]]*)\]\s*$')
_ATTR_RE = re.compile(r'(\w+)\s*=\s*"([^"]*)"')
_EXTRES_CALL_RE = re.compile(r'ExtResource\(\s*"?([^")]+)"?\s*\)')


def _project_root(path: Path) -> Path:
    for parent in [path.parent, *path.parents]:
        if (parent / "project.godot").exists():
            return parent
    return path.parent


def _resolve_res(res_path: str, root: Path) -> Path | None:
    if not res_path.startswith("res://"):
        return None
    candidate = root / res_path[len("res://"):]
    try:
        return candidate.resolve()
    except Exception:
        return candidate


def _parse_attrs(attr_str: str) -> dict:
    return {k: v for k, v in _ATTR_RE.findall(attr_str)}


def extract_godot_scene(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"error": f"cannot read {path}"}

    if path.name == "project.godot":
        return _extract_project(path, text)

    root = _project_root(path)
    file_nid = _make_id(str(path))
    nodes: list[dict] = [{
        "id": file_nid, "label": path.name, "file_type": "code",
        "source_file": str(path), "source_location": None,
    }]
    edges: list[dict] = []
    defined: set[str] = {file_nid}

    def add_node(nid: str, label: str, loc: str | None = None) -> None:
        if nid not in defined:
            nodes.append({"id": nid, "label": label, "file_type": "code",
                          "source_file": str(path), "source_location": loc})
            defined.add(nid)

    def add_edge(src: str, tgt: str, relation: str, loc: str | None = None,
                 context: str | None = None) -> None:
        e = {"source": src, "target": tgt, "relation": relation,
             "confidence": "EXTRACTED", "confidence_score": 1.0,
             "source_file": str(path), "source_location": loc, "weight": 1.0}
        if context:
            e["context"] = context
        edges.append(e)

    ext_resources: dict[str, dict] = {}   # id -> {type, path, resolved, nid}
    root_script_stem: str | None = None   # stem of the script on the "." node
    node_scripts: dict[str, str] = {}     # node path -> script stem

    lines = text.splitlines()
    current_kind: str | None = None
    current_attrs: dict = {}
    current_node_path: str | None = None

    for i, line in enumerate(lines):
        loc = f"L{i + 1}"
        m = _SECTION_RE.match(line)
        if m:
            current_kind = m.group("kind")
            current_attrs = _parse_attrs(m.group("attrs"))
            current_node_path = None

            if current_kind == "ext_resource":
                rid = current_attrs.get("id", "")
                rtype = current_attrs.get("type", "")
                rpath = current_attrs.get("path", "")
                resolved = _resolve_res(rpath, root)
                info = {"type": rtype, "path": rpath, "resolved": resolved}
                ext_resources[rid] = info
                if resolved is not None:
                    tgt = _make_id(str(resolved))
                    add_node(tgt, resolved.name)
                    if rpath.endswith(".gd") or rtype == "Script":
                        add_edge(file_nid, tgt, "attaches_script", loc)
                    elif rpath.endswith(".tscn") or rtype == "PackedScene":
                        add_edge(file_nid, tgt, "instances", loc)
                    else:
                        add_edge(file_nid, tgt, "uses_resource", loc, context=rtype or None)

            elif current_kind == "node":
                name = current_attrs.get("name", "")
                parent = current_attrs.get("parent")
                if parent is None:
                    current_node_path = "."          # scene root
                elif parent == ".":
                    current_node_path = name
                else:
                    current_node_path = f"{parent}/{name}"

            elif current_kind == "connection":
                sig = current_attrs.get("signal", "")
                frm = current_attrs.get("from", "")
                to = current_attrs.get("to", "")
                method = current_attrs.get("method", "")
                if method:
                    tgt_stem = node_scripts.get(to)
                    if tgt_stem is None and to == ".":
                        tgt_stem = root_script_stem
                    if tgt_stem is not None:
                        tgt = _make_id(tgt_stem, method)
                    else:
                        tgt = _make_id(method)
                        add_node(tgt, method + "()")
                    add_edge(file_nid, tgt, "connects", loc,
                             context=f"{sig} from {frm}")
            continue

        # property line inside a [node] block: script = ExtResource("id")
        if current_kind == "node" and current_node_path is not None:
            stripped = line.strip()
            if stripped.startswith("script ") or stripped.startswith("script="):
                cm = _EXTRES_CALL_RE.search(stripped)
                if cm:
                    rid = cm.group(1)
                    info = ext_resources.get(rid)
                    if info and info.get("resolved") is not None:
                        resolved = info["resolved"]
                        tgt = _make_id(str(resolved))
                        add_node(tgt, resolved.name)
                        add_edge(file_nid, tgt, "attaches_script", loc,
                                 context=current_node_path)
                        stem = _file_stem(resolved)
                        node_scripts[current_node_path] = stem
                        if current_node_path == ".":
                            root_script_stem = stem

    return {"nodes": nodes, "edges": edges}


def _extract_project(path: Path, text: str) -> dict:
    root = path.parent
    file_nid = _make_id(str(path))
    nodes: list[dict] = [{
        "id": file_nid, "label": "project.godot", "file_type": "code",
        "source_file": str(path), "source_location": None,
    }]
    edges: list[dict] = []
    defined: set[str] = {file_nid}

    def add_node(nid: str, label: str, loc: str | None = None) -> None:
        if nid not in defined:
            nodes.append({"id": nid, "label": label, "file_type": "code",
                          "source_file": str(path), "source_location": loc})
            defined.add(nid)

    def add_edge(src: str, tgt: str, relation: str, loc: str | None = None,
                 context: str | None = None) -> None:
        e = {"source": src, "target": tgt, "relation": relation,
             "confidence": "EXTRACTED", "confidence_score": 1.0,
             "source_file": str(path), "source_location": loc, "weight": 1.0}
        if context:
            e["context"] = context
        edges.append(e)

    section: str | None = None
    for i, line in enumerate(text.splitlines()):
        loc = f"L{i + 1}"
        s = line.strip()
        if not s or s.startswith(";"):
            continue
        sm = _SECTION_RE.match(line)
        if sm:
            section = sm.group("kind")
            continue
        if "=" not in s:
            continue
        key, _, val = s.partition("=")
        key = key.strip()
        val = val.strip()

        if section == "autoload":
            # GameState="*res://scripts/game_state.gd"
            raw = val.strip().strip('"')
            res = raw[1:] if raw.startswith("*") else raw
            resolved = _resolve_res(res, root)
            gid = _make_id("autoload", key)
            add_node(gid, key + " (autoload)", loc)
            add_edge(file_nid, gid, "autoload", loc)
            if resolved is not None:
                tgt = _make_id(str(resolved))
                add_node(tgt, resolved.name)
                add_edge(gid, tgt, "script", loc)
        elif key == "run/main_scene":
            resolved = _resolve_res(val.strip('"'), root)
            if resolved is not None:
                tgt = _make_id(str(resolved))
                add_node(tgt, resolved.name)
                add_edge(file_nid, tgt, "main_scene", loc)

    return {"nodes": nodes, "edges": edges}
