"""Generic tree-sitter extractor with configurable language support."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Any

from ._utils import make_id, file_stem, safe_extract

_RECURSION_LIMIT = 10_000


def _raise_recursion_limit() -> None:
    if sys.getrecursionlimit() < _RECURSION_LIMIT:
        sys.setrecursionlimit(_RECURSION_LIMIT)


def _read_text(node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


@dataclass
class LanguageConfig:
    """Configuration for generic tree-sitter based extraction."""
    ts_module: str
    ts_language_fn: str = "language"
    
    class_types: frozenset = frozenset()
    function_types: frozenset = frozenset()
    import_types: frozenset = frozenset()
    call_types: frozenset = frozenset()
    static_prop_types: frozenset = frozenset()
    helper_fn_names: frozenset = frozenset()
    container_bind_methods: frozenset = frozenset()
    event_listener_properties: frozenset = frozenset()
    
    name_field: str = "name"
    name_fallback_child_types: tuple = ()
    
    body_field: str = "body"
    body_fallback_child_types: tuple = ()
    
    call_function_field: str = "function"
    call_accessor_node_types: frozenset = frozenset()
    call_accessor_field: str = "attribute"
    
    function_boundary_types: frozenset = frozenset()
    
    import_handler: Callable | None = None
    resolve_function_name_fn: Callable | None = None
    function_label_parens: bool = True
    extra_walk_fn: Callable | None = None


def extract_generic(path: Path, config: LanguageConfig) -> dict:
    """Extract nodes and edges from a source file using tree-sitter.
    
    This is a generic extractor that works with any tree-sitter grammar
    given a LanguageConfig.
    """
    _raise_recursion_limit()
    
    try:
        mod = __import__(config.ts_module, fromlist=[config.ts_language_fn])
        lang_fn = getattr(mod, config.ts_language_fn, None)
        if lang_fn is None:
            return {"nodes": [], "edges": [], "error": f"No {config.ts_language_fn} in {config.ts_module}"}
        
        from tree_sitter import Language, Parser
        language = Language(lang_fn())
        parser = Parser(language)
        
        source = path.read_bytes()
        tree = parser.parse(source)
        root = tree.root_node
    except Exception as e:
        if os.environ.get("GRAPHIFY_DEBUG"):
            import traceback
            traceback.print_exc(file=sys.stderr)
        return {"nodes": [], "edges": [], "error": str(e)}
    
    stem = file_stem(path)
    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()
    
    def add_node(nid: str, label: str, line: int, **extra) -> None:
        if nid and nid not in seen_ids:
            seen_ids.add(nid)
            n = {"id": nid, "label": label, "file_type": "code",
                 "source_file": str_path, "source_location": f"L{line}"}
            n.update(extra)
            nodes.append(n)
    
    def add_edge(src: str, tgt: str, relation: str, line: int,
                 confidence: str = "EXTRACTED", weight: float = 1.0,
                 context: str | None = None) -> None:
        if not src or not tgt or src == tgt:
            return
        e = {"source": src, "target": tgt, "relation": relation,
             "confidence": confidence, "source_file": str_path,
             "source_location": f"L{line}", "weight": weight}
        if context:
            e["context"] = context
        edges.append(e)
    
    file_nid = make_id(str(path))
    add_node(file_nid, path.name, 1)
    
    # TODO: Implement full walk logic from original _extract_generic
    # This is a simplified version - the full version needs all the walk_* functions
    
    return {"nodes": nodes, "edges": edges}
