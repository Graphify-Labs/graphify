"""Julia extractor - extracts modules, structs, functions, imports, and calls."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .registry import register
from ._utils import make_id, file_stem

_EXTENSIONS = {".jl"}


@register(_EXTENSIONS)
def extract_julia(path: Path) -> dict:
    """Extract modules, structs, functions, imports, and calls from a .jl file."""
    try:
        import tree_sitter_julia as tsjulia
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree-sitter-julia not installed"}

    try:
        language = Language(tsjulia.language())
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
            nodes.append(
                {
                    "id": nid,
                    "label": label,
                    "file_type": "code",
                    "source_file": str_path,
                    "source_location": f"L{line}",
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

    def _read_text(node, source: bytes) -> str:
        return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")

    def _func_name_from_signature(sig_node) -> str | None:
        for child in sig_node.children:
            if child.type == "call_expression":
                callee = child.children[0] if child.children else None
                if callee and callee.type == "identifier":
                    return _read_text(callee, source)
        return None

    def walk_calls(body_node, func_nid: str) -> None:
        if body_node is None:
            return
        t = body_node.type
        if t in ("function_definition", "short_function_definition"):
            return
        if t == "call_expression" and body_node.children:
            callee = body_node.children[0]
            if callee.type == "identifier":
                callee_name = _read_text(callee, source)
                target_nid = make_id(stem, callee_name)
                add_edge(
                    func_nid,
                    target_nid,
                    "calls",
                    body_node.start_point[0] + 1,
                    confidence="EXTRACTED",
                    context="call",
                )
            elif callee.type == "field_expression" and len(callee.children) >= 3:
                method_node = callee.children[-1]
                method_name = _read_text(method_node, source)
                target_nid = make_id(stem, method_name)
                add_edge(
                    func_nid,
                    target_nid,
                    "calls",
                    body_node.start_point[0] + 1,
                    confidence="EXTRACTED",
                    context="call",
                )
        for child in body_node.children:
            walk_calls(child, func_nid)

    def walk(node, scope_nid: str) -> None:
        t = node.type

        if t == "module_definition":
            name_node = next((c for c in node.children if c.type == "identifier"), None)
            if name_node:
                mod_name = _read_text(name_node, source)
                mod_nid = make_id(stem, mod_name)
                line = node.start_point[0] + 1
                add_node(mod_nid, mod_name, line)
                add_edge(file_nid, mod_nid, "defines", line)
                for child in node.children:
                    walk(child, mod_nid)
            return

        if t == "struct_definition":
            type_head = next((c for c in node.children if c.type == "type_head"), None)
            if not type_head:
                return
            struct_name: str | None = None
            super_name: str | None = None
            bin_expr = next((c for c in type_head.children if c.type == "binary_expression"), None)
            if bin_expr:
                identifiers = [c for c in bin_expr.children if c.type == "identifier"]
                if identifiers:
                    struct_name = _read_text(identifiers[0], source)
                    if len(identifiers) >= 2:
                        super_name = _read_text(identifiers[-1], source)
            else:
                name_node = next((c for c in type_head.children if c.type == "identifier"), None)
                if name_node:
                    struct_name = _read_text(name_node, source)
            if not struct_name:
                return
            struct_nid = make_id(stem, struct_name)
            line = node.start_point[0] + 1
            add_node(struct_nid, struct_name, line)
            add_edge(scope_nid, struct_nid, "defines", line)
            if super_name:
                add_edge(
                    struct_nid,
                    ensure_named_node(super_name, line),
                    "inherits",
                    line,
                    confidence="EXTRACTED",
                )
            for child in node.children:
                if child.type == "typed_expression":
                    type_ids = [c for c in child.children if c.type == "identifier"]
                    if len(type_ids) >= 2:
                        field_line = child.start_point[0] + 1
                        type_name = _read_text(type_ids[-1], source)
                        type_nid = ensure_named_node(type_name, field_line)
                        edges.append(
                            _semantic_reference_edge(
                                struct_nid, type_nid, "field", str_path, field_line
                            )
                        )
            return

        if t == "abstract_definition":
            type_head = next((c for c in node.children if c.type == "type_head"), None)
            if type_head:
                name_node = next((c for c in type_head.children if c.type == "identifier"), None)
                if name_node:
                    abs_name = _read_text(name_node, source)
                    abs_nid = make_id(stem, abs_name)
                    line = node.start_point[0] + 1
                    add_node(abs_nid, abs_name, line)
                    add_edge(scope_nid, abs_nid, "defines", line)
            return

        if t == "function_definition":
            sig_node = next((c for c in node.children if c.type == "signature"), None)
            if sig_node:
                func_name = _func_name_from_signature(sig_node)
                if func_name:
                    func_nid = make_id(stem, func_name)
                    line = node.start_point[0] + 1
                    add_node(func_nid, f"{func_name}()", line)
                    add_edge(scope_nid, func_nid, "defines", line)
                    function_bodies.append((func_nid, node))
            return

        if t == "assignment":
            lhs = node.children[0] if node.children else None
            if lhs and lhs.type == "call_expression" and lhs.children:
                callee = lhs.children[0]
                if callee.type == "identifier":
                    func_name = _read_text(callee, source)
                    func_nid = make_id(stem, func_name)
                    line = node.start_point[0] + 1
                    add_node(func_nid, f"{func_name}()", line)
                    add_edge(scope_nid, func_nid, "defines", line)
                    rhs = node.children[-1] if len(node.children) >= 3 else None
                    if rhs:
                        function_bodies.append((func_nid, rhs))
            return

        if t in ("using_statement", "import_statement"):
            line = node.start_point[0] + 1
            for child in node.children:
                if child.type == "identifier":
                    mod_name = _read_text(child, source)
                    imp_nid = make_id(mod_name)
                    add_node(imp_nid, mod_name, line)
                    add_edge(scope_nid, imp_nid, "imports", line, context="import")
                elif child.type == "selected_import":
                    identifiers = [c for c in child.children if c.type == "identifier"]
                    if identifiers:
                        pkg_name = _read_text(identifiers[0], source)
                        pkg_nid = make_id(pkg_name)
                        add_node(pkg_nid, pkg_name, line)
                        add_edge(scope_nid, pkg_nid, "imports", line, context="import")
            return

        for child in node.children:
            walk(child, scope_nid)

    walk(root, file_nid)

    for func_nid, body_node in function_bodies:
        if body_node.type == "function_definition":
            for child in body_node.children:
                if child.type != "signature":
                    walk_calls(child, func_nid)
        else:
            walk_calls(body_node, func_nid)

    return {"nodes": nodes, "edges": edges}


def _semantic_reference_edge(
    source: str,
    target: str,
    context: str,
    source_file: str,
    line: int | str | None,
) -> dict:
    REFERENCE_CONTEXTS = frozenset(
        {"type", "generic_arg", "return", "param", "field", "extends", "implements"}
    )
    if context not in REFERENCE_CONTEXTS:
        raise ValueError(f"unknown reference context: {context}")
    loc = f"L{line}" if line is not None else None
    return {
        "source": source,
        "target": target,
        "relation": "references",
        "context": context,
        "confidence": "EXTRACTED",
        "source_file": source_file,
        "source_location": loc,
        "weight": 1.0,
    }
