from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Callable

from prompt_toolkit.cache import FastDictCache
from prompt_toolkit.data_structures import Point
from prompt_toolkit.utils import get_cwidth

if TYPE_CHECKING:
    from .containers import Window


__all__ = [
    "Screen",
    "Char",
]


class Char:
    """
    Represent a single character in a :class:`.Screen`.

    This should be considered immutable.

    :param char: A single character (can be a double-width character).
    :param style: A style string. (Can contain classnames.)
    """

    __slots__ = ("char", "style", "width")

    # If we end up having one of these special control sequences in the input string,
    # we should display them as follows:
    # Usually this happens after a "quoted insert".
    display_mappings: dict[str, str] = {
        "\x00": "^@",  # Control space
        "\x01": "^A",
        "\x02": "^B",
        "\x03": "^C",
        "\x04": "^D",
        "\x05": "^E",
        "\x06": "^F",
        "\x07": "^G",
        "\x08": "^H",
        "\x09": "^I",
        "\x0a": "^J",
        "\x0b": "^K",
        "\x0c": "^L",
        "\x0d": "^M",
        "\x0e": "^N",
        "\x0f": "^O",
        "\x10": "^P",
        "\x11": "^Q",
        "\x12": "^R",
        "\x13": "^S",
        "\x14": "^T",
        "\x15": "^U",
        "\x16": "^V",
        "\x17": "^W",
        "\x18": "^X",
        "\x19": "^Y",
        "\x1a": "^Z",
        "\x1b": "^[",  # Escape
        "\x1c": "^\\",
        "\x1d": "^]",
        "\x1e": "^^",
        "\x1f": "^_",
        "\x7f": "^?",  # ASCII Delete (backspace).
        # Special characters. All visualized like Vim does.
        "\x80": "<80>",
        "\x81": "<81>",
        "\x82": "<82>",
        "\x83": "<83>",
        "\x84": "<84>",
        "\x85": "<85>",
        "\x86": "<86>",
        "\x87": "<87>",
        "\x88": "<88>",
        "\x89": "<89>",
        "\x8a": "<8a>",
        "\x8b": "<8b>",
        "\x8c": "<8c>",
        "\x8d": "<8d>",
        "\x8e": "<8e>",
        "\x8f": "<8f>",
        "\x90": "<90>",
        "\x91": "<91>",
        "\x92": "<92>",
        "\x93": "<93>",
        "\x94": "<94>",
        "\x95": "<95>",
        "\x96": "<96>",
        "\x97": "<97>",
        "\x98": "<98>",
        "\x99": "<99>",
        "\x9a": "<9a>",
        "\x9b": "<9b>",
        "\x9c": "<9c>",
        "\x9d": "<9d>",
        "\x9e": "<9e>",
        "\x9f": "<9f>",
        # For the non-breaking space: visualize like Emacs does by default.
        # (Print a space, but attach the 'nbsp' class that applies the
        # underline style.)
        "\xa0": " ",
    }

    def __init__(self, char: str = " ", style: str = "") -> None:
        # If this character has to be displayed otherwise, take that one.
        if char in self.display_mappings:
            if char == "\xa0":
                style += " class:nbsp "  # Will be underlined.
            else:
                style += " class:control-character "

            char = self.display_mappings[char]

        self.char = char
        self.style = style

        # Calculate width. (We always need this, so better to store it directly
        # as a member for performance.)
        self.width = get_cwidth(char)

    # In theory, `other` can be any type of object, but because of performance
    # we don't want to do an `isinstance` check every time. We assume "other"
    # is always a "Char".
    def _equal(self, other: Char) -> bool:
        return self.char == other.char and self.style == other.style

    def _not_equal(self, other: Char) -> bool:
        # Not equal: We don't do `not char.__eq__` here, because of the
        # performance of calling yet another function.
        return self.char != other.char or self.style != other.style

    if not TYPE_CHECKING:
        __eq__ = _equal
        __ne__ = _not_equal

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.char!r}, {self.style!r})"


_CHAR_CACHE: FastDictCache[tuple[str, str], Char] = FastDictCache(
    Char, size=1000 * 1000
)
Transparent = "[transparent]"


class Screen:
    """
    Two dimensional buffer of :class:`.Char` instances.
    """

    def __init__(
        self,
        default_char: Char | None = None,
        initial_width: int = 0,
        initial_height: int = 0,
    ) -> None:
        if default_char is None:
            default_char2 = _CHAR_CACHE[" ", Transparent]
        else:
            default_char2 = default_char

        self.data_buffer: defaultdict[int, defaultdict[int, Char]] = defaultdict(
            lambda: defaultdict(lambda: default_char2)
        )

        #: Escape sequences to be injected.
        self.zero_width_escapes: defaultdict[int, defaultdict[int, str]] = defaultdict(
            lambda: defaultdict(str)
        )

        #: Position of the cursor.
        self.cursor_positions: dict[
            Window, Point
        ] = {}  # Map `Window` objects to `Point` objects.

        #: Visibility of the cursor.
        self.show_cursor = True

        #: (Optional) Where to position the menu. E.g. at the start of a completion.
        #: (We can't use the cursor position, because we don't want the
        #: completion menu to change its position when we browse through all the
        #: completions.)
        self.menu_positions: dict[
            Window, Point
        ] = {}  # Map `Window` objects to `Point` objects.

        #: Currently used width/height of the screen. This will increase when
        #: data is written to the screen.
        self.width = initial_width or 0
        self.height = initial_height or 0

        # Windows that have been drawn. (Each `Window` class will add itself to
        # this list.)
        self.visible_windows_to_write_positions: dict[Window, WritePosition] = {}

        # List of (z_index, draw_func)
        self._draw_float_functions: list[tuple[int, Callable[[], None]]] = []

    @property
    def visible_windows(self) -> list[Window]:
        return list(self.visible_windows_to_write_positions.keys())

    def set_cursor_position(self, window: Window, position: Point) -> None:
        """
        Set the cursor position for a given window.
        """
        self.cursor_positions[window] = position

    def set_menu_position(self, window: Window, position: Point) -> None:
        """
        Set the cursor position for a given window.
        """
        self.menu_positions[window] = position

    def get_cursor_position(self, window: Window) -> Point:
        """
        Get the cursor position for a given window.
        Returns a `Point`.
        """
        try:
            return self.cursor_positions[window]
        except KeyError:
            return Point(x=0, y=0)

    def get_menu_position(self, window: Window) -> Point:
        """
        Get the menu position for a given window.
        (This falls back to the cursor position if no menu position was set.)
        """
        try:
            return self.menu_positions[window]
        except KeyError:
            try:
                return self.cursor_positions[window]
            except KeyError:
                return Point(x=0, y=0)

    def draw_with_z_index(self, z_index: int, draw_func: Callable[[], None]) -> None:
        """
        Add a draw-function for a `Window` which has a >= 0 z_index.
        This will be postponed until `draw_all_floats` is called.
        """
        self._draw_float_functions.append((z_index, draw_func))

    def draw_all_floats(self) -> None:
        """
        Draw all float functions in order of z-index.
        """
        # We keep looping because some draw functions could add new functions
        # to this list. See `FloatContainer`.
        while self._draw_float_functions:
            # Sort the floats that we have so far by z_index.
            functions = sorted(self._draw_float_functions, key=lambda item: item[0])

            # Draw only one at a time, then sort everything again. Now floats
            # might have been added.
            self._draw_float_functions = functions[1:]
            functions[0][1]()

    def append_style_to_content(self, style_str: str) -> None:
        """
        For all the characters in the screen.
        Set the style string to the given `style_str`.
        """
        b = self.data_buffer
        char_cache = _CHAR_CACHE

        append_style = " " + style_str

        for y, row in b.items():
            for x, char in row.items():
                row[x] = char_cache[char.char, char.style + append_style]

    def fill_area(
        self, write_position: WritePosition, style: str = "", after: bool = False
    ) -> None:
        """
        Fill the content of this area, using the given `style`.
        The style is prepended before whatever was here before.
        """
        if not style.strip():
            return

        xmin = write_position.xpos
        xmax = write_position.xpos + write_position.width
        char_cache = _CHAR_CACHE
        data_buffer = self.data_buffer

        if after:
            append_style = " " + style
            prepend_style = ""
        else:
            append_style = ""
            prepend_style = style + " "

        for y in range(
            write_position.ypos, write_position.ypos + write_position.height
        ):
            row = data_buffer[y]
            for x in range(xmin, xmax):
                cell = row[x]
                row[x] = char_cache[
                    cell.char, prepend_style + cell.style + append_style
                ]


class WritePosition:
    def __init__(self, xpos: int, ypos: int, width: int, height: int) -> None:
        assert height >= 0
        assert width >= 0
        # xpos and ypos can be negative. (A float can be partially visible.)

        self.xpos = xpos
        self.ypos = ypos
        self.width = width
        self.height = height

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(x={self.xpos!r}, y={self.ypos!r}, width={self.width!r}, height={self.height!r})"
