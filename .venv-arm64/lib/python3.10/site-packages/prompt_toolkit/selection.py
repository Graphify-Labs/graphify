"""
Data structures for the selection.
"""

from __future__ import annotations

from enum import Enum

__all__ = [
    "SelectionType",
    "PasteMode",
    "SelectionState",
]


class SelectionType(Enum):
    """
    Type of selection.
    """

    #: Characters. (Visual in Vi.)
    CHARACTERS = "CHARACTERS"

    #: Whole lines. (Visual-Line in Vi.)
    LINES = "LINES"

    #: A block selection. (Visual-Block in Vi.)
    BLOCK = "BLOCK"


class PasteMode(Enum):
    EMACS = "EMACS"  # Yank like emacs.
    VI_AFTER = "VI_AFTER"  # When pressing 'p' in Vi.
    VI_BEFORE = "VI_BEFORE"  # When pressing 'P' in Vi.


class SelectionState:
    """
    State of the current selection.

    :param original_cursor_position: int
    :param type: :class:`~.SelectionType`
    """

    def __init__(
        self,
        original_cursor_position: int = 0,
        type: SelectionType = SelectionType.CHARACTERS,
    ) -> None:
        self.original_cursor_position = original_cursor_position
        self.type = type
        self.shift_mode = False

    def enter_shift_mode(self) -> None:
        self.shift_mode = True

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(original_cursor_position={self.original_cursor_position!r}, type={self.type!r})"
