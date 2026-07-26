"""Godot scene / resource / project extractor.

Parses Godot's text formats for ``.tscn`` (PackedScene), ``.tres`` (Resource)
and ``project.godot`` and emits Graphify's node/edge dicts:

* ``.tscn`` / ``.tres``:
    - ``[ext_resource type="Script" path="res://x.gd"]`` -> ``attaches_script`` edge
    - ``[ext_resource type="PackedScene" path="res://y.tscn"]`` -> ``instances`` edge
    - ``[node name="N" type="T" parent="P"]`` -> scene-tree node
    - ``script = ExtResource("id")`` under a node -> that node's ``attaches_script`` edge
    - ``[connection signal="s" from="A" to="B" method="m"]`` -> ``connects`` edge,
      resolved to the target node's script function when possible

* ``project.godot``:
    - ``[autoload]`` entries -> global singleton node + ``autoload`` edge to the script
    - ``run/main_scene`` -> ``main_scene`` edge

Godot's scene / resource / project files all share one text format. When the
``godot_resource`` tree-sitter grammar is available (bundled in
``tree-sitter-language-pack``, the Godot extra) it is used for robust handling
of quoting, multi-line values and nested constructors. Both front ends lower a
file to the same intermediate list of ``_Block``s, which a single edge builder
consumes -- so the grammar path and the dependency-free line-parser fallback
produce identical nodes/edges. If the grammar is absent (or a file fails to
parse cleanly) the line parser takes over, so scene/autoload/signal-wire edges
keep working out of the box.
"""
from __future__ import annotations

import re

from pathlib import Path

from graphify.extractors.base import _file_stem, _make_id

_SECTION_RE = re.compile(r'^\[(?P<kind>[a-z_]+)(?P<attrs>[^\]]*)\]\s*$')
_ATTR_RE = re.compile(r'(\w+)\s*=\s*"([^"]*)"')
_PROP_RE = re.compile(r'^\s*(?P<key>[\w/]+)\s*=\s*(?P<val>.+?)\s*$')
_EXTRES_CALL_RE = re.compile(r'ExtResource\(\s*"?([^")]+)"?\s*\)')


class _Block:
    """One header section (or the file preamble) in normalized form.

    ``kind`` is the section identifier (``ext_resource``, ``node``,
    ``connection``, ``autoload`` ...) or ``None`` for top-level properties that
    precede any section (e.g. ``config_version`` in ``project.godot``).
    ``attrs`` are the header's ``key="value"`` pairs (unquoted). ``props`` are
    the ``key = value`` lines inside the section as ``(key, raw_value, loc)``;
    the raw value is kept verbatim so each builder applies its own unquoting /
    ``ExtResource(...)`` parsing exactly as before.
    """

    __slots__ = ("kind", "attrs", "props", "loc")

    def __init__(self, kind, attrs, props, loc):
        self.kind = kind
        self.attrs = attrs
        self.props = props
        self.loc = loc


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


# ---------------------------------------------------------------------------
# Grammar-based front end (tree-sitter-language-pack: "godot_resource")
# ---------------------------------------------------------------------------

# Sentinel so a failed import is cached and not retried per file.
_RESOURCE_PARSER: object = "unset"


def _load_resource_parser():
    """Return a tree-sitter Parser for Godot resource text, or ``None``.

    The ``godot_resource`` grammar (PrestonKnopp, MIT) is bundled in
    ``tree-sitter-language-pack`` (the Godot extra) and parses ``.tscn``,
    ``.tres`` and ``project.godot`` alike. When the pack is not installed the
    caller falls back to the line parser below.
    """
    global _RESOURCE_PARSER
    if _RESOURCE_PARSER != "unset":
        return _RESOURCE_PARSER
    parser = None
    try:
        from tree_sitter_language_pack import get_parser
        parser = get_parser("godot_resource")
    except Exception:
        parser = None
    _RESOURCE_PARSER = parser
    return parser


def _node_text(node, src: bytes) -> str:
    return src[node.start_byte:node.end_byte].decode("utf-8", "replace")


def _unquote(s: str) -> str:
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return s[1:-1]
    return s


def _key_value_nodes(node):
    """First and last named children of an ``attribute`` / ``property`` node.

    Both grammar shapes are ``key = value`` with the key as the first named
    child and the value as the last, so this covers both.
    """
    named = [c for c in node.children if c.is_named]
    if len(named) >= 2:
        return named[0], named[-1]
    if len(named) == 1:
        return named[0], None
    return None, None


def _blocks_from_grammar(text: str) -> list[_Block] | None:
    parser = _load_resource_parser()
    if parser is None:
        return None
    try:
        tree = parser.parse(text.encode("utf-8"))
    except Exception:
        return None
    if tree.root_node.has_error:
        # A malformed file: defer to the tolerant line parser instead.
        return None

    src = text.encode("utf-8")
    blocks: list[_Block] = []
    preamble: list[tuple[str, str, str]] = []

    for child in tree.root_node.children:
        if child.type == "property":
            k, v = _key_value_nodes(child)
            if k is not None:
                preamble.append((_node_text(k, src),
                                 _node_text(v, src) if v is not None else "",
                                 f"L{child.start_point[0] + 1}"))
        elif child.type == "section":
            kind: str | None = None
            attrs: dict = {}
            props: list[tuple[str, str, str]] = []
            for c in child.children:
                if c.type == "identifier" and kind is None:
                    kind = _node_text(c, src)
                elif c.type == "attribute":
                    k, v = _key_value_nodes(c)
                    if k is not None:
                        attrs[_node_text(k, src)] = (
                            _unquote(_node_text(v, src)) if v is not None else "")
                elif c.type == "property":
                    k, v = _key_value_nodes(c)
                    if k is not None:
                        props.append((_node_text(k, src),
                                      _node_text(v, src) if v is not None else "",
                                      f"L{c.start_point[0] + 1}"))
            blocks.append(_Block(kind, attrs, props, f"L{child.start_point[0] + 1}"))

    if preamble:
        blocks.insert(0, _Block(None, {}, preamble, "L1"))
    return blocks


# ---------------------------------------------------------------------------
# Dependency-free line parser (fallback when the grammar is absent)
# ---------------------------------------------------------------------------

def _blocks_from_lines(text: str) -> list[_Block]:
    blocks: list[_Block] = []
    preamble = _Block(None, {}, [], "L1")
    current: _Block | None = None

    for i, line in enumerate(text.splitlines()):
        loc = f"L{i + 1}"
        m = _SECTION_RE.match(line)
        if m:
            current = _Block(m.group("kind"), _parse_attrs(m.group("attrs")), [], loc)
            blocks.append(current)
            continue
        stripped = line.strip()
        if not stripped or stripped.startswith(";"):
            continue
        pm = _PROP_RE.match(line)
        if pm:
            target = current if current is not None else preamble
            target.props.append((pm.group("key"), pm.group("val"), loc))

    if preamble.props:
        blocks.insert(0, preamble)
    return blocks


def _blocks(text: str) -> list[_Block]:
    blocks = _blocks_from_grammar(text)
    if blocks is None:
        blocks = _blocks_from_lines(text)
    return blocks


# ---------------------------------------------------------------------------
# Shared edge builders
# ---------------------------------------------------------------------------

def extract_godot_scene(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"error": f"cannot read {path}"}

    blocks = _blocks(text)
    if path.name == "project.godot":
        return _build_project(path, blocks)
    return _build_scene(path, blocks)


def _build_scene(path: Path, blocks: list[_Block]) -> dict:
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

    ext_resources: dict[str, dict] = {}   # id -> {type, path, resolved}
    root_script_stem: str | None = None   # stem of the script on the "." node
    node_scripts: dict[str, str] = {}     # node path -> script stem

    for block in blocks:
        kind = block.kind
        loc = block.loc

        if kind == "ext_resource":
            rid = block.attrs.get("id", "")
            rtype = block.attrs.get("type", "")
            rpath = block.attrs.get("path", "")
            resolved = _resolve_res(rpath, root)
            ext_resources[rid] = {"type": rtype, "path": rpath, "resolved": resolved}
            if resolved is not None:
                tgt = _make_id(str(resolved))
                add_node(tgt, resolved.name)
                if rpath.endswith(".gd") or rtype == "Script":
                    add_edge(file_nid, tgt, "attaches_script", loc)
                elif rpath.endswith(".tscn") or rtype == "PackedScene":
                    add_edge(file_nid, tgt, "instances", loc)
                else:
                    add_edge(file_nid, tgt, "uses_resource", loc, context=rtype or None)

        elif kind == "node":
            name = block.attrs.get("name", "")
            parent = block.attrs.get("parent")
            if parent is None:
                node_path = "."                 # scene root
            elif parent == ".":
                node_path = name
            else:
                node_path = f"{parent}/{name}"

            for key, val, ploc in block.props:
                if key != "script":
                    continue
                cm = _EXTRES_CALL_RE.search(val)
                if not cm:
                    continue
                info = ext_resources.get(cm.group(1))
                if info and info.get("resolved") is not None:
                    resolved = info["resolved"]
                    tgt = _make_id(str(resolved))
                    add_node(tgt, resolved.name)
                    add_edge(file_nid, tgt, "attaches_script", ploc,
                             context=node_path)
                    stem = _file_stem(resolved)
                    node_scripts[node_path] = stem
                    if node_path == ".":
                        root_script_stem = stem

        elif kind == "connection":
            sig = block.attrs.get("signal", "")
            frm = block.attrs.get("from", "")
            to = block.attrs.get("to", "")
            method = block.attrs.get("method", "")
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

    return {"nodes": nodes, "edges": edges}


def _build_project(path: Path, blocks: list[_Block]) -> dict:
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

    for block in blocks:
        for key, val, loc in block.props:
            if block.kind == "autoload":
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
                resolved = _resolve_res(val.strip().strip('"'), root)
                if resolved is not None:
                    tgt = _make_id(str(resolved))
                    add_node(tgt, resolved.name)
                    add_edge(file_nid, tgt, "main_scene", loc)

    return {"nodes": nodes, "edges": edges}
