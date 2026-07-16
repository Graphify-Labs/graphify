r"""
`kitty text sizing protocol`_ (OSC 66) parsing and measurement.

The kitty text sizing protocol allows terminal apps to explicitly tell
terminals how many cells text occupies, using the escape sequence::

    ESC ] 66 ; metadata ; text BEL/ST

Metadata is colon-separated ``key=value`` pairs:

- ``s``: scale
- ``w``: width in cells
- ``n``: fractional numerator
- ``d``: fractional denominator
- ``v``: vertical alignment
- ``h``: horizontal alignment

Parsing is pretty straight-forward:

- When ``w > 0``, return ``s * w``.
- Otherwise ``w == 0``, ``s * wcswidth(inner_text_width)`` cells.

Numerator, denominator, and alignment codes and values are parsed but otherwise ignored
and have no effect on measurements made in this library.

.. _`kitty text sizing protocol`: https://sw.kovidgoyal.net/kitty/text-sizing-protocol/

.. versionadded:: 0.7.0
"""

from __future__ import annotations

# std imports
import re

import typing

# local
from ._wcswidth import wcswidth


class _FieldMeta(typing.NamedTuple):
    name: str
    low: int
    high: int
    default: int


TEXT_FIELD_MAPPING: dict[str, _FieldMeta] = {
    's': _FieldMeta(name='scale', low=1, high=7, default=1),
    'w': _FieldMeta(name='width', low=0, high=7, default=0),
    'n': _FieldMeta(name='numerator', low=0, high=15, default=0),
    'd': _FieldMeta(name='denominator', low=0, high=15, default=0),
    'v': _FieldMeta(name='vertical_align', low=0, high=2, default=0),
    'h': _FieldMeta(name='horizontal_align', low=0, high=2, default=0)}


class TextSizingParams(typing.NamedTuple):
    """
    Parsed parameters from a text sizing escape sequence (OSC 66).

    :param scale: Scale factor (1-7). Text occupies ``scale`` rows tall and ``scale * width``
        columns wide.
    :param width: Width in cells (0-7). When 0, width is auto-calculated from the inner text.
    :param numerator: Fractional scaling numerator (0-15).
    :param denominator: Fractional scaling denominator (0-15).
    :param vertical_align: Vertical alignment (0=top, 1=bottom, 2=center).
    :param horizontal_align: Horizontal alignment (0=left, 1=right, 2=center).
    """

    scale: int = 1
    width: int = 0
    numerator: int = 0
    denominator: int = 0
    vertical_align: int = 0
    horizontal_align: int = 0

    def __repr__(self) -> str:
        """
        Return a compact representation including only non-default fields.

        This avoids verbose output when most fields are defaults.
        """
        # modified to show values only when non-default
        repr_fmt = ', '.join(f'{field.name}={getattr(self, field.name)}'
                             for field in TEXT_FIELD_MAPPING.values()
                             if getattr(self, field.name) != field.default)
        return f'{self.__class__.__name__}({repr_fmt})'

    def make_sequence(self) -> str:
        """Build and return sub-part of an OSC 66 sequence."""
        parts = []
        # build string for all known parameters of non-default values
        for field_key, field in TEXT_FIELD_MAPPING.items():
            if (val := getattr(self, field.name)) != field.default:
                parts.append(f'{field_key}={val}')
        return ':'.join(parts)

    @classmethod
    def from_params(cls, raw: str, control_codes: str = 'parse') -> TextSizingParams:
        """
        Parse colon-separated ``key=value`` metadata string.

        :param raw: Metadata string, e.g. ``'s=2:w=3'``.
        :param control_codes: 'parse' or 'strict'.
        :raises ValueError: If ``control_codes='strict'`` unrecognized text sizing parameters raise
            ValueError.
        :returns: Parsed parameters with values clamped to valid ranges.
            Unknown keys are ignored. Non-integer values use defaults.

        Example::

            >>> TextSizingParams.from_params('s=2:w=3')
            TextSizingParams(scale=2, width=3, numerator=0, denominator=0, \
            vertical_align=0, horizontal_align=0)
        """
        kwargs: typing.Dict[str, int] = {}
        if not raw:
            return cls()
        for part in raw.split(':'):
            if '=' not in part:
                if control_codes == 'strict':
                    raise ValueError(f"Expected '=' in text sizing parameter (key=val), "
                                     f"got {part!r} in OSC 66 sequence, {raw!r}")
                continue
            key, _eq, val = part.partition('=')
            field = TEXT_FIELD_MAPPING.get(key)
            if field is None:
                if control_codes == 'strict':
                    raise ValueError(f"Unknown text sizing field '{key}' "
                                     f"in OSC 66 sequence, {raw!r}")
                # ignore unknown fields unless 'strict'
                continue
            try:
                value = int(val)
            except ValueError as exc:
                if control_codes == 'strict':
                    raise ValueError(f"Illegal text sizing value '{val}' "
                                     f"in OSC 66 sequence, {raw!r}: {exc}") from exc
                # ignore value, uses default value without warning unless 'strict'
                continue
            if control_codes == 'strict' and (value > field.high or value < field.low):
                raise ValueError(f"Out of bounds text sizing value '{val}' "
                                 f"in OSC 66 sequence, {raw!r}: "
                                 f"allowed range for '{key}' ({field.name}) "
                                 f"is {field.low} to {field.high}")
            kwargs[field.name] = max(field.low, min(field.high, value))
        return cls(**kwargs)


class TextSizing(typing.NamedTuple):
    """Basic horizontal width measurement for kitty text sizing protocol."""

    params: TextSizingParams
    text: str
    terminator: str

    @classmethod
    def from_match(cls, match: re.Match[str], control_codes: str = 'parse') -> TextSizing:
        r"""
        Parse using matching OSC 66 Sequence.

        :param match: match object from :attr:`wcwidth.escape_sequences.TEXT_SIZING_PATTERN`.
        :param control_codes: 'parse' or 'strict', same meaning as delegated by
            :func:`wcwidth.width`.
        :raises ValueError: When ``control_codes='strict'`` for unrecognized, invalid, or out of
            bounds text sizing parameters.
        :returns: TextSizing object from parsed sequence

        Example::

            from wcwidth.escape_sequences import TEXT_SIZING_PATTERN
            >>> TextSizing.from_match(TEXT_SIZING_PATTERN.match('\x1b]66;w=2;XY\x07'))
            TextSizing(params=TextSizingParams(scale=1, width=2, numerator=0, denominator=0, \
            vertical_align=0, horizontal_align=0), text='XY', terminator='\x07')
        """
        return cls(params=TextSizingParams.from_params(match.group(1), control_codes=control_codes),
                   text=match.group(2),
                   terminator=match.group(3))

    def display_width(self, ambiguous_width: int = 1) -> int:
        """
        Calculate the display width of a text sizing sequence.

        :param ambiguous_width: Width for East Asian Ambiguous characters.
        :returns: Display width in terminal cells. When ``width > 0``, returns
            ``params.scale * params.width``. When ``width == 0``, returns
            ``params.scale * measured_inner_width``.

        .. note: Fractional scaling (numerator/denominator) does not affect the
            cell count, it adjusts only the font size within the cells allocated by 'w'.
        """
        if self.params.width > 0:
            return self.params.scale * self.params.width
        w = wcswidth(self.text, ambiguous_width=ambiguous_width)
        if w < 0:
            w = 0
        return self.params.scale * w

    def make_sequence(self) -> str:
        """Build and return complete OSC 66 Terminal Sequence."""
        return f'\x1b]66;{self.params.make_sequence()};{self.text}{self.terminator}'
