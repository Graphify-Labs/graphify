from __future__ import annotations

from collections import deque

from .base import Clipboard, ClipboardData

__all__ = [
    "InMemoryClipboard",
]


class InMemoryClipboard(Clipboard):
    """
    Default clipboard implementation.
    Just keep the data in memory.

    This implements a kill-ring, for Emacs mode.
    """

    def __init__(self, data: ClipboardData | None = None, max_size: int = 60) -> None:
        assert max_size >= 1

        self.max_size = max_size
        self._ring: deque[ClipboardData] = deque()

        if data is not None:
            self.set_data(data)

    def set_data(self, data: ClipboardData) -> None:
        self._ring.appendleft(data)

        while len(self._ring) > self.max_size:
            self._ring.pop()

    def get_data(self) -> ClipboardData:
        if self._ring:
            return self._ring[0]
        else:
            return ClipboardData()

    def rotate(self) -> None:
        if self._ring:
            # Add the very first item at the end.
            self._ring.append(self._ring.popleft())
