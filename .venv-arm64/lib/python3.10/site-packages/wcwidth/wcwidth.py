"""
Legacy compatibility module for wcwidth.wcwidth.

This file contains no new definitions and is provided only for backwards compatibility.  This module
exists solely to support legacy "absolute" import paths, when this module published everything under
this single file, 'wcwidth'::

    from wcwidth.wcwidth import wcswidth
    import wcwidth.wcwidth as wc_module
"""
# pylint: disable=unused-import

__lazy_modules__ = [
    "wcwidth._clip",
    "wcwidth._constants",
    "wcwidth._wcswidth",
    "wcwidth._wcwidth",
    "wcwidth._width",
    "wcwidth.align",
    "wcwidth.bisearch",
    "wcwidth.control_codes",
    "wcwidth.escape_sequences",
    "wcwidth.grapheme",
    "wcwidth.sgr_state",
    "wcwidth.table_ambiguous",
    "wcwidth.table_grapheme",
    "wcwidth.table_mc",
    "wcwidth.table_vs16",
    "wcwidth.table_wide",
    "wcwidth.table_zero",
    "wcwidth.unicode_versions",
]

# local
from ._clip import clip
from .align import ljust, rjust, center
from ._width import _CONTROL_CHAR_TABLE, _WIDTH_FAST_PATH_MIN_LEN, width, _width_ignored_codes
from ._wcwidth import wcwidth, _wcmatch_version, _wcversion_value
from .bisearch import bisearch as _bisearch
from .grapheme import iter_graphemes
from .table_mc import CATEGORY_MC
from ._wcswidth import wcswidth, wcstwidth
from .sgr_state import (_SGR_PATTERN,
                        _SGR_STATE_DEFAULT,
                        _sgr_state_update,
                        _sgr_state_is_active,
                        _sgr_state_to_sequence)
from ._constants import (_EMOJI_ZWJ_SET,
                         _ISC_VIRAMA_SET,
                         _LATEST_VERSION,
                         _AMBIGUOUS_TABLE,
                         _ZERO_WIDTH_TABLE,
                         _CATEGORY_MC_TABLE,
                         _FITZPATRICK_RANGE,
                         _WIDE_EASTASIAN_TABLE,
                         _REGIONAL_INDICATOR_SET)
from .table_vs16 import VS16_NARROW_TO_WIDE
from .table_wide import WIDE_EASTASIAN
from .table_zero import ZERO_WIDTH
from .control_codes import ILLEGAL_CTRL, VERTICAL_CTRL, HORIZONTAL_CTRL, ZERO_WIDTH_CTRL
from .table_ambiguous import AMBIGUOUS_EASTASIAN
from .escape_sequences import (ZERO_WIDTH_PATTERN,
                               CURSOR_LEFT_SEQUENCE,
                               CURSOR_RIGHT_SEQUENCE,
                               INDETERMINATE_EFFECT_SEQUENCE,
                               iter_sequences,
                               strip_sequences)
from .unicode_versions import list_versions

__all__ = (
    'ZERO_WIDTH',
    'WIDE_EASTASIAN',
    'AMBIGUOUS_EASTASIAN',
    'VS16_NARROW_TO_WIDE',
    'list_versions',
    'wcwidth',
    'wcswidth',
    'wcstwidth',
    'width',
    'iter_sequences',
    'ljust',
    'rjust',
    'center',
    'clip',
    'strip_sequences',
    '_wcmatch_version',
    '_wcversion_value',
)
