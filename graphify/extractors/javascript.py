"""JavaScript extractor - delegates to _extract_generic with JS config."""

from __future__ import annotations

from pathlib import Path

from .registry import register

_EXTENSIONS = {".js", ".mjs"}


@register(_EXTENSIONS)
def extract_js(path: Path) -> dict:
    """Extract classes, functions, arrow functions, and imports from a .js file."""
    from ._core import _JS_CONFIG, _extract_generic

    return _extract_generic(path, _JS_CONFIG)
