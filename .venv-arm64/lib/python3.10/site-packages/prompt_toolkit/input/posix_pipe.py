from __future__ import annotations

import sys

assert sys.platform != "win32"

import os
from contextlib import contextmanager
from typing import ContextManager, Iterator, TextIO, cast

from ..utils import DummyContext
from .base import PipeInput
from .vt100 import Vt100Input

__all__ = [
    "PosixPipeInput",
]


class _Pipe:
    "Wrapper around os.pipe, that ensures we don't double close any end."

    def __init__(self) -> None:
        self.read_fd, self.write_fd = os.pipe()
        self._read_closed = False
        self._write_closed = False

    def close_read(self) -> None:
        "Close read-end if not yet closed."
        if self._read_closed:
            return

        os.close(self.read_fd)
        self._read_closed = True

    def close_write(self) -> None:
        "Close write-end if not yet closed."
        if self._write_closed:
            return

        os.close(self.write_fd)
        self._write_closed = True

    def close(self) -> None:
        "Close both read and write ends."
        self.close_read()
        self.close_write()


class PosixPipeInput(Vt100Input, PipeInput):
    """
    Input that is send through a pipe.
    This is useful if we want to send the input programmatically into the
    application. Mostly useful for unit testing.

    Usage::

        with PosixPipeInput.create() as input:
            input.send_text('inputdata')
    """

    _id = 0

    def __init__(self, _pipe: _Pipe, _text: str = "") -> None:
        # Private constructor. Users should use the public `.create()` method.
        self.pipe = _pipe

        class Stdin:
            encoding = "utf-8"

            def isatty(stdin) -> bool:
                return True

            def fileno(stdin) -> int:
                return self.pipe.read_fd

        super().__init__(cast(TextIO, Stdin()))
        self.send_text(_text)

        # Identifier for every PipeInput for the hash.
        self.__class__._id += 1
        self._id = self.__class__._id

    @classmethod
    @contextmanager
    def create(cls, text: str = "") -> Iterator[PosixPipeInput]:
        pipe = _Pipe()
        try:
            yield PosixPipeInput(_pipe=pipe, _text=text)
        finally:
            pipe.close()

    def send_bytes(self, data: bytes) -> None:
        os.write(self.pipe.write_fd, data)

    def send_text(self, data: str) -> None:
        "Send text to the input."
        os.write(self.pipe.write_fd, data.encode("utf-8"))

    def raw_mode(self) -> ContextManager[None]:
        return DummyContext()

    def cooked_mode(self) -> ContextManager[None]:
        return DummyContext()

    def close(self) -> None:
        "Close pipe fds."
        # Only close the write-end of the pipe. This will unblock the reader
        # callback (in vt100.py > _attached_input), which eventually will raise
        # `EOFError`. If we'd also close the read-end, then the event loop
        # won't wake up the corresponding callback because of this.
        self.pipe.close_write()

    def typeahead_hash(self) -> str:
        """
        This needs to be unique for every `PipeInput`.
        """
        return f"pipe-input-{self._id}"
