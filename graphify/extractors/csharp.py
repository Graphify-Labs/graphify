"""C# extractor - delegates to _extract_generic with C# config."""

from __future__ import annotations

from pathlib import Path

from .registry import register

_EXTENSIONS = {".cs"}


@register(_EXTENSIONS)
def extract_csharp(path: Path) -> dict:
    """Extract classes, interfaces, methods, namespaces, and usings from a .cs file."""
    from graphify.extract import _CSHARP_CONFIG, _extract_generic

    return _extract_generic(path, _CSHARP_CONFIG)
