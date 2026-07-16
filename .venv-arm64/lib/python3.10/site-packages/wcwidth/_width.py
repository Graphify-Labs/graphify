"""This is a high-level width() supporting terminal output."""

from __future__ import annotations

from typing import Literal

__lazy_modules__ = [
    "wcwidth._constants",
    "wcwidth._wcswidth",
    "wcwidth._wcwidth",
    "wcwidth.bisearch",
    "wcwidth.control_codes",
    "wcwidth.escape_sequences",
    "wcwidth.table_grapheme",
    "wcwidth.table_vs16",
    "wcwidth.text_sizing",
]
# local
from . import table_grapheme_overrides
from ._wcwidth import wcwidth
from .bisearch import bisearch
from ._wcswidth import wcswidth, wcstwidth, _scan_zwj_cluster_end
from ._constants import (_EMOJI_ZWJ_SET,
                         _ISC_VIRAMA_SET,
                         _CATEGORY_MC_TABLE,
                         _FITZPATRICK_RANGE,
                         _REGIONAL_INDICATOR_SET,
                         resolve_terminal,
                         get_term_overrides)
from .table_vs15 import VS15_WIDE_TO_NARROW
from .table_vs16 import VS16_NARROW_TO_WIDE
from .text_sizing import TextSizing, TextSizingParams
from .control_codes import ILLEGAL_CTRL, VERTICAL_CTRL, HORIZONTAL_CTRL, ZERO_WIDTH_CTRL
from .escape_sequences import (_SEQUENCE_CLASSIFY,
                               TEXT_SIZING_PATTERN,
                               CURSOR_MOVEMENT_SEQUENCE,
                               INDETERMINATE_EFFECT_SEQUENCE,
                               strip_sequences)

# In 'parse' mode, strings longer than this are checked for cursor-movement
# controls (BS, TAB, CR, cursor sequences); when absent, mode downgrades to
# 'ignore' to skip character-by-character parsing. The detection scan cost is
# negligible for long strings but wasted on short ones like labels or headings.
_WIDTH_FAST_PATH_MIN_LEN = 20

# Translation table to strip C0/C1 control characters for fast 'ignore' mode.
_CONTROL_CHAR_TABLE = str.maketrans('', '', (
    ''.join(chr(c) for c in range(0x00, 0x20)) +   # C0: NUL through US (including tab)
    '\x7f' +                                       # DEL
    ''.join(chr(c) for c in range(0x80, 0xa0))     # C1: U+0080-U+009F
))


def _width_ignored_codes(text: str, ambiguous_width: int = 1,
                         term_program: bool | str = False) -> int:
    """
    Fast path for width() with control_codes='ignore'.

    Strips escape sequences and control characters, then measures remaining text.
    """
    if term_program is False:
        return wcswidth(
            strip_sequences(text).translate(_CONTROL_CHAR_TABLE),
            ambiguous_width=ambiguous_width,
        )
    return wcstwidth(
        strip_sequences(text).translate(_CONTROL_CHAR_TABLE),
        ambiguous_width=ambiguous_width,
        term_program=term_program,
    )


def width(
    text: str,
    *,
    control_codes: Literal['parse', 'strict', 'ignore'] = 'parse',
    tabsize: int = 8,
    ambiguous_width: int = 1,
    term_program: bool | str = False,
) -> int:
    r"""
    Return printable width of text containing many kinds of control codes and sequences.

    Unlike :func:`wcswidth`, this function handles most control characters and many popular terminal
    output sequences.  Never returns -1.

    :param text: String to measure.
    :param control_codes: How to handle control characters and sequences:

        - ``'parse'`` (default): Track horizontal cursor movement like BS ``\b``, CR ``\r``, TAB
          ``\t``, cursor left and right movement sequences.  Vertical movement (LF, VT, FF) and
          indeterminate terminal sequences are zero-width. OSC 66 Kitty Text Sizing protocol, OSC 8
          Hyperlink, and many other kinds of output sequences are parsed for displayed measurements.
        - ``'strict'``: Like parse, but raises :exc:`ValueError` on control characters with
          indeterminate results of the screen or cursor, like clear or vertical movement. Generally,
          these should be handled with a virtual terminal emulator (like 'pyte').
        - ``'ignore'``: All C0 and C1 control characters and escape sequences are measured as
          width 0. This is the fastest measurement for text already filtered or known not to contain
          any kinds of control codes or sequences. TAB ``\t`` is zero-width; to ensure
          tab expansion, pre-process text using :func:`str.expandtabs`.

    :param tabsize: Tab stop width for ``'parse'`` and ``'strict'`` modes. Default is 8.  Must be
        positive. Has no effect when ``control_codes='ignore'``.
    :param ambiguous_width: Width to use for East Asian Ambiguous (A) characters. Default is ``1``
        (narrow). Set to ``2`` for CJK contexts.
    :param term_program: Terminal software identifier for table correction.
        ``False`` (default) disables override lookup.  ``True`` reads the
        ``TERM_PROGRAM`` or ``TERM`` environment variable for auto-detection.
        Accepts a canonical terminal name matching :func:`list_term_programs`,
        such as from XTVERSION_, ENQ_, or ``TERM_PROGRAM``.

        .. versionadded:: 0.8.0
    :returns: Maximum cursor position reached, "extent", accounting for cursor movement sequences
        present in ``text`` according to given parameters.  This represents the rightmost column the
        cursor reaches.  Always a non-negative integer.
    :raises ValueError: If ``control_codes='strict'`` and control characters with indeterminate
        effects, such as vertical movement or clear sequences are encountered, or on unexpected
        C0 or C1 control code. Also raised when ``control_codes`` is not one of the valid values.

    .. versionadded:: 0.3.0

    .. versionchanged:: 0.7.0
       Expanded strict-mode to raise :exc:`ValueError` when cursor-left movement
       (CSI D) would move beyond the beginning of the string. Previously, cursor-left
       was silently clamped to column 0 in all modes.

       Support horizontal cursor sequences (``cub``, ``cuf``, ``hpa``). Cursor-left (``cub``) or
       backspace (``\b``) now overwrites text.  ``column_address`` (``hpa``) and carriage return
       (``\r``) are now parsed, and some values conditionally raise ``ValueError`` when
       ``control_codes='parse'``.

    Examples::

        >>> width('hello')
        5
        >>> width('コンニチハ')
        10
        >>> width('\x1b[31mred\x1b[0m')
        3
        >>> width('\x1b[31mred\x1b[0m', control_codes='ignore')  # same result (ignored)
        3
        >>> width('123\b4')     # backspace overwrites previous cell (outputs '124')
        3
        >>> width('abc\t')      # tab caused cursor to move to column 8
        8
        >>> width('1\x1b[10C')  # '1' + cursor right 10, cursor ends on column 11
        11
        >>> width('1\x1b[10C', control_codes='ignore')   # faster but wrong in this case
        1
    """
    # pylint: disable=too-complex,too-many-branches,too-many-statements,too-many-locals,redefined-variable-type,too-many-nested-blocks
    # This could be broken into sub-functions (#1, #3, and #6 especially), but for reduced overhead
    # in consideration of this function a likely "hot path", they are inline, breaking many pylint
    # complexity rules.

    # Fast path for ASCII printable (no tabs, escapes, or control chars)
    if text.isascii() and text.isprintable():
        return len(text)

    # Fast parse: if no horizontal cursor movements are possible, switch to 'ignore' mode.
    # Only check longer strings - the detection overhead hurts short string performance.
    if control_codes == 'parse' and len(text) > _WIDTH_FAST_PATH_MIN_LEN:
        # Check for cursor-affecting control characters
        if '\b' not in text and '\t' not in text and '\r' not in text:
            # Check for escape sequences, if none contain cursor movement or
            # text sizing, downgrade to 'ignore'
            if '\x1b' not in text or (
                not CURSOR_MOVEMENT_SEQUENCE.search(text)
                and not TEXT_SIZING_PATTERN.search(text)
            ):
                control_codes = 'ignore'

    # Fast path for ignore mode, useful if you know the text is already free of control codes
    if control_codes == 'ignore':
        return _width_ignored_codes(text, ambiguous_width, term_program=term_program)

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

    strict = control_codes == 'strict'
    # Track absolute positions: tab stops need modulo on absolute column, CR resets to 0.
    # Initialize max_extent to 0 so backward movement (CR, BS) won't yield negative width.
    current_col = 0
    max_extent = 0
    idx = 0
    text_len = len(text)

    # Select wcwidth call pattern for best lru_cache performance:
    # - ambiguous_width=1 (default): single-arg calls share cache with direct wcwidth() calls
    # - ambiguous_width=2: full positional args needed (results differ, separate cache is correct)
    _wcwidth = wcwidth if ambiguous_width == 1 else lambda c: wcwidth(c, 'auto', ambiguous_width)

    # grapheme-clustering state and local re-binding for performance.
    # Widths accumulate in cluster_width and flush at boundaries (see _wcswidth.py)
    last_measured_idx = -2  # -2 sentinel blocks VS16/VS15 (no base available)
    last_measured_ucs = -1
    last_measured_w = 0
    prev_was_virama = False
    _max_extent_before = 0
    cluster_start = -1
    col_before_cluster = 0
    max_extent_before_cluster = 0
    cluster_width = 0
    vs16_nw_table = VS16_NARROW_TO_WIDE['9.0.0']
    vs15_wn_table = VS15_WIDE_TO_NARROW['9.0.0']
    _bisearch = bisearch

    while idx < text_len:
        char = text[idx]

        # 1. ESC sequences
        if char == '\x1b':
            # Flush pending cluster before processing escape sequence
            if cluster_width:
                current_col += cluster_width
                if current_col > max_extent:
                    max_extent = current_col
                cluster_width = 0
            m = _SEQUENCE_CLASSIFY.match(text, idx)
            if not m:
                # 1a. Errant ESC or unknown sequence: only the first character is zero-width
                idx += 1
            else:
                seq = m.group()
                if strict and INDETERMINATE_EFFECT_SEQUENCE.match(seq):
                    raise ValueError(f"Indeterminate cursor sequence at position {idx}, {seq!r}")

                # 2b. horizontal position absolute (before forward/backward to
                #     avoid other_seq match in _SEQUENCE_CLASSIFY)
                if (hpa_n := m.group('hpa_n')) is not None:
                    target_col = int(hpa_n) if hpa_n else 1
                    if strict:
                        raise ValueError(
                            f"Indeterminate horizontal position at position {idx}, "
                            f"{seq!r} (absolute column unknown)"
                        )
                    current_col = target_col - 1  # HPA is 1-indexed, convert to 0-indexed
                # 2c. cursor forward, backward
                elif (cforward_n := m.group('cforward_n')) is not None:
                    current_col += int(cforward_n) if cforward_n else 1
                elif (cbackward_n := m.group('cbackward_n')) is not None:
                    n_backward = int(cbackward_n) if cbackward_n else 1
                    if strict and n_backward > current_col:
                        raise ValueError(
                            f"Cursor left movement at position {idx} would move "
                            f"{n_backward} cells left from column {current_col}, "
                            f"exceeding string start"
                        )
                    current_col -= n_backward
                    if current_col < 0:
                        current_col = 0
                # 2d. OSC 66 Text Sizing — has positive display width
                elif (ts_meta := m.group('ts_meta')) is not None:
                    ts_text = m.group('ts_text')
                    ts_term = m.group('ts_term')
                    assert ts_text is not None and ts_term is not None
                    text_size = TextSizing(
                        TextSizingParams.from_params(ts_meta, control_codes=control_codes),
                        ts_text, ts_term)
                    current_col += text_size.display_width(ambiguous_width)
                # 2e. SGR and other zero-width sequences -- no column advance
                idx = m.end()
            # Escape sequences break VS16 adjacency: reset last-measured state
            last_measured_idx = -2
            last_measured_ucs = -1
            cluster_start = -1
            if current_col > max_extent:
                max_extent = current_col
            continue

        # 2. Vertical or Illegal control characters zero width or error when 'strict'
        if char in ILLEGAL_CTRL:
            if strict:
                raise ValueError(f"Illegal control character {ord(char):#x} at position {idx}")
            if cluster_width:
                current_col += cluster_width
                if current_col > max_extent:
                    max_extent = current_col
                cluster_width = 0
            idx += 1
            last_measured_idx = -2
            last_measured_ucs = -1
            cluster_start = -1
            continue

        if char in VERTICAL_CTRL:
            if strict:
                raise ValueError(f"Vertical movement character {ord(char):#x} at position {idx}")
            if cluster_width:
                current_col += cluster_width
                if current_col > max_extent:
                    max_extent = current_col
                cluster_width = 0
            idx += 1
            last_measured_idx = -2
            last_measured_ucs = -1
            cluster_start = -1
            continue

        # 3. Horizontal movement characters
        if char in HORIZONTAL_CTRL:
            if cluster_width:
                current_col += cluster_width
                if current_col > max_extent:
                    max_extent = current_col
                cluster_width = 0
            if char == '\t' and tabsize > 0:
                current_col += tabsize - (current_col % tabsize)
            elif char == '\b':
                if current_col > 0:
                    current_col -= 1
            elif char == '\r':
                if strict:
                    raise ValueError(
                        f"Horizontal movement character \\r at position {idx}: "
                        "indeterminate starting column"
                    )
                current_col = 0
            if current_col > max_extent:
                max_extent = current_col
            idx += 1
            last_measured_idx = -2
            last_measured_ucs = -1
            cluster_start = -1
            continue

        # 4. Zero-width control characters
        if char in ZERO_WIDTH_CTRL:
            if cluster_width:
                current_col += cluster_width
                if current_col > max_extent:
                    max_extent = current_col
                cluster_width = 0
            idx += 1
            last_measured_idx = -2
            last_measured_ucs = -1
            cluster_start = -1
            continue

        # 5. Inline grapheme-clustering: ZWJ, Virama, VS16, Regional Indicators,
        #    Fitzpatrick, Mc, wcwidth
        ucs = ord(char)

        # ZWJ (U+200D)
        if ucs == 0x200D:
            if prev_was_virama:
                idx += 1
            elif idx + 1 < text_len:
                # Check for terminal grapheme override when base char is ExtPict/RI
                if (_grapheme_overrides
                        and last_measured_idx >= 0
                        and last_measured_ucs in _EMOJI_ZWJ_SET):
                    cluster_end = _scan_zwj_cluster_end(text, last_measured_idx, text_len)
                    cluster = text[last_measured_idx:cluster_end]
                    override_w = _grapheme_overrides.get(cluster)
                    if override_w is not None:
                        current_col += (override_w - last_measured_w)
                        max_extent = max(max_extent, current_col)
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
                current_col -= 1
                max_extent = max(_max_extent_before, current_col)
            idx += 1
            continue

        # 7. Regional Indicator & Fitzpatrick (both above BMP)
        if ucs > 0xFFFF:
            if ucs in _REGIONAL_INDICATOR_SET:
                ri_before = 0
                j = idx - 1
                while j >= 0 and ord(text[j]) in _REGIONAL_INDICATOR_SET:
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
                    # Two-phase override lookup (see _wcswidth.py)
                    candidate = text[cluster_start:idx + 1]
                    override_w = _grapheme_overrides.get(candidate)
                    if override_w is not None:
                        current_col = col_before_cluster + override_w
                        max_extent = max(max_extent_before_cluster, current_col)
                        flushed = True
                        cluster_width = 0
                    else:
                        cluster_text = text[cluster_start:idx]
                        override_w = _grapheme_overrides.get(cluster_text)
                        if override_w is not None:
                            current_col = col_before_cluster + override_w
                            max_extent = max(max_extent_before_cluster, current_col)
                        else:
                            current_col += cluster_width
                else:
                    current_col += cluster_width
                if current_col > max_extent:
                    max_extent = current_col
                if not flushed:
                    cluster_width = w
                    cluster_start = idx
                    col_before_cluster = current_col
                    max_extent_before_cluster = max_extent
            else:
                cluster_width = w
                cluster_start = idx
                col_before_cluster = current_col
                max_extent_before_cluster = max_extent
            last_measured_idx = idx
            last_measured_ucs = ucs
            last_measured_w = w
            _max_extent_before = max_extent
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
            cluster_text = text[cluster_start:text_len]
            override_w = _grapheme_overrides.get(cluster_text)
            if override_w is not None:
                current_col = col_before_cluster + override_w
                max_extent = max(max_extent_before_cluster, current_col)
            else:
                current_col += cluster_width
                if current_col > max_extent:
                    max_extent = current_col
        else:
            current_col += cluster_width
            if current_col > max_extent:
                max_extent = current_col
    return max_extent
