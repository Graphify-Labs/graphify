"""
Clipboard for command line interface.
"""

from __future__ import annotations

from abc import ABCMeta, abstractmethod
from typing import Callable

from prompt_toolkit.selection import SelectionType

__all__ = [
    "Clipboard",
    "ClipboardData",
    "DummyClipboard",
    "DynamicClipboard",
]


class ClipboardData:
    """
    Text on the clipboard.

    :param text: string
    :param type: :class:`~prompt_toolkit.selection.SelectionType`
    """

    def __init__(
        self, text: str = "", type: SelectionType = SelectionType.CHARACTERS
    ) -> None:
        self.text = text
        self.type = type


class Clipboard(metaclass=ABCMeta):
    """
    Abstract baseclass for clipboards.
    (An implementation can be in memory, it can share the X11 or Windows
    keyboard, or can be persistent.)
    """

    @abstractmethod
    def set_data(self, data: ClipboardData) -> None:
        """
        Set data to the clipboard.

        :param data: :class:`~.ClipboardData` instance.
        """

    def set_text(self, text: str) -> None:  # Not abstract.
        """
        Shortcut for setting plain text on clipboard.
        """
        self.set_data(ClipboardData(text))

    def rotate(self) -> None:
        """
        For Emacs mode, rotate the kill ring.
        """

    @abstractmethod
    def get_data(self) -> ClipboardData:
        """
        Return clipboard data.
        """


class DummyClipboard(Clipboard):
    """
    Clipboard implementation that doesn't remember anything.
    """

    def set_data(self, data: ClipboardData) -> None:
        pass

    def set_text(self, text: str) -> None:
        pass

    def rotate(self) -> None:
        pass

    def get_data(self) -> ClipboardData:
        return ClipboardData()


class DynamicClipboard(Clipboard):
    """
    Clipboard class that can dynamically returns any Clipboard.

    :param get_clipboard: Callable that returns a :class:`.Clipboard` instance.
    """

    def __init__(self, get_clipboard: Callable[[], Clipboard | None]) -> None:
        self.get_clipboard = get_clipboard

    def _clipboard(self) -> Clipboard:
        return self.get_clipboard() or DummyClipboard()

    def set_data(self, data: ClipboardData) -> None:
        self._clipboard().set_data(data)

    def set_text(self, text: str) -> None:
        self._clipboard().set_text(text)

    def rotate(self) -> None:
        self._clipboard().rotate()

    def get_data(self) -> ClipboardData:
        return self._clipboard().get_data()
