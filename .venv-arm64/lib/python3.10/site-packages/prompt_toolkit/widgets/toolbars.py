from __future__ import annotations

from typing import Any

from prompt_toolkit.application.current import get_app
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.enums import SYSTEM_BUFFER
from prompt_toolkit.filters import (
    Condition,
    FilterOrBool,
    emacs_mode,
    has_arg,
    has_completions,
    has_focus,
    has_validation_error,
    to_filter,
    vi_mode,
    vi_navigation_mode,
)
from prompt_toolkit.formatted_text import (
    AnyFormattedText,
    StyleAndTextTuples,
    fragment_list_len,
    to_formatted_text,
)
from prompt_toolkit.key_binding.key_bindings import (
    ConditionalKeyBindings,
    KeyBindings,
    KeyBindingsBase,
    merge_key_bindings,
)
from prompt_toolkit.key_binding.key_processor import KeyPressEvent
from prompt_toolkit.key_binding.vi_state import InputMode
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout.containers import ConditionalContainer, Container, Window
from prompt_toolkit.layout.controls import (
    BufferControl,
    FormattedTextControl,
    SearchBufferControl,
    UIContent,
    UIControl,
)
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.layout.processors import BeforeInput
from prompt_toolkit.lexers import SimpleLexer
from prompt_toolkit.search import SearchDirection

__all__ = [
    "ArgToolbar",
    "CompletionsToolbar",
    "FormattedTextToolbar",
    "SearchToolbar",
    "SystemToolbar",
    "ValidationToolbar",
]

E = KeyPressEvent


class FormattedTextToolbar(Window):
    def __init__(self, text: AnyFormattedText, style: str = "", **kw: Any) -> None:
        # Note: The style needs to be applied to the toolbar as a whole, not
        #       just the `FormattedTextControl`.
        super().__init__(
            FormattedTextControl(text, **kw),
            style=style,
            dont_extend_height=True,
            height=Dimension(min=1),
        )


class SystemToolbar:
    """
    Toolbar for a system prompt.

    :param prompt: Prompt to be displayed to the user.
    """

    def __init__(
        self,
        prompt: AnyFormattedText = "Shell command: ",
        enable_global_bindings: FilterOrBool = True,
    ) -> None:
        self.prompt = prompt
        self.enable_global_bindings = to_filter(enable_global_bindings)

        self.system_buffer = Buffer(name=SYSTEM_BUFFER)

        self._bindings = self._build_key_bindings()

        self.buffer_control = BufferControl(
            buffer=self.system_buffer,
            lexer=SimpleLexer(style="class:system-toolbar.text"),
            input_processors=[
                BeforeInput(lambda: self.prompt, style="class:system-toolbar")
            ],
            key_bindings=self._bindings,
        )

        self.window = Window(
            self.buffer_control, height=1, style="class:system-toolbar"
        )

        self.container = ConditionalContainer(
            content=self.window, filter=has_focus(self.system_buffer)
        )

    def _get_display_before_text(self) -> StyleAndTextTuples:
        return [
            ("class:system-toolbar", "Shell command: "),
            ("class:system-toolbar.text", self.system_buffer.text),
            ("", "\n"),
        ]

    def _build_key_bindings(self) -> KeyBindingsBase:
        focused = has_focus(self.system_buffer)

        # Emacs
        emacs_bindings = KeyBindings()
        handle = emacs_bindings.add

        @handle("escape", filter=focused)
        @handle("c-g", filter=focused)
        @handle("c-c", filter=focused)
        def _cancel(event: E) -> None:
            "Hide system prompt."
            self.system_buffer.reset()
            event.app.layout.focus_last()

        @handle("enter", filter=focused)
        async def _accept(event: E) -> None:
            "Run system command."
            await event.app.run_system_command(
                self.system_buffer.text,
                display_before_text=self._get_display_before_text(),
            )
            self.system_buffer.reset(append_to_history=True)
            event.app.layout.focus_last()

        # Vi.
        vi_bindings = KeyBindings()
        handle = vi_bindings.add

        @handle("escape", filter=focused)
        @handle("c-c", filter=focused)
        def _cancel_vi(event: E) -> None:
            "Hide system prompt."
            event.app.vi_state.input_mode = InputMode.NAVIGATION
            self.system_buffer.reset()
            event.app.layout.focus_last()

        @handle("enter", filter=focused)
        async def _accept_vi(event: E) -> None:
            "Run system command."
            event.app.vi_state.input_mode = InputMode.NAVIGATION
            await event.app.run_system_command(
                self.system_buffer.text,
                display_before_text=self._get_display_before_text(),
            )
            self.system_buffer.reset(append_to_history=True)
            event.app.layout.focus_last()

        # Global bindings. (Listen to these bindings, even when this widget is
        # not focussed.)
        global_bindings = KeyBindings()
        handle = global_bindings.add

        @handle(Keys.Escape, "!", filter=~focused & emacs_mode, is_global=True)
        def _focus_me(event: E) -> None:
            "M-'!' will focus this user control."
            event.app.layout.focus(self.window)

        @handle("!", filter=~focused & vi_mode & vi_navigation_mode, is_global=True)
        def _focus_me_vi(event: E) -> None:
            "Focus."
            event.app.vi_state.input_mode = InputMode.INSERT
            event.app.layout.focus(self.window)

        return merge_key_bindings(
            [
                ConditionalKeyBindings(emacs_bindings, emacs_mode),
                ConditionalKeyBindings(vi_bindings, vi_mode),
                ConditionalKeyBindings(global_bindings, self.enable_global_bindings),
            ]
        )

    def __pt_container__(self) -> Container:
        return self.container


class ArgToolbar:
    def __init__(self) -> None:
        def get_formatted_text() -> StyleAndTextTuples:
            arg = get_app().key_processor.arg or ""
            if arg == "-":
                arg = "-1"

            return [
                ("class:arg-toolbar", "Repeat: "),
                ("class:arg-toolbar.text", arg),
            ]

        self.window = Window(FormattedTextControl(get_formatted_text), height=1)

        self.container = ConditionalContainer(content=self.window, filter=has_arg)

    def __pt_container__(self) -> Container:
        return self.container


class SearchToolbar:
    """
    :param vi_mode: Display '/' and '?' instead of I-search.
    :param ignore_case: Search case insensitive.
    """

    def __init__(
        self,
        search_buffer: Buffer | None = None,
        vi_mode: bool = False,
        text_if_not_searching: AnyFormattedText = "",
        forward_search_prompt: AnyFormattedText = "I-search: ",
        backward_search_prompt: AnyFormattedText = "I-search backward: ",
        ignore_case: FilterOrBool = False,
    ) -> None:
        if search_buffer is None:
            search_buffer = Buffer()

        @Condition
        def is_searching() -> bool:
            return self.control in get_app().layout.search_links

        def get_before_input() -> AnyFormattedText:
            if not is_searching():
                return text_if_not_searching
            elif (
                self.control.searcher_search_state.direction == SearchDirection.BACKWARD
            ):
                return "?" if vi_mode else backward_search_prompt
            else:
                return "/" if vi_mode else forward_search_prompt

        self.search_buffer = search_buffer

        self.control = SearchBufferControl(
            buffer=search_buffer,
            input_processors=[
                BeforeInput(get_before_input, style="class:search-toolbar.prompt")
            ],
            lexer=SimpleLexer(style="class:search-toolbar.text"),
            ignore_case=ignore_case,
        )

        self.container = ConditionalContainer(
            content=Window(self.control, height=1, style="class:search-toolbar"),
            filter=is_searching,
        )

    def __pt_container__(self) -> Container:
        return self.container


class _CompletionsToolbarControl(UIControl):
    def create_content(self, width: int, height: int) -> UIContent:
        all_fragments: StyleAndTextTuples = []

        complete_state = get_app().current_buffer.complete_state
        if complete_state:
            completions = complete_state.completions
            index = complete_state.complete_index  # Can be None!

            # Width of the completions without the left/right arrows in the margins.
            content_width = width - 6

            # Booleans indicating whether we stripped from the left/right
            cut_left = False
            cut_right = False

            # Create Menu content.
            fragments: StyleAndTextTuples = []

            for i, c in enumerate(completions):
                # When there is no more place for the next completion
                if fragment_list_len(fragments) + len(c.display_text) >= content_width:
                    # If the current one was not yet displayed, page to the next sequence.
                    if i <= (index or 0):
                        fragments = []
                        cut_left = True
                    # If the current one is visible, stop here.
                    else:
                        cut_right = True
                        break

                fragments.extend(
                    to_formatted_text(
                        c.display_text,
                        style=(
                            "class:completion-toolbar.completion.current"
                            if i == index
                            else "class:completion-toolbar.completion"
                        ),
                    )
                )
                fragments.append(("", " "))

            # Extend/strip until the content width.
            fragments.append(("", " " * (content_width - fragment_list_len(fragments))))
            fragments = fragments[:content_width]

            # Return fragments
            all_fragments.append(("", " "))
            all_fragments.append(
                ("class:completion-toolbar.arrow", "<" if cut_left else " ")
            )
            all_fragments.append(("", " "))

            all_fragments.extend(fragments)

            all_fragments.append(("", " "))
            all_fragments.append(
                ("class:completion-toolbar.arrow", ">" if cut_right else " ")
            )
            all_fragments.append(("", " "))

        def get_line(i: int) -> StyleAndTextTuples:
            return all_fragments

        return UIContent(get_line=get_line, line_count=1)


class CompletionsToolbar:
    def __init__(self) -> None:
        self.container = ConditionalContainer(
            content=Window(
                _CompletionsToolbarControl(), height=1, style="class:completion-toolbar"
            ),
            filter=has_completions,
        )

    def __pt_container__(self) -> Container:
        return self.container


class ValidationToolbar:
    def __init__(self, show_position: bool = False) -> None:
        def get_formatted_text() -> StyleAndTextTuples:
            buff = get_app().current_buffer

            if buff.validation_error:
                row, column = buff.document.translate_index_to_position(
                    buff.validation_error.cursor_position
                )

                if show_position:
                    text = f"{buff.validation_error.message} (line={row + 1} column={column + 1})"
                else:
                    text = buff.validation_error.message

                return [("class:validation-toolbar", text)]
            else:
                return []

        self.control = FormattedTextControl(get_formatted_text)

        self.container = ConditionalContainer(
            content=Window(self.control, height=1), filter=has_validation_error
        )

    def __pt_container__(self) -> Container:
        return self.container
