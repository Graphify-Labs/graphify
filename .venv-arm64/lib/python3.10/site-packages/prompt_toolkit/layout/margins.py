"""
Margin implementations for a :class:`~prompt_toolkit.layout.containers.Window`.
"""

from __future__ import annotations

from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING, Callable

from prompt_toolkit.filters import FilterOrBool, to_filter
from prompt_toolkit.formatted_text import (
    StyleAndTextTuples,
    fragment_list_to_text,
    to_formatted_text,
)
from prompt_toolkit.utils import get_cwidth

from .controls import UIContent

if TYPE_CHECKING:
    from .containers import WindowRenderInfo

__all__ = [
    "Margin",
    "NumberedMargin",
    "ScrollbarMargin",
    "ConditionalMargin",
    "PromptMargin",
]


class Margin(metaclass=ABCMeta):
    """
    Base interface for a margin.
    """

    @abstractmethod
    def get_width(self, get_ui_content: Callable[[], UIContent]) -> int:
        """
        Return the width that this margin is going to consume.

        :param get_ui_content: Callable that asks the user control to create
            a :class:`.UIContent` instance. This can be used for instance to
            obtain the number of lines.
        """
        return 0

    @abstractmethod
    def create_margin(
        self, window_render_info: WindowRenderInfo, width: int, height: int
    ) -> StyleAndTextTuples:
        """
        Creates a margin.
        This should return a list of (style_str, text) tuples.

        :param window_render_info:
            :class:`~prompt_toolkit.layout.containers.WindowRenderInfo`
            instance, generated after rendering and copying the visible part of
            the :class:`~prompt_toolkit.layout.controls.UIControl` into the
            :class:`~prompt_toolkit.layout.containers.Window`.
        :param width: The width that's available for this margin. (As reported
            by :meth:`.get_width`.)
        :param height: The height that's available for this margin. (The height
            of the :class:`~prompt_toolkit.layout.containers.Window`.)
        """
        return []


class NumberedMargin(Margin):
    """
    Margin that displays the line numbers.

    :param relative: Number relative to the cursor position. Similar to the Vi
                     'relativenumber' option.
    :param display_tildes: Display tildes after the end of the document, just
        like Vi does.
    """

    def __init__(
        self, relative: FilterOrBool = False, display_tildes: FilterOrBool = False
    ) -> None:
        self.relative = to_filter(relative)
        self.display_tildes = to_filter(display_tildes)

    def get_width(self, get_ui_content: Callable[[], UIContent]) -> int:
        line_count = get_ui_content().line_count
        return max(3, len(f"{line_count}") + 1)

    def create_margin(
        self, window_render_info: WindowRenderInfo, width: int, height: int
    ) -> StyleAndTextTuples:
        relative = self.relative()

        style = "class:line-number"
        style_current = "class:line-number.current"

        # Get current line number.
        current_lineno = window_render_info.ui_content.cursor_position.y

        # Construct margin.
        result: StyleAndTextTuples = []
        last_lineno = None

        for y, lineno in enumerate(window_render_info.displayed_lines):
            # Only display line number if this line is not a continuation of the previous line.
            if lineno != last_lineno:
                if lineno is None:
                    pass
                elif lineno == current_lineno:
                    # Current line.
                    if relative:
                        # Left align current number in relative mode.
                        result.append((style_current, "%i" % (lineno + 1)))
                    else:
                        result.append(
                            (style_current, ("%i " % (lineno + 1)).rjust(width))
                        )
                else:
                    # Other lines.
                    if relative:
                        lineno = abs(lineno - current_lineno) - 1

                    result.append((style, ("%i " % (lineno + 1)).rjust(width)))

            last_lineno = lineno
            result.append(("", "\n"))

        # Fill with tildes.
        if self.display_tildes():
            while y < window_render_info.window_height:
                result.append(("class:tilde", "~\n"))
                y += 1

        return result


class ConditionalMargin(Margin):
    """
    Wrapper around other :class:`.Margin` classes to show/hide them.
    """

    def __init__(self, margin: Margin, filter: FilterOrBool) -> None:
        self.margin = margin
        self.filter = to_filter(filter)

    def get_width(self, get_ui_content: Callable[[], UIContent]) -> int:
        if self.filter():
            return self.margin.get_width(get_ui_content)
        else:
            return 0

    def create_margin(
        self, window_render_info: WindowRenderInfo, width: int, height: int
    ) -> StyleAndTextTuples:
        if width and self.filter():
            return self.margin.create_margin(window_render_info, width, height)
        else:
            return []


class ScrollbarMargin(Margin):
    """
    Margin displaying a scrollbar.

    :param display_arrows: Display scroll up/down arrows.
    """

    def __init__(
        self,
        display_arrows: FilterOrBool = False,
        up_arrow_symbol: str = "^",
        down_arrow_symbol: str = "v",
    ) -> None:
        self.display_arrows = to_filter(display_arrows)
        self.up_arrow_symbol = up_arrow_symbol
        self.down_arrow_symbol = down_arrow_symbol

    def get_width(self, get_ui_content: Callable[[], UIContent]) -> int:
        return 1

    def create_margin(
        self, window_render_info: WindowRenderInfo, width: int, height: int
    ) -> StyleAndTextTuples:
        content_height = window_render_info.content_height
        window_height = window_render_info.window_height
        display_arrows = self.display_arrows()

        if display_arrows:
            window_height -= 2

        try:
            fraction_visible = len(window_render_info.displayed_lines) / float(
                content_height
            )
            fraction_above = window_render_info.vertical_scroll / float(content_height)

            scrollbar_height = int(
                min(window_height, max(1, window_height * fraction_visible))
            )
            scrollbar_top = int(window_height * fraction_above)
        except ZeroDivisionError:
            return []
        else:

            def is_scroll_button(row: int) -> bool:
                "True if we should display a button on this row."
                return scrollbar_top <= row <= scrollbar_top + scrollbar_height

            # Up arrow.
            result: StyleAndTextTuples = []
            if display_arrows:
                result.extend(
                    [
                        ("class:scrollbar.arrow", self.up_arrow_symbol),
                        ("class:scrollbar", "\n"),
                    ]
                )

            # Scrollbar body.
            scrollbar_background = "class:scrollbar.background"
            scrollbar_background_start = "class:scrollbar.background,scrollbar.start"
            scrollbar_button = "class:scrollbar.button"
            scrollbar_button_end = "class:scrollbar.button,scrollbar.end"

            for i in range(window_height):
                if is_scroll_button(i):
                    if not is_scroll_button(i + 1):
                        # Give the last cell a different style, because we
                        # want to underline this.
                        result.append((scrollbar_button_end, " "))
                    else:
                        result.append((scrollbar_button, " "))
                else:
                    if is_scroll_button(i + 1):
                        result.append((scrollbar_background_start, " "))
                    else:
                        result.append((scrollbar_background, " "))
                result.append(("", "\n"))

            # Down arrow
            if display_arrows:
                result.append(("class:scrollbar.arrow", self.down_arrow_symbol))

            return result


class PromptMargin(Margin):
    """
    [Deprecated]

    Create margin that displays a prompt.
    This can display one prompt at the first line, and a continuation prompt
    (e.g, just dots) on all the following lines.

    This `PromptMargin` implementation has been largely superseded in favor of
    the `get_line_prefix` attribute of `Window`. The reason is that a margin is
    always a fixed width, while `get_line_prefix` can return a variable width
    prefix in front of every line, making it more powerful, especially for line
    continuations.

    :param get_prompt: Callable returns formatted text or a list of
        `(style_str, type)` tuples to be shown as the prompt at the first line.
    :param get_continuation: Callable that takes three inputs. The width (int),
        line_number (int), and is_soft_wrap (bool). It should return formatted
        text or a list of `(style_str, type)` tuples for the next lines of the
        input.
    """

    def __init__(
        self,
        get_prompt: Callable[[], StyleAndTextTuples],
        get_continuation: None
        | (Callable[[int, int, bool], StyleAndTextTuples]) = None,
    ) -> None:
        self.get_prompt = get_prompt
        self.get_continuation = get_continuation

    def get_width(self, get_ui_content: Callable[[], UIContent]) -> int:
        "Width to report to the `Window`."
        # Take the width from the first line.
        text = fragment_list_to_text(self.get_prompt())
        return get_cwidth(text)

    def create_margin(
        self, window_render_info: WindowRenderInfo, width: int, height: int
    ) -> StyleAndTextTuples:
        get_continuation = self.get_continuation
        result: StyleAndTextTuples = []

        # First line.
        result.extend(to_formatted_text(self.get_prompt()))

        # Next lines.
        if get_continuation:
            last_y = None

            for y in window_render_info.displayed_lines[1:]:
                result.append(("", "\n"))
                result.extend(
                    to_formatted_text(get_continuation(width, y, y == last_y))
                )
                last_y = y

        return result
