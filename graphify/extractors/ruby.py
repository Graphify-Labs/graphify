"""Ruby extractor - delegates to _extract_generic with Ruby config."""

from __future__ import annotations

from pathlib import Path

from .registry import register

_EXTENSIONS = {".rb"}


@register(_EXTENSIONS)
def extract_ruby(path: Path) -> dict:
    """Extract classes, methods, singleton methods, and calls from a .rb file."""
    from ._core import _RUBY_CONFIG, _extract_generic

    return _extract_generic(path, _RUBY_CONFIG)
