"""VHDL extractor for graphify.

Extracts entities, architectures, packages, subprograms, use-clause imports,
and component instantiation edges from .vhd/.vhdl files via tree-sitter-vhdl.

Grammar: alemuller/tree-sitter-vhdl (MIT) — covers VHDL-93 through VHDL-2008.
Requires: pip install tree-sitter-vhdl
"""
from __future__ import annotations

from pathlib import Path

from graphify.extractors.base import _file_stem, _make_id


def _first_id(node, source: bytes) -> str | None:
    """Return the text of the first identifier/library_namespace/label child."""
    if node is None:
        return None
    for c in node.children:
        if c.type in ("identifier", "library_namespace", "label"):
            return source[c.start_byte:c.end_byte].decode("utf-8", errors="replace").strip()
    return None


def extract_vhdl(path: Path) -> dict:
    """Extract VHDL design units and their relationships from a .vhd/.vhdl file."""
    try:
        import tree_sitter_vhdl as tsvhdl
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree-sitter-vhdl not installed; run: pip install tree-sitter-vhdl"}

    try:
        language = Language(tsvhdl.language())
        parser = Parser(language)
        source = path.read_bytes()
        tree = parser.parse(source)
        root = tree.root_node
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    stem = _file_stem(path)
    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()

    def add_node(nid: str, label: str, line: int) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({
                "id": nid, "label": label, "file_type": "code",
                "source_file": str_path, "source_location": f"L{line}",
                "confidence_score": 1.0,
            })

    def add_edge(src: str, tgt: str, relation: str, line: int,
                 confidence: str = "EXTRACTED", score: float = 1.0) -> None:
        edges.append({
            "source": src, "target": tgt, "relation": relation,
            "confidence": confidence, "confidence_score": score,
            "source_file": str_path, "source_location": f"L{line}",
            "weight": 1.0,
        })

    file_nid = _make_id(str(path))
    add_node(file_nid, path.name, 1)

    def walk(node, scope_nid: str | None = None) -> None:
        t = node.type

        if t == "entity_declaration":
            name = _first_id(node, source)
            if name:
                line = node.start_point[0] + 1
                nid = _make_id(stem, name)
                add_node(nid, name, line)
                add_edge(file_nid, nid, "defines", line)
                for c in node.children:
                    walk(c, nid)
                return

        elif t == "architecture_definition":
            arch_name = _first_id(node, source)
            entity_name = next(
                (_first_id(c, source) for c in node.children if c.type == "name"), None)
            if arch_name:
                line = node.start_point[0] + 1
                nid = _make_id(stem, arch_name)
                add_node(nid, arch_name, line)
                add_edge(file_nid, nid, "defines", line)
                if entity_name:
                    # Same id scheme as entity_declaration's own node (_make_id(stem, name))
                    # — architecture and entity are almost always in the same file, so this
                    # resolves to the real entity node instead of minting a disconnected one.
                    tgt = _make_id(stem, entity_name)
                    add_node(tgt, entity_name, line)
                    add_edge(nid, tgt, "implements", line, "INFERRED", 0.9)
                for c in node.children:
                    walk(c, nid)
                return

        elif t in ("package_declaration", "package_definition"):
            name = _first_id(node, source)
            if name:
                line = node.start_point[0] + 1
                nid = _make_id(stem, name)
                add_node(nid, name, line)
                add_edge(file_nid, nid, "defines", line)
                for c in node.children:
                    walk(c, nid)
                return

        elif t in ("subprogram_declaration", "subprogram_definition"):
            subprog_name = next(
                (_first_id(c, source) for c in node.children
                 if c.type in ("function_specification", "procedure_specification")),
                None)
            if subprog_name:
                line = node.start_point[0] + 1
                parent = scope_nid or file_nid
                nid = _make_id(parent, subprog_name)
                add_node(nid, f"{subprog_name}()", line)
                add_edge(parent, nid, "contains", line)

        elif t == "component_instantiation_statement" and scope_nid:
            inst_type = next(
                (_first_id(c, source) for c in node.children if c.type == "name"), None)
            if inst_type:
                line = node.start_point[0] + 1
                tgt = _make_id(inst_type)
                add_node(tgt, inst_type, line)
                add_edge(scope_nid, tgt, "instantiates", line, "INFERRED", 0.9)

        elif t == "use_clause":
            for sel_list in node.children:
                for sel_name in sel_list.children:
                    if sel_name.type == "selected_name":
                        ids = [c for c in sel_name.children
                               if c.type in ("identifier", "library_namespace")]
                        if len(ids) >= 2:
                            pkg = source[ids[1].start_byte:ids[1].end_byte].decode(
                                "utf-8", errors="replace").strip()
                            if pkg.lower() != "all":
                                line = node.start_point[0] + 1
                                tgt = _make_id(pkg)
                                add_node(tgt, pkg, line)
                                add_edge(scope_nid or file_nid, tgt, "imports_from", line)

        for c in node.children:
            walk(c, scope_nid)

    walk(root)
    return {"nodes": nodes, "edges": edges}
