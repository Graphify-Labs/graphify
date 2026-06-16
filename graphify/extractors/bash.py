"""Bash extractor - functions, source imports, and calls."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .registry import register
from ._utils import make_id, file_stem

_EXTENSIONS = {".sh", ".bash"}


def _read_text(node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


@register(_EXTENSIONS)
def extract_bash(path: Path) -> dict:
    """Extract functions, source imports, and cross-function calls from a .sh file."""
    try:
        import tree_sitter_bash as tsbash
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree-sitter-bash not installed"}

    try:
        language = Language(tsbash.language())
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
    function_bodies: list[tuple[str, Any]] = []
    defined_functions: set[str] = set()

    from graphify.security import sanitize_metadata

    def add_node(nid: str, label: str, line: int, kind: str = "code") -> None:
        if nid and nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append(
                {
                    "id": nid,
                    "label": label,
                    "file_type": "code",
                    "source_file": str_path,
                    "source_location": f"L{line}",
                    "metadata": sanitize_metadata({"language": "bash", "kind": kind}),
                }
            )

    def add_edge(
        src: str,
        tgt: str,
        relation: str,
        line: int,
        confidence: str = "EXTRACTED",
        weight: float = 1.0,
        context: str | None = None,
    ) -> None:
        if not src or not tgt or src == tgt:
            return
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
    entry_nid = file_nid + "__entry"
    add_node(file_nid, path.name, 1, kind="file")
    add_node(entry_nid, f"{path.name} script", 1, kind="bash_entrypoint")
    add_edge(file_nid, entry_nid, "contains", 1)

    _BASH_SOURCE_COMMANDS = frozenset({"source", "."})
    _BASH_EXPANSION_PARENTS = frozenset(
        {
            "command_substitution",
            "process_substitution",
        }
    )

    def text(node) -> str:
        return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")

    def is_inside_expansion(node) -> bool:
        parent = node.parent
        while parent is not None:
            if parent.type in _BASH_EXPANSION_PARENTS:
                return True
            parent = parent.parent
        return False

    def literal(node) -> str | None:
        raw = text(node).strip()
        if not raw:
            return None
        if raw[0:1] in {"'", '"'} and raw[-1:] == raw[0]:
            raw = raw[1:-1]
        if any(token in raw for token in ("$", "`", "$(", "<(", ">", "|", ";", "&")):
            return None
        return raw

    def _bash_func_name(node) -> str | None:
        for child in node.children:
            if child.type == "word":
                return literal(child)
        return None

    def walk_calls(body_node, func_nid: str, seen_calls: set) -> None:
        if body_node is None:
            return
        for child in body_node.children:
            if child.type == "function_definition":
                continue
            if child.type == "command" and not is_inside_expansion(child):
                cmd_name_node = child.child_by_field_name("name")
                if cmd_name_node is None and child.children:
                    cmd_name_node = child.children[0]
                if cmd_name_node:
                    name = literal(cmd_name_node)
                    if name and name in defined_functions:
                        tgt = make_id(stem, name)
                        key = (func_nid, tgt)
                        if tgt and key not in seen_calls:
                            seen_calls.add(key)
                            add_edge(
                                func_nid,
                                tgt,
                                "calls",
                                child.start_point[0] + 1,
                                confidence="EXTRACTED",
                                context="call",
                            )
            walk_calls(child, func_nid, seen_calls)

    def walk(node, parent_nid: str) -> None:
        t = node.type
        if t == "function_definition":
            name = _bash_func_name(node)
            if name:
                fn_nid = make_id(stem, name)
                line = node.start_point[0] + 1
                add_node(fn_nid, f"{name}()", line, kind="bash_function")
                add_edge(parent_nid, fn_nid, "defines", line)
                defined_functions.add(name)
                body = None
                for child in node.children:
                    if child.type == "compound_statement":
                        body = child
                        break
                function_bodies.append((fn_nid, body))
                if body is not None:
                    walk(body, fn_nid)
            return

        if t == "command":
            if is_inside_expansion(node):
                return
            cmd_name_node = node.child_by_field_name("name")
            if cmd_name_node is None and node.children:
                cmd_name_node = node.children[0]
            if cmd_name_node:
                cmd = literal(cmd_name_node)
                if cmd in _BASH_SOURCE_COMMANDS and cmd not in defined_functions:
                    args = [
                        c
                        for c in node.children
                        if c.type in ("word", "string", "concatenation") and c != cmd_name_node
                    ]
                    if args:
                        raw = _read_text(args[0], source).strip().strip("'\"")
                        line = node.start_point[0] + 1
                        if raw.startswith((".", "/")):
                            resolved = (path.parent / raw).resolve()
                            if resolved.exists():
                                tgt_nid = make_id(str(resolved))
                                add_edge(file_nid, tgt_nid, "imports_from", line, context="import")
                        else:
                            tgt_nid = make_id(raw)
                            if tgt_nid:
                                add_edge(file_nid, tgt_nid, "imports", line, context="import")
            return

        if t == "declaration_command":
            if node.parent and node.parent.type == "program":
                for child in node.children:
                    if child.type == "variable_assignment":
                        var_node = child.child_by_field_name("name")
                        if var_node:
                            var = _read_text(var_node, source).strip()
                            if var:
                                var_nid = make_id(stem, var)
                                line = child.start_point[0] + 1
                                add_node(var_nid, var, line)
                                add_edge(file_nid, var_nid, "defines", line)
            return

        for child in node.children:
            walk(child, parent_nid)

    def _prescan_functions(node) -> None:
        if node.type == "function_definition":
            name = _bash_func_name(node)
            if name:
                defined_functions.add(name)
            for child in node.children:
                _prescan_functions(child)
        else:
            for child in node.children:
                _prescan_functions(child)

    _prescan_functions(root)
    walk(root, file_nid)

    top_seen: set = set()
    walk_calls(root, entry_nid, top_seen)
    for fn_nid, body in function_bodies:
        walk_calls(body, fn_nid, set())

    return {"nodes": nodes, "edges": edges}
