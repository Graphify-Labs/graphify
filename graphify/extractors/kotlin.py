"""Kotlin AST extractor."""

from __future__ import annotations

from pathlib import Path

from .registry import register
from ._utils import make_id, file_stem

_EXTENSIONS = {".kt", ".kts"}


def _read_text(node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _kotlin_user_type_name(user_type_node, source: bytes) -> str | None:
    """Return the head identifier text from a Kotlin user_type node (without generics)."""
    if user_type_node is None:
        return None
    for c in user_type_node.children:
        if c.type == "type_identifier":
            text = _read_text(c, source)
            return text or None
        if c.type == "identifier":
            text = _read_text(c, source)
            return text or None
        if c.type == "simple_user_type":
            for sub in c.children:
                if sub.type in ("identifier", "type_identifier"):
                    text = _read_text(sub, source)
                    return text or None
    return None


def _kotlin_collect_type_refs(
    node, source: bytes, generic: bool, out: list[tuple[str, str]]
) -> None:
    """Walk a Kotlin type expression; append (name, role) tuples."""
    if node is None:
        return
    t = node.type
    if t in ("integral_literal", "boolean_literal"):
        return
    if t == "user_type":
        for c in node.children:
            if c.type in ("identifier", "type_identifier"):
                text = _read_text(c, source)
                if text:
                    out.append((text, "generic_arg" if generic else "type"))
                break
            if c.type == "simple_user_type":
                for sub in c.children:
                    if sub.type in ("identifier", "type_identifier"):
                        text = _read_text(sub, source)
                        if text:
                            out.append((text, "generic_arg" if generic else "type"))
                        break
                break
        for c in node.children:
            if c.type == "type_arguments":
                for arg in c.children:
                    if arg.type == "type_projection":
                        for sub in arg.children:
                            if sub.is_named:
                                _kotlin_collect_type_refs(sub, source, True, out)
                    elif arg.is_named:
                        _kotlin_collect_type_refs(arg, source, True, out)
        return
    if t in ("identifier", "type_identifier"):
        text = _read_text(node, source)
        if text:
            out.append((text, "generic_arg" if generic else "type"))
        return
    if t in ("nullable_type", "parenthesized_type", "type_reference"):
        for c in node.children:
            if c.is_named:
                _kotlin_collect_type_refs(c, source, generic, out)
        return
    if node.is_named:
        for c in node.children:
            if c.is_named:
                _kotlin_collect_type_refs(c, source, generic, out)


def _kotlin_property_type_node(property_node):
    """Find the user_type node within a Kotlin property_declaration."""
    for c in property_node.children:
        if c.type == "variable_declaration":
            for sub in c.children:
                if sub.type in ("user_type", "nullable_type", "type_reference"):
                    return sub
        if c.type in ("user_type", "nullable_type", "type_reference"):
            return c
    return None


def _kotlin_function_return_type_node(func_node):
    """Find the return-type node of a Kotlin function_declaration (the type after `: ` post-params)."""
    saw_params = False
    saw_colon = False
    for c in func_node.children:
        if c.type == "function_value_parameters":
            saw_params = True
            continue
        if saw_params and c.type == ":":
            saw_colon = True
            continue
        if saw_colon:
            if c.is_named:
                return c
    return None


def _import_kotlin(
    node, source: bytes, file_nid: str, stem: str, edges: list, str_path: str
) -> None:
    path_node = node.child_by_field_name("path")
    if path_node:
        raw = _read_text(path_node, source)
        module_name = raw.split(".")[-1].strip()
        if module_name:
            tgt_nid = make_id(module_name)
            edges.append(
                {
                    "source": file_nid,
                    "target": tgt_nid,
                    "relation": "imports",
                    "context": "import",
                    "confidence": "EXTRACTED",
                    "source_file": str_path,
                    "source_location": f"L{node.start_point[0] + 1}",
                    "weight": 1.0,
                }
            )
        return
    for child in node.children:
        if child.type == "identifier":
            raw = _read_text(child, source)
            tgt_nid = make_id(raw)
            edges.append(
                {
                    "source": file_nid,
                    "target": tgt_nid,
                    "relation": "imports",
                    "context": "import",
                    "confidence": "EXTRACTED",
                    "source_file": str_path,
                    "source_location": f"L{node.start_point[0] + 1}",
                    "weight": 1.0,
                }
            )
            break


@register(_EXTENSIONS)
def extract_kotlin(path: Path) -> dict:
    """Extract classes, objects, functions, and imports from a .kt/.kts file."""
    try:
        import tree_sitter_kotlin as tskotlin
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree-sitter-kotlin not installed"}

    try:
        language = Language(tskotlin.language())
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

    def walk(node) -> None:
        t = node.type

        if t == "class_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                class_name = _read_text(name_node, source)
                line = node.start_point[0] + 1
                class_nid = make_id(stem, class_name)
                add_node(class_nid, class_name, line)
                add_edge(file_nid, class_nid, "contains", line)

                for c in node.children:
                    if c.type == "primary_constructor":
                        for param in c.children:
                            if param.type == "parameter":
                                param_name_node = param.child_by_field_name("name")
                                if param_name_node:
                                    param_name = _read_text(param_name_node, source)
                                    param_nid = make_id(class_nid, param_name)
                                    add_node(param_nid, param_name, line)
                                    add_edge(class_nid, param_nid, "contains", line)
                    elif c.type == "class_body":
                        for member in c.children:
                            walk(member)
            return

        if t == "object_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                obj_name = _read_text(name_node, source)
                line = node.start_point[0] + 1
                obj_nid = make_id(stem, obj_name)
                add_node(obj_nid, obj_name, line)
                add_edge(file_nid, obj_nid, "contains", line)
            return

        if t == "function_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                func_name = _read_text(name_node, source)
                line = node.start_point[0] + 1
                func_nid = make_id(stem, func_name)
                add_node(func_nid, f"{func_name}()", line)
                add_edge(file_nid, func_nid, "contains", line)
            return

        if t == "import_header":
            _import_kotlin(node, source, file_nid, stem, edges, str_path)
            return

        for child in node.children:
            walk(child)

    walk(root)

    clean_edges = [
        e
        for e in edges
        if e["source"] in seen_ids
        and (e["target"] in seen_ids or e["relation"] in ("imports", "imports_from"))
    ]
    return {"nodes": nodes, "edges": clean_edges}
