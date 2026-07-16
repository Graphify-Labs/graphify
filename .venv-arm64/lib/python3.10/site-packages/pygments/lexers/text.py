"""
    pygments.lexers.text
    ~~~~~~~~~~~~~~~~~~~~

    Lexers for non-source code file types.

    :copyright: Copyright 2006-present by the Pygments team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""

# ruff: noqa: F401
from pygments.lexers.configs import ApacheConfLexer, NginxConfLexer, \
    SquidConfLexer, LighttpdConfLexer, IniLexer, RegeditLexer, PropertiesLexer, \
    UnixConfigLexer
from pygments.lexers.console import PyPyLogLexer
from pygments.lexers.textedit import VimLexer
from pygments.lexers.markup import BBCodeLexer, MoinWikiLexer, RstLexer, \
    TexLexer, GroffLexer
from pygments.lexers.installers import DebianControlLexer, DebianSourcesLexer, SourcesListLexer
from pygments.lexers.make import MakefileLexer, BaseMakefileLexer, CMakeLexer
from pygments.lexers.haxe import HxmlLexer
from pygments.lexers.sgf import SmartGameFormatLexer
from pygments.lexers.diff import DiffLexer, DarcsPatchLexer
from pygments.lexers.data import YamlLexer
from pygments.lexers.textfmts import IrcLogsLexer, GettextLexer, HttpLexer

__all__ = []
