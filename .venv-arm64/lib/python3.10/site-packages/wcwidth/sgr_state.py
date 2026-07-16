"""
SGR (Select Graphic Rendition) state tracking for terminal escape sequences.

This module provides functions for tracking and propagating terminal styling (bold, italic, colors,
etc.) via public API propagate_sgr(), and its dependent functions, cut() and wrap(). It only has
attributes necessary to perform its functions, eg 'RED' and 'BLUE' attributes are not defined.
"""

from __future__ import annotations

# std imports
import re
from enum import IntEnum

from typing import TYPE_CHECKING, Iterator, NamedTuple

if TYPE_CHECKING:  # pragma: no cover
    from typing import Sequence


class _SGR(IntEnum):
    """
    SGR (Select Graphic Rendition) parameter codes.

    References:
    - https://invisible-island.net/xterm/ctlseqs/ctlseqs.html
    - https://github.com/tehmaze/ansi/tree/master/ansi/colour
    """

    RESET = 0
    BOLD = 1
    DIM = 2
    ITALIC = 3
    UNDERLINE = 4
    BLINK = 5
    RAPID_BLINK = 6
    INVERSE = 7
    HIDDEN = 8
    STRIKETHROUGH = 9
    DOUBLE_UNDERLINE = 21
    BOLD_DIM_OFF = 22
    ITALIC_OFF = 23
    UNDERLINE_OFF = 24
    BLINK_OFF = 25
    INVERSE_OFF = 27
    HIDDEN_OFF = 28
    STRIKETHROUGH_OFF = 29
    FG_BLACK = 30
    FG_WHITE = 37
    FG_EXTENDED = 38
    FG_DEFAULT = 39
    BG_BLACK = 40
    BG_WHITE = 47
    BG_EXTENDED = 48
    BG_DEFAULT = 49
    FG_BRIGHT_BLACK = 90
    FG_BRIGHT_WHITE = 97
    BG_BRIGHT_BLACK = 100
    BG_BRIGHT_WHITE = 107


# SGR sequence pattern: CSI followed by params (digits, semicolons, colons) ending with 'm'
# Colons are used in ITU T.416 (ISO 8613-6) extended color format: 38:2::R:G:B
# This colon format is less common than semicolon (38;2;R;G;B) but supported by kitty,
# iTerm2, and newer VTE-based terminals.
_SGR_PATTERN = re.compile(r'\x1b\[([\d;:]*)m')

# Fast path: quick check if any SGR sequence exists
_SGR_QUICK_CHECK = re.compile(r'\x1b\[[\d;:]*m')

# Reset sequence
_SGR_RESET = '\x1b[0m'


class _SGRState(NamedTuple):
    """
    Track active SGR terminal attributes by category (immutable).

    :param bold: Bold attribute (SGR 1).
    :param dim: Dim/faint attribute (SGR 2).
    :param italic: Italic attribute (SGR 3).
    :param underline: Underline attribute (SGR 4).
    :param blink: Slow blink attribute (SGR 5).
    :param rapid_blink: Rapid blink attribute (SGR 6).
    :param inverse: Inverse/reverse attribute (SGR 7).
    :param hidden: Hidden/invisible attribute (SGR 8).
    :param strikethrough: Strikethrough attribute (SGR 9).
    :param double_underline: Double underline attribute (SGR 21).
    :param foreground: Foreground color as tuple of SGR params, or None for default.
    :param background: Background color as tuple of SGR params, or None for default.
    """

    bold: bool = False
    dim: bool = False
    italic: bool = False
    underline: bool = False
    blink: bool = False
    rapid_blink: bool = False
    inverse: bool = False
    hidden: bool = False
    strikethrough: bool = False
    double_underline: bool = False
    foreground: tuple[int, ...] | None = None
    background: tuple[int, ...] | None = None


# Default state with no attributes set
_SGR_STATE_DEFAULT = _SGRState()


def _sgr_state_is_active(state: _SGRState) -> bool:
    """
    Return True if any attributes are set.

    :param state: The SGR state to check.
    :returns: True if any attribute differs from default.
    """
    return (state.bold or state.dim or state.italic or state.underline
            or state.blink or state.rapid_blink or state.inverse or state.hidden
            or state.strikethrough or state.double_underline
            or state.foreground is not None or state.background is not None)


def _sgr_state_to_sequence(state: _SGRState) -> str:
    """
    Generate minimal SGR sequence to restore this state from reset.

    :param state: The SGR state to convert.
    :returns: SGR escape sequence string, or empty string if no attributes set.
    """
    if not _sgr_state_is_active(state):
        return ''

    # Map boolean attributes to their SGR codes
    bool_attrs = [
        (state.bold, '1'), (state.dim, '2'), (state.italic, '3'),
        (state.underline, '4'), (state.blink, '5'), (state.rapid_blink, '6'),
        (state.inverse, '7'), (state.hidden, '8'), (state.strikethrough, '9'),
        (state.double_underline, '21'),
    ]
    params = [code for active, code in bool_attrs if active]

    # Add color params (already formatted as tuples)
    if state.foreground is not None:
        params.append(';'.join(str(p) for p in state.foreground))
    if state.background is not None:
        params.append(';'.join(str(p) for p in state.background))

    return f'\x1b[{";".join(params)}m'


def _parse_sgr_params(sequence: str) -> list[int | tuple[int, ...]]:
    r"""
    Parse SGR sequence and return list of parameter values.

    Handles compound sequences like ``\x1b[1;31;4m`` -> [1, 31, 4].
    Empty params (e.g., ``\x1b[m``) are treated as [0] (reset).
    Colon-separated extended colors like ``\x1b[38:2::255:0:0m`` are returned
    as tuples: [(38, 2, 255, 0, 0)].

    :param sequence: SGR escape sequence string.
    :returns: List of integer parameters or tuples for colon-separated colors.
    """
    match = _SGR_PATTERN.match(sequence)
    if not match:
        return []
    params_str = match.group(1)
    if not params_str:
        return [0]  # \x1b[m is equivalent to \x1b[0m
    result: list[int | tuple[int, ...]] = []
    for param in params_str.split(';'):
        if ':' in param:
            # Colon-separated extended color (ITU T.416 format)
            # e.g., "38:2::255:0:0" or "38:2:1:255:0:0" (with colorspace)
            parts = [int(p) if p else 0 for p in param.split(':')]
            result.append(tuple(parts))
        else:
            result.append(int(param) if param else 0)
    return result


def _parse_extended_color(
    params: Iterator[int | tuple[int, ...]], base: int
) -> tuple[int, ...] | None:
    """
    Parse extended color (256-color or RGB) from parameter iterator.

    :param params: Iterator of remaining SGR parameters (semicolon-separated format).
    :param base: Base code (38 for foreground, 48 for background).
    :returns: Color tuple like (38, 5, N) or (38, 2, R, G, B), or None if malformed.
    """
    try:
        mode = next(params)
        if isinstance(mode, tuple):
            return None  # Unexpected tuple, colon format handled separately
        if mode == 5:  # 256-color
            n = next(params)
            if isinstance(n, tuple):
                return None
            return (int(base), 5, n)
        if mode == 2:  # RGB
            r, g, b = next(params), next(params), next(params)
            if isinstance(r, tuple) or isinstance(g, tuple) or isinstance(b, tuple):
                return None
            return (int(base), 2, r, g, b)
    except StopIteration:
        pass
    return None


def _sgr_state_update(state: _SGRState, sequence: str) -> _SGRState:
    # pylint: disable=too-many-branches,too-complex,too-many-statements
    # NOTE: When minimum Python version is 3.10+, this can be simplified using match/case.
    """
    Parse SGR sequence and return new state with updates applied.

    :param state: Current SGR state.
    :param sequence: SGR escape sequence string.
    :returns: New SGRState with updates applied.
    """
    params_list = _parse_sgr_params(sequence)
    params = iter(params_list)
    for p in params:
        # Handle colon-separated extended colors (ITU T.416 format)
        if isinstance(p, tuple):
            if len(p) >= 2 and p[0] == _SGR.FG_EXTENDED:
                # Foreground: (38, 2, [colorspace,] R, G, B) or (38, 5, N)
                state = state._replace(foreground=p)
            elif len(p) >= 2 and p[0] == _SGR.BG_EXTENDED:
                # Background: (48, 2, [colorspace,] R, G, B) or (48, 5, N)
                state = state._replace(background=p)
            continue
        if p == _SGR.RESET:
            state = _SGR_STATE_DEFAULT
        # Attribute ON codes
        elif p == _SGR.BOLD:
            state = state._replace(bold=True)
        elif p == _SGR.DIM:
            state = state._replace(dim=True)
        elif p == _SGR.ITALIC:
            state = state._replace(italic=True)
        elif p == _SGR.UNDERLINE:
            state = state._replace(underline=True)
        elif p == _SGR.BLINK:
            state = state._replace(blink=True)
        elif p == _SGR.RAPID_BLINK:
            state = state._replace(rapid_blink=True)
        elif p == _SGR.INVERSE:
            state = state._replace(inverse=True)
        elif p == _SGR.HIDDEN:
            state = state._replace(hidden=True)
        elif p == _SGR.STRIKETHROUGH:
            state = state._replace(strikethrough=True)
        elif p == _SGR.DOUBLE_UNDERLINE:
            state = state._replace(double_underline=True)
        # Attribute OFF codes
        elif p == _SGR.BOLD_DIM_OFF:
            state = state._replace(bold=False, dim=False)
        elif p == _SGR.ITALIC_OFF:
            state = state._replace(italic=False)
        elif p == _SGR.UNDERLINE_OFF:
            state = state._replace(underline=False, double_underline=False)
        elif p == _SGR.BLINK_OFF:
            state = state._replace(blink=False, rapid_blink=False)
        elif p == _SGR.INVERSE_OFF:
            state = state._replace(inverse=False)
        elif p == _SGR.HIDDEN_OFF:
            state = state._replace(hidden=False)
        elif p == _SGR.STRIKETHROUGH_OFF:
            state = state._replace(strikethrough=False)
        # Basic colors (30-37, 40-47 standard; 90-97, 100-107 bright)
        elif (_SGR.FG_BLACK <= p <= _SGR.FG_WHITE
              or _SGR.FG_BRIGHT_BLACK <= p <= _SGR.FG_BRIGHT_WHITE):
            state = state._replace(foreground=(p,))
        elif (_SGR.BG_BLACK <= p <= _SGR.BG_WHITE
              or _SGR.BG_BRIGHT_BLACK <= p <= _SGR.BG_BRIGHT_WHITE):
            state = state._replace(background=(p,))
        elif p == _SGR.FG_DEFAULT:
            state = state._replace(foreground=None)
        elif p == _SGR.BG_DEFAULT:
            state = state._replace(background=None)
        # Extended colors (semicolon-separated format)
        elif p == _SGR.FG_EXTENDED:
            if color := _parse_extended_color(params, _SGR.FG_EXTENDED):
                state = state._replace(foreground=color)
        elif p == _SGR.BG_EXTENDED:
            if color := _parse_extended_color(params, _SGR.BG_EXTENDED):
                state = state._replace(background=color)
    return state


def propagate_sgr(lines: Sequence[str]) -> list[str]:
    r"""
    Propagate SGR codes across wrapped lines.

    When text with SGR styling is wrapped across multiple lines, each line
    needs to be self-contained for proper display. This function:

    - Ends each line with ``\x1b[0m`` if styles are active (prevents bleeding)
    - Starts each subsequent line with the active style restored

    :param lines: List of text lines, possibly containing SGR sequences.
    :returns: List of lines with SGR codes propagated.

    Example::

        >>> propagate_sgr(['\x1b[31mhello', 'world\x1b[0m'])
        ['\x1b[31mhello\x1b[0m', '\x1b[31mworld\x1b[0m']

    This is useful in cases of making special editors and viewers, and is used for the
    default modes (propagate_sgr=True) of :func:`wcwidth.wrap` and :func:`wcwidth.clip`.

    When wrapping and clipping text containing SGR sequences, maybe a previous line enabled the BLUE
    color--if we are viewing *only* the line following, we would want the carry over the BLUE color,
    and all lines with sequences should end with terminating reset (``\x1b[0m``).
    """
    # Fast path: check if any line contains SGR sequences
    if not any(_SGR_QUICK_CHECK.search(line) for line in lines) or not lines:
        return list(lines)

    result: list[str] = []
    state = _SGR_STATE_DEFAULT

    for line in lines:
        # Prefix with restoration sequence if state is active
        prefix = _sgr_state_to_sequence(state)

        # Update state by processing all SGR sequences in this line
        for match in _SGR_PATTERN.finditer(line):
            state = _sgr_state_update(state, match.group())

        # Build output line
        output_line = prefix + line if prefix else line
        if _sgr_state_is_active(state):
            output_line = output_line + _SGR_RESET

        result.append(output_line)

    return result
