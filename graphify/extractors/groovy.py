"""Groovy extractor - delegates to _extract_generic with Groovy config."""

from __future__ import annotations

from pathlib import Path

from .registry import register

_EXTENSIONS = {".groovy", ".gradle"}


@register(_EXTENSIONS)
def extract_groovy(path: Path) -> dict:
    """Extract classes, methods, constructors, and imports from a .groovy/.gradle file.

    Falls back to a regex-based Spock extractor when tree-sitter-groovy cannot parse
    ``def "feature name"()`` methods (common in Spock specification classes).
    """
    from ._core import (
        _GROOVY_CONFIG,
        _extract_generic,
        _is_spock_file,
        _extract_spock_fallback,
    )

    result = _extract_generic(path, _GROOVY_CONFIG)
    if _is_spock_file(path, result):
        result = _extract_spock_fallback(path, result)
    return result
