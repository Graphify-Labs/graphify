"""Python grapheme, emoji, and sequence-aware ljust, rjust, center()."""
from __future__ import annotations

from typing import Literal

# local
from ._width import width


def ljust(
    text: str,
    dest_width: int,
    fillchar: str = ' ',
    *,
    control_codes: Literal['parse', 'strict', 'ignore'] = 'parse',
    ambiguous_width: int = 1,
    term_program: bool | str = False,
) -> str:
    r"""
    Return text left-justified in a string of given display width.

    :param text: String to justify, may contain terminal sequences.
    :param dest_width: Total display width of result in terminal cells.
    :param fillchar: Single character for padding (default space). Must have
        display width of 1 (not wide, not zero-width, not combining). Unicode
        characters like ``'·'`` are acceptable. The width is not validated.
    :param control_codes: How to handle control sequences when measuring.
        Passed to :func:`width` for measurement.
    :param ambiguous_width: Width to use for East Asian Ambiguous (A)
        characters. Default is ``1`` (narrow). Set to ``2`` for CJK contexts.
    :param term_program: Terminal software identifier for table correction.
        ``False`` (default) disables override lookup.  ``True`` reads the
        ``TERM_PROGRAM`` or ``TERM`` environment variable for auto-detection.
        Accepts a canonical terminal name matching :func:`list_term_programs`,
        such as from XTVERSION_, ENQ_, or ``TERM_PROGRAM``.

        .. versionadded:: 0.8.0
    :returns: Text padded on the right to reach ``dest_width``.

    .. versionadded:: 0.3.0

    Example::

        >>> wcwidth.ljust('hi', 5)
        'hi   '
        >>> wcwidth.ljust('\x1b[31mhi\x1b[0m', 5)
        '\x1b[31mhi\x1b[0m   '
        >>> wcwidth.ljust('\U0001F468\u200D\U0001F469\u200D\U0001F467', 6)
        '👨‍👩‍👧    '
    """
    if text.isascii() and text.isprintable():
        text_width = len(text)
    else:
        text_width = width(text, control_codes=control_codes, ambiguous_width=ambiguous_width,
                           term_program=term_program)
    padding_cells = max(0, dest_width - text_width)
    return text + fillchar * padding_cells


def rjust(
    text: str,
    dest_width: int,
    fillchar: str = ' ',
    *,
    control_codes: Literal['parse', 'strict', 'ignore'] = 'parse',
    ambiguous_width: int = 1,
    term_program: bool | str = False,
) -> str:
    r"""
    Return text right-justified in a string of given display width.

    :param text: String to justify, may contain terminal sequences.
    :param dest_width: Total display width of result in terminal cells.
    :param fillchar: Single character for padding (default space). Must have
        display width of 1 (not wide, not zero-width, not combining). Unicode
        characters like ``'·'`` are acceptable. The width is not validated.
    :param control_codes: How to handle control sequences when measuring.
        Passed to :func:`width` for measurement.
    :param ambiguous_width: Width to use for East Asian Ambiguous (A)
        characters. Default is ``1`` (narrow). Set to ``2`` for CJK contexts.
    :param term_program: Terminal software identifier for table correction.
        ``False`` (default) disables override lookup.  ``True`` reads the
        ``TERM_PROGRAM`` or ``TERM`` environment variable for auto-detection.
        Accepts a canonical terminal name matching :func:`list_term_programs`,
        such as from XTVERSION_, ENQ_, or ``TERM_PROGRAM``.

        .. versionadded:: 0.8.0
    :returns: Text padded on the left to reach ``dest_width``.

    .. versionadded:: 0.3.0

    Example::

        >>> wcwidth.rjust('hi', 5)
        '   hi'
        >>> wcwidth.rjust('\x1b[31mhi\x1b[0m', 5)
        '   \x1b[31mhi\x1b[0m'
        >>> wcwidth.rjust('\U0001F468\u200D\U0001F469\u200D\U0001F467', 6)
        '    👨‍👩‍👧'
    """
    if text.isascii() and text.isprintable():
        text_width = len(text)
    else:
        text_width = width(text, control_codes=control_codes, ambiguous_width=ambiguous_width,
                           term_program=term_program)
    padding_cells = max(0, dest_width - text_width)
    return fillchar * padding_cells + text


def center(
    text: str,
    dest_width: int,
    fillchar: str = ' ',
    *,
    control_codes: Literal['parse', 'strict', 'ignore'] = 'parse',
    ambiguous_width: int = 1,
    term_program: bool | str = False,
) -> str:
    r"""
    Return text centered in a string of given display width.

    :param text: String to center, may contain terminal sequences.
    :param dest_width: Total display width of result in terminal cells.
    :param fillchar: Single character for padding (default space). Must have
        display width of 1 (not wide, not zero-width, not combining). Unicode
        characters like ``'·'`` are acceptable. The width is not validated.
    :param control_codes: How to handle control sequences when measuring.
        Passed to :func:`width` for measurement.
    :param ambiguous_width: Width to use for East Asian Ambiguous (A)
        characters. Default is ``1`` (narrow). Set to ``2`` for CJK contexts.
    :param term_program: Terminal software identifier for table correction.
        ``False`` (default) disables override lookup.  ``True`` reads the
        ``TERM_PROGRAM`` or ``TERM`` environment variable for auto-detection.
        Accepts a canonical terminal name matching :func:`list_term_programs`,
        such as from XTVERSION_, ENQ_, or ``TERM_PROGRAM``.

        .. versionadded:: 0.8.0
    :returns: Text padded on both sides to reach ``dest_width``.

    For odd-width padding, the extra cell fills in the same cell position as
    Python's :meth:`str.center` behavior (the left side when ``dest_width`` is
    odd, the right side when ``dest_width`` is even).
    See `the eccentric str.center <https://jazcap53.github.io/pythons-eccentric-strcenter.html>`_.

    .. versionadded:: 0.3.0

    Example::

        >>> wcwidth.center('hi', 6)
        '  hi  '
        >>> wcwidth.center('\x1b[31mhi\x1b[0m', 6)
        '  \x1b[31mhi\x1b[0m  '
        >>> wcwidth.center('\U0001F468\u200D\U0001F469\u200D\U0001F467', 6)
        '  👨‍👩‍👧  '
    """
    if text.isascii() and text.isprintable():
        text_width = len(text)
    else:
        text_width = width(text, control_codes=control_codes, ambiguous_width=ambiguous_width,
                           term_program=term_program)
    total_padding = max(0, dest_width - text_width)
    # matching https://jazcap53.github.io/pythons-eccentric-strcenter.html
    left_pad = total_padding // 2 + (total_padding & dest_width & 1)
    right_pad = total_padding - left_pad
    return fillchar * left_pad + text + fillchar * right_pad
