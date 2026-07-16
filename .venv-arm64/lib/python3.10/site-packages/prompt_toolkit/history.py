"""
Implementations for the history of a `Buffer`.

NOTE: There is no `DynamicHistory`:
      This doesn't work well, because the `Buffer` needs to be able to attach
      an event handler to the event when a history entry is loaded. This
      loading can be done asynchronously and making the history swappable would
      probably break this.
"""

from __future__ import annotations

import datetime
import os
import threading
from abc import ABCMeta, abstractmethod
from asyncio import get_running_loop
from typing import AsyncGenerator, Iterable, Sequence, Union

__all__ = [
    "History",
    "ThreadedHistory",
    "DummyHistory",
    "FileHistory",
    "InMemoryHistory",
]


class History(metaclass=ABCMeta):
    """
    Base ``History`` class.

    This also includes abstract methods for loading/storing history.
    """

    def __init__(self) -> None:
        # In memory storage for strings.
        self._loaded = False

        # History that's loaded already, in reverse order. Latest, most recent
        # item first.
        self._loaded_strings: list[str] = []

    #
    # Methods expected by `Buffer`.
    #

    async def load(self) -> AsyncGenerator[str, None]:
        """
        Load the history and yield all the entries in reverse order (latest,
        most recent history entry first).

        This method can be called multiple times from the `Buffer` to
        repopulate the history when prompting for a new input. So we are
        responsible here for both caching, and making sure that strings that
        were were appended to the history will be incorporated next time this
        method is called.
        """
        if not self._loaded:
            self._loaded_strings = list(self.load_history_strings())
            self._loaded = True

        for item in self._loaded_strings:
            yield item

    def get_strings(self) -> list[str]:
        """
        Get the strings from the history that are loaded so far.
        (In order. Oldest item first.)
        """
        return self._loaded_strings[::-1]

    def append_string(self, string: str) -> None:
        "Add string to the history."
        self._loaded_strings.insert(0, string)
        self.store_string(string)

    #
    # Implementation for specific backends.
    #

    @abstractmethod
    def load_history_strings(self) -> Iterable[str]:
        """
        This should be a generator that yields `str` instances.

        It should yield the most recent items first, because they are the most
        important. (The history can already be used, even when it's only
        partially loaded.)
        """
        while False:
            yield

    @abstractmethod
    def store_string(self, string: str) -> None:
        """
        Store the string in persistent storage.
        """


class ThreadedHistory(History):
    """
    Wrapper around `History` implementations that run the `load()` generator in
    a thread.

    Use this to increase the start-up time of prompt_toolkit applications.
    History entries are available as soon as they are loaded. We don't have to
    wait for everything to be loaded.
    """

    def __init__(self, history: History) -> None:
        super().__init__()

        self.history = history

        self._load_thread: threading.Thread | None = None

        # Lock for accessing/manipulating `_loaded_strings` and `_loaded`
        # together in a consistent state.
        self._lock = threading.Lock()

        # Events created by each `load()` call. Used to wait for new history
        # entries from the loader thread.
        self._string_load_events: list[threading.Event] = []

    async def load(self) -> AsyncGenerator[str, None]:
        """
        Like `History.load(), but call `self.load_history_strings()` in a
        background thread.
        """
        # Start the load thread, if this is called for the first time.
        if not self._load_thread:
            self._load_thread = threading.Thread(
                target=self._in_load_thread,
                daemon=True,
            )
            self._load_thread.start()

        # Consume the `_loaded_strings` list, using asyncio.
        loop = get_running_loop()

        # Create threading Event so that we can wait for new items.
        event = threading.Event()
        event.set()
        self._string_load_events.append(event)

        items_yielded = 0

        try:
            while True:
                # Wait for new items to be available.
                # (Use a timeout, because the executor thread is not a daemon
                # thread. The "slow-history.py" example would otherwise hang if
                # Control-C is pressed before the history is fully loaded,
                # because there's still this non-daemon executor thread waiting
                # for this event.)
                got_timeout = await loop.run_in_executor(
                    None, lambda: event.wait(timeout=0.5)
                )
                if not got_timeout:
                    continue

                # Read new items (in lock).
                def in_executor() -> tuple[list[str], bool]:
                    with self._lock:
                        new_items = self._loaded_strings[items_yielded:]
                        done = self._loaded
                        event.clear()
                    return new_items, done

                new_items, done = await loop.run_in_executor(None, in_executor)

                items_yielded += len(new_items)

                for item in new_items:
                    yield item

                if done:
                    break
        finally:
            self._string_load_events.remove(event)

    def _in_load_thread(self) -> None:
        try:
            # Start with an empty list. In case `append_string()` was called
            # before `load()` happened. Then `.store_string()` will have
            # written these entries back to disk and we will reload it.
            self._loaded_strings = []

            for item in self.history.load_history_strings():
                with self._lock:
                    self._loaded_strings.append(item)

                for event in self._string_load_events:
                    event.set()
        finally:
            with self._lock:
                self._loaded = True
            for event in self._string_load_events:
                event.set()

    def append_string(self, string: str) -> None:
        with self._lock:
            self._loaded_strings.insert(0, string)
        self.store_string(string)

    # All of the following are proxied to `self.history`.

    def load_history_strings(self) -> Iterable[str]:
        return self.history.load_history_strings()

    def store_string(self, string: str) -> None:
        self.history.store_string(string)

    def __repr__(self) -> str:
        return f"ThreadedHistory({self.history!r})"


class InMemoryHistory(History):
    """
    :class:`.History` class that keeps a list of all strings in memory.

    In order to prepopulate the history, it's possible to call either
    `append_string` for all items or pass a list of strings to `__init__` here.
    """

    def __init__(self, history_strings: Sequence[str] | None = None) -> None:
        super().__init__()
        # Emulating disk storage.
        if history_strings is None:
            self._storage = []
        else:
            self._storage = list(history_strings)

    def load_history_strings(self) -> Iterable[str]:
        yield from self._storage[::-1]

    def store_string(self, string: str) -> None:
        self._storage.append(string)


class DummyHistory(History):
    """
    :class:`.History` object that doesn't remember anything.
    """

    def load_history_strings(self) -> Iterable[str]:
        return []

    def store_string(self, string: str) -> None:
        pass

    def append_string(self, string: str) -> None:
        # Don't remember this.
        pass


_StrOrBytesPath = Union[str, bytes, "os.PathLike[str]", "os.PathLike[bytes]"]


class FileHistory(History):
    """
    :class:`.History` class that stores all strings in a file.
    """

    def __init__(self, filename: _StrOrBytesPath) -> None:
        self.filename = filename
        super().__init__()

    def load_history_strings(self) -> Iterable[str]:
        strings: list[str] = []
        lines: list[str] = []

        def add() -> None:
            if lines:
                # Join and drop trailing newline.
                string = "".join(lines)[:-1]

                strings.append(string)

        if os.path.exists(self.filename):
            with open(self.filename, "rb") as f:
                for line_bytes in f:
                    line = line_bytes.decode("utf-8", errors="replace")

                    if line.startswith("+"):
                        lines.append(line[1:])
                    else:
                        add()
                        lines = []

                add()

        # Reverse the order, because newest items have to go first.
        return reversed(strings)

    def store_string(self, string: str) -> None:
        # Save to file.
        with open(self.filename, "ab") as f:

            def write(t: str) -> None:
                f.write(t.encode("utf-8"))

            write(f"\n# {datetime.datetime.now()}\n")
            for line in string.split("\n"):
                write(f"+{line}\n")
