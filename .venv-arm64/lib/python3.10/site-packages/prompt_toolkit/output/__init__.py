from __future__ import annotations

from .base import DummyOutput, Output
from .color_depth import ColorDepth
from .defaults import create_output

__all__ = [
    # Base.
    "Output",
    "DummyOutput",
    # Color depth.
    "ColorDepth",
    # Defaults.
    "create_output",
]
