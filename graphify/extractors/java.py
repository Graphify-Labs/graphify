"""Java extractor - delegates to _extract_generic with Java config."""

from __future__ import annotations

from pathlib import Path

from .registry import register

_EXTENSIONS = {".java"}


@register(_EXTENSIONS)
def extract_java(path: Path) -> dict:
    """Extract classes, interfaces, methods, constructors, and imports from a .java file."""
    from ._core import _JAVA_CONFIG, _extract_generic

    return _extract_generic(path, _JAVA_CONFIG)
