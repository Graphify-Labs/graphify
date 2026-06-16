"""BYOND DreamMaker extractor - delegates to extract.py implementation."""

from __future__ import annotations

from pathlib import Path

from .registry import register

_EXTENSIONS = {".dm", ".dme"}


@register(_EXTENSIONS)
def extract_dm(path: Path) -> dict:
    """Extract types, procs, includes, and calls from a .dm/.dme file."""
    from ._core import extract_dm as _extract_dm

    return _extract_dm(path)
