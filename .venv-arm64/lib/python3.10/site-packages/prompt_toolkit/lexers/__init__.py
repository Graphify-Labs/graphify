"""
Lexer interface and implementations.
Used for syntax highlighting.
"""

from __future__ import annotations

from .base import DynamicLexer, Lexer, SimpleLexer
from .pygments import PygmentsLexer, RegexSync, SyncFromStart, SyntaxSync

__all__ = [
    # Base.
    "Lexer",
    "SimpleLexer",
    "DynamicLexer",
    # Pygments.
    "PygmentsLexer",
    "RegexSync",
    "SyncFromStart",
    "SyntaxSync",
]
