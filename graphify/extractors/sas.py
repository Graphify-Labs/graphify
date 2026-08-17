"""SAS extractor (tree-sitter).

Extracts data steps, proc steps, and %macro definitions from a .sas file,
plus calls edges from %macro call sites to macros defined in the same file.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from graphify.extractors.base import _file_stem, _make_id


def extract_sas(path: Path) -> dict:
    """Extract data/proc steps and macro definitions from a .sas file."""
    try:
        import tree_sitter_sas as tssas
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree_sitter_sas not installed"}

    try:
        language = Language(tssas.language())
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
    macro_defs: dict[str, str] = {}

    def add_node(nid: str, label: str, line: int) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({"id": nid, "label": label, "file_type": "code",
                          "source_file": str_path, "source_location": f"L{line}"})

    def add_edge(src: str, tgt: str, relation: str, line: int,
                 confidence: str = "EXTRACTED", weight: float = 1.0,
                 context: str | None = None) -> None:
        edge = {"source": src, "target": tgt, "relation": relation,
                "confidence": confidence, "source_file": str_path,
                "source_location": f"L{line}", "weight": weight}
        if context:
            edge["context"] = context
        edges.append(edge)

    file_nid = _make_id(str(path))
    add_node(file_nid, path.name, 1)

    def _macro_name_text(node: Any) -> str | None:
        for child in node.children:
            if child.type == "macro_name":
                return child.text.decode("utf-8", errors="replace").strip()
        return None

    # First pass: collect macro definitions so call sites can resolve.
    for node in root.children:
        if node.type == "macro_definition":
            name = _macro_name_text(node)
            if name:
                macro_defs[name] = _make_id(stem, name)

    def _step_label(node: Any) -> str | None:
        for child in node.children:
            if child.type in ("data_step_header", "proc_step_header"):
                text = child.text.decode("utf-8", errors="replace").strip()
                # strip the trailing `;` so the label reads `data work.customers`
                return text.rstrip(";").strip() if text else None
        return None

    for node in root.children:
        if node.type == "macro_definition":
            name = _macro_name_text(node)
            if not name:
                continue
            nid = macro_defs[name]
            add_node(nid, f"%{name}", node.start_point.row + 1)
            add_edge(file_nid, nid, "defines", node.start_point.row + 1, context="macro")
        elif node.type == "data_step":
            label = _step_label(node) or "data"
            nid = _make_id(stem, "data")
            add_node(nid, label, node.start_point.row + 1)
            add_edge(file_nid, nid, "defines", node.start_point.row + 1, context="data_step")
        elif node.type == "proc_step":
            label = _step_label(node) or "proc"
            nid = _make_id(stem, "proc")
            add_node(nid, label, node.start_point.row + 1)
            add_edge(file_nid, nid, "defines", node.start_point.row + 1, context="proc_step")

    # Macro call sites: emit calls edges to macros defined in this file.
    for node in root.children:
        if node.type == "macro_call_statement":
            name = _macro_name_text(node)
            if name and name in macro_defs:
                add_edge(file_nid, macro_defs[name], "calls",
                         node.start_point.row + 1, context="call")

    return {"nodes": nodes, "edges": edges, "raw_calls": []}
