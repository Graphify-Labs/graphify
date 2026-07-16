"""
Abstraction of CLI Input.
"""

from __future__ import annotations

from abc import ABCMeta, abstractmethod
from contextlib import contextmanager
from typing import Callable, ContextManager, Generator

from prompt_toolkit.key_binding import KeyPress

__all__ = [
    "Input",
    "PipeInput",
    "DummyInput",
]


class Input(metaclass=ABCMeta):
    """
    Abstraction for any input.

    An instance of this class can be given to the constructor of a
    :class:`~prompt_toolkit.application.Application` and will also be
    passed to the :class:`~prompt_toolkit.eventloop.base.EventLoop`.
    """

    @abstractmethod
    def fileno(self) -> int:
        """
        Fileno for putting this in an event loop.
        """

    @abstractmethod
    def typeahead_hash(self) -> str:
        """
        Identifier for storing type ahead key presses.
        """

    @abstractmethod
    def read_keys(self) -> list[KeyPress]:
        """
        Return a list of Key objects which are read/parsed from the input.
        """

    def flush_keys(self) -> list[KeyPress]:
        """
        Flush the underlying parser. and return the pending keys.
        (Used for vt100 input.)
        """
        return []

    def flush(self) -> None:
        "The event loop can call this when the input has to be flushed."
        pass

    @property
    @abstractmethod
    def closed(self) -> bool:
        "Should be true when the input stream is closed."
        return False

    @abstractmethod
    def raw_mode(self) -> ContextManager[None]:
        """
        Context manager that turns the input into raw mode.
        """

    @abstractmethod
    def cooked_mode(self) -> ContextManager[None]:
        """
        Context manager that turns the input into cooked mode.
        """

    @abstractmethod
    def attach(self, input_ready_callback: Callable[[], None]) -> ContextManager[None]:
        """
        Return a context manager that makes this input active in the current
        event loop.
        """

    @abstractmethod
    def detach(self) -> ContextManager[None]:
        """
        Return a context manager that makes sure that this input is not active
        in the current event loop.
        """

    def close(self) -> None:
        "Close input."
        pass


class PipeInput(Input):
    """
    Abstraction for pipe input.
    """

    @abstractmethod
    def send_bytes(self, data: bytes) -> None:
        """Feed byte string into the pipe"""

    @abstractmethod
    def send_text(self, data: str) -> None:
        """Feed a text string into the pipe"""


class DummyInput(Input):
    """
    Input for use in a `DummyApplication`

    If used in an actual application, it will make the application render
    itself once and exit immediately, due to an `EOFError`.
    """

    def fileno(self) -> int:
        raise NotImplementedError

    def typeahead_hash(self) -> str:
        return f"dummy-{id(self)}"

    def read_keys(self) -> list[KeyPress]:
        return []

    @property
    def closed(self) -> bool:
        # This needs to be true, so that the dummy input will trigger an
        # `EOFError` immediately in the application.
        return True

    def raw_mode(self) -> ContextManager[None]:
        return _dummy_context_manager()

    def cooked_mode(self) -> ContextManager[None]:
        return _dummy_context_manager()

    def attach(self, input_ready_callback: Callable[[], None]) -> ContextManager[None]:
        # Call the callback immediately once after attaching.
        # This tells the callback to call `read_keys` and check the
        # `input.closed` flag, after which it won't receive any keys, but knows
        # that `EOFError` should be raised. This unblocks `read_from_input` in
        # `application.py`.
        input_ready_callback()

        return _dummy_context_manager()

    def detach(self) -> ContextManager[None]:
        return _dummy_context_manager()


@contextmanager
def _dummy_context_manager() -> Generator[None, None, None]:
    yield
