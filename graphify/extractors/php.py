"""PHP AST extractor."""
from __future__ import annotations
from pathlib import Path
from .registry import register

_EXTENSIONS = {".php"}

@register(_EXTENSIONS)
def extract_php(path: Path) -> dict:
    """Extract classes, functions, methods, namespace uses, and calls from a .php file."""
    from ..extract import _extract_generic, _PHP_CONFIG
    return _extract_generic(path, _PHP_CONFIG)
