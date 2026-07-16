"""
Grapheme cluster segmentation following Unicode Standard Annex #29.

This module provides pure-Python implementation of the grapheme cluster boundary algorithm as
defined in UAX #29: Unicode Text Segmentation.

https://www.unicode.org/reports/tr29/
"""

from __future__ import annotations

# std imports
import sys
import unicodedata
from enum import IntEnum
from functools import lru_cache

from typing import TYPE_CHECKING, Optional, NamedTuple

__lazy_modules__ = [
    "wcwidth.bisearch",
    "wcwidth.table_grapheme",
]
# local
from .bisearch import bisearch as _bisearch
from .table_grapheme import (GRAPHEME_L,
                             GRAPHEME_T,
                             GRAPHEME_V,
                             GRAPHEME_LV,
                             INCB_EXTEND,
                             INCB_LINKER,
                             GRAPHEME_LVT,
                             INCB_CONSONANT,
                             GRAPHEME_EXTEND,
                             GRAPHEME_CONTROL,
                             GRAPHEME_PREPEND,
                             GRAPHEME_SPACINGMARK,
                             EXTENDED_PICTOGRAPHIC,
                             GRAPHEME_REGIONAL_INDICATOR)

if TYPE_CHECKING:  # pragma: no cover
    # std imports
    from collections.abc import Iterator

# check for python 3.15 for new iter_graphemes() function
_HAS_PYTHON315_ITER_GRAPHEMES = (
    sys.version_info >= (3, 15)
    and hasattr(unicodedata, 'iter_graphemes')
)

# Maximum backward scan distance when finding grapheme cluster boundaries.
# Covers all known Unicode grapheme clusters with margin; longer sequences are pathological.
MAX_GRAPHEME_SCAN = 32


class GCB(IntEnum):
    """Grapheme Cluster Break property values."""

    OTHER = 0
    CR = 1
    LF = 2
    CONTROL = 3
    EXTEND = 4
    ZWJ = 5
    REGIONAL_INDICATOR = 6
    PREPEND = 7
    SPACING_MARK = 8
    L = 9
    V = 10
    T = 11
    LV = 12
    LVT = 13


# All lru_cache sizes in this file use maxsize=1024, chosen by benchmarking UDHR data (500+
# languages) and considering typical process-long sessions: western scripts need ~64 unique
# codepoints, but CJK could reach ~2000 -- but likely not.
@lru_cache(maxsize=1024)
def _grapheme_cluster_break(ucs: int) -> GCB:
    # pylint: disable=too-many-branches,too-complex
    """Return the Grapheme_Cluster_Break property for a codepoint."""
    # Single codepoint matches
    if ucs == 0x000d:
        return GCB.CR
    if ucs == 0x000a:
        return GCB.LF
    if ucs == 0x200d:
        return GCB.ZWJ
    # Matching by codepoint ranges, requiring binary search
    if _bisearch(ucs, GRAPHEME_CONTROL):
        return GCB.CONTROL
    if _bisearch(ucs, GRAPHEME_EXTEND):
        return GCB.EXTEND
    if _bisearch(ucs, GRAPHEME_REGIONAL_INDICATOR):
        return GCB.REGIONAL_INDICATOR
    if _bisearch(ucs, GRAPHEME_PREPEND):
        return GCB.PREPEND
    if _bisearch(ucs, GRAPHEME_SPACINGMARK):
        return GCB.SPACING_MARK
    if _bisearch(ucs, GRAPHEME_L):
        return GCB.L
    if _bisearch(ucs, GRAPHEME_V):
        return GCB.V
    if _bisearch(ucs, GRAPHEME_T):
        return GCB.T
    if _bisearch(ucs, GRAPHEME_LV):
        return GCB.LV
    if _bisearch(ucs, GRAPHEME_LVT):
        return GCB.LVT
    return GCB.OTHER


@lru_cache(maxsize=1024)
def _is_extended_pictographic(ucs: int) -> bool:
    """Check if codepoint has Extended_Pictographic property."""
    return bool(_bisearch(ucs, EXTENDED_PICTOGRAPHIC))


@lru_cache(maxsize=1024)
def _is_incb_linker(ucs: int) -> bool:
    """Check if codepoint has InCB=Linker property."""
    return bool(_bisearch(ucs, INCB_LINKER))


@lru_cache(maxsize=1024)
def _is_incb_consonant(ucs: int) -> bool:
    """Check if codepoint has InCB=Consonant property."""
    return bool(_bisearch(ucs, INCB_CONSONANT))


@lru_cache(maxsize=1024)
def _is_incb_extend(ucs: int) -> bool:
    """Check if codepoint has InCB=Extend property."""
    return bool(_bisearch(ucs, INCB_EXTEND))


class BreakResult(NamedTuple):
    """Result of grapheme cluster break decision."""

    should_break: bool
    ri_count: int


@lru_cache(maxsize=1024)
def _simple_break_check(prev_gcb: GCB, curr_gcb: GCB) -> Optional[BreakResult]:
    """
    Check simple GCB-pair-based break rules (cacheable).

    Returns BreakResult for rules that can be determined from GCB properties alone, or None if
    complex lookback rules (GB9c, GB11) need to be checked.
    """
    # GB3: CR x LF
    if prev_gcb == GCB.CR and curr_gcb == GCB.LF:
        return BreakResult(should_break=False, ri_count=0)

    # GB4: (Control|CR|LF) ÷
    if prev_gcb in (GCB.CONTROL, GCB.CR, GCB.LF):
        return BreakResult(should_break=True, ri_count=0)

    # GB5: ÷ (Control|CR|LF)
    if curr_gcb in (GCB.CONTROL, GCB.CR, GCB.LF):
        return BreakResult(should_break=True, ri_count=0)

    # GB6: L x (L|V|LV|LVT)
    if prev_gcb == GCB.L and curr_gcb in (GCB.L, GCB.V, GCB.LV, GCB.LVT):
        return BreakResult(should_break=False, ri_count=0)

    # GB7: (LV|V) x (V|T)
    if prev_gcb in (GCB.LV, GCB.V) and curr_gcb in (GCB.V, GCB.T):
        return BreakResult(should_break=False, ri_count=0)

    # GB8: (LVT|T) x T
    if prev_gcb in (GCB.LVT, GCB.T) and curr_gcb == GCB.T:
        return BreakResult(should_break=False, ri_count=0)

    # GB9: x (Extend|ZWJ) - but ZWJ needs GB11 check, so only handle Extend here
    if curr_gcb == GCB.EXTEND:
        return BreakResult(should_break=False, ri_count=0)

    # GB9a: x SpacingMark
    if curr_gcb == GCB.SPACING_MARK:
        return BreakResult(should_break=False, ri_count=0)

    # GB9b: Prepend x
    if prev_gcb == GCB.PREPEND:
        return BreakResult(should_break=False, ri_count=0)

    # GB9c and GB11 need lookback - return None to signal complex check needed
    # GB12/13 (RI pairs) need ri_count state - also handled in main function
    return None


def _should_break(
    prev_gcb: GCB,
    curr_gcb: GCB,
    text: str,
    curr_idx: int,
    ri_count: int,
) -> BreakResult:
    # pylint: disable=too-many-branches,too-complex
    """
    Determine if there should be a grapheme cluster break between prev and curr.

    Implements UAX #29 grapheme cluster boundary rules.
    """
    # Try cached simple rules first
    result = _simple_break_check(prev_gcb, curr_gcb)
    if result is not None:
        return result

    # GB9: x ZWJ (not cached because GB11 needs lookback when prev is ZWJ)
    if curr_gcb == GCB.ZWJ:
        return BreakResult(should_break=False, ri_count=0)

    # GB9c: Indic conjunct cluster
    # \p{InCB=Consonant} [\p{InCB=Extend}\p{InCB=Linker}]* \p{InCB=Linker}
    #     [\p{InCB=Extend}\p{InCB=Linker}]* x \p{InCB=Consonant}
    curr_ucs = ord(text[curr_idx])
    if _is_incb_consonant(curr_ucs):
        has_linker = False
        i = curr_idx - 1
        while i >= 0:
            prev_ucs = ord(text[i])
            if _is_incb_linker(prev_ucs):
                has_linker = True
                i -= 1
            elif _is_incb_extend(prev_ucs):
                i -= 1
            elif _is_incb_consonant(prev_ucs):
                if has_linker:
                    return BreakResult(should_break=False, ri_count=0)
                break
            else:
                break

    # GB11: ExtPict Extend* ZWJ x ExtPict
    if prev_gcb == GCB.ZWJ and _is_extended_pictographic(curr_ucs):
        i = curr_idx - 2  # Skip the ZWJ at curr_idx - 1
        while i >= 0:
            prev_ucs = ord(text[i])
            prev_prop = _grapheme_cluster_break(prev_ucs)
            if prev_prop == GCB.EXTEND:
                i -= 1
            elif _is_extended_pictographic(prev_ucs):
                return BreakResult(should_break=False, ri_count=0)
            else:
                break

    # GB12/GB13: RI x RI (pair matching)
    if prev_gcb == GCB.REGIONAL_INDICATOR and curr_gcb == GCB.REGIONAL_INDICATOR:
        if ri_count % 2 == 1:
            return BreakResult(should_break=False, ri_count=ri_count + 1)
        return BreakResult(should_break=True, ri_count=1)

    # GB999: Any ÷ Any
    ri_count = 1 if curr_gcb == GCB.REGIONAL_INDICATOR else 0
    return BreakResult(should_break=True, ri_count=ri_count)


def _iter_graphemes_stdlib(
    unistr: str,
    start: int = 0,
    end: Optional[int] = None,
) -> Iterator[str]:
    r"""
    Iterate over grapheme clusters using :func:`unicodedata.iter_graphemes`.

    Grapheme clusters are "user-perceived characters" - what a user would
    consider a single character, which may consist of multiple Unicode
    codepoints (e.g., a base character with combining marks, emoji sequences).

    :param unistr: The Unicode string to segment.
    :param start: Starting index (default 0).
    :param end: Ending index (default len(unistr)).
    :yields: Grapheme cluster substrings.

    Example::

        >>> list(iter_graphemes('cafe\u0301'))
        ['c', 'a', 'f', 'e\u0301']
        >>> list(iter_graphemes('ok\U0001F468\u200D\U0001F469\u200D\U0001F467'))
        ['o', 'k', '\U0001F468\u200D\U0001F469\u200D\U0001F467']
        >>> list(iter_graphemes('ok\U0001F1FA\U0001F1F8'))
        ['o', 'k', '\U0001F1FA\U0001F1F8']

    .. versionadded:: 0.3.0
    """
    if not unistr:
        return

    length = len(unistr)

    if end is None:
        end = length

    if start >= end or start >= length:
        return

    end = min(end, length)

    full_segment = unistr[start:end]
    for seg in unicodedata.iter_graphemes(full_segment):  # type: ignore[attr-defined]  # pylint: disable=no-member
        yield full_segment[seg.start:seg.end]


def _iter_graphemes_python(
    unistr: str,
    start: int = 0,
    end: int | None = None,
) -> Iterator[str]:
    r"""
    Iterate over grapheme clusters using :func:`unicodedata.iter_graphemes`.

    Grapheme clusters are "user-perceived characters" - what a user would
    consider a single character, which may consist of multiple Unicode
    codepoints (e.g., a base character with combining marks, emoji sequences).

    :param unistr: The Unicode string to segment.
    :param start: Starting index (default 0).
    :param end: Ending index (default len(unistr)).
    :yields: Grapheme cluster substrings.

    Example::

        >>> list(iter_graphemes('cafe\u0301'))
        ['c', 'a', 'f', 'e\u0301']
        >>> list(iter_graphemes('ok\U0001F468\u200D\U0001F469\u200D\U0001F467'))
        ['o', 'k', '\U0001F468\u200D\U0001F469\u200D\U0001F467']
        >>> list(iter_graphemes('ok\U0001F1FA\U0001F1F8'))
        ['o', 'k', '\U0001F1FA\U0001F1F8']

    .. versionadded:: 0.3.0
    """
    if not unistr:
        return

    length = len(unistr)

    if end is None:
        end = length

    if start >= end or start >= length:
        return

    end = min(end, length)

    # Track state for grapheme cluster boundaries
    cluster_start = start
    ri_count = 0

    # Get GCB for first character
    prev_gcb = _grapheme_cluster_break(ord(unistr[start]))

    # Handle Regional Indicator count initialization
    if prev_gcb == GCB.REGIONAL_INDICATOR:
        ri_count = 1

    for idx in range(start + 1, end):
        curr_gcb = _grapheme_cluster_break(ord(unistr[idx]))

        result = _should_break(prev_gcb, curr_gcb, unistr, idx, ri_count)
        ri_count = result.ri_count

        if result.should_break:
            yield unistr[cluster_start:idx]
            cluster_start = idx

        prev_gcb = curr_gcb

    # Yield the final cluster
    yield unistr[cluster_start:end]


def _find_cluster_start(text: str, pos: int) -> int:
    """
    Find the start of the grapheme cluster containing the character before pos.

    Scans backwards from pos to find a safe starting point, then iterates forward using standard
    break rules to find the actual cluster boundary.

    :param text: The Unicode string.
    :param pos: Position to search before (exclusive).
    :returns: Start position of the grapheme cluster.
    """
    target_cp = ord(text[pos - 1])

    # GB3: CR x LF - LF after CR is part of same cluster
    if target_cp == 0x0A and pos >= 2 and text[pos - 2] == '\r':
        return pos - 2

    # Fast path: ASCII (except LF) starts its own cluster
    if target_cp < 0x80:
        # GB9b: Check for preceding PREPEND (rare: Arabic/Brahmic)
        if pos >= 2 and target_cp >= 0x20:
            prev_cp = ord(text[pos - 2])
            if prev_cp >= 0x80 and _grapheme_cluster_break(prev_cp) == GCB.PREPEND:
                return _find_cluster_start(text, pos - 1)
        return pos - 1

    # Scan backward to find a safe starting point
    safe_start = pos - 1
    while safe_start > 0 and (pos - safe_start) < MAX_GRAPHEME_SCAN:
        cp = ord(text[safe_start])
        if 0x20 <= cp < 0x80:  # ASCII always starts a cluster
            break
        if _grapheme_cluster_break(cp) == GCB.CONTROL:  # GB4
            break
        safe_start -= 1

    # Verify forward to find the actual cluster boundary
    cluster_start = safe_start
    left_gcb = _grapheme_cluster_break(ord(text[safe_start]))
    ri_count = 1 if left_gcb == GCB.REGIONAL_INDICATOR else 0

    for i in range(safe_start + 1, pos):
        right_gcb = _grapheme_cluster_break(ord(text[i]))
        result = _should_break(left_gcb, right_gcb, text, i, ri_count)
        ri_count = result.ri_count
        if result.should_break:
            cluster_start = i
        left_gcb = right_gcb

    return cluster_start


def grapheme_boundary_before(unistr: str, pos: int) -> int:
    r"""
    Find the grapheme cluster boundary immediately before a position.

    :param unistr: The Unicode string to search.
    :param pos: Position in the string (0 < pos <= len(unistr)).
    :returns: Start index of the grapheme cluster containing the character at pos-1.

    Example::

        >>> grapheme_boundary_before('Hello \U0001F44B\U0001F3FB', 8)
        6
        >>> grapheme_boundary_before('a\r\nb', 3)
        1

    .. versionadded:: 0.3.6
    """
    if pos <= 0:
        return 0
    return _find_cluster_start(unistr, min(pos, len(unistr)))


def iter_graphemes_reverse(
    unistr: str,
    start: int = 0,
    end: Optional[int] = None,
) -> Iterator[str]:
    r"""
    Iterate over grapheme clusters in reverse order (last to first).

    :param unistr: The Unicode string to segment.
    :param start: Starting index (default 0).
    :param end: Ending index (default len(unistr)).
    :yields: Grapheme cluster substrings in reverse order.

    Example::

        >>> list(iter_graphemes_reverse('cafe\u0301'))
        ['e\u0301', 'f', 'a', 'c']

    .. versionadded:: 0.3.6
    """
    if not unistr:
        return

    length = len(unistr)

    end = length if end is None else min(end, length)
    start = max(start, 0)

    if start >= end or start >= length:
        return

    pos = end
    while pos > start:
        cluster_start = _find_cluster_start(unistr, pos)
        # Don't yield partial graphemes that extend before start
        if cluster_start < start:
            break
        yield unistr[cluster_start:pos]
        pos = cluster_start


# Bind iter_graphemes at module level to avoid per-call dispatch overhead.
iter_graphemes = (
    _iter_graphemes_stdlib if _HAS_PYTHON315_ITER_GRAPHEMES
    else _iter_graphemes_python
)
