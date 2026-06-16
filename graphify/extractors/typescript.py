"""TypeScript extractor - delegates to _extract_generic with TS/TSX configs."""

from __future__ import annotations

from pathlib import Path

from .registry import register

_TS_EXTENSIONS = {".ts"}
_TSX_EXTENSIONS = {".tsx"}


@register(_TS_EXTENSIONS)
def extract_ts(path: Path) -> dict:
    """Extract classes, interfaces, enums, functions, arrow functions, and imports from a .ts file."""
    from ._core import _TS_CONFIG, _extract_generic

    return _extract_generic(path, _TS_CONFIG)


@register(_TSX_EXTENSIONS)
def extract_tsx(path: Path) -> dict:
    """Extract classes, interfaces, enums, functions, arrow functions, and imports from a .tsx file."""
    from ._core import _TSX_CONFIG, _extract_generic

    return _extract_generic(path, _TSX_CONFIG)
