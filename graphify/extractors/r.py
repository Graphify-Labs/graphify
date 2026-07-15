"""R extractor.

R's named functions are assignments whose left- or right-hand side is an
anonymous ``function_definition`` (``name <- function(...) ...`` and the
right-assignment forms ``function(...) -> name``), so a bespoke extractor is
required rather than the generic one. The contract mirrors the other
extractors: file/function nodes, ``contains``/``calls``/``imports`` edges and
``raw_calls`` for the shared cross-file bare-call resolver.

Package metadata (DESCRIPTION/NAMESPACE/exports) is intentionally out of scope
for this initial integration; package-qualified ``pkg::fn`` calls are recorded
as member raw facts only.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from graphify.extractors.base import _LANGUAGE_BUILTIN_GLOBALS, _file_stem, _make_id


_ASSIGN_OPS_LEFT = frozenset({"<-", "<<-", "="})
_ASSIGN_OPS_RIGHT = frozenset({"->", "->>"})
_PKG_LOADERS = frozenset({"library", "require", "requireNamespace"})


def extract_r(path: Path) -> dict:
    """Extract functions, calls, imports, and static source() from a .r/.R file."""
    try:
        from tree_sitter_language_pack import get_language
        from tree_sitter import Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree-sitter-language-pack not installed"}

    try:
        language = get_language("r")
        parser = Parser(language)
        source = path.read_bytes()
        tree = parser.parse(source)
        root = tree.root_node
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    stem = _file_stem(path)
    str_path = str(path)
    del stem  # current contract builds function ids from scope nids, not the file stem

    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()
    function_bodies: list[tuple[str, Any]] = []
    pkg_imports_seen: set[tuple[str, str]] = set()

    def _text(node) -> str:
        return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

    def add_node(nid: str, label: str, line: int) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({"id": nid, "label": label, "file_type": "code",
                          "source_file": str_path, "source_location": f"L{line}"})

    def add_edge(src: str, tgt: str, relation: str, line: int,
                 confidence: str = "EXTRACTED", weight: float = 1.0,
                 context: str | None = None) -> None:
        if not src or not tgt or src == tgt:
            return
        edge = {"source": src, "target": tgt, "relation": relation,
                "confidence": confidence, "source_file": str_path,
                "source_location": f"L{line}", "weight": weight}
        if context:
            edge["context"] = context
        edges.append(edge)

    file_nid = _make_id(str(path))
    add_node(file_nid, path.name, 1)

    def _op_of(binop) -> str:
        for child in binop.children:
            if child.type in _ASSIGN_OPS_LEFT or child.type in _ASSIGN_OPS_RIGHT:
                return child.type
        return ""

    def _parent_type(node) -> str:
        parent = node.parent
        return parent.type if parent is not None else ""

    def _named_children(node):
        return [c for c in node.children if c.is_named]

    def _function_body(fn_def):
        for c in _named_children(fn_def):
            if c.type != "parameters":
                return c
        return None

    def walk(node, scope_nid: str) -> None:
        if node.type == "binary_operator":
            op = _op_of(node)
            named = _named_children(node)
            if op in _ASSIGN_OPS_LEFT and len(named) >= 2:
                lhs, rhs = named[0], named[1]
                in_call_arg = _parent_type(node) == "argument"
                if (not in_call_arg and lhs.type == "identifier"
                        and rhs.type == "function_definition"):
                    name = _text(lhs)
                    line = node.start_point[0] + 1
                    func_nid = _make_id(scope_nid, name)
                    add_node(func_nid, f"{name}()", line)
                    add_edge(scope_nid, func_nid, "contains", line)
                    body = _function_body(rhs)
                    if body is not None:
                        function_bodies.append((func_nid, body))
                    walk(rhs, func_nid)
                    return
            elif op in _ASSIGN_OPS_RIGHT and len(named) >= 2:
                lhs, rhs = named[0], named[1]
                if rhs.type == "identifier" and lhs.type == "function_definition":
                    name = _text(rhs)
                    line = node.start_point[0] + 1
                    func_nid = _make_id(scope_nid, name)
                    add_node(func_nid, f"{name}()", line)
                    add_edge(scope_nid, func_nid, "contains", line)
                    body = _function_body(lhs)
                    if body is not None:
                        function_bodies.append((func_nid, body))
                    walk(lhs, func_nid)
                    return
            for c in node.children:
                walk(c, scope_nid)
            return

        if node.type == "function_definition":
            parent_op = _op_of(node.parent) if node.parent is not None and node.parent.type == "binary_operator" else ""
            if parent_op in _ASSIGN_OPS_LEFT or parent_op in _ASSIGN_OPS_RIGHT:
                for c in node.children:
                    walk(c, scope_nid)
                return
            body = None
            for c in _named_children(node):
                if c.type not in ("parameters",):
                    body = c
                    break
            if (body is not None and body.type == "binary_operator"
                    and _op_of(body) in _ASSIGN_OPS_RIGHT
                    and _named_children(body)[-1].type == "identifier"):
                body_named = _named_children(body)
                rhs = body_named[-1]
                name = _text(rhs)
                line = node.start_point[0] + 1
                func_nid = _make_id(scope_nid, name)
                add_node(func_nid, f"{name}()", line)
                add_edge(scope_nid, func_nid, "contains", line)
                fbody = _function_body(node)
                if fbody is not None:
                    function_bodies.append((func_nid, fbody))
                if len(body_named) >= 2:
                    walk(body_named[0], func_nid)
                return
            for c in node.children:
                walk(c, scope_nid)
            return

        for c in node.children:
            walk(c, scope_nid)

    walk(root, file_nid)

    label_to_nid: dict[str, str] = {}
    for n in nodes:
        normalised = n["label"].strip("()").lstrip(".")
        label_to_nid[normalised] = n["id"]

    seen_call_pairs: set[tuple[str, str]] = set()
    raw_calls: list[dict] = []

    def _first_string(node) -> str | None:
        for c in node.children:
            if c.type == "string":
                inner = c.children[1] if len(c.children) > 1 else c
                return _text(inner)
            if c.type == "argument":
                return _first_string(c)
        return None

    def _first_identifier(node) -> str | None:
        for c in node.children:
            if c.type == "identifier":
                return _text(c)
            if c.type == "argument":
                return _first_identifier(c)
        return None

    def _emit_pkg_import(scope_nid: str, pkg: str, line: int) -> None:
        key = (scope_nid, pkg)
        if pkg and key not in pkg_imports_seen:
            pkg_imports_seen.add(key)
            add_edge(scope_nid, _make_id(pkg), "imports", line, context="import")

    def walk_calls(node, caller_nid: str) -> None:
        if node.type == "function_definition":
            return
        if node.type != "call":
            for c in node.children:
                walk_calls(c, caller_nid)
            return

        line = node.start_point[0] + 1
        fn_node = None
        arguments_node = None
        for c in node.children:
            if c.type in ("identifier", "namespace_operator", "extract_operator"):
                fn_node = c
            elif c.type == "arguments":
                arguments_node = c

        if fn_node is not None and fn_node.type == "identifier":
            callee = _text(fn_node)
            if callee in _PKG_LOADERS:
                if arguments_node is not None:
                    pkg = _first_identifier(arguments_node) or _first_string(arguments_node)
                    if pkg:
                        _emit_pkg_import(caller_nid, pkg, line)
                for c in node.children:
                    walk_calls(c, caller_nid)
                return
            if callee == "source":
                if arguments_node is not None:
                    raw = _first_string(arguments_node)
                    if raw and raw.lower().endswith(".r"):
                        if not raw.startswith(("http://", "https://", "ftp://")):
                            resolved = (path.parent / raw).resolve()
                            if resolved.exists():
                                add_edge(file_nid, _make_id(str(resolved)), "imports_from", line, context="import")
                for c in node.children:
                    walk_calls(c, caller_nid)
                return
            is_member_call = False
        elif fn_node is not None and fn_node.type == "namespace_operator":
            named = _named_children(fn_node)
            pkg = _text(named[0]) if named else ""
            callee = _text(named[-1]) if named else ""
            is_member_call = True
            if pkg:
                _emit_pkg_import(caller_nid, pkg, line)
        elif fn_node is not None and fn_node.type == "extract_operator":
            named = _named_children(fn_node)
            callee = _text(named[-1]) if named else ""
            is_member_call = True
        else:
            callee = ""
            is_member_call = False

        if callee and callee not in _LANGUAGE_BUILTIN_GLOBALS:
            tgt_nid = label_to_nid.get(callee)
            if tgt_nid and tgt_nid != caller_nid:
                pair = (caller_nid, tgt_nid)
                if pair not in seen_call_pairs:
                    seen_call_pairs.add(pair)
                    add_edge(caller_nid, tgt_nid, "calls", line,
                             confidence="EXTRACTED", weight=1.0, context="call")
            else:
                raw_calls.append({
                    "caller_nid": caller_nid,
                    "callee": callee,
                    "is_member_call": is_member_call,
                    "source_file": str_path,
                    "source_location": f"L{line}",
                })

        for c in node.children:
            walk_calls(c, caller_nid)

    walk_calls(root, file_nid)
    for caller_nid, body in function_bodies:
        walk_calls(body, caller_nid)

    clean_edges = [e for e in edges if e["source"] in seen_ids and
                   (e["target"] in seen_ids or e["relation"] in ("imports", "imports_from"))]
    return {"nodes": nodes, "edges": clean_edges, "raw_calls": raw_calls,
            "input_tokens": 0, "output_tokens": 0}