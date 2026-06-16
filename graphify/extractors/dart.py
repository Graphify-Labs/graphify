"""Dart AST extractor."""
from __future__ import annotations
from pathlib import Path
from .registry import register

_EXTENSIONS = {".dart"}

@register(_EXTENSIONS)
def extract_dart(path: Path) -> dict:
    """Extract classes, functions, imports, and calls from a .dart file."""
    from ..extract import _extract_generic, _DART_CONFIG
    return _extract_generic(path, _DART_CONFIG)
