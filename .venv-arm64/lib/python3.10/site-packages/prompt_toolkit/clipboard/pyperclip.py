from __future__ import annotations

import pyperclip

from prompt_toolkit.selection import SelectionType

from .base import Clipboard, ClipboardData

__all__ = [
    "PyperclipClipboard",
]


class PyperclipClipboard(Clipboard):
    """
    Clipboard that synchronizes with the Windows/Mac/Linux system clipboard,
    using the pyperclip module.
    """

    def __init__(self) -> None:
        self._data: ClipboardData | None = None

    def set_data(self, data: ClipboardData) -> None:
        self._data = data
        pyperclip.copy(data.text)

    def get_data(self) -> ClipboardData:
        text = pyperclip.paste()

        # When the clipboard data is equal to what we copied last time, reuse
        # the `ClipboardData` instance. That way we're sure to keep the same
        # `SelectionType`.
        if self._data and self._data.text == text:
            return self._data

        # Pyperclip returned something else. Create a new `ClipboardData`
        # instance.
        else:
            return ClipboardData(
                text=text,
                type=SelectionType.LINES if "\n" in text else SelectionType.CHARACTERS,
            )
