"""Extractor registry - maps file extensions to extractor functions."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, Set

ExtractorFunc = Callable[[Path], dict]

_REGISTRY: Dict[str, ExtractorFunc] = {}


def register(extensions: Set[str]):
    """Decorator to register an extractor for given extensions."""

    def decorator(func: ExtractorFunc) -> ExtractorFunc:
        for ext in extensions:
            ext_lower = ext.lower()
            if ext_lower in _REGISTRY:
                raise ValueError(f"Extension {ext_lower} already registered")
            _REGISTRY[ext_lower] = func
        return func

    return decorator


def get_extractor(path: Path) -> ExtractorFunc | None:
    """Get the extractor for a file path."""
    ext = path.suffix.lower()
    return _REGISTRY.get(ext)


def get_all_extensions() -> Set[str]:
    """Get all registered file extensions."""
    return set(_REGISTRY.keys())


def extract(path: Path) -> dict:
    """Extract nodes and edges from a file using the registered extractor."""
    extractor = get_extractor(path)
    if extractor is None:
        return {"nodes": [], "edges": [], "error": f"no extractor for {path.suffix}"}
    return extractor(path)
