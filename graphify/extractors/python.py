"""Python AST extractor using tree-sitter-python."""
from __future__ import annotations
from pathlib import Path
from .registry import register
from .generic import LanguageConfig, extract_generic

_EXTENSIONS = {".py", ".pyw", ".pyi"}

PYTHON_CONFIG = LanguageConfig(
    ts_module="tree_sitter_python",
    ts_language_fn="language_python",
    class_types=frozenset({"class_definition"}),
    function_types=frozenset({"function_definition"}),
    import_types=frozenset({"import_statement", "import_from_statement"}),
    call_types=frozenset({"call"}),
    name_field="name",
    body_field="body",
    function_label_parens=True,
)


@register(_EXTENSIONS)
def extract_python(path: Path) -> dict:
    """Extract classes, functions, imports, and calls from a Python file."""
    return extract_generic(path, PYTHON_CONFIG)
