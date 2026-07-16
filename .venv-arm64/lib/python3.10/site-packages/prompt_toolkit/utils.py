from __future__ import annotations

import os
import signal
import sys
import threading
from collections import deque
from typing import (
    Callable,
    ContextManager,
    Dict,
    Generator,
    Generic,
    TypeVar,
    Union,
)

from wcwidth import wcwidth

__all__ = [
    "Event",
    "DummyContext",
    "get_cwidth",
    "suspend_to_background_supported",
    "is_conemu_ansi",
    "is_windows",
    "in_main_thread",
    "get_bell_environment_variable",
    "get_term_environment_variable",
    "take_using_weights",
    "to_str",
    "to_int",
    "AnyFloat",
    "to_float",
    "is_dumb_terminal",
]

# Used to ensure sphinx autodoc does not try to import platform-specific
# stuff when documenting win32.py modules.
SPHINX_AUTODOC_RUNNING = "sphinx.ext.autodoc" in sys.modules

_Sender = TypeVar("_Sender", covariant=True)


class Event(Generic[_Sender]):
    """
    Simple event to which event handlers can be attached. For instance::

        class Cls:
            def __init__(self):
                # Define event. The first parameter is the sender.
                self.event = Event(self)

        obj = Cls()

        def handler(sender):
            pass

        # Add event handler by using the += operator.
        obj.event += handler

        # Fire event.
        obj.event()
    """

    def __init__(
        self, sender: _Sender, handler: Callable[[_Sender], None] | None = None
    ) -> None:
        self.sender = sender
        self._handlers: list[Callable[[_Sender], None]] = []

        if handler is not None:
            self += handler

    def __call__(self) -> None:
        "Fire event."
        for handler in self._handlers:
            handler(self.sender)

    def fire(self) -> None:
        "Alias for just calling the event."
        self()

    def add_handler(self, handler: Callable[[_Sender], None]) -> None:
        """
        Add another handler to this callback.
        (Handler should be a callable that takes exactly one parameter: the
        sender object.)
        """
        # Add to list of event handlers.
        self._handlers.append(handler)

    def remove_handler(self, handler: Callable[[_Sender], None]) -> None:
        """
        Remove a handler from this callback.
        """
        if handler in self._handlers:
            self._handlers.remove(handler)

    def __iadd__(self, handler: Callable[[_Sender], None]) -> Event[_Sender]:
        """
        `event += handler` notation for adding a handler.
        """
        self.add_handler(handler)
        return self

    def __isub__(self, handler: Callable[[_Sender], None]) -> Event[_Sender]:
        """
        `event -= handler` notation for removing a handler.
        """
        self.remove_handler(handler)
        return self


class DummyContext(ContextManager[None]):
    """
    (contextlib.nested is not available on Py3)
    """

    def __enter__(self) -> None:
        pass

    def __exit__(self, *a: object) -> None:
        pass


class _CharSizesCache(Dict[str, int]):
    """
    Cache for wcwidth sizes.
    """

    LONG_STRING_MIN_LEN = 64  # Minimum string length for considering it long.
    MAX_LONG_STRINGS = 16  # Maximum number of long strings to remember.

    def __init__(self) -> None:
        super().__init__()
        # Keep track of the "long" strings in this cache.
        self._long_strings: deque[str] = deque()

    def __missing__(self, string: str) -> int:
        # Note: We use the `max(0, ...` because some non printable control
        #       characters, like e.g. Ctrl-underscore get a -1 wcwidth value.
        #       It can be possible that these characters end up in the input
        #       text.
        result: int
        if len(string) == 1:
            result = max(0, wcwidth(string))
        else:
            result = sum(self[c] for c in string)

        # Store in cache.
        self[string] = result

        # Rotate long strings.
        # (It's hard to tell what we can consider short...)
        if len(string) > self.LONG_STRING_MIN_LEN:
            long_strings = self._long_strings
            long_strings.append(string)

            if len(long_strings) > self.MAX_LONG_STRINGS:
                key_to_remove = long_strings.popleft()
                if key_to_remove in self:
                    del self[key_to_remove]

        return result


_CHAR_SIZES_CACHE = _CharSizesCache()


def get_cwidth(string: str) -> int:
    """
    Return width of a string. Wrapper around ``wcwidth``.
    """
    return _CHAR_SIZES_CACHE[string]


def suspend_to_background_supported() -> bool:
    """
    Returns `True` when the Python implementation supports
    suspend-to-background. This is typically `False' on Windows systems.
    """
    return hasattr(signal, "SIGTSTP")


def is_windows() -> bool:
    """
    True when we are using Windows.
    """
    return sys.platform == "win32"  # Not 'darwin' or 'linux2'


def is_windows_vt100_supported() -> bool:
    """
    True when we are using Windows, but VT100 escape sequences are supported.
    """
    if sys.platform == "win32":
        # Import needs to be inline. Windows libraries are not always available.
        from prompt_toolkit.output.windows10 import is_win_vt100_enabled

        return is_win_vt100_enabled()

    return False


def is_conemu_ansi() -> bool:
    """
    True when the ConEmu Windows console is used.
    """
    return sys.platform == "win32" and os.environ.get("ConEmuANSI", "OFF") == "ON"


def in_main_thread() -> bool:
    """
    True when the current thread is the main thread.
    """
    return threading.current_thread().__class__.__name__ == "_MainThread"


def get_bell_environment_variable() -> bool:
    """
    True if env variable is set to true (true, TRUE, True, 1).
    """
    value = os.environ.get("PROMPT_TOOLKIT_BELL", "true")
    return value.lower() in ("1", "true")


def get_term_environment_variable() -> str:
    "Return the $TERM environment variable."
    return os.environ.get("TERM", "")


_T = TypeVar("_T")


def take_using_weights(
    items: list[_T], weights: list[int]
) -> Generator[_T, None, None]:
    """
    Generator that keeps yielding items from the items list, in proportion to
    their weight. For instance::

        # Getting the first 70 items from this generator should have yielded 10
        # times A, 20 times B and 40 times C, all distributed equally..
        take_using_weights(['A', 'B', 'C'], [5, 10, 20])

    :param items: List of items to take from.
    :param weights: Integers representing the weight. (Numbers have to be
                    integers, not floats.)
    """
    assert len(items) == len(weights)
    assert len(items) > 0

    # Remove items with zero-weight.
    items2 = []
    weights2 = []
    for item, w in zip(items, weights):
        if w > 0:
            items2.append(item)
            weights2.append(w)

    items = items2
    weights = weights2

    # Make sure that we have some items left.
    if not items:
        raise ValueError("Did't got any items with a positive weight.")

    #
    already_taken = [0 for i in items]
    item_count = len(items)
    max_weight = max(weights)

    i = 0
    while True:
        # Each iteration of this loop, we fill up until by (total_weight/max_weight).
        adding = True
        while adding:
            adding = False

            for item_i, item, weight in zip(range(item_count), items, weights):
                if already_taken[item_i] < i * weight / float(max_weight):
                    yield item
                    already_taken[item_i] += 1
                    adding = True

        i += 1


def to_str(value: Callable[[], str] | str) -> str:
    "Turn callable or string into string."
    if callable(value):
        return to_str(value())
    else:
        return str(value)


def to_int(value: Callable[[], int] | int) -> int:
    "Turn callable or int into int."
    if callable(value):
        return to_int(value())
    else:
        return int(value)


AnyFloat = Union[Callable[[], float], float]


def to_float(value: AnyFloat) -> float:
    "Turn callable or float into float."
    if callable(value):
        return to_float(value())
    else:
        return float(value)


def is_dumb_terminal(term: str | None = None) -> bool:
    """
    True if this terminal type is considered "dumb".

    If so, we should fall back to the simplest possible form of line editing,
    without cursor positioning and color support.
    """
    if term is None:
        return is_dumb_terminal(os.environ.get("TERM", ""))

    return term.lower() in ["dumb", "unknown"]
