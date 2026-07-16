from __future__ import annotations

from .base import Clipboard, ClipboardData, DummyClipboard, DynamicClipboard
from .in_memory import InMemoryClipboard

# We are not importing `PyperclipClipboard` here, because it would require the
# `pyperclip` module to be present.

# from .pyperclip import PyperclipClipboard

__all__ = [
    "Clipboard",
    "ClipboardData",
    "DummyClipboard",
    "DynamicClipboard",
    "InMemoryClipboard",
]
