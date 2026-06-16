"""Scala AST extractor."""

from __future__ import annotations

from pathlib import Path

from .registry import register
from ._utils import make_id, file_stem

_EXTENSIONS = {".scala"}


def _read_text(node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _scala_collect_type_refs(
    node, source: bytes, generic: bool, out: list[tuple[str, str]]
) -> None:
    """Walk a Scala type expression; append (name, role) tuples.
    Handles type_identifier, generic_type (List[T]), and common type wrappers."""
    if node is None:
        return
    t = node.type
    if t == "type_identifier":
        text = _read_text(node, source)
        if text:
            out.append((text, "generic_arg" if generic else "type"))
        return
    if t == "generic_type":
        base = node.child_by_field_name("type")
        if base is None:
            for c in node.children:
                if c.type == "type_identifier":
                    base = c
                    break
        if base is not None and base.type == "type_identifier":
            text = _read_text(base, source)
            if text:
                out.append((text, "generic_arg" if generic else "type"))
        for c in node.children:
            if c.type == "type_arguments":
                for arg in c.children:
                    if arg.is_named:
                        _scala_collect_type_refs(arg, source, True, out)
        return
    if t in (
        "compound_type",
        "infix_type",
        "function_type",
        "tuple_type",
        "annotated_type",
        "projected_type",
    ):
        for c in node.children:
            if c.is_named:
                _scala_collect_type_refs(c, source, generic, out)


def _import_scala(
    node, source: bytes, file_nid: str, stem: str, edges: list, str_path: str
) -> None:
    for child in node.children:
        if child.type in ("stable_id", "identifier"):
            raw = _read_text(child, source)
            module_name = raw.split(".")[-1].strip("{} ")
            if module_name and module_name != "_":
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
            break


@register(_EXTENSIONS)
def extract_scala(path: Path) -> dict:
    """Extract classes, objects, functions, and imports from a .scala file."""
    try:
        import tree_sitter_scala as tsscala
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree-sitter-scala not installed"}

    try:
        language = Language(tsscala.language())
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

        if t == "class_definition":
            name_node = node.child_by_field_name("name")
            if name_node:
                class_name = _read_text(name_node, source)
                line = node.start_point[0] + 1
                class_nid = make_id(stem, class_name)
                add_node(class_nid, class_name, line)
                add_edge(file_nid, class_nid, "contains", line)

                for c in node.children:
                    if c.type == "template_body":
                        for member in c.children:
                            walk(member)
            return

        if t == "object_definition":
            name_node = node.child_by_field_name("name")
            if name_node:
                obj_name = _read_text(name_node, source)
                line = node.start_point[0] + 1
                obj_nid = make_id(stem, obj_name)
                add_node(obj_nid, obj_name, line)
                add_edge(file_nid, obj_nid, "contains", line)
            return

        if t == "function_definition":
            name_node = node.child_by_field_name("name")
            if name_node:
                func_name = _read_text(name_node, source)
                line = node.start_point[0] + 1
                func_nid = make_id(stem, func_name)
                add_node(func_nid, f"{func_name}()", line)
                add_edge(file_nid, func_nid, "contains", line)
            return

        if t == "import_declaration":
            _import_scala(node, source, file_nid, stem, edges, str_path)
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
