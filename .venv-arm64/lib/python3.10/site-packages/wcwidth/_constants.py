"""Shared data tables and constants for wcwidth.py, _wcwidth.py, and _wcswidth.py."""
from __future__ import annotations

# std imports
import os
from functools import lru_cache

from typing import Tuple, NamedTuple

# local
from .table_mc import CATEGORY_MC
from .table_wide import WIDE_EASTASIAN
from .table_zero import ZERO_WIDTH
from .table_grapheme import (ISC_VIRAMA,
                             EXTENDED_PICTOGRAPHIC,
                             ISC_INVISIBLE_STACKER,
                             GRAPHEME_REGIONAL_INDICATOR)
from .table_ambiguous import AMBIGUOUS_EASTASIAN
from .table_overrides import (SFZ_OVERRIDES,
                              SRI_OVERRIDES,
                              VS15_OVERRIDES,
                              VS16_OVERRIDES,
                              WIDE_OVERRIDES,
                              NARROW_OVERRIDES)
from .unicode_versions import list_versions
from .table_term_programs import ALIASES, KNOWN_TERMINALS

_RangeTuple = Tuple[Tuple[int, int], ...]


__all__ = (
    "_REGIONAL_INDICATOR_SET",
    "_ISC_VIRAMA_SET",
    "_LATEST_VERSION",
    "_CATEGORY_MC_TABLE",
    "_EMOJI_ZWJ_SET",
    "_FITZPATRICK_RANGE",
    "_ZERO_WIDTH_TABLE",
    "_WIDE_EASTASIAN_TABLE",
    "_AMBIGUOUS_TABLE",
    "resolve_terminal",
    "get_term_overrides",
    "list_term_programs",
)

_REGIONAL_INDICATOR_SET = frozenset(
    range(GRAPHEME_REGIONAL_INDICATOR[0][0], GRAPHEME_REGIONAL_INDICATOR[0][1] + 1)
)
_ISC_VIRAMA_SET = frozenset(
    cp for lo, hi in (*ISC_VIRAMA, *ISC_INVISIBLE_STACKER)
    for cp in range(lo, hi + 1)
)
# pylint: disable=invalid-name
_LATEST_VERSION = list_versions()[-1]
_CATEGORY_MC_TABLE = CATEGORY_MC[_LATEST_VERSION]
_EMOJI_ZWJ_SET = frozenset(
    cp for lo, hi in EXTENDED_PICTOGRAPHIC for cp in range(lo, hi + 1)
) | _REGIONAL_INDICATOR_SET
_FITZPATRICK_RANGE = (0x1F3FB, 0x1F3FF)

_ZERO_WIDTH_TABLE = ZERO_WIDTH[_LATEST_VERSION]
_WIDE_EASTASIAN_TABLE = WIDE_EASTASIAN[_LATEST_VERSION]
_AMBIGUOUS_TABLE = AMBIGUOUS_EASTASIAN[_LATEST_VERSION]


def list_term_programs() -> tuple[str, ...]:
    """
    Return all recognized values for the ``term_program`` argument.

    Includes canonical terminal names and their TERM/TERM_PROGRAM aliases.

    .. versionadded:: 0.8.0
    """
    return tuple(sorted(KNOWN_TERMINALS | ALIASES.keys()))


def _merge_ranges(*tuples: _RangeTuple) -> _RangeTuple:
    """Merge multiple sorted range tuples into one sorted, non-overlapping tuple."""
    all_ranges: list[tuple[int, int]] = []
    for t in tuples:
        all_ranges.extend(t)
    if not all_ranges:
        return ()
    all_ranges.sort(key=lambda r: r[0])
    merged = [all_ranges[0]]
    for lo, hi in all_ranges[1:]:
        _, prev_hi = merged[-1]
        if lo <= prev_hi:
            merged[-1] = (merged[-1][0], max(prev_hi, hi))
        else:
            merged.append((lo, hi))
    return tuple(merged)


class TerminalOverrides(NamedTuple):
    """Pre-merged override range tuples for a single terminal."""

    narrower: _RangeTuple
    vs16_narrower: _RangeTuple
    vs15_wider: _RangeTuple
    zeroer: _RangeTuple
    narrow_wider: _RangeTuple
    narrow_zeroer: _RangeTuple


_EMPTY_OVERRIDES = TerminalOverrides((), (), (), (), (), ())


@lru_cache(maxsize=32)
def get_term_overrides(term_canonical: str) -> TerminalOverrides:
    """Return a TerminalOverrides, with all empty tuples when there are no overrides."""
    # wide, sri, sfz: all narrow characters Unicode expects wide (no 'wider' data exists)
    narrower = _merge_ranges(
        WIDE_OVERRIDES.get(term_canonical, {}).get('narrower', ()),
        SRI_OVERRIDES.get(term_canonical, {}).get('narrower', ()),
        SFZ_OVERRIDES.get(term_canonical, {}).get('narrower', ()),
    )
    vs16_narrower = VS16_OVERRIDES.get(term_canonical, {}).get('narrower', ())
    vs15_wider = VS15_OVERRIDES.get(term_canonical, {}).get('wider', ())
    zeroer = _merge_ranges(
        WIDE_OVERRIDES.get(term_canonical, {}).get('zeroer', ()),
        SRI_OVERRIDES.get(term_canonical, {}).get('zeroer', ()),
        SFZ_OVERRIDES.get(term_canonical, {}).get('zeroer', ()),
    )
    narrow_wider = NARROW_OVERRIDES.get(term_canonical, {}).get('wider', ())
    narrow_zeroer = NARROW_OVERRIDES.get(term_canonical, {}).get('narrow_zeroer', ())
    # vs15_narrower intentionally excluded: no known terminal narrows VS15
    # vs16_wider intentionally excluded: any 'wider' entries in emoji_vs16_results
    #   ucs-detect YAML are from the vs16n baseline test (base char without VS16),
    #   not actual VS16 correction data.

    if not (narrower or vs16_narrower or vs15_wider or zeroer
            or narrow_wider or narrow_zeroer):
        return _EMPTY_OVERRIDES
    return TerminalOverrides(narrower, vs16_narrower, vs15_wider, zeroer,
                             narrow_wider, narrow_zeroer)


@lru_cache(maxsize=32)
def resolve_terminal(term_program: bool | str = False) -> str | None:
    """
    Resolve a terminal identifier to its canonical name.

    :param term_program: Terminal identifier.  ``False`` (default) disables override lookup.
        ``True`` reads the ``TERM_PROGRAM`` environment variable, falling back to ``TERM``.
        A string value is used directly (canonical name, alias, XTVERSION/ENQ result, etc.).
    :returns: Canonical terminal name if recognized, ``None`` otherwise.

    The auto-detection path (``term_program=True``) reads environment variables at call time
    and caches the result.  The environment is assumed immutable for the process lifetime;
    callers that change ``TERM`` or ``TERM_PROGRAM`` mid-process must call
    :func:`resolve_terminal.cache_clear` afterward.
    """
    if term_program is False:
        return None
    if term_program is True:
        term_program = os.environ.get('TERM_PROGRAM', '') or os.environ.get('TERM', '')
    if not term_program:
        return None
    key = term_program.strip().lower()
    canonical = ALIASES.get(key, key)
    if canonical not in KNOWN_TERMINALS:
        return None
    return canonical
