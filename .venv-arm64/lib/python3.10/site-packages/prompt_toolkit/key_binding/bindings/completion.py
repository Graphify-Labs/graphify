"""
Key binding handlers for displaying completions.
"""

from __future__ import annotations

import asyncio
import math
from typing import TYPE_CHECKING

from prompt_toolkit.application.run_in_terminal import in_terminal
from prompt_toolkit.completion import (
    CompleteEvent,
    Completion,
    get_common_complete_suffix,
)
from prompt_toolkit.formatted_text import StyleAndTextTuples
from prompt_toolkit.key_binding.key_bindings import KeyBindings
from prompt_toolkit.key_binding.key_processor import KeyPressEvent
from prompt_toolkit.keys import Keys
from prompt_toolkit.utils import get_cwidth

if TYPE_CHECKING:
    from prompt_toolkit.application import Application
    from prompt_toolkit.shortcuts import PromptSession

__all__ = [
    "generate_completions",
    "display_completions_like_readline",
]

E = KeyPressEvent


def generate_completions(event: E) -> None:
    r"""
    Tab-completion: where the first tab completes the common suffix and the
    second tab lists all the completions.
    """
    b = event.current_buffer

    # When already navigating through completions, select the next one.
    if b.complete_state:
        b.complete_next()
    else:
        b.start_completion(insert_common_part=True)


def display_completions_like_readline(event: E) -> None:
    """
    Key binding handler for readline-style tab completion.
    This is meant to be as similar as possible to the way how readline displays
    completions.

    Generate the completions immediately (blocking) and display them above the
    prompt in columns.

    Usage::

        # Call this handler when 'Tab' has been pressed.
        key_bindings.add(Keys.ControlI)(display_completions_like_readline)
    """
    # Request completions.
    b = event.current_buffer
    if b.completer is None:
        return
    complete_event = CompleteEvent(completion_requested=True)
    completions = list(b.completer.get_completions(b.document, complete_event))

    # Calculate the common suffix.
    common_suffix = get_common_complete_suffix(b.document, completions)

    # One completion: insert it.
    if len(completions) == 1:
        b.delete_before_cursor(-completions[0].start_position)
        b.insert_text(completions[0].text)
    # Multiple completions with common part.
    elif common_suffix:
        b.insert_text(common_suffix)
    # Otherwise: display all completions.
    elif completions:
        _display_completions_like_readline(event.app, completions)


def _display_completions_like_readline(
    app: Application[object], completions: list[Completion]
) -> asyncio.Task[None]:
    """
    Display the list of completions in columns above the prompt.
    This will ask for a confirmation if there are too many completions to fit
    on a single page and provide a paginator to walk through them.
    """
    from prompt_toolkit.formatted_text import to_formatted_text
    from prompt_toolkit.shortcuts.prompt import create_confirm_session

    # Get terminal dimensions.
    term_size = app.output.get_size()
    term_width = term_size.columns
    term_height = term_size.rows

    # Calculate amount of required columns/rows for displaying the
    # completions. (Keep in mind that completions are displayed
    # alphabetically column-wise.)
    max_compl_width = min(
        term_width, max(get_cwidth(c.display_text) for c in completions) + 1
    )
    column_count = max(1, term_width // max_compl_width)
    completions_per_page = column_count * (term_height - 1)
    page_count = int(math.ceil(len(completions) / float(completions_per_page)))
    # Note: math.ceil can return float on Python2.

    def display(page: int) -> None:
        # Display completions.
        page_completions = completions[
            page * completions_per_page : (page + 1) * completions_per_page
        ]

        page_row_count = int(math.ceil(len(page_completions) / float(column_count)))
        page_columns = [
            page_completions[i * page_row_count : (i + 1) * page_row_count]
            for i in range(column_count)
        ]

        result: StyleAndTextTuples = []

        for r in range(page_row_count):
            for c in range(column_count):
                try:
                    completion = page_columns[c][r]
                    style = "class:readline-like-completions.completion " + (
                        completion.style or ""
                    )

                    result.extend(to_formatted_text(completion.display, style=style))

                    # Add padding.
                    padding = max_compl_width - get_cwidth(completion.display_text)
                    result.append((completion.style, " " * padding))
                except IndexError:
                    pass
            result.append(("", "\n"))

        app.print_text(to_formatted_text(result, "class:readline-like-completions"))

    # User interaction through an application generator function.
    async def run_compl() -> None:
        "Coroutine."
        async with in_terminal(render_cli_done=True):
            if len(completions) > completions_per_page:
                # Ask confirmation if it doesn't fit on the screen.
                confirm = await create_confirm_session(
                    f"Display all {len(completions)} possibilities?",
                ).prompt_async()

                if confirm:
                    # Display pages.
                    for page in range(page_count):
                        display(page)

                        if page != page_count - 1:
                            # Display --MORE-- and go to the next page.
                            show_more = await _create_more_session(
                                "--MORE--"
                            ).prompt_async()

                            if not show_more:
                                return
                else:
                    app.output.flush()
            else:
                # Display all completions.
                display(0)

    return app.create_background_task(run_compl())


def _create_more_session(message: str = "--MORE--") -> PromptSession[bool]:
    """
    Create a `PromptSession` object for displaying the "--MORE--".
    """
    from prompt_toolkit.shortcuts import PromptSession

    bindings = KeyBindings()

    @bindings.add(" ")
    @bindings.add("y")
    @bindings.add("Y")
    @bindings.add(Keys.ControlJ)
    @bindings.add(Keys.ControlM)
    @bindings.add(Keys.ControlI)  # Tab.
    def _yes(event: E) -> None:
        event.app.exit(result=True)

    @bindings.add("n")
    @bindings.add("N")
    @bindings.add("q")
    @bindings.add("Q")
    @bindings.add(Keys.ControlC)
    def _no(event: E) -> None:
        event.app.exit(result=False)

    @bindings.add(Keys.Any)
    def _ignore(event: E) -> None:
        "Disable inserting of text."

    return PromptSession(message, key_bindings=bindings, erase_when_done=True)
