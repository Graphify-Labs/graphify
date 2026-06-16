"""Swift extractor - delegates to _extract_generic with Swift config."""

from __future__ import annotations

from pathlib import Path

from .registry import register

_EXTENSIONS = {".swift"}


@register(_EXTENSIONS)
def extract_swift(path: Path) -> dict:
    """Extract classes, structs, protocols, functions, imports, and calls from a .swift file."""
    from graphify.extract import _SWIFT_CONFIG, _extract_generic

    return _extract_generic(path, _SWIFT_CONFIG)
