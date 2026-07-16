"""
Output for vt100 terminals.

A lot of thanks, regarding outputting of colors, goes to the Pygments project:
(We don't rely on Pygments anymore, because many things are very custom, and
everything has been highly optimized.)
http://pygments.org/
"""

from __future__ import annotations

import io
import os
import sys
from typing import Callable, Dict, Hashable, Iterable, Sequence, TextIO, Tuple

from prompt_toolkit.cursor_shapes import CursorShape
from prompt_toolkit.data_structures import Size
from prompt_toolkit.output import Output
from prompt_toolkit.styles import ANSI_COLOR_NAMES, Attrs
from prompt_toolkit.utils import is_dumb_terminal

from .color_depth import ColorDepth
from .flush_stdout import flush_stdout

__all__ = [
    "Vt100_Output",
]


FG_ANSI_COLORS = {
    "ansidefault": 39,
    # Low intensity.
    "ansiblack": 30,
    "ansired": 31,
    "ansigreen": 32,
    "ansiyellow": 33,
    "ansiblue": 34,
    "ansimagenta": 35,
    "ansicyan": 36,
    "ansigray": 37,
    # High intensity.
    "ansibrightblack": 90,
    "ansibrightred": 91,
    "ansibrightgreen": 92,
    "ansibrightyellow": 93,
    "ansibrightblue": 94,
    "ansibrightmagenta": 95,
    "ansibrightcyan": 96,
    "ansiwhite": 97,
}

BG_ANSI_COLORS = {
    "ansidefault": 49,
    # Low intensity.
    "ansiblack": 40,
    "ansired": 41,
    "ansigreen": 42,
    "ansiyellow": 43,
    "ansiblue": 44,
    "ansimagenta": 45,
    "ansicyan": 46,
    "ansigray": 47,
    # High intensity.
    "ansibrightblack": 100,
    "ansibrightred": 101,
    "ansibrightgreen": 102,
    "ansibrightyellow": 103,
    "ansibrightblue": 104,
    "ansibrightmagenta": 105,
    "ansibrightcyan": 106,
    "ansiwhite": 107,
}


ANSI_COLORS_TO_RGB = {
    "ansidefault": (
        0x00,
        0x00,
        0x00,
    ),  # Don't use, 'default' doesn't really have a value.
    "ansiblack": (0x00, 0x00, 0x00),
    "ansigray": (0xE5, 0xE5, 0xE5),
    "ansibrightblack": (0x7F, 0x7F, 0x7F),
    "ansiwhite": (0xFF, 0xFF, 0xFF),
    # Low intensity.
    "ansired": (0xCD, 0x00, 0x00),
    "ansigreen": (0x00, 0xCD, 0x00),
    "ansiyellow": (0xCD, 0xCD, 0x00),
    "ansiblue": (0x00, 0x00, 0xCD),
    "ansimagenta": (0xCD, 0x00, 0xCD),
    "ansicyan": (0x00, 0xCD, 0xCD),
    # High intensity.
    "ansibrightred": (0xFF, 0x00, 0x00),
    "ansibrightgreen": (0x00, 0xFF, 0x00),
    "ansibrightyellow": (0xFF, 0xFF, 0x00),
    "ansibrightblue": (0x00, 0x00, 0xFF),
    "ansibrightmagenta": (0xFF, 0x00, 0xFF),
    "ansibrightcyan": (0x00, 0xFF, 0xFF),
}


assert set(FG_ANSI_COLORS) == set(ANSI_COLOR_NAMES)
assert set(BG_ANSI_COLORS) == set(ANSI_COLOR_NAMES)
assert set(ANSI_COLORS_TO_RGB) == set(ANSI_COLOR_NAMES)


def _get_closest_ansi_color(r: int, g: int, b: int, exclude: Sequence[str] = ()) -> str:
    """
    Find closest ANSI color. Return it by name.

    :param r: Red (Between 0 and 255.)
    :param g: Green (Between 0 and 255.)
    :param b: Blue (Between 0 and 255.)
    :param exclude: A tuple of color names to exclude. (E.g. ``('ansired', )``.)
    """
    exclude = list(exclude)

    # When we have a bit of saturation, avoid the gray-like colors, otherwise,
    # too often the distance to the gray color is less.
    saturation = abs(r - g) + abs(g - b) + abs(b - r)  # Between 0..510

    if saturation > 30:
        exclude.extend(["ansilightgray", "ansidarkgray", "ansiwhite", "ansiblack"])

    # Take the closest color.
    # (Thanks to Pygments for this part.)
    distance = 257 * 257 * 3  # "infinity" (>distance from #000000 to #ffffff)
    match = "ansidefault"

    for name, (r2, g2, b2) in ANSI_COLORS_TO_RGB.items():
        if name != "ansidefault" and name not in exclude:
            d = (r - r2) ** 2 + (g - g2) ** 2 + (b - b2) ** 2

            if d < distance:
                match = name
                distance = d

    return match


_ColorCodeAndName = Tuple[int, str]


class _16ColorCache:
    """
    Cache which maps (r, g, b) tuples to 16 ansi colors.

    :param bg: Cache for background colors, instead of foreground.
    """

    def __init__(self, bg: bool = False) -> None:
        self.bg = bg
        self._cache: dict[Hashable, _ColorCodeAndName] = {}

    def get_code(
        self, value: tuple[int, int, int], exclude: Sequence[str] = ()
    ) -> _ColorCodeAndName:
        """
        Return a (ansi_code, ansi_name) tuple. (E.g. ``(44, 'ansiblue')``.) for
        a given (r,g,b) value.
        """
        key: Hashable = (value, tuple(exclude))
        cache = self._cache

        if key not in cache:
            cache[key] = self._get(value, exclude)

        return cache[key]

    def _get(
        self, value: tuple[int, int, int], exclude: Sequence[str] = ()
    ) -> _ColorCodeAndName:
        r, g, b = value
        match = _get_closest_ansi_color(r, g, b, exclude=exclude)

        # Turn color name into code.
        if self.bg:
            code = BG_ANSI_COLORS[match]
        else:
            code = FG_ANSI_COLORS[match]

        return code, match


class _256ColorCache(Dict[Tuple[int, int, int], int]):
    """
    Cache which maps (r, g, b) tuples to 256 colors.
    """

    def __init__(self) -> None:
        # Build color table.
        colors: list[tuple[int, int, int]] = []

        # colors 0..15: 16 basic colors
        colors.append((0x00, 0x00, 0x00))  # 0
        colors.append((0xCD, 0x00, 0x00))  # 1
        colors.append((0x00, 0xCD, 0x00))  # 2
        colors.append((0xCD, 0xCD, 0x00))  # 3
        colors.append((0x00, 0x00, 0xEE))  # 4
        colors.append((0xCD, 0x00, 0xCD))  # 5
        colors.append((0x00, 0xCD, 0xCD))  # 6
        colors.append((0xE5, 0xE5, 0xE5))  # 7
        colors.append((0x7F, 0x7F, 0x7F))  # 8
        colors.append((0xFF, 0x00, 0x00))  # 9
        colors.append((0x00, 0xFF, 0x00))  # 10
        colors.append((0xFF, 0xFF, 0x00))  # 11
        colors.append((0x5C, 0x5C, 0xFF))  # 12
        colors.append((0xFF, 0x00, 0xFF))  # 13
        colors.append((0x00, 0xFF, 0xFF))  # 14
        colors.append((0xFF, 0xFF, 0xFF))  # 15

        # colors 16..232: the 6x6x6 color cube
        valuerange = (0x00, 0x5F, 0x87, 0xAF, 0xD7, 0xFF)

        for i in range(217):
            r = valuerange[(i // 36) % 6]
            g = valuerange[(i // 6) % 6]
            b = valuerange[i % 6]
            colors.append((r, g, b))

        # colors 233..253: grayscale
        for i in range(1, 22):
            v = 8 + i * 10
            colors.append((v, v, v))

        self.colors = colors

    def __missing__(self, value: tuple[int, int, int]) -> int:
        r, g, b = value

        # Find closest color.
        # (Thanks to Pygments for this!)
        distance = 257 * 257 * 3  # "infinity" (>distance from #000000 to #ffffff)
        match = 0

        for i, (r2, g2, b2) in enumerate(self.colors):
            if i >= 16:  # XXX: We ignore the 16 ANSI colors when mapping RGB
                # to the 256 colors, because these highly depend on
                # the color scheme of the terminal.
                d = (r - r2) ** 2 + (g - g2) ** 2 + (b - b2) ** 2

                if d < distance:
                    match = i
                    distance = d

        # Turn color name into code.
        self[value] = match
        return match


_16_fg_colors = _16ColorCache(bg=False)
_16_bg_colors = _16ColorCache(bg=True)
_256_colors = _256ColorCache()


class _EscapeCodeCache(Dict[Attrs, str]):
    """
    Cache for VT100 escape codes. It maps
    (fgcolor, bgcolor, bold, underline, strike, italic, blink, reverse, hidden, dim) tuples to VT100
    escape sequences.

    :param true_color: When True, use 24bit colors instead of 256 colors.
    """

    def __init__(self, color_depth: ColorDepth) -> None:
        self.color_depth = color_depth

    def __missing__(self, attrs: Attrs) -> str:
        (
            fgcolor,
            bgcolor,
            bold,
            underline,
            strike,
            italic,
            blink,
            reverse,
            hidden,
            dim,
        ) = attrs
        parts: list[str] = []

        parts.extend(self._colors_to_code(fgcolor or "", bgcolor or ""))

        if bold:
            parts.append("1")
        if dim:
            parts.append("2")
        if italic:
            parts.append("3")
        if blink:
            parts.append("5")
        if underline:
            parts.append("4")
        if reverse:
            parts.append("7")
        if hidden:
            parts.append("8")
        if strike:
            parts.append("9")

        if parts:
            result = "\x1b[0;" + ";".join(parts) + "m"
        else:
            result = "\x1b[0m"

        self[attrs] = result
        return result

    def _color_name_to_rgb(self, color: str) -> tuple[int, int, int]:
        "Turn 'ffffff', into (0xff, 0xff, 0xff)."
        try:
            rgb = int(color, 16)
        except ValueError:
            raise
        else:
            r = (rgb >> 16) & 0xFF
            g = (rgb >> 8) & 0xFF
            b = rgb & 0xFF
            return r, g, b

    def _colors_to_code(self, fg_color: str, bg_color: str) -> Iterable[str]:
        """
        Return a tuple with the vt100 values  that represent this color.
        """
        # When requesting ANSI colors only, and both fg/bg color were converted
        # to ANSI, ensure that the foreground and background color are not the
        # same. (Unless they were explicitly defined to be the same color.)
        fg_ansi = ""

        def get(color: str, bg: bool) -> list[int]:
            nonlocal fg_ansi

            table = BG_ANSI_COLORS if bg else FG_ANSI_COLORS

            if not color or self.color_depth == ColorDepth.DEPTH_1_BIT:
                return []

            # 16 ANSI colors. (Given by name.)
            elif color in table:
                return [table[color]]

            # RGB colors. (Defined as 'ffffff'.)
            else:
                try:
                    rgb = self._color_name_to_rgb(color)
                except ValueError:
                    return []

                # When only 16 colors are supported, use that.
                if self.color_depth == ColorDepth.DEPTH_4_BIT:
                    if bg:  # Background.
                        if fg_color != bg_color:
                            exclude = [fg_ansi]
                        else:
                            exclude = []
                        code, name = _16_bg_colors.get_code(rgb, exclude=exclude)
                        return [code]
                    else:  # Foreground.
                        code, name = _16_fg_colors.get_code(rgb)
                        fg_ansi = name
                        return [code]

                # True colors. (Only when this feature is enabled.)
                elif self.color_depth == ColorDepth.DEPTH_24_BIT:
                    r, g, b = rgb
                    return [(48 if bg else 38), 2, r, g, b]

                # 256 RGB colors.
                else:
                    return [(48 if bg else 38), 5, _256_colors[rgb]]

        result: list[int] = []
        result.extend(get(fg_color, False))
        result.extend(get(bg_color, True))

        return map(str, result)


def _get_size(fileno: int) -> tuple[int, int]:
    """
    Get the size of this pseudo terminal.

    :param fileno: stdout.fileno()
    :returns: A (rows, cols) tuple.
    """
    size = os.get_terminal_size(fileno)
    return size.lines, size.columns


class Vt100_Output(Output):
    """
    :param get_size: A callable which returns the `Size` of the output terminal.
    :param stdout: Any object with has a `write` and `flush` method + an 'encoding' property.
    :param term: The terminal environment variable. (xterm, xterm-256color, linux, ...)
    :param enable_cpr: When `True` (the default), send "cursor position
        request" escape sequences to the output in order to detect the cursor
        position. That way, we can properly determine how much space there is
        available for the UI (especially for drop down menus) to render. The
        `Renderer` will still try to figure out whether the current terminal
        does respond to CPR escapes. When `False`, never attempt to send CPR
        requests.
    """

    # For the error messages. Only display "Output is not a terminal" once per
    # file descriptor.
    _fds_not_a_terminal: set[int] = set()

    def __init__(
        self,
        stdout: TextIO,
        get_size: Callable[[], Size],
        term: str | None = None,
        default_color_depth: ColorDepth | None = None,
        enable_bell: bool = True,
        enable_cpr: bool = True,
    ) -> None:
        assert all(hasattr(stdout, a) for a in ("write", "flush"))

        self._buffer: list[str] = []
        self.stdout: TextIO = stdout
        self.default_color_depth = default_color_depth
        self._get_size = get_size
        self.term = term
        self.enable_bell = enable_bell
        self.enable_cpr = enable_cpr

        # Cache for escape codes.
        self._escape_code_caches: dict[ColorDepth, _EscapeCodeCache] = {
            ColorDepth.DEPTH_1_BIT: _EscapeCodeCache(ColorDepth.DEPTH_1_BIT),
            ColorDepth.DEPTH_4_BIT: _EscapeCodeCache(ColorDepth.DEPTH_4_BIT),
            ColorDepth.DEPTH_8_BIT: _EscapeCodeCache(ColorDepth.DEPTH_8_BIT),
            ColorDepth.DEPTH_24_BIT: _EscapeCodeCache(ColorDepth.DEPTH_24_BIT),
        }

        # Keep track of whether the cursor shape was ever changed.
        # (We don't restore the cursor shape if it was never changed - by
        # default, we don't change them.)
        self._cursor_shape_changed = False

        # Don't hide/show the cursor when this was already done.
        # (`None` means that we don't know whether the cursor is visible or
        # not.)
        self._cursor_visible: bool | None = None

    @classmethod
    def from_pty(
        cls,
        stdout: TextIO,
        term: str | None = None,
        default_color_depth: ColorDepth | None = None,
        enable_bell: bool = True,
    ) -> Vt100_Output:
        """
        Create an Output class from a pseudo terminal.
        (This will take the dimensions by reading the pseudo
        terminal attributes.)
        """
        fd: int | None
        # Normally, this requires a real TTY device, but people instantiate
        # this class often during unit tests as well. For convenience, we print
        # an error message, use standard dimensions, and go on.
        try:
            fd = stdout.fileno()
        except io.UnsupportedOperation:
            fd = None

        if not stdout.isatty() and (fd is None or fd not in cls._fds_not_a_terminal):
            msg = "Warning: Output is not a terminal (fd=%r).\n"
            sys.stderr.write(msg % fd)
            sys.stderr.flush()
            if fd is not None:
                cls._fds_not_a_terminal.add(fd)

        def get_size() -> Size:
            # If terminal (incorrectly) reports its size as 0, pick a
            # reasonable default.  See
            # https://github.com/ipython/ipython/issues/10071
            rows, columns = (None, None)

            # It is possible that `stdout` is no longer a TTY device at this
            # point. In that case we get an `OSError` in the ioctl call in
            # `get_size`. See:
            # https://github.com/prompt-toolkit/python-prompt-toolkit/pull/1021
            try:
                rows, columns = _get_size(stdout.fileno())
            except OSError:
                pass
            return Size(rows=rows or 24, columns=columns or 80)

        return cls(
            stdout,
            get_size,
            term=term,
            default_color_depth=default_color_depth,
            enable_bell=enable_bell,
        )

    def get_size(self) -> Size:
        return self._get_size()

    def fileno(self) -> int:
        "Return file descriptor."
        return self.stdout.fileno()

    def encoding(self) -> str:
        "Return encoding used for stdout."
        return self.stdout.encoding

    def write_raw(self, data: str) -> None:
        """
        Write raw data to output.
        """
        self._buffer.append(data)

    def write(self, data: str) -> None:
        """
        Write text to output.
        (Removes vt100 escape codes. -- used for safely writing text.)
        """
        self._buffer.append(data.replace("\x1b", "?"))

    def set_title(self, title: str) -> None:
        """
        Set terminal title.
        """
        if self.term not in (
            "linux",
            "eterm-color",
        ):  # Not supported by the Linux console.
            self.write_raw(
                "\x1b]2;{}\x07".format(title.replace("\x1b", "").replace("\x07", ""))
            )

    def clear_title(self) -> None:
        self.set_title("")

    def erase_screen(self) -> None:
        """
        Erases the screen with the background color and moves the cursor to
        home.
        """
        self.write_raw("\x1b[2J")

    def enter_alternate_screen(self) -> None:
        self.write_raw("\x1b[?1049h\x1b[H")

    def quit_alternate_screen(self) -> None:
        self.write_raw("\x1b[?1049l")

    def enable_mouse_support(self) -> None:
        self.write_raw("\x1b[?1000h")

        # Enable mouse-drag support.
        self.write_raw("\x1b[?1003h")

        # Enable urxvt Mouse mode. (For terminals that understand this.)
        self.write_raw("\x1b[?1015h")

        # Also enable Xterm SGR mouse mode. (For terminals that understand this.)
        self.write_raw("\x1b[?1006h")

        # Note: E.g. lxterminal understands 1000h, but not the urxvt or sgr
        #       extensions.

    def disable_mouse_support(self) -> None:
        self.write_raw("\x1b[?1000l")
        self.write_raw("\x1b[?1015l")
        self.write_raw("\x1b[?1006l")
        self.write_raw("\x1b[?1003l")

    def erase_end_of_line(self) -> None:
        """
        Erases from the current cursor position to the end of the current line.
        """
        self.write_raw("\x1b[K")

    def erase_down(self) -> None:
        """
        Erases the screen from the current line down to the bottom of the
        screen.
        """
        self.write_raw("\x1b[J")

    def reset_attributes(self) -> None:
        self.write_raw("\x1b[0m")

    def set_attributes(self, attrs: Attrs, color_depth: ColorDepth) -> None:
        """
        Create new style and output.

        :param attrs: `Attrs` instance.
        """
        # Get current depth.
        escape_code_cache = self._escape_code_caches[color_depth]

        # Write escape character.
        self.write_raw(escape_code_cache[attrs])

    def disable_autowrap(self) -> None:
        self.write_raw("\x1b[?7l")

    def enable_autowrap(self) -> None:
        self.write_raw("\x1b[?7h")

    def enable_bracketed_paste(self) -> None:
        self.write_raw("\x1b[?2004h")

    def disable_bracketed_paste(self) -> None:
        self.write_raw("\x1b[?2004l")

    def reset_cursor_key_mode(self) -> None:
        """
        For vt100 only.
        Put the terminal in cursor mode (instead of application mode).
        """
        # Put the terminal in cursor mode. (Instead of application mode.)
        self.write_raw("\x1b[?1l")

    def cursor_goto(self, row: int = 0, column: int = 0) -> None:
        """
        Move cursor position.
        """
        self.write_raw("\x1b[%i;%iH" % (row, column))

    def cursor_up(self, amount: int) -> None:
        if amount == 0:
            pass
        elif amount == 1:
            self.write_raw("\x1b[A")
        else:
            self.write_raw("\x1b[%iA" % amount)

    def cursor_down(self, amount: int) -> None:
        if amount == 0:
            pass
        elif amount == 1:
            # Note: Not the same as '\n', '\n' can cause the window content to
            #       scroll.
            self.write_raw("\x1b[B")
        else:
            self.write_raw("\x1b[%iB" % amount)

    def cursor_forward(self, amount: int) -> None:
        if amount == 0:
            pass
        elif amount == 1:
            self.write_raw("\x1b[C")
        else:
            self.write_raw("\x1b[%iC" % amount)

    def cursor_backward(self, amount: int) -> None:
        if amount == 0:
            pass
        elif amount == 1:
            self.write_raw("\b")  # '\x1b[D'
        else:
            self.write_raw("\x1b[%iD" % amount)

    def hide_cursor(self) -> None:
        if self._cursor_visible in (True, None):
            self._cursor_visible = False
            self.write_raw("\x1b[?25l")

    def show_cursor(self) -> None:
        if self._cursor_visible in (False, None):
            self._cursor_visible = True
            self.write_raw("\x1b[?12l\x1b[?25h")  # Stop blinking cursor and show.

    def set_cursor_shape(self, cursor_shape: CursorShape) -> None:
        if cursor_shape == CursorShape._NEVER_CHANGE:
            return

        self._cursor_shape_changed = True
        self.write_raw(
            {
                CursorShape.BLOCK: "\x1b[2 q",
                CursorShape.BEAM: "\x1b[6 q",
                CursorShape.UNDERLINE: "\x1b[4 q",
                CursorShape.BLINKING_BLOCK: "\x1b[1 q",
                CursorShape.BLINKING_BEAM: "\x1b[5 q",
                CursorShape.BLINKING_UNDERLINE: "\x1b[3 q",
            }.get(cursor_shape, "")
        )

    def reset_cursor_shape(self) -> None:
        "Reset cursor shape."
        # (Only reset cursor shape, if we ever changed it.)
        if self._cursor_shape_changed:
            self._cursor_shape_changed = False

            # Reset cursor shape.
            self.write_raw("\x1b[0 q")

    def flush(self) -> None:
        """
        Write to output stream and flush.
        """
        if not self._buffer:
            return

        data = "".join(self._buffer)
        self._buffer = []

        flush_stdout(self.stdout, data)

    def ask_for_cpr(self) -> None:
        """
        Asks for a cursor position report (CPR).
        """
        self.write_raw("\x1b[6n")
        self.flush()

    @property
    def responds_to_cpr(self) -> bool:
        if not self.enable_cpr:
            return False

        # When the input is a tty, we assume that CPR is supported.
        # It's not when the input is piped from Pexpect.
        if os.environ.get("PROMPT_TOOLKIT_NO_CPR", "") == "1":
            return False

        if is_dumb_terminal(self.term):
            return False
        try:
            return self.stdout.isatty()
        except ValueError:
            return False  # ValueError: I/O operation on closed file

    def bell(self) -> None:
        "Sound bell."
        if self.enable_bell:
            self.write_raw("\a")
            self.flush()

    def get_default_color_depth(self) -> ColorDepth:
        """
        Return the default color depth for a vt100 terminal, according to the
        our term value.

        We prefer 256 colors almost always, because this is what most terminals
        support these days, and is a good default.
        """
        if self.default_color_depth is not None:
            return self.default_color_depth

        term = self.term

        if term is None:
            return ColorDepth.DEFAULT

        if is_dumb_terminal(term):
            return ColorDepth.DEPTH_1_BIT

        if term in ("linux", "eterm-color"):
            return ColorDepth.DEPTH_4_BIT

        return ColorDepth.DEFAULT
