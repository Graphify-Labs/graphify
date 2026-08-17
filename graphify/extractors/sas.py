"""SAS extractor (tree-sitter).

Extracts data steps, proc steps, and %macro definitions from a .sas file,
plus calls edges from %macro call sites to macros defined in the same file.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from graphify.extractors.base import _file_stem, _make_id, _read_text


def extract_sas(path: Path) -> dict:
    """Extract data/proc steps and macro definitions from a .sas file."""
    try:
        import tree_sitter_sas as tssas
        from tree_sitter import Language, Parser
    except ImportError as e:
        import importlib.util
        # Distinguish a genuinely-absent grammar from an installed-but-broken
        # one (e.g. a C extension built for a different Python ABI, #2602) so
        # the #1745 warning does not send the user to a no-op install.
        if importlib.util.find_spec("tree_sitter_sas") is None:
            return {"nodes": [], "edges": [],
                    "error": "tree_sitter_sas not installed"}
        return {"nodes": [], "edges": [],
                "error": f"tree_sitter_sas is installed but failed to load: {e}"}

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
    seen_edges: set[tuple[str, str, str]] = set()
    macro_defs: dict[str, str] = {}

    def add_node(nid: str, label: str, line: int) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({"id": nid, "label": label, "file_type": "code",
                          "source_file": str_path, "source_location": f"L{line}"})

    def add_edge(src: str, tgt: str, relation: str, line: int,
                 context: str | None = None) -> None:
        key = (src, tgt, relation)
        if key in seen_edges:
            return
        seen_edges.add(key)
        edge = {"source": src, "target": tgt, "relation": relation,
                "confidence": "EXTRACTED", "source_file": str_path,
                "source_location": f"L{line}", "weight": 1.0}
        if context:
            edge["context"] = context
        edges.append(edge)

    file_nid = _make_id(str(path))
    add_node(file_nid, path.name, 1)

    def _child_text(node: Any, child_types: tuple[str, ...]) -> str | None:
        for child in node.children:
            if child.type in child_types:
                return _read_text(child, source).strip()
        return None

    def _macro_name_text(node: Any) -> str | None:
        return _child_text(node, ("macro_name",))

    # First pass: collect macro definitions (case-insensitively, per SAS) so
    # call sites resolve regardless of where the definition appears.
    for node in root.children:
        if node.type == "macro_definition":
            name = _macro_name_text(node)
            if name:
                macro_defs[name.casefold()] = _make_id(stem, name)

    def _step_label(node: Any) -> str | None:
        text = _child_text(node, ("data_step_header", "proc_step_header"))
        # strip the trailing `;` so the label reads `data work.customers`
        return text.rstrip(";").strip() if text else None

    def _emit_macro_calls(node: Any) -> None:
        """Emit calls edges for macro call statements anywhere in the subtree."""
        stack = [node]
        while stack:
            current = stack.pop()
            if current.type == "macro_call_statement":
                name = _macro_name_text(current)
                if name:
                    nid = macro_defs.get(name.casefold())
                    if nid:
                        add_edge(file_nid, nid, "calls",
                                 current.start_point.row + 1, context="call")
            stack.extend(current.children)

    for node in root.children:
        if node.type == "macro_definition":
            name = _macro_name_text(node)
            if not name:
                continue
            nid = macro_defs[name.casefold()]
            add_node(nid, f"%{name}", node.start_point.row + 1)
            add_edge(file_nid, nid, "defines", node.start_point.row + 1, context="macro")
            _emit_macro_calls(node)
        elif node.type == "data_step":
            label = _step_label(node) or "data"
            # disambiguate by byte offset so multiple steps (even on one line)
            # stay distinct
            nid = _make_id(stem, "data", str(node.start_byte))
            add_node(nid, label, node.start_point.row + 1)
            add_edge(file_nid, nid, "defines", node.start_point.row + 1, context="data_step")
            _emit_macro_calls(node)
        elif node.type == "proc_step":
            label = _step_label(node) or "proc"
            nid = _make_id(stem, "proc", str(node.start_byte))
            add_node(nid, label, node.start_point.row + 1)
            add_edge(file_nid, nid, "defines", node.start_point.row + 1, context="proc_step")
            _emit_macro_calls(node)
        else:
            _emit_macro_calls(node)

    return {"nodes": nodes, "edges": edges}
