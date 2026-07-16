from __future__ import annotations

from typing import Literal
from typing import Protocol


_AssertionTextDiffStyle = Literal["ndiff", "block"]


class _HighlightFunc(Protocol):  # noqa: PYI046
    def __call__(self, source: str, lexer: Literal["diff", "python"] = "python") -> str:
        """Apply highlighting to the given source."""
