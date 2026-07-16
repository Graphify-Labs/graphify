"""
patch_stdout
============

This implements a context manager that ensures that print statements within
it won't destroy the user interface. The context manager will replace
`sys.stdout` by something that draws the output above the current prompt,
rather than overwriting the UI.

Usage::

    with patch_stdout(application):
        ...
        application.run()
        ...

Multiple applications can run in the body of the context manager, one after the
other.
"""

from __future__ import annotations

import asyncio
import queue
import sys
import threading
import time
from contextlib import contextmanager
from typing import Generator, TextIO, cast

from .application import get_app_session, run_in_terminal
from .output import Output

__all__ = [
    "patch_stdout",
    "StdoutProxy",
]


@contextmanager
def patch_stdout(raw: bool = False) -> Generator[None, None, None]:
    """
    Replace `sys.stdout` by an :class:`_StdoutProxy` instance.

    Writing to this proxy will make sure that the text appears above the
    prompt, and that it doesn't destroy the output from the renderer.  If no
    application is curring, the behavior should be identical to writing to
    `sys.stdout` directly.

    Warning: If a new event loop is installed using `asyncio.set_event_loop()`,
        then make sure that the context manager is applied after the event loop
        is changed. Printing to stdout will be scheduled in the event loop
        that's active when the context manager is created.

    :param raw: (`bool`) When True, vt100 terminal escape sequences are not
                removed/escaped.
    """
    with StdoutProxy(raw=raw) as proxy:
        original_stdout = sys.stdout
        original_stderr = sys.stderr

        # Enter.
        sys.stdout = cast(TextIO, proxy)
        sys.stderr = cast(TextIO, proxy)

        try:
            yield
        finally:
            sys.stdout = original_stdout
            sys.stderr = original_stderr


class _Done:
    "Sentinel value for stopping the stdout proxy."


class StdoutProxy:
    """
    File-like object, which prints everything written to it, output above the
    current application/prompt. This class is compatible with other file
    objects and can be used as a drop-in replacement for `sys.stdout` or can
    for instance be passed to `logging.StreamHandler`.

    The current application, above which we print, is determined by looking
    what application currently runs in the `AppSession` that is active during
    the creation of this instance.

    This class can be used as a context manager.

    In order to avoid having to repaint the prompt continuously for every
    little write, a short delay of `sleep_between_writes` seconds will be added
    between writes in order to bundle many smaller writes in a short timespan.
    """

    def __init__(
        self,
        sleep_between_writes: float = 0.2,
        raw: bool = False,
    ) -> None:
        self.sleep_between_writes = sleep_between_writes
        self.raw = raw

        self._lock = threading.RLock()
        self._buffer: list[str] = []

        # Keep track of the curret app session.
        self.app_session = get_app_session()

        # See what output is active *right now*. We should do it at this point,
        # before this `StdoutProxy` instance is possibly assigned to `sys.stdout`.
        # Otherwise, if `patch_stdout` is used, and no `Output` instance has
        # been created, then the default output creation code will see this
        # proxy object as `sys.stdout`, and get in a recursive loop trying to
        # access `StdoutProxy.isatty()` which will again retrieve the output.
        self._output: Output = self.app_session.output

        # Flush thread
        self._flush_queue: queue.Queue[str | _Done] = queue.Queue()
        self._flush_thread = self._start_write_thread()
        self.closed = False

    def __enter__(self) -> StdoutProxy:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def close(self) -> None:
        """
        Stop `StdoutProxy` proxy.

        This will terminate the write thread, make sure everything is flushed
        and wait for the write thread to finish.
        """
        if not self.closed:
            self._flush_queue.put(_Done())
            self._flush_thread.join()
            self.closed = True

    def _start_write_thread(self) -> threading.Thread:
        thread = threading.Thread(
            target=self._write_thread,
            name="patch-stdout-flush-thread",
            daemon=True,
        )
        thread.start()
        return thread

    def _write_thread(self) -> None:
        done = False

        while not done:
            item = self._flush_queue.get()

            if isinstance(item, _Done):
                break

            # Don't bother calling when we got an empty string.
            if not item:
                continue

            text = []
            text.append(item)

            # Read the rest of the queue if more data was queued up.
            while True:
                try:
                    item = self._flush_queue.get_nowait()
                except queue.Empty:
                    break
                else:
                    if isinstance(item, _Done):
                        done = True
                    else:
                        text.append(item)

            app_loop = self._get_app_loop()
            self._write_and_flush(app_loop, "".join(text))

            # If an application was running that requires repainting, then wait
            # for a very short time, in order to bundle actual writes and avoid
            # having to repaint to often.
            if app_loop is not None:
                time.sleep(self.sleep_between_writes)

    def _get_app_loop(self) -> asyncio.AbstractEventLoop | None:
        """
        Return the event loop for the application currently running in our
        `AppSession`.
        """
        app = self.app_session.app

        if app is None:
            return None

        return app.loop

    def _write_and_flush(
        self, loop: asyncio.AbstractEventLoop | None, text: str
    ) -> None:
        """
        Write the given text to stdout and flush.
        If an application is running, use `run_in_terminal`.
        """

        def write_and_flush() -> None:
            # Ensure that autowrap is enabled before calling `write`.
            # XXX: On Windows, the `Windows10_Output` enables/disables VT
            #      terminal processing for every flush. It turns out that this
            #      causes autowrap to be reset (disabled) after each flush. So,
            #      we have to enable it again before writing text.
            self._output.enable_autowrap()

            if self.raw:
                self._output.write_raw(text)
            else:
                self._output.write(text)

            self._output.flush()

        def write_and_flush_in_loop() -> None:
            # If an application is running, use `run_in_terminal`, otherwise
            # call it directly.
            run_in_terminal(write_and_flush, in_executor=False)

        if loop is None:
            # No loop, write immediately.
            write_and_flush()
        else:
            # Make sure `write_and_flush` is executed *in* the event loop, not
            # in another thread.
            loop.call_soon_threadsafe(write_and_flush_in_loop)

    def _write(self, data: str) -> None:
        """
        Note: print()-statements cause to multiple write calls.
              (write('line') and write('\n')). Of course we don't want to call
              `run_in_terminal` for every individual call, because that's too
              expensive, and as long as the newline hasn't been written, the
              text itself is again overwritten by the rendering of the input
              command line. Therefor, we have a little buffer which holds the
              text until a newline is written to stdout.
        """
        if "\n" in data:
            # When there is a newline in the data, write everything before the
            # newline, including the newline itself.
            before, after = data.rsplit("\n", 1)
            to_write = self._buffer + [before, "\n"]
            self._buffer = [after]

            text = "".join(to_write)
            self._flush_queue.put(text)
        else:
            # Otherwise, cache in buffer.
            self._buffer.append(data)

    def _flush(self) -> None:
        text = "".join(self._buffer)
        self._buffer = []
        self._flush_queue.put(text)

    def write(self, data: str) -> int:
        with self._lock:
            self._write(data)

        return len(data)  # Pretend everything was written.

    def flush(self) -> None:
        """
        Flush buffered output.
        """
        with self._lock:
            self._flush()

    @property
    def original_stdout(self) -> TextIO | None:
        return self._output.stdout or sys.__stdout__

    # Attributes for compatibility with sys.__stdout__:

    def fileno(self) -> int:
        return self._output.fileno()

    def isatty(self) -> bool:
        stdout = self._output.stdout
        if stdout is None:
            return False

        return stdout.isatty()

    @property
    def encoding(self) -> str:
        return self._output.encoding()

    @property
    def errors(self) -> str:
        return "strict"
