from __future__ import annotations

from typing import TextIO

from prompt_toolkit.cursor_shapes import CursorShape
from prompt_toolkit.data_structures import Size
from prompt_toolkit.styles import Attrs

from .base import Output
from .color_depth import ColorDepth
from .flush_stdout import flush_stdout

__all__ = ["PlainTextOutput"]


class PlainTextOutput(Output):
    """
    Output that won't include any ANSI escape sequences.

    Useful when stdout is not a terminal. Maybe stdout is redirected to a file.
    In this case, if `print_formatted_text` is used, for instance, we don't
    want to include formatting.

    (The code is mostly identical to `Vt100_Output`, but without the
    formatting.)
    """

    def __init__(self, stdout: TextIO) -> None:
        assert all(hasattr(stdout, a) for a in ("write", "flush"))

        self.stdout: TextIO = stdout
        self._buffer: list[str] = []

    def fileno(self) -> int:
        "There is no sensible default for fileno()."
        return self.stdout.fileno()

    def encoding(self) -> str:
        return "utf-8"

    def write(self, data: str) -> None:
        self._buffer.append(data)

    def write_raw(self, data: str) -> None:
        self._buffer.append(data)

    def set_title(self, title: str) -> None:
        pass

    def clear_title(self) -> None:
        pass

    def flush(self) -> None:
        if not self._buffer:
            return

        data = "".join(self._buffer)
        self._buffer = []
        flush_stdout(self.stdout, data)

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
        self._buffer.append("\n")

    def cursor_forward(self, amount: int) -> None:
        self._buffer.append(" " * amount)

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
        return 8

    def get_default_color_depth(self) -> ColorDepth:
        return ColorDepth.DEPTH_1_BIT
