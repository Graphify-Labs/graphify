"""C++ extractor - delegates to _extract_generic with C++ config."""

from __future__ import annotations

from pathlib import Path

from .registry import register

_EXTENSIONS = {".cpp", ".cc", ".cxx", ".hpp", ".hxx", ".hh"}


@register(_EXTENSIONS)
def extract_cpp(path: Path) -> dict:
    """Extract functions, classes, and includes from a .cpp/.cc/.cxx/.hpp file."""
    from graphify.extract import _CPP_CONFIG, _extract_generic

    return _extract_generic(path, _CPP_CONFIG)
