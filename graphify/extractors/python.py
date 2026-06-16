"""Python extractor - delegates to _extract_generic with Python config."""

from __future__ import annotations

from pathlib import Path

from .registry import register

_EXTENSIONS = {".py"}


@register(_EXTENSIONS)
def extract_python(path: Path) -> dict:
    """Extract classes, functions, and imports from a .py file via tree-sitter AST."""
    from graphify.extract import _PYTHON_CONFIG, _extract_generic, _extract_python_rationale

    result = _extract_generic(path, _PYTHON_CONFIG)
    if "error" not in result:
        _extract_python_rationale(path, result)
    return result
