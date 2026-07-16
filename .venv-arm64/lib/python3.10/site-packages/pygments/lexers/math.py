"""
    pygments.lexers.math
    ~~~~~~~~~~~~~~~~~~~~

    Just export lexers that were contained in this module.

    :copyright: Copyright 2006-present by the Pygments team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""

# ruff: noqa: F401
from pygments.lexers.python import NumPyLexer
from pygments.lexers.matlab import MatlabLexer, MatlabSessionLexer, \
    OctaveLexer, ScilabLexer
from pygments.lexers.julia import JuliaLexer, JuliaConsoleLexer
from pygments.lexers.r import RConsoleLexer, SLexer, RdLexer
from pygments.lexers.modeling import BugsLexer, JagsLexer, StanLexer
from pygments.lexers.idl import IDLLexer
from pygments.lexers.algebra import MuPADLexer

__all__ = []
