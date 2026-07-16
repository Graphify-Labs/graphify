"""This is a python implementation of wcswidth()."""

from __future__ import annotations

from typing import Optional

__lazy_modules__ = [
    "wcwidth._constants",
    "wcwidth._wcwidth",
    "wcwidth.bisearch",
    "wcwidth.table_grapheme",
    "wcwidth.table_vs16",
]
# local
from . import table_grapheme_overrides
from ._wcwidth import wcwidth
from .bisearch import bisearch
from ._constants import (_EMOJI_ZWJ_SET,
                         _ISC_VIRAMA_SET,
                         _CATEGORY_MC_TABLE,
                         _FITZPATRICK_RANGE,
                         _REGIONAL_INDICATOR_SET,
                         resolve_terminal,
                         get_term_overrides)
from .table_vs15 import VS15_WIDE_TO_NARROW
from .table_vs16 import VS16_NARROW_TO_WIDE
from .table_grapheme import GRAPHEME_EXTEND


def _scan_zwj_cluster_end(text: str, start: int, end: int) -> int:
    """
    Scan forward from *start* (base character) to end of a ZWJ grapheme cluster.

    Follows the UAX #29 GB11 pattern (ExtPict Extend* ZWJ x ExtPict) chained repeatedly until no
    more ZWJ joins are found.
    """
    idx = start + 1
    # Skip Extend characters (Fitzpatrick modifiers, etc.) before first ZWJ
    while idx < end and bisearch(ord(text[idx]), GRAPHEME_EXTEND):
        idx += 1
    # Follow ZWJ chains
    while idx < end:
        if ord(text[idx]) != 0x200D:
            break
        idx += 1
        # GB11: \p{ExtPict} Extend* ZWJ × \p{ExtPict}
        # Extend modifiers (VS16, Fitzpatrick skin tones, etc.) attach to
        # the ExtPict *before* the ZWJ, not after it.  After ZWJ the next
        # codepoint is always an ExtPict directly, no Extend skip needed.
        if idx < end and ord(text[idx]) in _EMOJI_ZWJ_SET:
            idx += 1
            # Skip trailing Extend (VS16, etc.) after ExtPict before next ZWJ
            while idx < end and bisearch(ord(text[idx]), GRAPHEME_EXTEND):
                idx += 1
            continue
        break
    return idx


def wcswidth(
    pwcs: str,
    n: Optional[int] = None,
    unicode_version: str = 'auto',
    ambiguous_width: int = 1,
) -> int:
    """
    Given a unicode string, return its printable length on a terminal.

    See :ref:`Specification` for details of cell measurement.

    This implementation differs from Markus Khun's original POSIX C implementation, in that this
    ``wcswidth()`` processes graphemes strings yielded by :func:`wcwidth.iter_graphemes` defined by
    `Unicode Standard Annex #29`_. POSIX wcswidth(3) is not grapheme-aware and does not measure many
    kinds of Emojis or complex scripts correctly.

    :param pwcs: Measure width of given unicode string.
    :param n: When ``n`` is None (default), return the length of the entire
        string, otherwise only the first ``n`` characters are measured.
    :param unicode_version: Ignored. Retained for backwards compatibility.

        .. deprecated:: 0.3.0
           Only the latest Unicode version is now shipped.

    :param ambiguous_width: Width to use for East Asian Ambiguous (A)
        characters. Default is ``1`` (narrow). Set to ``2`` for CJK contexts.
    :returns: The width, in cells, needed to display the first ``n`` characters
        of the unicode string ``pwcs``.  Returns ``-1`` for C0 and C1 control
        characters!

    .. _`Unicode Standard Annex #29`: https://www.unicode.org/reports/tr29/
    """
    # pylint: disable=unused-argument,too-many-locals,too-many-statements,redefined-variable-type
    # pylint: disable=too-complex,too-many-branches,duplicate-code,too-many-nested-blocks

    # Fast path: pure ASCII printable strings are always width == length
    if n is None and pwcs.isascii() and pwcs.isprintable():
        return len(pwcs)

    _wcwidth = wcwidth if ambiguous_width == 1 else lambda c: wcwidth(c, 'auto', ambiguous_width)

    end = len(pwcs) if n is None else min(n, len(pwcs))
    total_width = 0
    idx = 0

    last_measured_idx = -2  # -2 sentinel blocks VS16/VS15 (no base available)
    last_measured_ucs = -1
    last_measured_w = 0
    prev_was_virama = False
    cluster_width = 0
    vs16_nw_table = VS16_NARROW_TO_WIDE['9.0.0']
    vs15_wn_table = VS15_WIDE_TO_NARROW['9.0.0']
    _bisearch = bisearch

    while idx < end:
        char = pwcs[idx]
        ucs = ord(char)

        # 5. ZWJ (U+200D): consumed without contributing width.
        # Virama codepoints are treated as zero-width combining marks (Mn). When a
        # virama+consonant sequence forms a conjunct, its width is capped at 2 cells.

        # ZWJ (U+200D)
        if ucs == 0x200D:
            if prev_was_virama:
                idx += 1
            elif idx + 1 < end:
                last_measured_w = 0
                prev_was_virama = False
                idx += 2
            else:
                prev_was_virama = False
                idx += 1
            continue

        # 6. VS16 (U+FE0F): converts preceding narrow character to wide.
        if ucs == 0xFE0F and last_measured_idx >= 0:
            if _bisearch(last_measured_ucs, vs16_nw_table):
                cluster_width = 2
            last_measured_idx = -2
            idx += 1
            continue

        # VS15 (U+FE0E): text variation selector, requests narrow presentation.
        if ucs == 0xFE0E and last_measured_idx >= 0:
            if bisearch(last_measured_ucs, vs15_wn_table) and last_measured_w == 2:
                total_width -= 1
            idx += 1
            continue

        # 7. Regional Indicator & Fitzpatrick (both above BMP)
        if ucs > 0xFFFF:
            if ucs in _REGIONAL_INDICATOR_SET:
                ri_before = 0
                j = idx - 1
                while j >= 0 and ord(pwcs[j]) in _REGIONAL_INDICATOR_SET:
                    ri_before += 1
                    j -= 1
                if ri_before % 2 == 1:
                    last_measured_ucs = ucs
                    idx += 1
                    continue
            elif (_FITZPATRICK_RANGE[0] <= ucs <= _FITZPATRICK_RANGE[1]
                  and last_measured_ucs in _EMOJI_ZWJ_SET):
                idx += 1
                continue

        # 8. Normal character: measure with wcwidth
        w = _wcwidth(char)
        if w < 0:
            return -1
        if w > 0:
            if prev_was_virama:
                cluster_width = 2
            elif cluster_width:
                total_width += cluster_width
                cluster_width = w
            else:
                cluster_width = w

            last_measured_idx = idx
            last_measured_ucs = ucs
            last_measured_w = w
            prev_was_virama = False
        elif ucs in _ISC_VIRAMA_SET:
            prev_was_virama = True
        elif last_measured_idx >= 0 and _bisearch(ucs, _CATEGORY_MC_TABLE):
            cluster_width = 2
            last_measured_idx = -2
            prev_was_virama = False
        else:
            prev_was_virama = False
        idx += 1

    if cluster_width:
        total_width += cluster_width
    return total_width


def wcstwidth(
    pwcs: str,
    n: Optional[int] = None,
    unicode_version: str = 'auto',
    ambiguous_width: int = 1,
    term_program: bool | str = True,
) -> int:
    """
    Given a unicode string, return its printable length on a terminal given by ``term_program``.

    See :ref:`Specification` for details of cell measurement.

    Unlike :func:`wcswidth`, this function applies per-terminal correction tables for
    emoji presentation and grapheme clusters.

    :param pwcs: Measure width of given unicode string.
    :param n: When ``n`` is None (default), return the length of the entire
        string, otherwise only the first ``n`` characters are measured.
    :param unicode_version: Ignored. Retained for backwards compatibility.
    :param ambiguous_width: Width to use for East Asian Ambiguous (A)
        characters. Default is ``1`` (narrow). Set to ``2`` for CJK contexts.
    :param term_program: Terminal software identifier for table correction.
        ``True`` (default) reads the ``TERM_PROGRAM`` or ``TERM`` environment
        variable for auto-detection.  ``False`` disables override lookup.
        Accepts a canonical terminal name matching :func:`list_term_programs`,
        such as from XTVERSION_, ENQ_, or ``TERM_PROGRAM``.

        .. versionadded:: 0.8.0
    :returns: The width, in cells, needed to display the first ``n`` characters
        of the unicode string ``pwcs``.  Returns ``-1`` for C0 and C1 control
        characters!
    """
    # pylint: disable=unused-argument,too-many-locals,too-many-statements,redefined-variable-type
    # pylint: disable=too-complex,too-many-branches,duplicate-code,too-many-nested-blocks
    # This function intentionally keeps all logic inline for performance.

    # Fast path: pure ASCII printable strings are always width == length
    if n is None and pwcs.isascii() and pwcs.isprintable():
        return len(pwcs)

    # Resolve terminal software for override lookup
    term_canonical = resolve_terminal(term_program)

    # Skip override lookup when no terminal detected (avoids lru_cache call overhead).
    # Extract locals for hot-loop performance (NamedTuple attribute access is slow).
    if term_canonical:
        overrides = get_term_overrides(term_canonical)
        _narrower = overrides.narrower
        _vs16_narrower = overrides.vs16_narrower
        _vs15_wider = overrides.vs15_wider
        _zeroer = overrides.zeroer
        _narrow_wider = overrides.narrow_wider
        _narrow_zeroer = overrides.narrow_zeroer
        _grapheme_overrides = table_grapheme_overrides.get(term_canonical)
    else:
        _narrower = ()
        _vs16_narrower = ()
        _vs15_wider = ()
        _zeroer = ()
        _narrow_wider = ()
        _narrow_zeroer = ()
        _grapheme_overrides = {}

    # Select wcwidth call pattern for best lru_cache performance
    _wcwidth = wcwidth if ambiguous_width == 1 else lambda c: wcwidth(c, 'auto', ambiguous_width)

    end = len(pwcs) if n is None else min(n, len(pwcs))
    total_width = 0
    idx = 0

    # grapheme-clustering state and local re-binding for performance.
    # Widths accumulate in cluster_width and flush at boundaries.  A cluster is a base character
    # plus combining marks, deferring the flush lets grapheme overrides replace the measured width
    # retrospectively.
    last_measured_idx = -2  # -2 sentinel blocks VS16/VS15 (no base available)
    last_measured_ucs = -1
    last_measured_w = 0
    prev_was_virama = False
    cluster_start = -1
    total_before_cluster = 0
    cluster_width = 0
    vs16_nw_table = VS16_NARROW_TO_WIDE['9.0.0']
    vs15_wn_table = VS15_WIDE_TO_NARROW['9.0.0']
    _bisearch = bisearch

    while idx < end:
        char = pwcs[idx]
        ucs = ord(char)

        #
        # Much of the logic below matches the logic in width(), but is repeated for improved
        # performance, they are given matching index reference numbers (starting at #5).
        #
        # 5. ZWJ (U+200D): consumed without contributing width.
        # Virama codepoints are treated as zero-width combining marks (Mn). When a
        # virama+consonant sequence forms a conjunct, its width is capped at 2 cells
        # matching behavior of popular terminals (PR #224)

        # ZWJ (U+200D)
        if ucs == 0x200D:
            if prev_was_virama:
                idx += 1
            elif idx + 1 < end:
                # Check for terminal grapheme override when base char is ExtPict/RI
                if (_grapheme_overrides
                        and last_measured_idx >= 0
                        and last_measured_ucs in _EMOJI_ZWJ_SET):
                    cluster_end = _scan_zwj_cluster_end(pwcs, last_measured_idx, end)
                    cluster = pwcs[last_measured_idx:cluster_end]
                    override_w = _grapheme_overrides.get(cluster)
                    if override_w is not None:
                        total_width += (override_w - last_measured_w)
                        last_measured_idx = -2
                        last_measured_ucs = -1
                        last_measured_w = 0
                        prev_was_virama = False
                        cluster_start = -1
                        idx = cluster_end
                        continue
                # No override; ZWJ breaks VS adjacency.
                # VS16 already set last_measured_idx = -2, blocking further VS16.
                last_measured_w = 0
                prev_was_virama = False
                idx += 2
            else:
                prev_was_virama = False
                idx += 1
            continue

        # 6. VS16 (U+FE0F): converts preceding narrow character to wide.
        if ucs == 0xFE0F and last_measured_idx >= 0:
            if _vs16_narrower and _bisearch(last_measured_ucs, _vs16_narrower):
                pass
            elif _bisearch(last_measured_ucs, vs16_nw_table):
                cluster_width = 2
            last_measured_idx = -2  # prevent double application
            idx += 1
            continue

        # VS15 (U+FE0E): text variation selector, requests narrow presentation.
        if ucs == 0xFE0E and last_measured_idx >= 0:
            base_ucs = last_measured_ucs
            vs15_narrow = bisearch(base_ucs, vs15_wn_table)
            if _vs15_wider and bisearch(base_ucs, _vs15_wider):
                vs15_narrow = False
            if vs15_narrow and last_measured_w == 2:
                total_width -= 1
            idx += 1
            continue

        # 7. Regional Indicator & Fitzpatrick (both above BMP)
        if ucs > 0xFFFF:
            if ucs in _REGIONAL_INDICATOR_SET:
                ri_before = 0
                j = idx - 1
                while j >= 0 and ord(pwcs[j]) in _REGIONAL_INDICATOR_SET:
                    ri_before += 1
                    j -= 1
                if ri_before % 2 == 1:
                    last_measured_ucs = ucs
                    idx += 1
                    continue
            elif (_FITZPATRICK_RANGE[0] <= ucs <= _FITZPATRICK_RANGE[1]
                  and last_measured_ucs in _EMOJI_ZWJ_SET):
                idx += 1
                continue

        # 8. Normal character: measure with wcwidth
        w = _wcwidth(char)
        if w < 0:
            # C0/C1 control character
            return -1
        # Apply single-codepoint terminal overrides (pre-merged tuples)
        if w == 2 and _narrower and bisearch(ucs, _narrower):
            w = 1
        elif w == 2 and _zeroer and bisearch(ucs, _zeroer):
            w = 0
        if w == 1 and _narrow_wider and bisearch(ucs, _narrow_wider):
            w = 2
        elif w == 1 and _narrow_zeroer and bisearch(ucs, _narrow_zeroer):
            w = 0
        if w > 0:
            # virama+consonant extends current cluster; otherwise start new
            if prev_was_virama:
                cluster_width = 2
            elif cluster_width:
                # flush previous cluster, check for grapheme overrides
                flushed = False
                if _grapheme_overrides and cluster_start >= 0:
                    # Two-phase override lookup: candidate (cluster+current) catches Lo+Lo pairs
                    # where both chars bear width (Thai KO KAI + SARA AM).  cluster_text (cluster
                    # alone) catches C+Mc clusters where the override key is shorter.
                    candidate = pwcs[cluster_start:idx + 1]
                    override_w = _grapheme_overrides.get(candidate)
                    if override_w is not None:
                        total_width = total_before_cluster + override_w
                        flushed = True
                        cluster_width = 0
                    else:
                        cluster_text = pwcs[cluster_start:idx]
                        override_w = _grapheme_overrides.get(cluster_text)
                        if override_w is not None:
                            total_width = total_before_cluster + override_w
                        else:
                            total_width += cluster_width
                else:
                    total_width += cluster_width
                if not flushed:
                    cluster_width = w
                    cluster_start = idx
                    total_before_cluster = total_width
            else:
                cluster_width = w
                cluster_start = idx
                total_before_cluster = total_width
            last_measured_idx = idx
            last_measured_ucs = ucs
            last_measured_w = w
            prev_was_virama = False
        elif ucs in _ISC_VIRAMA_SET:
            prev_was_virama = True
        elif last_measured_idx >= 0 and _bisearch(ucs, _CATEGORY_MC_TABLE):
            # Spacing Combining Mark (Mc) following a base character
            cluster_width = 2
            last_measured_idx = -2
            prev_was_virama = False
        else:
            prev_was_virama = False
        idx += 1

    if cluster_width:
        if _grapheme_overrides and cluster_start >= 0:
            cluster_text = pwcs[cluster_start:end]
            override_w = _grapheme_overrides.get(cluster_text)
            if override_w is not None:
                total_width = total_before_cluster + override_w
            else:
                total_width += cluster_width
        else:
            total_width += cluster_width
    return total_width
