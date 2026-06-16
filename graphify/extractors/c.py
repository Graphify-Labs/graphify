"""C extractor - delegates to _extract_generic with C config."""

from __future__ import annotations

from pathlib import Path

from .registry import register

_EXTENSIONS = {".c", ".h"}


@register(_EXTENSIONS)
def extract_c(path: Path) -> dict:
    """Extract functions and includes from a .c/.h file."""
    from graphify.extract import _C_CONFIG, _extract_generic

    return _extract_generic(path, _C_CONFIG)
