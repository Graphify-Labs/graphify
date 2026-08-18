"""Kotlin extractor. Moved verbatim from graphify/extract.py."""
from __future__ import annotations

from pathlib import Path

from graphify.extractors.models import LanguageConfig
from graphify.extractors.engine import _extract_generic
from graphify.extractors.base import _make_id, _read_text
from graphify.security import sanitize_metadata


def _import_kotlin(node, source: bytes, file_nid: str, stem: str, edges: list, str_path: str, scope_stack: list[str] | None = None) -> None:
    # Grammar 1.1.0 (PyPI tree_sitter_kotlin) emits an `import` node whose
    # children are the `import` keyword and a `qualified_identifier` (the dotted
    # path), optionally followed by `.` `*` (wildcard) or `as` + `identifier`
    # (alias). There is no `path` field. Older forks emit `import_header` with a
    # `path` field or a bare `identifier` child; keep those branches so the
    # extractor works across grammar generations (#2526, adapted from PR #2531
    # by @Mustaqeem66).
    path_node = node.child_by_field_name("path")
    if path_node is None:
        path_node = next(
            (c for c in node.children if c.type == "qualified_identifier"), None
        )
    if path_node is not None:
        raw = _read_text(path_node, source).strip()
    else:
        raw = next(
            (_read_text(c, source).strip() for c in node.children
             if c.type == "identifier"),
            "",
        )
    if not raw:
        return
    # Wildcard (`import a.b.*`): imports a whole package, not a symbol. The last
    # path segment is a PACKAGE name, so a symbol-level edge would dangle on (or
    # collide with) an unrelated node that happens to share the package's name.
    if raw.endswith(".*") or raw == "*" or any(c.type == "*" for c in node.children):
        return
    # Alias (`import a.b.C as D`): the alias is the identifier child after `as`.
    alias = None
    saw_as = False
    for child in node.children:
        if not saw_as:
            saw_as = child.type == "as"
        elif child.type in ("identifier", "simple_identifier"):
            alias = _read_text(child, source).strip() or None
            break
    module_name = raw.split(".")[-1].strip()
    if not module_name:
        return
    # Target is the bare last segment for now; _resolve_kotlin_import_targets
    # rewrites it to the real node id via the target_fqn stamped here, once the
    # per-file package index exists. Unresolved targets stay dangling like other
    # languages' external imports.
    edges.append({
        "source": file_nid,
        "target": _make_id(module_name),
        "relation": "imports",
        "context": "import",
        "confidence": "EXTRACTED",
        "source_file": str_path,
        "source_location": f"L{node.start_point[0] + 1}",
        "weight": 1.0,
        "metadata": sanitize_metadata({k: v for k, v in
            {"target_fqn": raw, "alias": alias}.items() if v is not None}),
    })


_KOTLIN_CONFIG = LanguageConfig(
    ts_module="tree_sitter_kotlin",
    class_types=frozenset({"class_declaration", "object_declaration"}),
    function_types=frozenset({"function_declaration"}),
    # Grammar 1.1.0 (PyPI tree_sitter_kotlin) names the import node `import`;
    # older forks use `import_header`. Accept both (#2526).
    import_types=frozenset({"import_header", "import"}),
    call_types=frozenset({"call_expression"}),
    call_function_field="",
    call_accessor_node_types=frozenset({"navigation_expression"}),
    call_accessor_field="",
    # Different tree-sitter-kotlin grammar versions name plain identifier
    # nodes differently: PyPI's `tree_sitter_kotlin` uses `identifier`,
    # older forks use `simple_identifier`. Accept both so the extractor
    # works across grammar generations.
    name_fallback_child_types=("simple_identifier", "identifier"),
    body_fallback_child_types=("function_body", "class_body", "enum_class_body"),
    function_boundary_types=frozenset({"function_declaration"}),
    import_handler=_import_kotlin,
)


def extract_kotlin(path: Path) -> dict:
    """Extract classes, objects, functions, and imports from a .kt/.kts file."""
    return _extract_generic(path, _KOTLIN_CONFIG)
