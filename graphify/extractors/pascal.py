"""Pascal/Delphi extractor - delegates to extract.py implementation."""

from __future__ import annotations

from pathlib import Path

from .registry import register

_EXTENSIONS = {".pas", ".pp", ".dpr", ".dpk", ".lpr", ".inc"}


@register(_EXTENSIONS)
def extract_pascal(path: Path) -> dict:
    """Extract units, classes, procedures, uses-imports, and calls from Pascal/Delphi files."""
    from graphify.extract import extract_pascal as _extract_pascal

    return _extract_pascal(path)
