"""
Similar to `PyOS_InputHook` of the Python API, we can plug in an input hook in
the asyncio event loop.

The way this works is by using a custom 'selector' that runs the other event
loop until the real selector is ready.

It's the responsibility of this event hook to return when there is input ready.
There are two ways to detect when input is ready:

The inputhook itself is a callable that receives an `InputHookContext`. This
callable should run the other event loop, and return when the main loop has
stuff to do. There are two ways to detect when to return:

- Call the `input_is_ready` method periodically. Quit when this returns `True`.

- Add the `fileno` as a watch to the external eventloop. Quit when file descriptor
  becomes readable. (But don't read from it.)

  Note that this is not the same as checking for `sys.stdin.fileno()`. The
  eventloop of prompt-toolkit allows thread-based executors, for example for
  asynchronous autocompletion. When the completion for instance is ready, we
  also want prompt-toolkit to gain control again in order to display that.
"""

from __future__ import annotations

import asyncio
import os
import select
import selectors
import sys
import threading
from asyncio import AbstractEventLoop, get_running_loop
from selectors import BaseSelector, SelectorKey
from typing import TYPE_CHECKING, Any, Callable, Mapping

__all__ = [
    "new_eventloop_with_inputhook",
    "set_eventloop_with_inputhook",
    "InputHookSelector",
    "InputHookContext",
    "InputHook",
]

if TYPE_CHECKING:
    from _typeshed import FileDescriptorLike
    from typing_extensions import TypeAlias

    _EventMask = int


class InputHookContext:
    """
    Given as a parameter to the inputhook.
    """

    def __init__(self, fileno: int, input_is_ready: Callable[[], bool]) -> None:
        self._fileno = fileno
        self.input_is_ready = input_is_ready

    def fileno(self) -> int:
        return self._fileno


InputHook: TypeAlias = Callable[[InputHookContext], None]


def new_eventloop_with_inputhook(
    inputhook: Callable[[InputHookContext], None],
) -> AbstractEventLoop:
    """
    Create a new event loop with the given inputhook.
    """
    selector = InputHookSelector(selectors.DefaultSelector(), inputhook)
    loop = asyncio.SelectorEventLoop(selector)
    return loop


def set_eventloop_with_inputhook(
    inputhook: Callable[[InputHookContext], None],
) -> AbstractEventLoop:
    """
    Create a new event loop with the given inputhook, and activate it.
    """
    # Deprecated!

    loop = new_eventloop_with_inputhook(inputhook)
    asyncio.set_event_loop(loop)
    return loop


class InputHookSelector(BaseSelector):
    """
    Usage:

        selector = selectors.SelectSelector()
        loop = asyncio.SelectorEventLoop(InputHookSelector(selector, inputhook))
        asyncio.set_event_loop(loop)
    """

    def __init__(
        self, selector: BaseSelector, inputhook: Callable[[InputHookContext], None]
    ) -> None:
        self.selector = selector
        self.inputhook = inputhook
        self._r, self._w = os.pipe()

    def register(
        self, fileobj: FileDescriptorLike, events: _EventMask, data: Any = None
    ) -> SelectorKey:
        return self.selector.register(fileobj, events, data=data)

    def unregister(self, fileobj: FileDescriptorLike) -> SelectorKey:
        return self.selector.unregister(fileobj)

    def modify(
        self, fileobj: FileDescriptorLike, events: _EventMask, data: Any = None
    ) -> SelectorKey:
        return self.selector.modify(fileobj, events, data=None)

    def select(
        self, timeout: float | None = None
    ) -> list[tuple[SelectorKey, _EventMask]]:
        # If there are tasks in the current event loop,
        # don't run the input hook.
        if len(getattr(get_running_loop(), "_ready", [])) > 0:
            return self.selector.select(timeout=timeout)

        ready = False
        result = None

        # Run selector in other thread.
        def run_selector() -> None:
            nonlocal ready, result
            result = self.selector.select(timeout=timeout)
            os.write(self._w, b"x")
            ready = True

        th = threading.Thread(target=run_selector)
        th.start()

        def input_is_ready() -> bool:
            return ready

        # Call inputhook.
        # The inputhook function is supposed to return when our selector
        # becomes ready. The inputhook can do that by registering the fd in its
        # own loop, or by checking the `input_is_ready` function regularly.
        self.inputhook(InputHookContext(self._r, input_is_ready))

        # Flush the read end of the pipe.
        try:
            # Before calling 'os.read', call select.select. This is required
            # when the gevent monkey patch has been applied. 'os.read' is never
            # monkey patched and won't be cooperative, so that would block all
            # other select() calls otherwise.
            # See: http://www.gevent.org/gevent.os.html

            # Note: On Windows, this is apparently not an issue.
            #       However, if we would ever want to add a select call, it
            #       should use `windll.kernel32.WaitForMultipleObjects`,
            #       because `select.select` can't wait for a pipe on Windows.
            if sys.platform != "win32":
                select.select([self._r], [], [], None)

            os.read(self._r, 1024)
        except OSError:
            # This happens when the window resizes and a SIGWINCH was received.
            # We get 'Error: [Errno 4] Interrupted system call'
            # Just ignore.
            pass

        # Wait for the real selector to be done.
        th.join()
        assert result is not None
        return result

    def close(self) -> None:
        """
        Clean up resources.
        """
        if self._r:
            os.close(self._r)
            os.close(self._w)

        self._r = self._w = -1
        self.selector.close()

    def get_map(self) -> Mapping[FileDescriptorLike, SelectorKey]:
        return self.selector.get_map()
