"""Deterministic structural extraction from source code using tree-sitter.

All implementation lives in graphify.extractors._core for modularity.
This module re-exports everything for backward compatibility and test patching.
"""
from __future__ import annotations

# Import the _core module
from .extractors import _core

# Re-export everything (both public and private)
import sys as _sys
for _name in dir(_core):
    if not _name.startswith('__'):
        globals()[_name] = getattr(_core, _name)

# Clean up namespace
del _core, _sys, _name

# Define __all__ for proper exports
__all__ = [name for name in dir() if not name.startswith('__')]
