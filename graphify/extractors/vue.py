"""Vue component extractor - delegates to JavaScript/TypeScript extractor."""

from __future__ import annotations

from pathlib import Path

from .registry import register

_EXTENSIONS = {".vue"}


@register(_EXTENSIONS)
def extract_vue(path: Path) -> dict:
    """Extract structure from .vue files using JS/TS extractor.

    Vue single-file components contain <script>, <template>, and <style> blocks.
    The script block is processed by the JavaScript/TypeScript extractor.
    """
    from ..extract import extract_js

    return extract_js(path)
