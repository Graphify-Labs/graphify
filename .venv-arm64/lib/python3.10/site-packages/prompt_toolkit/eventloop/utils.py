from __future__ import annotations

import asyncio
import contextvars
import sys
import time
from asyncio import get_running_loop
from types import TracebackType
from typing import Any, Awaitable, Callable, TypeVar, cast

__all__ = [
    "run_in_executor_with_context",
    "call_soon_threadsafe",
    "get_traceback_from_context",
]

_T = TypeVar("_T")


def run_in_executor_with_context(
    func: Callable[..., _T],
    *args: Any,
    loop: asyncio.AbstractEventLoop | None = None,
) -> Awaitable[_T]:
    """
    Run a function in an executor, but make sure it uses the same contextvars.
    This is required so that the function will see the right application.

    See also: https://bugs.python.org/issue34014
    """
    loop = loop or get_running_loop()
    ctx: contextvars.Context = contextvars.copy_context()

    return loop.run_in_executor(None, ctx.run, func, *args)


def call_soon_threadsafe(
    func: Callable[[], None],
    max_postpone_time: float | None = None,
    loop: asyncio.AbstractEventLoop | None = None,
) -> None:
    """
    Wrapper around asyncio's `call_soon_threadsafe`.

    This takes a `max_postpone_time` which can be used to tune the urgency of
    the method.

    Asyncio runs tasks in first-in-first-out. However, this is not what we
    want for the render function of the prompt_toolkit UI. Rendering is
    expensive, but since the UI is invalidated very often, in some situations
    we render the UI too often, so much that the rendering CPU usage slows down
    the rest of the processing of the application.  (Pymux is an example where
    we have to balance the CPU time spend on rendering the UI, and parsing
    process output.)
    However, we want to set a deadline value, for when the rendering should
    happen. (The UI should stay responsive).
    """
    loop2 = loop or get_running_loop()

    # If no `max_postpone_time` has been given, schedule right now.
    if max_postpone_time is None:
        loop2.call_soon_threadsafe(func)
        return

    max_postpone_until = time.time() + max_postpone_time

    def schedule() -> None:
        # When there are no other tasks scheduled in the event loop. Run it
        # now.
        # Notice: uvloop doesn't have this _ready attribute. In that case,
        #         always call immediately.
        if not getattr(loop2, "_ready", []):
            func()
            return

        # If the timeout expired, run this now.
        if time.time() > max_postpone_until:
            func()
            return

        # Schedule again for later.
        loop2.call_soon_threadsafe(schedule)

    loop2.call_soon_threadsafe(schedule)


def get_traceback_from_context(context: dict[str, Any]) -> TracebackType | None:
    """
    Get the traceback object from the context.
    """
    exception = context.get("exception")
    if exception:
        if hasattr(exception, "__traceback__"):
            return cast(TracebackType, exception.__traceback__)
        else:
            # call_exception_handler() is usually called indirectly
            # from an except block. If it's not the case, the traceback
            # is undefined...
            return sys.exc_info()[2]

    return None
