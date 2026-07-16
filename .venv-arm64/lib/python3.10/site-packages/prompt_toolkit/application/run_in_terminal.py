"""
Tools for running functions on the terminal above the current application or prompt.
"""

from __future__ import annotations

from asyncio import Future, ensure_future
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Awaitable, Callable, TypeVar

from prompt_toolkit.eventloop import run_in_executor_with_context

from .current import get_app_or_none

__all__ = [
    "run_in_terminal",
    "in_terminal",
]

_T = TypeVar("_T")


def run_in_terminal(
    func: Callable[[], _T], render_cli_done: bool = False, in_executor: bool = False
) -> Awaitable[_T]:
    """
    Run function on the terminal above the current application or prompt.

    What this does is first hiding the prompt, then running this callable
    (which can safely output to the terminal), and then again rendering the
    prompt which causes the output of this function to scroll above the
    prompt.

    ``func`` is supposed to be a synchronous function. If you need an
    asynchronous version of this function, use the ``in_terminal`` context
    manager directly.

    :param func: The callable to execute.
    :param render_cli_done: When True, render the interface in the
            'Done' state first, then execute the function. If False,
            erase the interface first.
    :param in_executor: When True, run in executor. (Use this for long
        blocking functions, when you don't want to block the event loop.)

    :returns: A `Future`.
    """

    async def run() -> _T:
        async with in_terminal(render_cli_done=render_cli_done):
            if in_executor:
                return await run_in_executor_with_context(func)
            else:
                return func()

    return ensure_future(run())


@asynccontextmanager
async def in_terminal(render_cli_done: bool = False) -> AsyncGenerator[None, None]:
    """
    Asynchronous context manager that suspends the current application and runs
    the body in the terminal.

    .. code::

        async def f():
            async with in_terminal():
                call_some_function()
                await call_some_async_function()
    """
    app = get_app_or_none()
    if app is None or not app._is_running:
        yield
        return

    # When a previous `run_in_terminal` call was in progress. Wait for that
    # to finish, before starting this one. Chain to previous call.
    previous_run_in_terminal_f = app._running_in_terminal_f
    new_run_in_terminal_f: Future[None] = Future()
    app._running_in_terminal_f = new_run_in_terminal_f

    # Wait for the previous `run_in_terminal` to finish.
    if previous_run_in_terminal_f is not None:
        await previous_run_in_terminal_f

    # Wait for all CPRs to arrive. We don't want to detach the input until
    # all cursor position responses have been arrived. Otherwise, the tty
    # will echo its input and can show stuff like ^[[39;1R.
    if app.output.responds_to_cpr:
        await app.renderer.wait_for_cpr_responses()

    # Draw interface in 'done' state, or erase.
    if render_cli_done:
        app._redraw(render_as_done=True)
    else:
        app.renderer.erase()

    # Disable rendering.
    app._running_in_terminal = True

    # Detach input.
    try:
        with app.input.detach():
            with app.input.cooked_mode():
                yield
    finally:
        # Redraw interface again.
        try:
            app._running_in_terminal = False
            app.renderer.reset()
            app._request_absolute_cursor_position()
            app._redraw()
        finally:
            # (Check for `.done()`, because it can be that this future was
            # cancelled.)
            if not new_run_in_terminal_f.done():
                new_run_in_terminal_f.set_result(None)
