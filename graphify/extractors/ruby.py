"""Ruby extractor. Moved verbatim from graphify/extract.py."""
from __future__ import annotations

from pathlib import Path

from graphify.extractors.models import LanguageConfig
from graphify.extractors.engine import _extract_generic


_RUBY_CONFIG = LanguageConfig(
    ts_module="tree_sitter_ruby",
    # `module Foo` is a container node just like `class Foo` in tree-sitter's
    # Ruby grammar (name in a `constant` child, body in `body_statement`), so it
    # gets a node and its methods attach via `method` (#1640). Without it, plain
    # utility/`module_function` modules produced no node and their methods hung
    # off the file via `contains` with dot-less labels.
    class_types=frozenset({"class", "module"}),
    function_types=frozenset({"method", "singleton_method"}),
    import_types=frozenset(),
    call_types=frozenset({"call"}),
    call_function_field="method",
    call_accessor_node_types=frozenset(),
    name_fallback_child_types=("constant", "scope_resolution", "identifier"),
    body_fallback_child_types=("body_statement",),
    function_boundary_types=frozenset({"method", "singleton_method"}),
)


def extract_ruby(path: Path) -> dict:
    """Extract classes, methods, singleton methods, and calls from a .rb file."""
    return _extract_generic(path, _RUBY_CONFIG)
