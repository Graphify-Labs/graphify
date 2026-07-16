"""Helper functions for writing to terminals and files."""

from __future__ import annotations

from collections.abc import Sequence
import os
import shutil
import sys
from typing import final
from typing import Literal
from typing import TextIO

import pygments
from pygments.formatters.terminal import TerminalFormatter
from pygments.lexer import Lexer
from pygments.lexers.diff import DiffLexer
from pygments.lexers.python import PythonLexer

from ..compat import assert_never
from .wcwidth import wcswidth


# This code was initially copied from py 1.8.1, file _io/terminalwriter.py.


def get_terminal_width() -> int:
    width, _ = shutil.get_terminal_size(fallback=(80, 24))

    # The Windows get_terminal_size may be bogus, let's sanify a bit.
    if width < 40:
        width = 80

    return width


def should_do_markup(file: TextIO) -> bool:
    if os.environ.get("PY_COLORS") == "1":
        return True
    if os.environ.get("PY_COLORS") == "0":
        return False
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return (
        hasattr(file, "isatty") and file.isatty() and os.environ.get("TERM") != "dumb"
    )


@final
class TerminalWriter:
    _esctable = dict(
        black=30,
        red=31,
        green=32,
        yellow=33,
        blue=34,
        purple=35,
        cyan=36,
        white=37,
        Black=40,
        Red=41,
        Green=42,
        Yellow=43,
        Blue=44,
        Purple=45,
        Cyan=46,
        White=47,
        bold=1,
        light=2,
        blink=5,
        invert=7,
    )

    def __init__(self, file: TextIO | None = None) -> None:
        if file is None:
            file = sys.stdout
        if hasattr(file, "isatty") and file.isatty() and sys.platform == "win32":
            try:
                import colorama
            except ImportError:
                pass
            else:
                file = colorama.AnsiToWin32(file).stream
                assert file is not None
        self._file = file
        self.hasmarkup = should_do_markup(file)
        self._current_line = ""
        self._terminal_width: int | None = None
        self.code_highlight = True

    @property
    def fullwidth(self) -> int:
        if self._terminal_width is not None:
            return self._terminal_width
        return get_terminal_width()

    @fullwidth.setter
    def fullwidth(self, value: int) -> None:
        self._terminal_width = value

    @property
    def width_of_current_line(self) -> int:
        """Return an estimate of the width so far in the current line."""
        return wcswidth(self._current_line)

    def markup(self, text: str, **markup: bool) -> str:
        for name in markup:
            if name not in self._esctable:
                raise ValueError(f"unknown markup: {name!r}")
        if self.hasmarkup:
            esc = [self._esctable[name] for name, on in markup.items() if on]
            if esc:
                text = "".join(f"\x1b[{cod}m" for cod in esc) + text + "\x1b[0m"
        return text

    def sep(
        self,
        sepchar: str,
        title: str | None = None,
        fullwidth: int | None = None,
        **markup: bool,
    ) -> None:
        if fullwidth is None:
            fullwidth = self.fullwidth
        # The goal is to have the line be as long as possible
        # under the condition that len(line) <= fullwidth.
        if sys.platform == "win32":
            # If we print in the last column on windows we are on a
            # new line but there is no way to verify/neutralize this
            # (we may not know the exact line width).
            # So let's be defensive to avoid empty lines in the output.
            fullwidth -= 1
        if title is not None:
            # we want 2 + 2*len(fill) + len(title) <= fullwidth
            # i.e.    2 + 2*len(sepchar)*N + len(title) <= fullwidth
            #         2*len(sepchar)*N <= fullwidth - len(title) - 2
            #         N <= (fullwidth - len(title) - 2) // (2*len(sepchar))
            N = max((fullwidth - len(title) - 2) // (2 * len(sepchar)), 1)
            fill = sepchar * N
            line = f"{fill} {title} {fill}"
        else:
            # we want len(sepchar)*N <= fullwidth
            # i.e.    N <= fullwidth // len(sepchar)
            line = sepchar * (fullwidth // len(sepchar))
        # In some situations there is room for an extra sepchar at the right,
        # in particular if we consider that with a sepchar like "_ " the
        # trailing space is not important at the end of the line.
        if len(line) + len(sepchar.rstrip()) <= fullwidth:
            line += sepchar.rstrip()

        self.line(line, **markup)

    def write(self, msg: str, *, flush: bool = False, **markup: bool) -> None:
        if msg:
            current_line = msg.rsplit("\n", 1)[-1]
            if "\n" in msg:
                self._current_line = current_line
            else:
                self._current_line += current_line

            msg = self.markup(msg, **markup)

            self.write_raw(msg, flush=flush)

    def write_raw(self, msg: str, *, flush: bool = False) -> None:
        try:
            self._file.write(msg)
        except UnicodeEncodeError:
            # Some environments don't support printing general Unicode
            # strings, due to misconfiguration or otherwise; in that case,
            # print the string escaped to ASCII.
            # When the Unicode situation improves we should consider
            # letting the error propagate instead of masking it (see #7475
            # for one brief attempt).
            msg = msg.encode("unicode-escape").decode("ascii")
            self._file.write(msg)

        if flush:
            self.flush()

    def line(self, s: str = "", **markup: bool) -> None:
        self.write(s, **markup)
        self.write("\n")

    def flush(self) -> None:
        self._file.flush()

    def _write_source(self, lines: Sequence[str], indents: Sequence[str] = ()) -> None:
        """Write lines of source code possibly highlighted.

        Keeping this private for now because the API is clunky. We should discuss how
        to evolve the terminal writer so we can have more precise color support, for example
        being able to write part of a line in one color and the rest in another, and so on.
        """
        if indents and len(indents) != len(lines):
            raise ValueError(
                f"indents size ({len(indents)}) should have same size as lines ({len(lines)})"
            )
        if not indents:
            indents = [""] * len(lines)
        source = "\n".join(lines)
        new_lines = self._highlight(source).splitlines()
        # Would be better to strict=True but that fails some CI jobs.
        for indent, new_line in zip(indents, new_lines, strict=False):
            self.line(indent + new_line)

    def _get_pygments_lexer(self, lexer: Literal["python", "diff"]) -> Lexer:
        if lexer == "python":
            return PythonLexer()
        elif lexer == "diff":
            return DiffLexer()
        else:
            assert_never(lexer)

    def _get_pygments_formatter(self) -> TerminalFormatter:
        from _pytest.config.exceptions import UsageError

        theme = os.getenv("PYTEST_THEME")
        theme_mode = os.getenv("PYTEST_THEME_MODE", "dark")

        try:
            return TerminalFormatter(bg=theme_mode, style=theme)
        except pygments.util.ClassNotFound as e:
            raise UsageError(
                f"PYTEST_THEME environment variable has an invalid value: '{theme}'. "
                "Hint: See available pygments styles with `pygmentize -L styles`."
            ) from e
        except pygments.util.OptionError as e:
            raise UsageError(
                f"PYTEST_THEME_MODE environment variable has an invalid value: '{theme_mode}'. "
                "The allowed values are 'dark' (default) and 'light'."
            ) from e

    def _highlight(
        self, source: str, lexer: Literal["diff", "python"] = "python"
    ) -> str:
        """Highlight the given source if we have markup support."""
        if not source or not self.hasmarkup or not self.code_highlight:
            return source

        pygments_lexer = self._get_pygments_lexer(lexer)
        pygments_formatter = self._get_pygments_formatter()

        highlighted: str = pygments.highlight(
            source, pygments_lexer, pygments_formatter
        )
        # pygments terminal formatter may add a newline when there wasn't one.
        # We don't want this, remove.
        if highlighted[-1] == "\n" and source[-1] != "\n":
            highlighted = highlighted[:-1]

        # Some lexers will not set the initial color explicitly
        # which may lead to the previous color being propagated to the
        # start of the expression, so reset first.
        highlighted = "\x1b[0m" + highlighted

        return highlighted
