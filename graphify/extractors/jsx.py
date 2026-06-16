"""JSX extractor - delegates to _extract_generic with JS config."""

from __future__ import annotations

from pathlib import Path

from .registry import register

_EXTENSIONS = {".jsx"}


@register(_EXTENSIONS)
def extract_jsx(path: Path) -> dict:
    """Extract classes, functions, arrow functions, and imports from a .jsx file."""
    from ._core import _JS_CONFIG, _extract_generic

    return _extract_generic(path, _JS_CONFIG)
