"""
Python 'wcwidth' module.

https://github.com/jquast/wcwidth
"""

# re-export common and outermost functions & definitions, even a few private
# ones, some for convenience, others for legacy, only the items in __all__ are
# documented as public API

__lazy_modules__ = [
    "wcwidth._clip",
    "wcwidth._wcswidth",
    "wcwidth._wcwidth",
    "wcwidth._width",
    "wcwidth.align",
    "wcwidth.bisearch",
    "wcwidth.escape_sequences",
    "wcwidth.grapheme",
    "wcwidth.hyperlink",
    "wcwidth.sgr_state",
    "wcwidth.table_ambiguous",
    "wcwidth.table_vs16",
    "wcwidth.table_wide",
    "wcwidth.table_zero",
    "wcwidth.text_sizing",
    "wcwidth.textwrap",
    "wcwidth.unicode_versions",
]

# local
from ._clip import clip
from .align import ljust, rjust, center
from ._width import width
from .bisearch import bisearch as _bisearch
from .grapheme import iter_graphemes, iter_graphemes_reverse, grapheme_boundary_before
from .textwrap import SequenceTextWrapper, wrap
from ._wcswidth import wcswidth, wcstwidth
from .hyperlink import Hyperlink, HyperlinkParams
from .sgr_state import propagate_sgr
from ._constants import list_term_programs
from .table_vs16 import VS16_NARROW_TO_WIDE
from .table_wide import WIDE_EASTASIAN
from .table_zero import ZERO_WIDTH
from .text_sizing import TextSizing, TextSizingParams
from .table_ambiguous import AMBIGUOUS_EASTASIAN
from .escape_sequences import iter_sequences, strip_sequences
from .unicode_versions import list_versions

# NOTE: this sort order is important for legacy import API compatibility before release 0.7.0
#
# On Python < 3.15 the legacy submodule is eagerly pre-imported for backward compatibility
# (populates sys.modules['wcwidth.wcwidth']).  On 3.15+ __lazy_modules__ handles all submodules; the
# legacy shim loads on-demand via file discovery when ``from wcwidth.wcwidth import ...`` is used.
if __import__('sys').version_info < (3, 15):
    # Pre-import the legacy submodule so that sys.modules['wcwidth.wcwidth'] is populated during
    # package initialization.  Without this, a later downstream dependent ``import wcwidth.wcwidth``
    # triggers on-disk file discovery which rebinds wcwidth.wcwidth from the function to the module
    # object.
    #
    # this is just a lot of carefulness for the original release that contained all functions in a
    # single 'wcwidth.py' file. Even though we always exposed our API at the top-level the preferred
    # 'from wcwidth import wcswidth', it was always possible to import them more directly,
    # 'from wcwidth.wcwidth import wcswidth'
    # -- and we make a lot of effort to allow any such import statements to continue to function.
    from . import wcwidth as _wcwidth_module  # isort:skip
from ._wcwidth import wcwidth, _wcmatch_version, _wcversion_value  # isort:skip  # pylint: disable=wrong-import-position


# The __all__ attribute defines the items exported from statement,
# 'from wcwidth import *', but also to say, "This is the public API".
__all__ = ('wcwidth', 'wcswidth', 'wcstwidth', 'width', 'iter_sequences', 'iter_graphemes',
           'iter_graphemes_reverse', 'grapheme_boundary_before',
           'ljust', 'rjust', 'center', 'wrap', 'clip', 'strip_sequences',
           'list_versions', 'list_term_programs', 'propagate_sgr',
           'Hyperlink', 'HyperlinkParams', 'TextSizing', 'TextSizingParams')

# Using 'hatchling', it does not seem to provide the pyproject.toml nicety, "dynamic = ['version']"
# like flit_core, maybe there is some better way but for now we have to duplicate it in both places
# Prefer the installed distribution version when available (helps test environments)
__version__ = '0.8.2'  # don't forget to also update pyproject.toml:version
