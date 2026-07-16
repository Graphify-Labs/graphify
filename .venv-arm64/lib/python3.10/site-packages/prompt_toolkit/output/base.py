"""
Interface for an output.
"""

from __future__ import annotations

from abc import ABCMeta, abstractmethod
from typing import TextIO

from prompt_toolkit.cursor_shapes import CursorShape
from prompt_toolkit.data_structures import Size
from prompt_toolkit.styles import Attrs

from .color_depth import ColorDepth

__all__ = [
    "Output",
    "DummyOutput",
]


class Output(metaclass=ABCMeta):
    """
    Base class defining the output interface for a
    :class:`~prompt_toolkit.renderer.Renderer`.

    Actual implementations are
    :class:`~prompt_toolkit.output.vt100.Vt100_Output` and
    :class:`~prompt_toolkit.output.win32.Win32Output`.
    """

    stdout: TextIO | None = None

    @abstractmethod
    def fileno(self) -> int:
        "Return the file descriptor to which we can write for the output."

    @abstractmethod
    def encoding(self) -> str:
        """
        Return the encoding for this output, e.g. 'utf-8'.
        (This is used mainly to know which characters are supported by the
        output the data, so that the UI can provide alternatives, when
        required.)
        """

    @abstractmethod
    def write(self, data: str) -> None:
        "Write text (Terminal escape sequences will be removed/escaped.)"

    @abstractmethod
    def write_raw(self, data: str) -> None:
        "Write text."

    @abstractmethod
    def set_title(self, title: str) -> None:
        "Set terminal title."

    @abstractmethod
    def clear_title(self) -> None:
        "Clear title again. (or restore previous title.)"

    @abstractmethod
    def flush(self) -> None:
        "Write to output stream and flush."

    @abstractmethod
    def erase_screen(self) -> None:
        """
        Erases the screen with the background color and moves the cursor to
        home.
        """

    @abstractmethod
    def enter_alternate_screen(self) -> None:
        "Go to the alternate screen buffer. (For full screen applications)."

    @abstractmethod
    def quit_alternate_screen(self) -> None:
        "Leave the alternate screen buffer."

    @abstractmethod
    def enable_mouse_support(self) -> None:
        "Enable mouse."

    @abstractmethod
    def disable_mouse_support(self) -> None:
        "Disable mouse."

    @abstractmethod
    def erase_end_of_line(self) -> None:
        """
        Erases from the current cursor position to the end of the current line.
        """

    @abstractmethod
    def erase_down(self) -> None:
        """
        Erases the screen from the current line down to the bottom of the
        screen.
        """

    @abstractmethod
    def reset_attributes(self) -> None:
        "Reset color and styling attributes."

    @abstractmethod
    def set_attributes(self, attrs: Attrs, color_depth: ColorDepth) -> None:
        "Set new color and styling attributes."

    @abstractmethod
    def disable_autowrap(self) -> None:
        "Disable auto line wrapping."

    @abstractmethod
    def enable_autowrap(self) -> None:
        "Enable auto line wrapping."

    @abstractmethod
    def cursor_goto(self, row: int = 0, column: int = 0) -> None:
        "Move cursor position."

    @abstractmethod
    def cursor_up(self, amount: int) -> None:
        "Move cursor `amount` place up."

    @abstractmethod
    def cursor_down(self, amount: int) -> None:
        "Move cursor `amount` place down."

    @abstractmethod
    def cursor_forward(self, amount: int) -> None:
        "Move cursor `amount` place forward."

    @abstractmethod
    def cursor_backward(self, amount: int) -> None:
        "Move cursor `amount` place backward."

    @abstractmethod
    def hide_cursor(self) -> None:
        "Hide cursor."

    @abstractmethod
    def show_cursor(self) -> None:
        "Show cursor."

    @abstractmethod
    def set_cursor_shape(self, cursor_shape: CursorShape) -> None:
        "Set cursor shape to block, beam or underline."

    @abstractmethod
    def reset_cursor_shape(self) -> None:
        "Reset cursor shape."

    def ask_for_cpr(self) -> None:
        """
        Asks for a cursor position report (CPR).
        (VT100 only.)
        """

    @property
    def responds_to_cpr(self) -> bool:
        """
        `True` if the `Application` can expect to receive a CPR response after
        calling `ask_for_cpr` (this will come back through the corresponding
        `Input`).

        This is used to determine the amount of available rows we have below
        the cursor position. In the first place, we have this so that the drop
        down autocompletion menus are sized according to the available space.

        On Windows, we don't need this, there we have
        `get_rows_below_cursor_position`.
        """
        return False

    @abstractmethod
    def get_size(self) -> Size:
        "Return the size of the output window."

    def bell(self) -> None:
        "Sound bell."

    def enable_bracketed_paste(self) -> None:
        "For vt100 only."

    def disable_bracketed_paste(self) -> None:
        "For vt100 only."

    def reset_cursor_key_mode(self) -> None:
        """
        For vt100 only.
        Put the terminal in normal cursor mode (instead of application mode).

        See: https://vt100.net/docs/vt100-ug/chapter3.html
        """

    def scroll_buffer_to_prompt(self) -> None:
        "For Win32 only."

    def get_rows_below_cursor_position(self) -> int:
        "For Windows only."
        raise NotImplementedError

    @abstractmethod
    def get_default_color_depth(self) -> ColorDepth:
        """
        Get default color depth for this output.

        This value will be used if no color depth was explicitly passed to the
        `Application`.

        .. note::

            If the `$PROMPT_TOOLKIT_COLOR_DEPTH` environment variable has been
            set, then `outputs.defaults.create_output` will pass this value to
            the implementation as the default_color_depth, which is returned
            here. (This is not used when the output corresponds to a
            prompt_toolkit SSH/Telnet session.)
        """


class DummyOutput(Output):
    """
    For testing. An output class that doesn't render anything.
    """

    def fileno(self) -> int:
        "There is no sensible default for fileno()."
        raise NotImplementedError

    def encoding(self) -> str:
        return "utf-8"

    def write(self, data: str) -> None:
        pass

    def write_raw(self, data: str) -> None:
        pass

    def set_title(self, title: str) -> None:
        pass

    def clear_title(self) -> None:
        pass

    def flush(self) -> None:
        pass

    def erase_screen(self) -> None:
        pass

    def enter_alternate_screen(self) -> None:
        pass

    def quit_alternate_screen(self) -> None:
        pass

    def enable_mouse_support(self) -> None:
        pass

    def disable_mouse_support(self) -> None:
        pass

    def erase_end_of_line(self) -> None:
        pass

    def erase_down(self) -> None:
        pass

    def reset_attributes(self) -> None:
        pass

    def set_attributes(self, attrs: Attrs, color_depth: ColorDepth) -> None:
        pass

    def disable_autowrap(self) -> None:
        pass

    def enable_autowrap(self) -> None:
        pass

    def cursor_goto(self, row: int = 0, column: int = 0) -> None:
        pass

    def cursor_up(self, amount: int) -> None:
        pass

    def cursor_down(self, amount: int) -> None:
        pass

    def cursor_forward(self, amount: int) -> None:
        pass

    def cursor_backward(self, amount: int) -> None:
        pass

    def hide_cursor(self) -> None:
        pass

    def show_cursor(self) -> None:
        pass

    def set_cursor_shape(self, cursor_shape: CursorShape) -> None:
        pass

    def reset_cursor_shape(self) -> None:
        pass

    def ask_for_cpr(self) -> None:
        pass

    def bell(self) -> None:
        pass

    def enable_bracketed_paste(self) -> None:
        pass

    def disable_bracketed_paste(self) -> None:
        pass

    def scroll_buffer_to_prompt(self) -> None:
        pass

    def get_size(self) -> Size:
        return Size(rows=40, columns=80)

    def get_rows_below_cursor_position(self) -> int:
        return 40

    def get_default_color_depth(self) -> ColorDepth:
        return ColorDepth.DEPTH_1_BIT
