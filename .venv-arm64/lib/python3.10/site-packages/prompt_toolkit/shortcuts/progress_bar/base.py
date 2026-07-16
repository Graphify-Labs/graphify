"""
Progress bar implementation on top of prompt_toolkit.

::

    with ProgressBar(...) as pb:
        for item in pb(data):
            ...
"""

from __future__ import annotations

import contextvars
import datetime
import functools
import os
import signal
import threading
import traceback
from typing import (
    Callable,
    Generic,
    Iterable,
    Iterator,
    Sequence,
    Sized,
    TextIO,
    TypeVar,
    cast,
)

from prompt_toolkit.application import Application
from prompt_toolkit.application.current import get_app_session
from prompt_toolkit.filters import Condition, is_done, renderer_height_is_known
from prompt_toolkit.formatted_text import (
    AnyFormattedText,
    StyleAndTextTuples,
    to_formatted_text,
)
from prompt_toolkit.input import Input
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.key_processor import KeyPressEvent
from prompt_toolkit.layout import (
    ConditionalContainer,
    FormattedTextControl,
    HSplit,
    Layout,
    VSplit,
    Window,
)
from prompt_toolkit.layout.controls import UIContent, UIControl
from prompt_toolkit.layout.dimension import AnyDimension, D
from prompt_toolkit.output import ColorDepth, Output
from prompt_toolkit.styles import BaseStyle
from prompt_toolkit.utils import in_main_thread

from .formatters import Formatter, create_default_formatters

__all__ = ["ProgressBar"]

E = KeyPressEvent

_SIGWINCH = getattr(signal, "SIGWINCH", None)


def create_key_bindings(cancel_callback: Callable[[], None] | None) -> KeyBindings:
    """
    Key bindings handled by the progress bar.
    (The main thread is not supposed to handle any key bindings.)
    """
    kb = KeyBindings()

    @kb.add("c-l")
    def _clear(event: E) -> None:
        event.app.renderer.clear()

    if cancel_callback is not None:

        @kb.add("c-c")
        def _interrupt(event: E) -> None:
            "Kill the 'body' of the progress bar, but only if we run from the main thread."
            assert cancel_callback is not None
            cancel_callback()

    return kb


_T = TypeVar("_T")


class ProgressBar:
    """
    Progress bar context manager.

    Usage ::

        with ProgressBar(...) as pb:
            for item in pb(data):
                ...

    :param title: Text to be displayed above the progress bars. This can be a
        callable or formatted text as well.
    :param formatters: List of :class:`.Formatter` instances.
    :param bottom_toolbar: Text to be displayed in the bottom toolbar. This
        can be a callable or formatted text.
    :param style: :class:`prompt_toolkit.styles.BaseStyle` instance.
    :param key_bindings: :class:`.KeyBindings` instance.
    :param cancel_callback: Callback function that's called when control-c is
        pressed by the user. This can be used for instance to start "proper"
        cancellation if the wrapped code supports it.
    :param file: The file object used for rendering, by default `sys.stderr` is used.

    :param color_depth: `prompt_toolkit` `ColorDepth` instance.
    :param output: :class:`~prompt_toolkit.output.Output` instance.
    :param input: :class:`~prompt_toolkit.input.Input` instance.
    """

    def __init__(
        self,
        title: AnyFormattedText = None,
        formatters: Sequence[Formatter] | None = None,
        bottom_toolbar: AnyFormattedText = None,
        style: BaseStyle | None = None,
        key_bindings: KeyBindings | None = None,
        cancel_callback: Callable[[], None] | None = None,
        file: TextIO | None = None,
        color_depth: ColorDepth | None = None,
        output: Output | None = None,
        input: Input | None = None,
    ) -> None:
        self.title = title
        self.formatters = formatters or create_default_formatters()
        self.bottom_toolbar = bottom_toolbar
        self.counters: list[ProgressBarCounter[object]] = []
        self.style = style
        self.key_bindings = key_bindings
        self.cancel_callback = cancel_callback

        # If no `cancel_callback` was given, and we're creating the progress
        # bar from the main thread. Cancel by sending a `KeyboardInterrupt` to
        # the main thread.
        if self.cancel_callback is None and in_main_thread():

            def keyboard_interrupt_to_main_thread() -> None:
                os.kill(os.getpid(), signal.SIGINT)

            self.cancel_callback = keyboard_interrupt_to_main_thread

        # Note that we use __stderr__ as default error output, because that
        # works best with `patch_stdout`.
        self.color_depth = color_depth
        self.output = output or get_app_session().output
        self.input = input or get_app_session().input

        self._thread: threading.Thread | None = None

        self._has_sigwinch = False
        self._app_started = threading.Event()

    def __enter__(self) -> ProgressBar:
        # Create UI Application.
        title_toolbar = ConditionalContainer(
            Window(
                FormattedTextControl(lambda: self.title),
                height=1,
                style="class:progressbar,title",
            ),
            filter=Condition(lambda: self.title is not None),
        )

        bottom_toolbar = ConditionalContainer(
            Window(
                FormattedTextControl(
                    lambda: self.bottom_toolbar, style="class:bottom-toolbar.text"
                ),
                style="class:bottom-toolbar",
                height=1,
            ),
            filter=~is_done
            & renderer_height_is_known
            & Condition(lambda: self.bottom_toolbar is not None),
        )

        def width_for_formatter(formatter: Formatter) -> AnyDimension:
            # Needs to be passed as callable (partial) to the 'width'
            # parameter, because we want to call it on every resize.
            return formatter.get_width(progress_bar=self)

        progress_controls = [
            Window(
                content=_ProgressControl(self, f, self.cancel_callback),
                width=functools.partial(width_for_formatter, f),
            )
            for f in self.formatters
        ]

        self.app: Application[None] = Application(
            min_redraw_interval=0.05,
            layout=Layout(
                HSplit(
                    [
                        title_toolbar,
                        VSplit(
                            progress_controls,
                            height=lambda: D(
                                preferred=len(self.counters), max=len(self.counters)
                            ),
                        ),
                        Window(),
                        bottom_toolbar,
                    ]
                )
            ),
            style=self.style,
            key_bindings=self.key_bindings,
            refresh_interval=0.3,
            color_depth=self.color_depth,
            output=self.output,
            input=self.input,
        )

        # Run application in different thread.
        def run() -> None:
            try:
                self.app.run(pre_run=self._app_started.set)
            except BaseException as e:
                traceback.print_exc()
                print(e)

        ctx: contextvars.Context = contextvars.copy_context()

        self._thread = threading.Thread(target=ctx.run, args=(run,))
        self._thread.start()

        return self

    def __exit__(self, *a: object) -> None:
        # Wait for the app to be started. Make sure we don't quit earlier,
        # otherwise `self.app.exit` won't terminate the app because
        # `self.app.future` has not yet been set.
        self._app_started.wait()

        # Quit UI application.
        if self.app.is_running and self.app.loop is not None:
            self.app.loop.call_soon_threadsafe(self.app.exit)

        if self._thread is not None:
            self._thread.join()

    def __call__(
        self,
        data: Iterable[_T] | None = None,
        label: AnyFormattedText = "",
        remove_when_done: bool = False,
        total: int | None = None,
    ) -> ProgressBarCounter[_T]:
        """
        Start a new counter.

        :param label: Title text or description for this progress. (This can be
            formatted text as well).
        :param remove_when_done: When `True`, hide this progress bar.
        :param total: Specify the maximum value if it can't be calculated by
            calling ``len``.
        """
        counter = ProgressBarCounter(
            self, data, label=label, remove_when_done=remove_when_done, total=total
        )
        self.counters.append(counter)
        return counter

    def invalidate(self) -> None:
        self.app.invalidate()


class _ProgressControl(UIControl):
    """
    User control for the progress bar.
    """

    def __init__(
        self,
        progress_bar: ProgressBar,
        formatter: Formatter,
        cancel_callback: Callable[[], None] | None,
    ) -> None:
        self.progress_bar = progress_bar
        self.formatter = formatter
        self._key_bindings = create_key_bindings(cancel_callback)

    def create_content(self, width: int, height: int) -> UIContent:
        items: list[StyleAndTextTuples] = []

        for pr in self.progress_bar.counters:
            try:
                text = self.formatter.format(self.progress_bar, pr, width)
            except BaseException:
                traceback.print_exc()
                text = "ERROR"

            items.append(to_formatted_text(text))

        def get_line(i: int) -> StyleAndTextTuples:
            return items[i]

        return UIContent(get_line=get_line, line_count=len(items), show_cursor=False)

    def is_focusable(self) -> bool:
        return True  # Make sure that the key bindings work.

    def get_key_bindings(self) -> KeyBindings:
        return self._key_bindings


_CounterItem = TypeVar("_CounterItem", covariant=True)


class ProgressBarCounter(Generic[_CounterItem]):
    """
    An individual counter (A progress bar can have multiple counters).
    """

    def __init__(
        self,
        progress_bar: ProgressBar,
        data: Iterable[_CounterItem] | None = None,
        label: AnyFormattedText = "",
        remove_when_done: bool = False,
        total: int | None = None,
    ) -> None:
        self.start_time = datetime.datetime.now()
        self.stop_time: datetime.datetime | None = None
        self.progress_bar = progress_bar
        self.data = data
        self.items_completed = 0
        self.label = label
        self.remove_when_done = remove_when_done
        self._done = False
        self.total: int | None

        if total is None:
            try:
                self.total = len(cast(Sized, data))
            except TypeError:
                self.total = None  # We don't know the total length.
        else:
            self.total = total

    def __iter__(self) -> Iterator[_CounterItem]:
        if self.data is not None:
            try:
                for item in self.data:
                    yield item
                    self.item_completed()

                # Only done if we iterate to the very end.
                self.done = True
            finally:
                # Ensure counter has stopped even if we did not iterate to the
                # end (e.g. break or exceptions).
                self.stopped = True
        else:
            raise NotImplementedError("No data defined to iterate over.")

    def item_completed(self) -> None:
        """
        Start handling the next item.

        (Can be called manually in case we don't have a collection to loop through.)
        """
        self.items_completed += 1
        self.progress_bar.invalidate()

    @property
    def done(self) -> bool:
        """Whether a counter has been completed.

        Done counter have been stopped (see stopped) and removed depending on
        remove_when_done value.

        Contrast this with stopped. A stopped counter may be terminated before
        100% completion. A done counter has reached its 100% completion.
        """
        return self._done

    @done.setter
    def done(self, value: bool) -> None:
        self._done = value
        self.stopped = value

        if value and self.remove_when_done:
            self.progress_bar.counters.remove(self)

    @property
    def stopped(self) -> bool:
        """Whether a counter has been stopped.

        Stopped counters no longer have increasing time_elapsed. This distinction is
        also used to prevent the Bar formatter with unknown totals from continuing to run.

        A stopped counter (but not done) can be used to signal that a given counter has
        encountered an error but allows other counters to continue
        (e.g. download X of Y failed). Given how only done counters are removed
        (see remove_when_done) this can help aggregate failures from a large number of
        successes.

        Contrast this with done. A done counter has reached its 100% completion.
        A stopped counter may be terminated before 100% completion.
        """
        return self.stop_time is not None

    @stopped.setter
    def stopped(self, value: bool) -> None:
        if value:
            # This counter has not already been stopped.
            if not self.stop_time:
                self.stop_time = datetime.datetime.now()
        else:
            # Clearing any previously set stop_time.
            self.stop_time = None

    @property
    def percentage(self) -> float:
        if self.total is None:
            return 0
        else:
            return self.items_completed * 100 / max(self.total, 1)

    @property
    def time_elapsed(self) -> datetime.timedelta:
        """
        Return how much time has been elapsed since the start.
        """
        if self.stop_time is None:
            return datetime.datetime.now() - self.start_time
        else:
            return self.stop_time - self.start_time

    @property
    def time_left(self) -> datetime.timedelta | None:
        """
        Timedelta representing the time left.
        """
        if self.total is None or not self.percentage:
            return None
        elif self.done or self.stopped:
            return datetime.timedelta(0)
        else:
            return self.time_elapsed * (100 - self.percentage) / self.percentage
