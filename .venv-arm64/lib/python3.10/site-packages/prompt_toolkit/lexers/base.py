"""
Base classes for prompt_toolkit lexers.
"""

from __future__ import annotations

from abc import ABCMeta, abstractmethod
from typing import Callable, Hashable

from prompt_toolkit.document import Document
from prompt_toolkit.formatted_text.base import StyleAndTextTuples

__all__ = [
    "Lexer",
    "SimpleLexer",
    "DynamicLexer",
]


class Lexer(metaclass=ABCMeta):
    """
    Base class for all lexers.
    """

    @abstractmethod
    def lex_document(self, document: Document) -> Callable[[int], StyleAndTextTuples]:
        """
        Takes a :class:`~prompt_toolkit.document.Document` and returns a
        callable that takes a line number and returns a list of
        ``(style_str, text)`` tuples for that line.

        XXX: Note that in the past, this was supposed to return a list
             of ``(Token, text)`` tuples, just like a Pygments lexer.
        """

    def invalidation_hash(self) -> Hashable:
        """
        When this changes, `lex_document` could give a different output.
        (Only used for `DynamicLexer`.)
        """
        return id(self)


class SimpleLexer(Lexer):
    """
    Lexer that doesn't do any tokenizing and returns the whole input as one
    token.

    :param style: The style string for this lexer.
    """

    def __init__(self, style: str = "") -> None:
        self.style = style

    def lex_document(self, document: Document) -> Callable[[int], StyleAndTextTuples]:
        lines = document.lines

        def get_line(lineno: int) -> StyleAndTextTuples:
            "Return the tokens for the given line."
            try:
                return [(self.style, lines[lineno])]
            except IndexError:
                return []

        return get_line


class DynamicLexer(Lexer):
    """
    Lexer class that can dynamically returns any Lexer.

    :param get_lexer: Callable that returns a :class:`.Lexer` instance.
    """

    def __init__(self, get_lexer: Callable[[], Lexer | None]) -> None:
        self.get_lexer = get_lexer
        self._dummy = SimpleLexer()

    def lex_document(self, document: Document) -> Callable[[int], StyleAndTextTuples]:
        lexer = self.get_lexer() or self._dummy
        return lexer.lex_document(document)

    def invalidation_hash(self) -> Hashable:
        lexer = self.get_lexer() or self._dummy
        return id(lexer)
