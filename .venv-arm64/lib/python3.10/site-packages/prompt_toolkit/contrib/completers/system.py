from __future__ import annotations

from prompt_toolkit.completion.filesystem import ExecutableCompleter, PathCompleter
from prompt_toolkit.contrib.regular_languages.compiler import compile
from prompt_toolkit.contrib.regular_languages.completion import GrammarCompleter

__all__ = [
    "SystemCompleter",
]


class SystemCompleter(GrammarCompleter):
    """
    Completer for system commands.
    """

    def __init__(self) -> None:
        # Compile grammar.
        g = compile(
            r"""
                # First we have an executable.
                (?P<executable>[^\s]+)

                # Ignore literals in between.
                (
                    \s+
                    ("[^"]*" | '[^']*' | [^'"]+ )
                )*

                \s+

                # Filename as parameters.
                (
                    (?P<filename>[^\s]+) |
                    "(?P<double_quoted_filename>[^\s]+)" |
                    '(?P<single_quoted_filename>[^\s]+)'
                )
            """,
            escape_funcs={
                "double_quoted_filename": (lambda string: string.replace('"', '\\"')),
                "single_quoted_filename": (lambda string: string.replace("'", "\\'")),
            },
            unescape_funcs={
                "double_quoted_filename": (
                    lambda string: string.replace('\\"', '"')
                ),  # XXX: not entirely correct.
                "single_quoted_filename": (lambda string: string.replace("\\'", "'")),
            },
        )

        # Create GrammarCompleter
        super().__init__(
            g,
            {
                "executable": ExecutableCompleter(),
                "filename": PathCompleter(only_directories=False, expanduser=True),
                "double_quoted_filename": PathCompleter(
                    only_directories=False, expanduser=True
                ),
                "single_quoted_filename": PathCompleter(
                    only_directories=False, expanduser=True
                ),
            },
        )
