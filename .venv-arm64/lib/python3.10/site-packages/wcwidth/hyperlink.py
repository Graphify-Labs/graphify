"""
OSC 8 hyperlink parsing and measurement.

.. versionadded:: 0.7.0
"""

from __future__ import annotations

# std imports
import re

import typing

# local
from ._width import width as _width
from .escape_sequences import _SEQUENCE_CLASSIFY

HYPERLINK_OPEN_RE = re.compile(r'\x1b]8;([^;]*);([^\x07\x1b]*)(\x07|\x1b\\)')
HYPERLINK_CLOSE_RE = re.compile(r'\x1b]8;;(\x07|\x1b\\)')


class HyperlinkParams(typing.NamedTuple):
    r"""
    Parsed parameters from an OSC 8 hyperlink open sequence.

    :param url: The hyperlink URL.
    :param params: Colon-separated metadata string (often empty).
    :param terminator: Sequence terminator (``\x07`` or ``\x1b\\``).
    """

    url: str
    params: str = ''
    terminator: str = '\x07'

    @classmethod
    def parse(cls, seq: str) -> HyperlinkParams | None:
        r"""
        Parse an OSC 8 open sequence string.

        Returns ``None`` if *seq* is not a valid OSC 8 open.

        Example::

            >>> HyperlinkParams.parse('\x1b]8;;http://example.com\x07')
            HyperlinkParams(url='http://example.com', params='', terminator='\\x07')
        """
        m = HYPERLINK_OPEN_RE.match(seq)
        if m is None:
            return None
        return cls(url=m.group(2), params=m.group(1), terminator=m.group(3))

    def make_open(self) -> str:
        """Generate the OSC 8 open escape sequence."""
        return f'\x1b]8;{self.params};{self.url}{self.terminator}'

    def make_close(self) -> str:
        """Generate the OSC 8 close escape sequence."""
        return f'\x1b]8;;{self.terminator}'


class Hyperlink(typing.NamedTuple):
    """
    A complete OSC 8 hyperlink with target and inner text.

    :param params: Parsed open sequence parameters.
    :param text: Inner text between the open and close sequences.
    """

    params: HyperlinkParams
    text: str

    @classmethod
    def find_close(cls, text: str, open_end: int) -> tuple[int, int]:
        """
        Find the matching OSC 8 close sequence.

        Searches 'text' starting at 'open_end', the position just past the open
        sequence.  Returns position of close sequence ``(close_start,
        close_end)`` or ``(-1, -1)`` if not found.

        Per the OSC 8 specification, terminal emulators treat hyperlinks as a
        state attribute, not as nested HTML anchors.  A close sequence closes
        the current hyperlink regardless of how many open sequences preceded it.
        """
        m = HYPERLINK_CLOSE_RE.search(text, open_end)
        if m is None:
            return (-1, -1)
        return (m.start(), m.end())

    def display_width(
        self,
        *,
        control_codes: typing.Literal['parse', 'strict', 'ignore'] = 'parse',
        tabsize: int = 8,
        ambiguous_width: int = 1,
    ) -> int:
        r"""
        Measure the display width of the hyperlink's inner text.

        Delegates to :func:`wcwidth.width` with the given parameters.

        Example::

            >>> hl = Hyperlink.parse('\x1b]8;;http://example.com\x07Hello\x1b]8;;\x07', 0)
            >>> hl.display_width()
            5
        """
        return _width(
            self.text,
            control_codes=control_codes,
            tabsize=tabsize,
            ambiguous_width=ambiguous_width,
        )

    @classmethod
    def parse(cls, text: str, start: int = 0) -> Hyperlink | None:
        r"""
        Parse a complete OSC 8 hyperlink unit from *text* at position *start*.

        Locates the open sequence, finds the matching close, and returns a
        ``Hyperlink`` containing the parsed parameters and inner text.  Returns
        ``None`` if the text at *start* is not a complete OSC 8 hyperlink.

        Example::

            >>> Hyperlink.parse('\x1b]8;;http://example.com\x07Hello\x1b]8;;\x07')
            Hyperlink(params=HyperlinkParams(url='http://example.com', ...), text='Hello')
        """
        m = _SEQUENCE_CLASSIFY.match(text, start)
        if m is None:
            return None
        params = HyperlinkParams.parse(m.group())
        if params is None:
            return None
        close_start, close_end = cls.find_close(text, m.end())
        if (close_start, close_end) == (-1, -1):
            return None
        return cls(params=params, text=text[m.end():close_start])

    def make_sequence(self) -> str:
        """Rebuild the complete OSC 8 hyperlink escape sequence."""
        return self.params.make_open() + self.text + self.params.make_close()
