from __future__ import annotations

import asyncio
import contextvars
import os
import re
import signal
import sys
import threading
import time
from asyncio import (
    AbstractEventLoop,
    Future,
    Task,
    ensure_future,
    get_running_loop,
    sleep,
)
from contextlib import ExitStack, contextmanager
from subprocess import Popen
from traceback import format_tb
from typing import (
    Any,
    Callable,
    Coroutine,
    Generator,
    Generic,
    Hashable,
    Iterable,
    Iterator,
    TypeVar,
    cast,
    overload,
)

from prompt_toolkit.buffer import Buffer
from prompt_toolkit.cache import SimpleCache
from prompt_toolkit.clipboard import Clipboard, InMemoryClipboard
from prompt_toolkit.cursor_shapes import AnyCursorShapeConfig, to_cursor_shape_config
from prompt_toolkit.data_structures import Size
from prompt_toolkit.enums import EditingMode
from prompt_toolkit.eventloop import (
    InputHook,
    get_traceback_from_context,
    new_eventloop_with_inputhook,
    run_in_executor_with_context,
)
from prompt_toolkit.eventloop.utils import call_soon_threadsafe
from prompt_toolkit.filters import Condition, Filter, FilterOrBool, to_filter
from prompt_toolkit.formatted_text import AnyFormattedText
from prompt_toolkit.input.base import Input
from prompt_toolkit.input.typeahead import get_typeahead, store_typeahead
from prompt_toolkit.key_binding.bindings.page_navigation import (
    load_page_navigation_bindings,
)
from prompt_toolkit.key_binding.defaults import load_key_bindings
from prompt_toolkit.key_binding.emacs_state import EmacsState
from prompt_toolkit.key_binding.key_bindings import (
    Binding,
    ConditionalKeyBindings,
    GlobalOnlyKeyBindings,
    KeyBindings,
    KeyBindingsBase,
    KeysTuple,
    merge_key_bindings,
)
from prompt_toolkit.key_binding.key_processor import KeyPressEvent, KeyProcessor
from prompt_toolkit.key_binding.vi_state import ViState
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout.containers import Container, Window
from prompt_toolkit.layout.controls import BufferControl, UIControl
from prompt_toolkit.layout.dummy import create_dummy_layout
from prompt_toolkit.layout.layout import Layout, walk
from prompt_toolkit.output import ColorDepth, Output
from prompt_toolkit.renderer import Renderer, print_formatted_text
from prompt_toolkit.search import SearchState
from prompt_toolkit.styles import (
    BaseStyle,
    DummyStyle,
    DummyStyleTransformation,
    DynamicStyle,
    StyleTransformation,
    default_pygments_style,
    default_ui_style,
    merge_styles,
)
from prompt_toolkit.utils import Event, in_main_thread

from .current import get_app_session, set_app
from .run_in_terminal import in_terminal, run_in_terminal

__all__ = [
    "Application",
]


E = KeyPressEvent
_AppResult = TypeVar("_AppResult")
ApplicationEventHandler = Callable[["Application[_AppResult]"], None]

_SIGWINCH = getattr(signal, "SIGWINCH", None)
_SIGTSTP = getattr(signal, "SIGTSTP", None)


class Application(Generic[_AppResult]):
    """
    The main Application class!
    This glues everything together.

    :param layout: A :class:`~prompt_toolkit.layout.Layout` instance.
    :param key_bindings:
        :class:`~prompt_toolkit.key_binding.KeyBindingsBase` instance for
        the key bindings.
    :param clipboard: :class:`~prompt_toolkit.clipboard.Clipboard` to use.
    :param full_screen: When True, run the application on the alternate screen buffer.
    :param color_depth: Any :class:`~.ColorDepth` value, a callable that
        returns a :class:`~.ColorDepth` or `None` for default.
    :param erase_when_done: (bool) Clear the application output when it finishes.
    :param reverse_vi_search_direction: Normally, in Vi mode, a '/' searches
        forward and a '?' searches backward. In Readline mode, this is usually
        reversed.
    :param min_redraw_interval: Number of seconds to wait between redraws. Use
        this for applications where `invalidate` is called a lot. This could cause
        a lot of terminal output, which some terminals are not able to process.

        `None` means that every `invalidate` will be scheduled right away
        (which is usually fine).

        When one `invalidate` is called, but a scheduled redraw of a previous
        `invalidate` call has not been executed yet, nothing will happen in any
        case.

    :param max_render_postpone_time: When there is high CPU (a lot of other
        scheduled calls), postpone the rendering max x seconds.  '0' means:
        don't postpone. '.5' means: try to draw at least twice a second.

    :param refresh_interval: Automatically invalidate the UI every so many
        seconds. When `None` (the default), only invalidate when `invalidate`
        has been called.

    :param terminal_size_polling_interval: Poll the terminal size every so many
        seconds. Useful if the applications runs in a thread other then then
        main thread where SIGWINCH can't be handled, or on Windows.

    Filters:

    :param mouse_support: (:class:`~prompt_toolkit.filters.Filter` or
        boolean). When True, enable mouse support.
    :param paste_mode: :class:`~prompt_toolkit.filters.Filter` or boolean.
    :param editing_mode: :class:`~prompt_toolkit.enums.EditingMode`.

    :param enable_page_navigation_bindings: When `True`, enable the page
        navigation key bindings. These include both Emacs and Vi bindings like
        page-up, page-down and so on to scroll through pages. Mostly useful for
        creating an editor or other full screen applications. Probably, you
        don't want this for the implementation of a REPL. By default, this is
        enabled if `full_screen` is set.

    Callbacks (all of these should accept an
    :class:`~prompt_toolkit.application.Application` object as input.)

    :param on_reset: Called during reset.
    :param on_invalidate: Called when the UI has been invalidated.
    :param before_render: Called right before rendering.
    :param after_render: Called right after rendering.

    I/O:
    (Note that the preferred way to change the input/output is by creating an
    `AppSession` with the required input/output objects. If you need multiple
    applications running at the same time, you have to create a separate
    `AppSession` using a `with create_app_session():` block.

    :param input: :class:`~prompt_toolkit.input.Input` instance.
    :param output: :class:`~prompt_toolkit.output.Output` instance. (Probably
                   Vt100_Output or Win32Output.)

    Usage:

        app = Application(...)
        app.run()

        # Or
        await app.run_async()
    """

    def __init__(
        self,
        layout: Layout | None = None,
        style: BaseStyle | None = None,
        include_default_pygments_style: FilterOrBool = True,
        style_transformation: StyleTransformation | None = None,
        key_bindings: KeyBindingsBase | None = None,
        clipboard: Clipboard | None = None,
        full_screen: bool = False,
        color_depth: (ColorDepth | Callable[[], ColorDepth | None] | None) = None,
        mouse_support: FilterOrBool = False,
        enable_page_navigation_bindings: None
        | (FilterOrBool) = None,  # Can be None, True or False.
        paste_mode: FilterOrBool = False,
        editing_mode: EditingMode = EditingMode.EMACS,
        erase_when_done: bool = False,
        reverse_vi_search_direction: FilterOrBool = False,
        min_redraw_interval: float | int | None = None,
        max_render_postpone_time: float | int | None = 0.01,
        refresh_interval: float | None = None,
        terminal_size_polling_interval: float | None = 0.5,
        cursor: AnyCursorShapeConfig = None,
        on_reset: ApplicationEventHandler[_AppResult] | None = None,
        on_invalidate: ApplicationEventHandler[_AppResult] | None = None,
        before_render: ApplicationEventHandler[_AppResult] | None = None,
        after_render: ApplicationEventHandler[_AppResult] | None = None,
        # I/O.
        input: Input | None = None,
        output: Output | None = None,
    ) -> None:
        # If `enable_page_navigation_bindings` is not specified, enable it in
        # case of full screen applications only. This can be overridden by the user.
        if enable_page_navigation_bindings is None:
            enable_page_navigation_bindings = Condition(lambda: self.full_screen)

        paste_mode = to_filter(paste_mode)
        mouse_support = to_filter(mouse_support)
        reverse_vi_search_direction = to_filter(reverse_vi_search_direction)
        enable_page_navigation_bindings = to_filter(enable_page_navigation_bindings)
        include_default_pygments_style = to_filter(include_default_pygments_style)

        if layout is None:
            layout = create_dummy_layout()

        if style_transformation is None:
            style_transformation = DummyStyleTransformation()

        self.style = style
        self.style_transformation = style_transformation

        # Key bindings.
        self.key_bindings = key_bindings
        self._default_bindings = load_key_bindings()
        self._page_navigation_bindings = load_page_navigation_bindings()

        self.layout = layout
        self.clipboard = clipboard or InMemoryClipboard()
        self.full_screen: bool = full_screen
        self._color_depth = color_depth
        self.mouse_support = mouse_support

        self.paste_mode = paste_mode
        self.editing_mode = editing_mode
        self.erase_when_done = erase_when_done
        self.reverse_vi_search_direction = reverse_vi_search_direction
        self.enable_page_navigation_bindings = enable_page_navigation_bindings
        self.min_redraw_interval = min_redraw_interval
        self.max_render_postpone_time = max_render_postpone_time
        self.refresh_interval = refresh_interval
        self.terminal_size_polling_interval = terminal_size_polling_interval

        self.cursor = to_cursor_shape_config(cursor)

        # Events.
        self.on_invalidate = Event(self, on_invalidate)
        self.on_reset = Event(self, on_reset)
        self.before_render = Event(self, before_render)
        self.after_render = Event(self, after_render)

        # I/O.
        session = get_app_session()
        self.output = output or session.output
        self.input = input or session.input

        # List of 'extra' functions to execute before a Application.run.
        self.pre_run_callables: list[Callable[[], None]] = []

        self._is_running = False
        self.future: Future[_AppResult] | None = None
        self.loop: AbstractEventLoop | None = None
        self._loop_thread: threading.Thread | None = None
        self.context: contextvars.Context | None = None

        #: Quoted insert. This flag is set if we go into quoted insert mode.
        self.quoted_insert = False

        #: Vi state. (For Vi key bindings.)
        self.vi_state = ViState()
        self.emacs_state = EmacsState()

        #: When to flush the input (For flushing escape keys.) This is important
        #: on terminals that use vt100 input. We can't distinguish the escape
        #: key from for instance the left-arrow key, if we don't know what follows
        #: after "\x1b". This little timer will consider "\x1b" to be escape if
        #: nothing did follow in this time span.
        #: This seems to work like the `ttimeoutlen` option in Vim.
        self.ttimeoutlen = 0.5  # Seconds.

        #: Like Vim's `timeoutlen` option. This can be `None` or a float.  For
        #: instance, suppose that we have a key binding AB and a second key
        #: binding A. If the uses presses A and then waits, we don't handle
        #: this binding yet (unless it was marked 'eager'), because we don't
        #: know what will follow. This timeout is the maximum amount of time
        #: that we wait until we call the handlers anyway. Pass `None` to
        #: disable this timeout.
        self.timeoutlen = 1.0

        #: The `Renderer` instance.
        # Make sure that the same stdout is used, when a custom renderer has been passed.
        self._merged_style = self._create_merged_style(include_default_pygments_style)

        self.renderer = Renderer(
            self._merged_style,
            self.output,
            full_screen=full_screen,
            mouse_support=mouse_support,
            cpr_not_supported_callback=self.cpr_not_supported_callback,
        )

        #: Render counter. This one is increased every time the UI is rendered.
        #: It can be used as a key for caching certain information during one
        #: rendering.
        self.render_counter = 0

        # Invalidate flag. When 'True', a repaint has been scheduled.
        self._invalidated = False
        self._invalidate_events: list[
            Event[object]
        ] = []  # Collection of 'invalidate' Event objects.
        self._last_redraw_time = 0.0  # Unix timestamp of last redraw. Used when
        # `min_redraw_interval` is given.

        #: The `InputProcessor` instance.
        self.key_processor = KeyProcessor(_CombinedRegistry(self))

        # If `run_in_terminal` was called. This will point to a `Future` what will be
        # set at the point when the previous run finishes.
        self._running_in_terminal = False
        self._running_in_terminal_f: Future[None] | None = None

        # Trigger initialize callback.
        self.reset()

    def _create_merged_style(self, include_default_pygments_style: Filter) -> BaseStyle:
        """
        Create a `Style` object that merges the default UI style, the default
        pygments style, and the custom user style.
        """
        dummy_style = DummyStyle()
        pygments_style = default_pygments_style()

        @DynamicStyle
        def conditional_pygments_style() -> BaseStyle:
            if include_default_pygments_style():
                return pygments_style
            else:
                return dummy_style

        return merge_styles(
            [
                default_ui_style(),
                conditional_pygments_style,
                DynamicStyle(lambda: self.style),
            ]
        )

    @property
    def color_depth(self) -> ColorDepth:
        """
        The active :class:`.ColorDepth`.

        The current value is determined as follows:

        - If a color depth was given explicitly to this application, use that
          value.
        - Otherwise, fall back to the color depth that is reported by the
          :class:`.Output` implementation. If the :class:`.Output` class was
          created using `output.defaults.create_output`, then this value is
          coming from the $PROMPT_TOOLKIT_COLOR_DEPTH environment variable.
        """
        depth = self._color_depth

        if callable(depth):
            depth = depth()

        if depth is None:
            depth = self.output.get_default_color_depth()

        return depth

    @property
    def current_buffer(self) -> Buffer:
        """
        The currently focused :class:`~.Buffer`.

        (This returns a dummy :class:`.Buffer` when none of the actual buffers
        has the focus. In this case, it's really not practical to check for
        `None` values or catch exceptions every time.)
        """
        return self.layout.current_buffer or Buffer(
            name="dummy-buffer"
        )  # Dummy buffer.

    @property
    def current_search_state(self) -> SearchState:
        """
        Return the current :class:`.SearchState`. (The one for the focused
        :class:`.BufferControl`.)
        """
        ui_control = self.layout.current_control
        if isinstance(ui_control, BufferControl):
            return ui_control.search_state
        else:
            return SearchState()  # Dummy search state.  (Don't return None!)

    def reset(self) -> None:
        """
        Reset everything, for reading the next input.
        """
        # Notice that we don't reset the buffers. (This happens just before
        # returning, and when we have multiple buffers, we clearly want the
        # content in the other buffers to remain unchanged between several
        # calls of `run`. (And the same is true for the focus stack.)

        self.exit_style = ""

        self._background_tasks: set[Task[None]] = set()

        self.renderer.reset()
        self.key_processor.reset()
        self.layout.reset()
        self.vi_state.reset()
        self.emacs_state.reset()

        # Trigger reset event.
        self.on_reset.fire()

        # Make sure that we have a 'focusable' widget focused.
        # (The `Layout` class can't determine this.)
        layout = self.layout

        if not layout.current_control.is_focusable():
            for w in layout.find_all_windows():
                if w.content.is_focusable():
                    layout.current_window = w
                    break

    def invalidate(self) -> None:
        """
        Thread safe way of sending a repaint trigger to the input event loop.
        """
        if not self._is_running:
            # Don't schedule a redraw if we're not running.
            # Otherwise, `get_running_loop()` in `call_soon_threadsafe` can fail.
            # See: https://github.com/dbcli/mycli/issues/797
            return

        # `invalidate()` called if we don't have a loop yet (not running?), or
        # after the event loop was closed.
        if self.loop is None or self.loop.is_closed():
            return

        # Never schedule a second redraw, when a previous one has not yet been
        # executed. (This should protect against other threads calling
        # 'invalidate' many times, resulting in 100% CPU.)
        if self._invalidated:
            return
        else:
            self._invalidated = True

        # Trigger event.
        self.loop.call_soon_threadsafe(self.on_invalidate.fire)

        def redraw() -> None:
            self._invalidated = False
            self._redraw()

        def schedule_redraw() -> None:
            call_soon_threadsafe(
                redraw, max_postpone_time=self.max_render_postpone_time, loop=self.loop
            )

        if self.min_redraw_interval:
            # When a minimum redraw interval is set, wait minimum this amount
            # of time between redraws.
            diff = time.time() - self._last_redraw_time
            if diff < self.min_redraw_interval:

                async def redraw_in_future() -> None:
                    await sleep(cast(float, self.min_redraw_interval) - diff)
                    schedule_redraw()

                self.loop.call_soon_threadsafe(
                    lambda: self.create_background_task(redraw_in_future())
                )
            else:
                schedule_redraw()
        else:
            schedule_redraw()

    @property
    def invalidated(self) -> bool:
        "True when a redraw operation has been scheduled."
        return self._invalidated

    def _redraw(self, render_as_done: bool = False) -> None:
        """
        Render the command line again. (Not thread safe!) (From other threads,
        or if unsure, use :meth:`.Application.invalidate`.)

        :param render_as_done: make sure to put the cursor after the UI.
        """

        def run_in_context() -> None:
            # Only draw when no sub application was started.
            if self._is_running and not self._running_in_terminal:
                if self.min_redraw_interval:
                    self._last_redraw_time = time.time()

                # Render
                self.render_counter += 1
                self.before_render.fire()

                if render_as_done:
                    if self.erase_when_done:
                        self.renderer.erase()
                    else:
                        # Draw in 'done' state and reset renderer.
                        self.renderer.render(self, self.layout, is_done=render_as_done)
                else:
                    self.renderer.render(self, self.layout)

                self.layout.update_parents_relations()

                # Fire render event.
                self.after_render.fire()

                self._update_invalidate_events()

        # NOTE: We want to make sure this Application is the active one. The
        #       invalidate function is often called from a context where this
        #       application is not the active one. (Like the
        #       `PromptSession._auto_refresh_context`).
        #       We copy the context in case the context was already active, to
        #       prevent RuntimeErrors. (The rendering is not supposed to change
        #       any context variables.)
        if self.context is not None:
            self.context.copy().run(run_in_context)

    def _start_auto_refresh_task(self) -> None:
        """
        Start a while/true loop in the background for automatic invalidation of
        the UI.
        """
        if self.refresh_interval is not None and self.refresh_interval != 0:

            async def auto_refresh(refresh_interval: float) -> None:
                while True:
                    await sleep(refresh_interval)
                    self.invalidate()

            self.create_background_task(auto_refresh(self.refresh_interval))

    def _update_invalidate_events(self) -> None:
        """
        Make sure to attach 'invalidate' handlers to all invalidate events in
        the UI.
        """
        # Remove all the original event handlers. (Components can be removed
        # from the UI.)
        for ev in self._invalidate_events:
            ev -= self._invalidate_handler

        # Gather all new events.
        # (All controls are able to invalidate themselves.)
        def gather_events() -> Iterable[Event[object]]:
            for c in self.layout.find_all_controls():
                yield from c.get_invalidate_events()

        self._invalidate_events = list(gather_events())

        for ev in self._invalidate_events:
            ev += self._invalidate_handler

    def _invalidate_handler(self, sender: object) -> None:
        """
        Handler for invalidate events coming from UIControls.

        (This handles the difference in signature between event handler and
        `self.invalidate`. It also needs to be a method -not a nested
        function-, so that we can remove it again .)
        """
        self.invalidate()

    def _on_resize(self) -> None:
        """
        When the window size changes, we erase the current output and request
        again the cursor position. When the CPR answer arrives, the output is
        drawn again.
        """
        # Erase, request position (when cursor is at the start position)
        # and redraw again. -- The order is important.
        self.renderer.erase(leave_alternate_screen=False)
        self._request_absolute_cursor_position()
        self._redraw()

    def _pre_run(self, pre_run: Callable[[], None] | None = None) -> None:
        """
        Called during `run`.

        `self.future` should be set to the new future at the point where this
        is called in order to avoid data races. `pre_run` can be used to set a
        `threading.Event` to synchronize with UI termination code, running in
        another thread that would call `Application.exit`. (See the progress
        bar code for an example.)
        """
        if pre_run:
            pre_run()

        # Process registered "pre_run_callables" and clear list.
        for c in self.pre_run_callables:
            c()
        del self.pre_run_callables[:]

    async def run_async(
        self,
        pre_run: Callable[[], None] | None = None,
        set_exception_handler: bool = True,
        handle_sigint: bool = True,
        slow_callback_duration: float = 0.5,
    ) -> _AppResult:
        """
        Run the prompt_toolkit :class:`~prompt_toolkit.application.Application`
        until :meth:`~prompt_toolkit.application.Application.exit` has been
        called. Return the value that was passed to
        :meth:`~prompt_toolkit.application.Application.exit`.

        This is the main entry point for a prompt_toolkit
        :class:`~prompt_toolkit.application.Application` and usually the only
        place where the event loop is actually running.

        :param pre_run: Optional callable, which is called right after the
            "reset" of the application.
        :param set_exception_handler: When set, in case of an exception, go out
            of the alternate screen and hide the application, display the
            exception, and wait for the user to press ENTER.
        :param handle_sigint: Handle SIGINT signal if possible. This will call
            the `<sigint>` key binding when a SIGINT is received. (This only
            works in the main thread.)
        :param slow_callback_duration: Display warnings if code scheduled in
            the asyncio event loop takes more time than this. The asyncio
            default of `0.1` is sometimes not sufficient on a slow system,
            because exceptionally, the drawing of the app, which happens in the
            event loop, can take a bit longer from time to time.
        """
        assert not self._is_running, "Application is already running."

        if not in_main_thread() or sys.platform == "win32":
            # Handling signals in other threads is not supported.
            # Also on Windows, `add_signal_handler(signal.SIGINT, ...)` raises
            # `NotImplementedError`.
            # See: https://github.com/prompt-toolkit/python-prompt-toolkit/issues/1553
            handle_sigint = False

        async def _run_async(f: asyncio.Future[_AppResult]) -> _AppResult:
            context = contextvars.copy_context()
            self.context = context

            # Counter for cancelling 'flush' timeouts. Every time when a key is
            # pressed, we start a 'flush' timer for flushing our escape key. But
            # when any subsequent input is received, a new timer is started and
            # the current timer will be ignored.
            flush_task: asyncio.Task[None] | None = None

            # Reset.
            # (`self.future` needs to be set when `pre_run` is called.)
            self.reset()
            self._pre_run(pre_run)

            # Feed type ahead input first.
            self.key_processor.feed_multiple(get_typeahead(self.input))
            self.key_processor.process_keys()

            def read_from_input() -> None:
                nonlocal flush_task

                # Ignore when we aren't running anymore. This callback will
                # removed from the loop next time. (It could be that it was
                # still in the 'tasks' list of the loop.)
                # Except: if we need to process incoming CPRs.
                if not self._is_running and not self.renderer.waiting_for_cpr:
                    return

                # Get keys from the input object.
                keys = self.input.read_keys()

                # Feed to key processor.
                self.key_processor.feed_multiple(keys)
                self.key_processor.process_keys()

                # Quit when the input stream was closed.
                if self.input.closed:
                    if not f.done():
                        f.set_exception(EOFError)
                else:
                    # Automatically flush keys.
                    if flush_task:
                        flush_task.cancel()
                    flush_task = self.create_background_task(auto_flush_input())

            def read_from_input_in_context() -> None:
                # Ensure that key bindings callbacks are always executed in the
                # current context. This is important when key bindings are
                # accessing contextvars. (These callbacks are currently being
                # called from a different context. Underneath,
                # `loop.add_reader` is used to register the stdin FD.)
                # (We copy the context to avoid a `RuntimeError` in case the
                # context is already active.)
                context.copy().run(read_from_input)

            async def auto_flush_input() -> None:
                # Flush input after timeout.
                # (Used for flushing the enter key.)
                # This sleep can be cancelled, in that case we won't flush yet.
                await sleep(self.ttimeoutlen)
                flush_input()

            def flush_input() -> None:
                if not self.is_done:
                    # Get keys, and feed to key processor.
                    keys = self.input.flush_keys()
                    self.key_processor.feed_multiple(keys)
                    self.key_processor.process_keys()

                    if self.input.closed:
                        f.set_exception(EOFError)

            # Enter raw mode, attach input and attach WINCH event handler.
            with self.input.raw_mode(), self.input.attach(
                read_from_input_in_context
            ), attach_winch_signal_handler(self._on_resize):
                # Draw UI.
                self._request_absolute_cursor_position()
                self._redraw()
                self._start_auto_refresh_task()

                self.create_background_task(self._poll_output_size())

                # Wait for UI to finish.
                try:
                    result = await f
                finally:
                    # In any case, when the application finishes.
                    # (Successful, or because of an error.)
                    try:
                        self._redraw(render_as_done=True)
                    finally:
                        # _redraw has a good chance to fail if it calls widgets
                        # with bad code. Make sure to reset the renderer
                        # anyway.
                        self.renderer.reset()

                        # Unset `is_running`, this ensures that possibly
                        # scheduled draws won't paint during the following
                        # yield.
                        self._is_running = False

                        # Detach event handlers for invalidate events.
                        # (Important when a UIControl is embedded in multiple
                        # applications, like ptterm in pymux. An invalidate
                        # should not trigger a repaint in terminated
                        # applications.)
                        for ev in self._invalidate_events:
                            ev -= self._invalidate_handler
                        self._invalidate_events = []

                        # Wait for CPR responses.
                        if self.output.responds_to_cpr:
                            await self.renderer.wait_for_cpr_responses()

                        # Wait for the run-in-terminals to terminate.
                        previous_run_in_terminal_f = self._running_in_terminal_f

                        if previous_run_in_terminal_f:
                            await previous_run_in_terminal_f

                        # Store unprocessed input as typeahead for next time.
                        store_typeahead(self.input, self.key_processor.empty_queue())

                return result

        @contextmanager
        def set_loop() -> Iterator[AbstractEventLoop]:
            loop = get_running_loop()
            self.loop = loop
            self._loop_thread = threading.current_thread()

            try:
                yield loop
            finally:
                self.loop = None
                self._loop_thread = None

        @contextmanager
        def set_is_running() -> Iterator[None]:
            self._is_running = True
            try:
                yield
            finally:
                self._is_running = False

        @contextmanager
        def set_handle_sigint(loop: AbstractEventLoop) -> Iterator[None]:
            if handle_sigint:
                with _restore_sigint_from_ctypes():
                    # save sigint handlers (python and os level)
                    # See: https://github.com/prompt-toolkit/python-prompt-toolkit/issues/1576
                    loop.add_signal_handler(
                        signal.SIGINT,
                        lambda *_: loop.call_soon_threadsafe(
                            self.key_processor.send_sigint
                        ),
                    )
                    try:
                        yield
                    finally:
                        loop.remove_signal_handler(signal.SIGINT)
            else:
                yield

        @contextmanager
        def set_exception_handler_ctx(loop: AbstractEventLoop) -> Iterator[None]:
            if set_exception_handler:
                previous_exc_handler = loop.get_exception_handler()
                loop.set_exception_handler(self._handle_exception)
                try:
                    yield
                finally:
                    loop.set_exception_handler(previous_exc_handler)

            else:
                yield

        @contextmanager
        def set_callback_duration(loop: AbstractEventLoop) -> Iterator[None]:
            # Set slow_callback_duration.
            original_slow_callback_duration = loop.slow_callback_duration
            loop.slow_callback_duration = slow_callback_duration
            try:
                yield
            finally:
                # Reset slow_callback_duration.
                loop.slow_callback_duration = original_slow_callback_duration

        @contextmanager
        def create_future(
            loop: AbstractEventLoop,
        ) -> Iterator[asyncio.Future[_AppResult]]:
            f = loop.create_future()
            self.future = f  # XXX: make sure to set this before calling '_redraw'.

            try:
                yield f
            finally:
                # Also remove the Future again. (This brings the
                # application back to its initial state, where it also
                # doesn't have a Future.)
                self.future = None

        with ExitStack() as stack:
            stack.enter_context(set_is_running())

            # Make sure to set `_invalidated` to `False` to begin with,
            # otherwise we're not going to paint anything. This can happen if
            # this application had run before on a different event loop, and a
            # paint was scheduled using `call_soon_threadsafe` with
            # `max_postpone_time`.
            self._invalidated = False

            loop = stack.enter_context(set_loop())

            stack.enter_context(set_handle_sigint(loop))
            stack.enter_context(set_exception_handler_ctx(loop))
            stack.enter_context(set_callback_duration(loop))
            stack.enter_context(set_app(self))
            stack.enter_context(self._enable_breakpointhook())

            f = stack.enter_context(create_future(loop))

            try:
                return await _run_async(f)
            finally:
                # Wait for the background tasks to be done. This needs to
                # go in the finally! If `_run_async` raises
                # `KeyboardInterrupt`, we still want to wait for the
                # background tasks.
                await self.cancel_and_wait_for_background_tasks()

        # The `ExitStack` above is defined in typeshed in a way that it can
        # swallow exceptions. Without next line, mypy would think that there's
        # a possibility we don't return here. See:
        # https://github.com/python/mypy/issues/7726
        assert False, "unreachable"

    def run(
        self,
        pre_run: Callable[[], None] | None = None,
        set_exception_handler: bool = True,
        handle_sigint: bool = True,
        in_thread: bool = False,
        inputhook: InputHook | None = None,
    ) -> _AppResult:
        """
        A blocking 'run' call that waits until the UI is finished.

        This will run the application in a fresh asyncio event loop.

        :param pre_run: Optional callable, which is called right after the
            "reset" of the application.
        :param set_exception_handler: When set, in case of an exception, go out
            of the alternate screen and hide the application, display the
            exception, and wait for the user to press ENTER.
        :param in_thread: When true, run the application in a background
            thread, and block the current thread until the application
            terminates. This is useful if we need to be sure the application
            won't use the current event loop (asyncio does not support nested
            event loops). A new event loop will be created in this background
            thread, and that loop will also be closed when the background
            thread terminates. When this is used, it's especially important to
            make sure that all asyncio background tasks are managed through
            `get_appp().create_background_task()`, so that unfinished tasks are
            properly cancelled before the event loop is closed. This is used
            for instance in ptpython.
        :param handle_sigint: Handle SIGINT signal. Call the key binding for
            `Keys.SIGINT`. (This only works in the main thread.)
        """
        if in_thread:
            result: _AppResult
            exception: BaseException | None = None

            def run_in_thread() -> None:
                nonlocal result, exception
                try:
                    result = self.run(
                        pre_run=pre_run,
                        set_exception_handler=set_exception_handler,
                        # Signal handling only works in the main thread.
                        handle_sigint=False,
                        inputhook=inputhook,
                    )
                except BaseException as e:
                    exception = e

            thread = threading.Thread(target=run_in_thread)
            thread.start()
            thread.join()

            if exception is not None:
                raise exception
            return result

        coro = self.run_async(
            pre_run=pre_run,
            set_exception_handler=set_exception_handler,
            handle_sigint=handle_sigint,
        )

        def _called_from_ipython() -> bool:
            try:
                return (
                    sys.modules["IPython"].version_info < (8, 18, 0, "")
                    and "IPython/terminal/interactiveshell.py"
                    in sys._getframe(3).f_code.co_filename
                )
            except BaseException:
                return False

        if inputhook is not None:
            # Create new event loop with given input hook and run the app.
            # In Python 3.12, we can use asyncio.run(loop_factory=...)
            # For now, use `run_until_complete()`.
            loop = new_eventloop_with_inputhook(inputhook)
            result = loop.run_until_complete(coro)
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()
            return result

        elif _called_from_ipython():
            # workaround to make input hooks work for IPython until
            # https://github.com/ipython/ipython/pull/14241 is merged.
            # IPython was setting the input hook by installing an event loop
            # previously.
            try:
                # See whether a loop was installed already. If so, use that.
                # That's required for the input hooks to work, they are
                # installed using `set_event_loop`.
                loop = asyncio.get_event_loop()
            except RuntimeError:
                # No loop installed. Run like usual.
                return asyncio.run(coro)
            else:
                # Use existing loop.
                return loop.run_until_complete(coro)

        else:
            # No loop installed. Run like usual.
            return asyncio.run(coro)

    def _handle_exception(
        self, loop: AbstractEventLoop, context: dict[str, Any]
    ) -> None:
        """
        Handler for event loop exceptions.
        This will print the exception, using run_in_terminal.
        """
        # For Python 2: we have to get traceback at this point, because
        # we're still in the 'except:' block of the event loop where the
        # traceback is still available. Moving this code in the
        # 'print_exception' coroutine will loose the exception.
        tb = get_traceback_from_context(context)
        formatted_tb = "".join(format_tb(tb))

        async def in_term() -> None:
            async with in_terminal():
                # Print output. Similar to 'loop.default_exception_handler',
                # but don't use logger. (This works better on Python 2.)
                print("\nUnhandled exception in event loop:")
                print(formatted_tb)
                print("Exception {}".format(context.get("exception")))

                await _do_wait_for_enter("Press ENTER to continue...")

        ensure_future(in_term())

    @contextmanager
    def _enable_breakpointhook(self) -> Generator[None, None, None]:
        """
        Install our custom breakpointhook for the duration of this context
        manager. (We will only install the hook if no other custom hook was
        set.)
        """
        if sys.breakpointhook == sys.__breakpointhook__:
            sys.breakpointhook = self._breakpointhook

            try:
                yield
            finally:
                sys.breakpointhook = sys.__breakpointhook__
        else:
            yield

    def _breakpointhook(self, *a: object, **kw: object) -> None:
        """
        Breakpointhook which uses PDB, but ensures that the application is
        hidden and input echoing is restored during each debugger dispatch.

        This can be called from any thread. In any case, the application's
        event loop will be blocked while the PDB input is displayed. The event
        will continue after leaving the debugger.
        """
        app = self
        # Inline import on purpose. We don't want to import pdb, if not needed.
        import pdb
        from types import FrameType

        TraceDispatch = Callable[[FrameType, str, Any], Any]

        @contextmanager
        def hide_app_from_eventloop_thread() -> Generator[None, None, None]:
            """Stop application if `__breakpointhook__` is called from within
            the App's event loop."""
            # Hide application.
            app.renderer.erase()

            # Detach input and dispatch to debugger.
            with app.input.detach():
                with app.input.cooked_mode():
                    yield

            # Note: we don't render the application again here, because
            # there's a good chance that there's a breakpoint on the next
            # line. This paint/erase cycle would move the PDB prompt back
            # to the middle of the screen.

        @contextmanager
        def hide_app_from_other_thread() -> Generator[None, None, None]:
            """Stop application if `__breakpointhook__` is called from a
            thread other than the App's event loop."""
            ready = threading.Event()
            done = threading.Event()

            async def in_loop() -> None:
                # from .run_in_terminal import in_terminal
                # async with in_terminal():
                #     ready.set()
                #     await asyncio.get_running_loop().run_in_executor(None, done.wait)
                #     return

                # Hide application.
                app.renderer.erase()

                # Detach input and dispatch to debugger.
                with app.input.detach():
                    with app.input.cooked_mode():
                        ready.set()
                        # Here we block the App's event loop thread until the
                        # debugger resumes. We could have used `with
                        # run_in_terminal.in_terminal():` like the commented
                        # code above, but it seems to work better if we
                        # completely stop the main event loop while debugging.
                        done.wait()

            self.create_background_task(in_loop())
            ready.wait()
            try:
                yield
            finally:
                done.set()

        class CustomPdb(pdb.Pdb):
            def trace_dispatch(
                self, frame: FrameType, event: str, arg: Any
            ) -> TraceDispatch:
                if app._loop_thread is None:
                    return super().trace_dispatch(frame, event, arg)

                if app._loop_thread == threading.current_thread():
                    with hide_app_from_eventloop_thread():
                        return super().trace_dispatch(frame, event, arg)

                with hide_app_from_other_thread():
                    return super().trace_dispatch(frame, event, arg)

        frame = sys._getframe().f_back
        CustomPdb(stdout=sys.__stdout__).set_trace(frame)

    def create_background_task(
        self, coroutine: Coroutine[Any, Any, None]
    ) -> asyncio.Task[None]:
        """
        Start a background task (coroutine) for the running application. When
        the `Application` terminates, unfinished background tasks will be
        cancelled.

        Given that we still support Python versions before 3.11, we can't use
        task groups (and exception groups), because of that, these background
        tasks are not allowed to raise exceptions. If they do, we'll call the
        default exception handler from the event loop.

        If at some point, we have Python 3.11 as the minimum supported Python
        version, then we can use a `TaskGroup` (with the lifetime of
        `Application.run_async()`, and run run the background tasks in there.

        This is not threadsafe.
        """
        loop = self.loop or get_running_loop()
        task: asyncio.Task[None] = loop.create_task(coroutine)
        self._background_tasks.add(task)

        task.add_done_callback(self._on_background_task_done)
        return task

    def _on_background_task_done(self, task: asyncio.Task[None]) -> None:
        """
        Called when a background task completes. Remove it from
        `_background_tasks`, and handle exceptions if any.
        """
        self._background_tasks.discard(task)

        if task.cancelled():
            return

        exc = task.exception()
        if exc is not None:
            get_running_loop().call_exception_handler(
                {
                    "message": f"prompt_toolkit.Application background task {task!r} "
                    "raised an unexpected exception.",
                    "exception": exc,
                    "task": task,
                }
            )

    async def cancel_and_wait_for_background_tasks(self) -> None:
        """
        Cancel all background tasks, and wait for the cancellation to complete.
        If any of the background tasks raised an exception, this will also
        propagate the exception.

        (If we had nurseries like Trio, this would be the `__aexit__` of a
        nursery.)
        """
        for task in self._background_tasks:
            task.cancel()

        # Wait until the cancellation of the background tasks completes.
        # `asyncio.wait()` does not propagate exceptions raised within any of
        # these tasks, which is what we want. Otherwise, we can't distinguish
        # between a `CancelledError` raised in this task because it got
        # cancelled, and a `CancelledError` raised on this `await` checkpoint,
        # because *we* got cancelled during the teardown of the application.
        # (If we get cancelled here, then it's important to not suppress the
        # `CancelledError`, and have it propagate.)
        # NOTE: Currently, if we get cancelled at this point then we can't wait
        #       for the cancellation to complete (in the future, we should be
        #       using anyio or Python's 3.11 TaskGroup.)
        #       Also, if we had exception groups, we could propagate an
        #       `ExceptionGroup` if something went wrong here. Right now, we
        #       don't propagate exceptions, but have them printed in
        #       `_on_background_task_done`.
        if len(self._background_tasks) > 0:
            await asyncio.wait(
                self._background_tasks, timeout=None, return_when=asyncio.ALL_COMPLETED
            )

    async def _poll_output_size(self) -> None:
        """
        Coroutine for polling the terminal dimensions.

        Useful for situations where `attach_winch_signal_handler` is not sufficient:
        - If we are not running in the main thread.
        - On Windows.
        """
        size: Size | None = None
        interval = self.terminal_size_polling_interval

        if interval is None:
            return

        while True:
            await asyncio.sleep(interval)
            new_size = self.output.get_size()

            if size is not None and new_size != size:
                self._on_resize()
            size = new_size

    def cpr_not_supported_callback(self) -> None:
        """
        Called when we don't receive the cursor position response in time.
        """
        if not self.output.responds_to_cpr:
            return  # We know about this already.

        def in_terminal() -> None:
            self.output.write(
                "WARNING: your terminal doesn't support cursor position requests (CPR).\r\n"
            )
            self.output.flush()

        run_in_terminal(in_terminal)

    @overload
    def exit(self) -> None:
        "Exit without arguments."

    @overload
    def exit(self, *, result: _AppResult, style: str = "") -> None:
        "Exit with `_AppResult`."

    @overload
    def exit(
        self, *, exception: BaseException | type[BaseException], style: str = ""
    ) -> None:
        "Exit with exception."

    def exit(
        self,
        result: _AppResult | None = None,
        exception: BaseException | type[BaseException] | None = None,
        style: str = "",
    ) -> None:
        """
        Exit application.

        .. note::

            If `Application.exit` is called before `Application.run()` is
            called, then the `Application` won't exit (because the
            `Application.future` doesn't correspond to the current run). Use a
            `pre_run` hook and an event to synchronize the closing if there's a
            chance this can happen.

        :param result: Set this result for the application.
        :param exception: Set this exception as the result for an application. For
            a prompt, this is often `EOFError` or `KeyboardInterrupt`.
        :param style: Apply this style on the whole content when quitting,
            often this is 'class:exiting' for a prompt. (Used when
            `erase_when_done` is not set.)
        """
        assert result is None or exception is None

        if self.future is None:
            raise Exception("Application is not running. Application.exit() failed.")

        if self.future.done():
            raise Exception("Return value already set. Application.exit() failed.")

        self.exit_style = style

        if exception is not None:
            self.future.set_exception(exception)
        else:
            self.future.set_result(cast(_AppResult, result))

    def _request_absolute_cursor_position(self) -> None:
        """
        Send CPR request.
        """
        # Note: only do this if the input queue is not empty, and a return
        # value has not been set. Otherwise, we won't be able to read the
        # response anyway.
        if not self.key_processor.input_queue and not self.is_done:
            self.renderer.request_absolute_cursor_position()

    async def run_system_command(
        self,
        command: str,
        wait_for_enter: bool = True,
        display_before_text: AnyFormattedText = "",
        wait_text: str = "Press ENTER to continue...",
    ) -> None:
        """
        Run system command (While hiding the prompt. When finished, all the
        output will scroll above the prompt.)

        :param command: Shell command to be executed.
        :param wait_for_enter: FWait for the user to press enter, when the
            command is finished.
        :param display_before_text: If given, text to be displayed before the
            command executes.
        :return: A `Future` object.
        """
        async with in_terminal():
            # Try to use the same input/output file descriptors as the one,
            # used to run this application.
            try:
                input_fd = self.input.fileno()
            except AttributeError:
                input_fd = sys.stdin.fileno()
            try:
                output_fd = self.output.fileno()
            except AttributeError:
                output_fd = sys.stdout.fileno()

            # Run sub process.
            def run_command() -> None:
                self.print_text(display_before_text)
                p = Popen(command, shell=True, stdin=input_fd, stdout=output_fd)
                p.wait()

            await run_in_executor_with_context(run_command)

            # Wait for the user to press enter.
            if wait_for_enter:
                await _do_wait_for_enter(wait_text)

    def suspend_to_background(self, suspend_group: bool = True) -> None:
        """
        (Not thread safe -- to be called from inside the key bindings.)
        Suspend process.

        :param suspend_group: When true, suspend the whole process group.
            (This is the default, and probably what you want.)
        """
        # Only suspend when the operating system supports it.
        # (Not on Windows.)
        if _SIGTSTP is not None:

            def run() -> None:
                signal = cast(int, _SIGTSTP)
                # Send `SIGTSTP` to own process.
                # This will cause it to suspend.

                # Usually we want the whole process group to be suspended. This
                # handles the case when input is piped from another process.
                if suspend_group:
                    os.kill(0, signal)
                else:
                    os.kill(os.getpid(), signal)

            run_in_terminal(run)

    def print_text(
        self, text: AnyFormattedText, style: BaseStyle | None = None
    ) -> None:
        """
        Print a list of (style_str, text) tuples to the output.
        (When the UI is running, this method has to be called through
        `run_in_terminal`, otherwise it will destroy the UI.)

        :param text: List of ``(style_str, text)`` tuples.
        :param style: Style class to use. Defaults to the active style in the CLI.
        """
        print_formatted_text(
            output=self.output,
            formatted_text=text,
            style=style or self._merged_style,
            color_depth=self.color_depth,
            style_transformation=self.style_transformation,
        )

    @property
    def is_running(self) -> bool:
        "`True` when the application is currently active/running."
        return self._is_running

    @property
    def is_done(self) -> bool:
        if self.future:
            return self.future.done()
        return False

    def get_used_style_strings(self) -> list[str]:
        """
        Return a list of used style strings. This is helpful for debugging, and
        for writing a new `Style`.
        """
        attrs_for_style = self.renderer._attrs_for_style

        if attrs_for_style:
            return sorted(
                re.sub(r"\s+", " ", style_str).strip()
                for style_str in attrs_for_style.keys()
            )

        return []


class _CombinedRegistry(KeyBindingsBase):
    """
    The `KeyBindings` of key bindings for a `Application`.
    This merges the global key bindings with the one of the current user
    control.
    """

    def __init__(self, app: Application[_AppResult]) -> None:
        self.app = app
        self._cache: SimpleCache[
            tuple[Window, frozenset[UIControl]], KeyBindingsBase
        ] = SimpleCache()

    @property
    def _version(self) -> Hashable:
        """Not needed - this object is not going to be wrapped in another
        KeyBindings object."""
        raise NotImplementedError

    @property
    def bindings(self) -> list[Binding]:
        """Not needed - this object is not going to be wrapped in another
        KeyBindings object."""
        raise NotImplementedError

    def _create_key_bindings(
        self, current_window: Window, other_controls: list[UIControl]
    ) -> KeyBindingsBase:
        """
        Create a `KeyBindings` object that merges the `KeyBindings` from the
        `UIControl` with all the parent controls and the global key bindings.
        """
        key_bindings = []
        collected_containers = set()

        # Collect key bindings from currently focused control and all parent
        # controls. Don't include key bindings of container parent controls.
        container: Container = current_window
        while True:
            collected_containers.add(container)
            kb = container.get_key_bindings()
            if kb is not None:
                key_bindings.append(kb)

            if container.is_modal():
                break

            parent = self.app.layout.get_parent(container)
            if parent is None:
                break
            else:
                container = parent

        # Include global bindings (starting at the top-model container).
        for c in walk(container):
            if c not in collected_containers:
                kb = c.get_key_bindings()
                if kb is not None:
                    key_bindings.append(GlobalOnlyKeyBindings(kb))

        # Add App key bindings
        if self.app.key_bindings:
            key_bindings.append(self.app.key_bindings)

        # Add mouse bindings.
        key_bindings.append(
            ConditionalKeyBindings(
                self.app._page_navigation_bindings,
                self.app.enable_page_navigation_bindings,
            )
        )
        key_bindings.append(self.app._default_bindings)

        # Reverse this list. The current control's key bindings should come
        # last. They need priority.
        key_bindings = key_bindings[::-1]

        return merge_key_bindings(key_bindings)

    @property
    def _key_bindings(self) -> KeyBindingsBase:
        current_window = self.app.layout.current_window
        other_controls = list(self.app.layout.find_all_controls())
        key = current_window, frozenset(other_controls)

        return self._cache.get(
            key, lambda: self._create_key_bindings(current_window, other_controls)
        )

    def get_bindings_for_keys(self, keys: KeysTuple) -> list[Binding]:
        return self._key_bindings.get_bindings_for_keys(keys)

    def get_bindings_starting_with_keys(self, keys: KeysTuple) -> list[Binding]:
        return self._key_bindings.get_bindings_starting_with_keys(keys)


async def _do_wait_for_enter(wait_text: AnyFormattedText) -> None:
    """
    Create a sub application to wait for the enter key press.
    This has two advantages over using 'input'/'raw_input':
    - This will share the same input/output I/O.
    - This doesn't block the event loop.
    """
    from prompt_toolkit.shortcuts import PromptSession

    key_bindings = KeyBindings()

    @key_bindings.add("enter")
    def _ok(event: E) -> None:
        event.app.exit()

    @key_bindings.add(Keys.Any)
    def _ignore(event: E) -> None:
        "Disallow typing."
        pass

    session: PromptSession[None] = PromptSession(
        message=wait_text, key_bindings=key_bindings
    )
    try:
        await session.app.run_async()
    except KeyboardInterrupt:
        pass  # Control-c pressed. Don't propagate this error.


@contextmanager
def attach_winch_signal_handler(
    handler: Callable[[], None],
) -> Generator[None, None, None]:
    """
    Attach the given callback as a WINCH signal handler within the context
    manager. Restore the original signal handler when done.

    The `Application.run` method will register SIGWINCH, so that it will
    properly repaint when the terminal window resizes. However, using
    `run_in_terminal`, we can temporarily send an application to the
    background, and run an other app in between, which will then overwrite the
    SIGWINCH. This is why it's important to restore the handler when the app
    terminates.
    """
    # The tricky part here is that signals are registered in the Unix event
    # loop with a wakeup fd, but another application could have registered
    # signals using signal.signal directly. For now, the implementation is
    # hard-coded for the `asyncio.unix_events._UnixSelectorEventLoop`.

    # No WINCH? Then don't do anything.
    sigwinch = getattr(signal, "SIGWINCH", None)
    if sigwinch is None or not in_main_thread():
        yield
        return

    # Keep track of the previous handler.
    # (Only UnixSelectorEventloop has `_signal_handlers`.)
    loop = get_running_loop()
    previous_winch_handler = getattr(loop, "_signal_handlers", {}).get(sigwinch)

    try:
        loop.add_signal_handler(sigwinch, handler)
        yield
    finally:
        # Restore the previous signal handler.
        loop.remove_signal_handler(sigwinch)
        if previous_winch_handler is not None:
            loop.add_signal_handler(
                sigwinch,
                previous_winch_handler._callback,
                *previous_winch_handler._args,
            )


@contextmanager
def _restore_sigint_from_ctypes() -> Generator[None, None, None]:
    # The following functions are part of the stable ABI since python 3.2
    # See: https://docs.python.org/3/c-api/sys.html#c.PyOS_getsig
    # Inline import: these are not available on Pypy.
    try:
        from ctypes import c_int, c_void_p, pythonapi
    except ImportError:
        have_ctypes_signal = False
    else:
        # GraalPy has the functions, but they don't work
        have_ctypes_signal = sys.implementation.name != "graalpy"

    if have_ctypes_signal:
        # PyOS_sighandler_t PyOS_getsig(int i)
        pythonapi.PyOS_getsig.restype = c_void_p
        pythonapi.PyOS_getsig.argtypes = (c_int,)

        # PyOS_sighandler_t PyOS_setsig(int i, PyOS_sighandler_t h)
        pythonapi.PyOS_setsig.restype = c_void_p
        pythonapi.PyOS_setsig.argtypes = (
            c_int,
            c_void_p,
        )

    sigint = signal.getsignal(signal.SIGINT)
    if have_ctypes_signal:
        sigint_os = pythonapi.PyOS_getsig(signal.SIGINT)

    try:
        yield
    finally:
        if sigint is not None:
            signal.signal(signal.SIGINT, sigint)
        if have_ctypes_signal:
            pythonapi.PyOS_setsig(signal.SIGINT, sigint_os)
