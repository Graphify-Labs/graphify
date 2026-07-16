"""
Adaptor classes for using Pygments lexers within prompt_toolkit.

This includes syntax synchronization code, so that we don't have to start
lexing at the beginning of a document, when displaying a very large text.
"""

from __future__ import annotations

import re
from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING, Callable, Dict, Generator, Iterable, Tuple

from prompt_toolkit.document import Document
from prompt_toolkit.filters import FilterOrBool, to_filter
from prompt_toolkit.formatted_text.base import StyleAndTextTuples
from prompt_toolkit.formatted_text.utils import split_lines
from prompt_toolkit.styles.pygments import pygments_token_to_classname

from .base import Lexer, SimpleLexer

if TYPE_CHECKING:
    from pygments.lexer import Lexer as PygmentsLexerCls

__all__ = [
    "PygmentsLexer",
    "SyntaxSync",
    "SyncFromStart",
    "RegexSync",
]


class SyntaxSync(metaclass=ABCMeta):
    """
    Syntax synchronizer. This is a tool that finds a start position for the
    lexer. This is especially important when editing big documents; we don't
    want to start the highlighting by running the lexer from the beginning of
    the file. That is very slow when editing.
    """

    @abstractmethod
    def get_sync_start_position(
        self, document: Document, lineno: int
    ) -> tuple[int, int]:
        """
        Return the position from where we can start lexing as a (row, column)
        tuple.

        :param document: `Document` instance that contains all the lines.
        :param lineno: The line that we want to highlight. (We need to return
            this line, or an earlier position.)
        """


class SyncFromStart(SyntaxSync):
    """
    Always start the syntax highlighting from the beginning.
    """

    def get_sync_start_position(
        self, document: Document, lineno: int
    ) -> tuple[int, int]:
        return 0, 0


class RegexSync(SyntaxSync):
    """
    Synchronize by starting at a line that matches the given regex pattern.
    """

    # Never go more than this amount of lines backwards for synchronization.
    # That would be too CPU intensive.
    MAX_BACKWARDS = 500

    # Start lexing at the start, if we are in the first 'n' lines and no
    # synchronization position was found.
    FROM_START_IF_NO_SYNC_POS_FOUND = 100

    def __init__(self, pattern: str) -> None:
        self._compiled_pattern = re.compile(pattern)

    def get_sync_start_position(
        self, document: Document, lineno: int
    ) -> tuple[int, int]:
        """
        Scan backwards, and find a possible position to start.
        """
        pattern = self._compiled_pattern
        lines = document.lines

        # Scan upwards, until we find a point where we can start the syntax
        # synchronization.
        for i in range(lineno, max(-1, lineno - self.MAX_BACKWARDS), -1):
            match = pattern.match(lines[i])
            if match:
                return i, match.start()

        # No synchronization point found. If we aren't that far from the
        # beginning, start at the very beginning, otherwise, just try to start
        # at the current line.
        if lineno < self.FROM_START_IF_NO_SYNC_POS_FOUND:
            return 0, 0
        else:
            return lineno, 0

    @classmethod
    def from_pygments_lexer_cls(cls, lexer_cls: PygmentsLexerCls) -> RegexSync:
        """
        Create a :class:`.RegexSync` instance for this Pygments lexer class.
        """
        patterns = {
            # For Python, start highlighting at any class/def block.
            "Python": r"^\s*(class|def)\s+",
            "Python 3": r"^\s*(class|def)\s+",
            # For HTML, start at any open/close tag definition.
            "HTML": r"<[/a-zA-Z]",
            # For javascript, start at a function.
            "JavaScript": r"\bfunction\b",
            # TODO: Add definitions for other languages.
            #       By default, we start at every possible line.
        }
        p = patterns.get(lexer_cls.name, "^")
        return cls(p)


class _TokenCache(Dict[Tuple[str, ...], str]):
    """
    Cache that converts Pygments tokens into `prompt_toolkit` style objects.

    ``Token.A.B.C`` will be converted into:
    ``class:pygments,pygments.A,pygments.A.B,pygments.A.B.C``
    """

    def __missing__(self, key: tuple[str, ...]) -> str:
        result = "class:" + pygments_token_to_classname(key)
        self[key] = result
        return result


_token_cache = _TokenCache()


class PygmentsLexer(Lexer):
    """
    Lexer that calls a pygments lexer.

    Example::

        from pygments.lexers.html import HtmlLexer
        lexer = PygmentsLexer(HtmlLexer)

    Note: Don't forget to also load a Pygments compatible style. E.g.::

        from prompt_toolkit.styles.from_pygments import style_from_pygments_cls
        from pygments.styles import get_style_by_name
        style = style_from_pygments_cls(get_style_by_name('monokai'))

    :param pygments_lexer_cls: A `Lexer` from Pygments.
    :param sync_from_start: Start lexing at the start of the document. This
        will always give the best results, but it will be slow for bigger
        documents. (When the last part of the document is display, then the
        whole document will be lexed by Pygments on every key stroke.) It is
        recommended to disable this for inputs that are expected to be more
        than 1,000 lines.
    :param syntax_sync: `SyntaxSync` object.
    """

    # Minimum amount of lines to go backwards when starting the parser.
    # This is important when the lines are retrieved in reverse order, or when
    # scrolling upwards. (Due to the complexity of calculating the vertical
    # scroll offset in the `Window` class, lines are not always retrieved in
    # order.)
    MIN_LINES_BACKWARDS = 50

    # When a parser was started this amount of lines back, read the parser
    # until we get the current line. Otherwise, start a new parser.
    # (This should probably be bigger than MIN_LINES_BACKWARDS.)
    REUSE_GENERATOR_MAX_DISTANCE = 100

    def __init__(
        self,
        pygments_lexer_cls: type[PygmentsLexerCls],
        sync_from_start: FilterOrBool = True,
        syntax_sync: SyntaxSync | None = None,
    ) -> None:
        self.pygments_lexer_cls = pygments_lexer_cls
        self.sync_from_start = to_filter(sync_from_start)

        # Instantiate the Pygments lexer.
        self.pygments_lexer = pygments_lexer_cls(
            stripnl=False, stripall=False, ensurenl=False
        )

        # Create syntax sync instance.
        self.syntax_sync = syntax_sync or RegexSync.from_pygments_lexer_cls(
            pygments_lexer_cls
        )

    @classmethod
    def from_filename(
        cls, filename: str, sync_from_start: FilterOrBool = True
    ) -> Lexer:
        """
        Create a `Lexer` from a filename.
        """
        # Inline imports: the Pygments dependency is optional!
        from pygments.lexers import get_lexer_for_filename
        from pygments.util import ClassNotFound

        try:
            pygments_lexer = get_lexer_for_filename(filename)
        except ClassNotFound:
            return SimpleLexer()
        else:
            return cls(pygments_lexer.__class__, sync_from_start=sync_from_start)

    def lex_document(self, document: Document) -> Callable[[int], StyleAndTextTuples]:
        """
        Create a lexer function that takes a line number and returns the list
        of (style_str, text) tuples as the Pygments lexer returns for that line.
        """
        LineGenerator = Generator[Tuple[int, StyleAndTextTuples], None, None]

        # Cache of already lexed lines.
        cache: dict[int, StyleAndTextTuples] = {}

        # Pygments generators that are currently lexing.
        # Map lexer generator to the line number.
        line_generators: dict[LineGenerator, int] = {}

        def get_syntax_sync() -> SyntaxSync:
            "The Syntax synchronization object that we currently use."
            if self.sync_from_start():
                return SyncFromStart()
            else:
                return self.syntax_sync

        def find_closest_generator(i: int) -> LineGenerator | None:
            "Return a generator close to line 'i', or None if none was found."
            for generator, lineno in line_generators.items():
                if lineno < i and i - lineno < self.REUSE_GENERATOR_MAX_DISTANCE:
                    return generator
            return None

        def create_line_generator(start_lineno: int, column: int = 0) -> LineGenerator:
            """
            Create a generator that yields the lexed lines.
            Each iteration it yields a (line_number, [(style_str, text), ...]) tuple.
            """

            def get_text_fragments() -> Iterable[tuple[str, str]]:
                text = "\n".join(document.lines[start_lineno:])[column:]

                # We call `get_text_fragments_unprocessed`, because `get_tokens` will
                # still replace \r\n and \r by \n.  (We don't want that,
                # Pygments should return exactly the same amount of text, as we
                # have given as input.)
                for _, t, v in self.pygments_lexer.get_tokens_unprocessed(text):
                    # Turn Pygments `Token` object into prompt_toolkit style
                    # strings.
                    yield _token_cache[t], v

            yield from enumerate(split_lines(list(get_text_fragments())), start_lineno)

        def get_generator(i: int) -> LineGenerator:
            """
            Find an already started generator that is close, or create a new one.
            """
            # Find closest line generator.
            generator = find_closest_generator(i)
            if generator:
                return generator

            # No generator found. Determine starting point for the syntax
            # synchronization first.

            # Go at least x lines back. (Make scrolling upwards more
            # efficient.)
            i = max(0, i - self.MIN_LINES_BACKWARDS)

            if i == 0:
                row = 0
                column = 0
            else:
                row, column = get_syntax_sync().get_sync_start_position(document, i)

            # Find generator close to this point, or otherwise create a new one.
            generator = find_closest_generator(i)
            if generator:
                return generator
            else:
                generator = create_line_generator(row, column)

            # If the column is not 0, ignore the first line. (Which is
            # incomplete. This happens when the synchronization algorithm tells
            # us to start parsing in the middle of a line.)
            if column:
                next(generator)
                row += 1

            line_generators[generator] = row
            return generator

        def get_line(i: int) -> StyleAndTextTuples:
            "Return the tokens for a given line number."
            try:
                return cache[i]
            except KeyError:
                generator = get_generator(i)

                # Exhaust the generator, until we find the requested line.
                for num, line in generator:
                    cache[num] = line
                    if num == i:
                        line_generators[generator] = i

                        # Remove the next item from the cache.
                        # (It could happen that it's already there, because of
                        # another generator that started filling these lines,
                        # but we want to synchronize these lines with the
                        # current lexer's state.)
                        if num + 1 in cache:
                            del cache[num + 1]

                        return cache[num]
            return []

        return get_line
