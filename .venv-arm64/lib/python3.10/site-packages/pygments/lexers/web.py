"""
    pygments.lexers.web
    ~~~~~~~~~~~~~~~~~~~

    Just export previously exported lexers.

    :copyright: Copyright 2006-present by the Pygments team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""

# ruff: noqa: F401
from pygments.lexers.html import HtmlLexer, DtdLexer, XmlLexer, XsltLexer, \
    HamlLexer, ScamlLexer, JadeLexer
from pygments.lexers.css import CssLexer, SassLexer, ScssLexer
from pygments.lexers.javascript import JavascriptLexer, LiveScriptLexer, \
    DartLexer, TypeScriptLexer, LassoLexer, ObjectiveJLexer, CoffeeScriptLexer
from pygments.lexers.actionscript import ActionScriptLexer, \
    ActionScript3Lexer, MxmlLexer
from pygments.lexers.php import PhpLexer
from pygments.lexers.webmisc import DuelLexer, XQueryLexer, SlimLexer, QmlLexer
from pygments.lexers.data import JsonLexer
JSONLexer = JsonLexer  # for backwards compatibility with Pygments 1.5

__all__ = []
