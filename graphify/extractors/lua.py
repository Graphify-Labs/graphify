"""Lua extractor - functions, methods, require() imports, and calls."""

from __future__ import annotations

import re
from pathlib import Path

from .registry import register
from ._utils import make_id, file_stem

_EXTENSIONS = {'.lua', '.luau'}


def _read_text(node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _resolve_lua_import_target(raw_module: str, str_path: str) -> str:
    """Resolve a Lua require() module name to a node id.

    Lua module names use dots as path separators: `require("pkg.b")` looks for
    `pkg/b.lua` (or `pkg/b/init.lua`) relative to a package root.
    """
    if not raw_module:
        return ""
    rel = raw_module.replace(".", "/")
    try:
        start_dir = Path(str_path).parent
    except Exception:
        start_dir = None
    if start_dir is not None:
        probe = start_dir
        for _ in range(6):
            for suffix in (".lua", ".luau"):
                cand = probe / f"{rel}{suffix}"
                if cand.is_file():
                    return make_id(str(cand))
            for suffix in (".lua", ".luau"):
                cand = probe / rel / f"init{suffix}"
                if cand.is_file():
                    return make_id(str(cand))
            if probe.parent == probe:
                break
            probe = probe.parent
    return make_id(raw_module)


@register(_EXTENSIONS)
def extract_lua(path: Path) -> dict:
    """Extract functions, methods, require() imports, and calls from a .lua file."""
    try:
        import tree_sitter_lua as tslua
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree-sitter-lua not installed"}

    try:
        language = Language(tslua.language())
        parser = Parser(language)
        source = path.read_bytes()
        tree = parser.parse(source)
        root = tree.root_node
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    stem = file_stem(path)
    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()
    function_bodies: list[tuple[str, object]] = []

    def add_node(nid: str, label: str, line: int) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({
                "id": nid,
                "label": label,
                "file_type": "code",
                "source_file": str_path,
                "source_location": f"L{line}",
            })

    def add_edge(src: str, tgt: str, relation: str, line: int,
                 confidence: str = "EXTRACTED", weight: float = 1.0,
                 context: str | None = None) -> None:
        edge = {
            "source": src,
            "target": tgt,
            "relation": relation,
            "confidence": confidence,
            "source_file": str_path,
            "source_location": f"L{line}",
            "weight": weight,
        }
        if context:
            edge["context"] = context
        edges.append(edge)

    file_nid = make_id(str(path))
    add_node(file_nid, path.name, 1)

    def ensure_named_node(name: str, line: int) -> str:
        nid = make_id(stem, name)
        if nid in seen_ids:
            return nid
        nid = make_id(name)
        if nid not in seen_ids:
            add_node(nid, name, line)
        return nid

    def walk(node, parent_nid: str = file_nid) -> None:
        t = node.type

        if t == "function_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                func_name = _read_text(name_node, source)
                line = node.start_point[0] + 1
                func_nid = make_id(stem, func_name)
                add_node(func_nid, f"{func_name}()", line)
                add_edge(parent_nid, func_nid, "contains", line)
                body = node.child_by_field_name("body")
                if body:
                    function_bodies.append((func_nid, body))
            return

        if t == "function_definition":
            name_node = node.child_by_field_name("name")
            if name_node:
                func_name = _read_text(name_node, source)
                line = node.start_point[0] + 1
                func_nid = make_id(stem, func_name)
                add_node(func_nid, f"{func_name}()", line)
                add_edge(parent_nid, func_nid, "contains", line)
                body = node.child_by_field_name("body")
                if body:
                    function_bodies.append((func_nid, body))
            return

        if t == "variable_declaration":
            text = _read_text(node, source)
            m = re.search(r"""require\s*[\('"]\s*['"]?([^'")\s]+)""", text)
            if m:
                raw_module = m.group(1)
                if raw_module:
                    tgt_nid = _resolve_lua_import_target(raw_module, str_path)
                    if tgt_nid:
                        edges.append({
                            "source": file_nid,
                            "target": tgt_nid,
                            "relation": "imports",
                            "context": "import",
                            "confidence": "EXTRACTED",
                            "confidence_score": 1.0,
                            "source_file": str_path,
                            "source_location": str(node.start_point[0] + 1),
                            "weight": 1.0,
                        })
            for child in node.children:
                walk(child, parent_nid)
            return

        for child in node.children:
            walk(child, parent_nid)

    walk(root)

    label_to_nid = {n["label"].strip("()").lower(): n["id"] for n in nodes}
    seen_call_pairs: set[tuple[str, str]] = set()
    raw_calls: list[dict] = []

    def walk_calls(node, caller_nid: str) -> None:
        if node.type in ("function_declaration", "function_definition"):
            return
        if node.type == "function_call":
            name_node = node.child_by_field_name("name")
            if name_node:
                call_name = _read_text(name_node, source)
                callee = call_name.split(".")[-1]
                tgt_nid = label_to_nid.get(f"{callee}()")
                if tgt_nid and tgt_nid != caller_nid:
                    pair = (caller_nid, tgt_nid)
                    if pair not in seen_call_pairs:
                        seen_call_pairs.add(pair)
                        add_edge(caller_nid, tgt_nid, "calls",
                                 node.start_point[0] + 1,
                                 confidence="EXTRACTED", weight=1.0)
                elif callee:
                    raw_calls.append({
                        "caller_nid": caller_nid,
                        "callee": callee,
                        "is_member_call": "." in call_name,
                        "source_file": str_path,
                        "source_location": f"L{node.start_point[0] + 1}",
                    })
        for child in node.children:
            walk_calls(child, caller_nid)

    for caller_nid, body_node in function_bodies:
        walk_calls(body_node, caller_nid)

    clean_edges = [e for e in edges if e["source"] in seen_ids and
                   (e["target"] in seen_ids or e["relation"] in ("imports", "imports_from"))]
    return {"nodes": nodes, "edges": clean_edges, "raw_calls": raw_calls}
