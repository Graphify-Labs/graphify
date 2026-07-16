"""
Completer for a regular grammar.
"""

from __future__ import annotations

from typing import Iterable

from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.document import Document

from .compiler import Match, _CompiledGrammar

__all__ = [
    "GrammarCompleter",
]


class GrammarCompleter(Completer):
    """
    Completer which can be used for autocompletion according to variables in
    the grammar. Each variable can have a different autocompleter.

    :param compiled_grammar: `GrammarCompleter` instance.
    :param completers: `dict` mapping variable names of the grammar to the
                       `Completer` instances to be used for each variable.
    """

    def __init__(
        self, compiled_grammar: _CompiledGrammar, completers: dict[str, Completer]
    ) -> None:
        self.compiled_grammar = compiled_grammar
        self.completers = completers

    def get_completions(
        self, document: Document, complete_event: CompleteEvent
    ) -> Iterable[Completion]:
        m = self.compiled_grammar.match_prefix(document.text_before_cursor)

        if m:
            yield from self._remove_duplicates(
                self._get_completions_for_match(m, complete_event)
            )

    def _get_completions_for_match(
        self, match: Match, complete_event: CompleteEvent
    ) -> Iterable[Completion]:
        """
        Yield all the possible completions for this input string.
        (The completer assumes that the cursor position was at the end of the
        input string.)
        """
        for match_variable in match.end_nodes():
            varname = match_variable.varname
            start = match_variable.start

            completer = self.completers.get(varname)

            if completer:
                text = match_variable.value

                # Unwrap text.
                unwrapped_text = self.compiled_grammar.unescape(varname, text)

                # Create a document, for the completions API (text/cursor_position)
                document = Document(unwrapped_text, len(unwrapped_text))

                # Call completer
                for completion in completer.get_completions(document, complete_event):
                    new_text = (
                        unwrapped_text[: len(text) + completion.start_position]
                        + completion.text
                    )

                    # Wrap again.
                    yield Completion(
                        text=self.compiled_grammar.escape(varname, new_text),
                        start_position=start - len(match.string),
                        display=completion.display,
                        display_meta=completion.display_meta,
                    )

    def _remove_duplicates(self, items: Iterable[Completion]) -> Iterable[Completion]:
        """
        Remove duplicates, while keeping the order.
        (Sometimes we have duplicates, because the there several matches of the
        same grammar, each yielding similar completions.)
        """

        def hash_completion(completion: Completion) -> tuple[str, int]:
            return completion.text, completion.start_position

        yielded_so_far: set[tuple[str, int]] = set()

        for completion in items:
            hash_value = hash_completion(completion)

            if hash_value not in yielded_so_far:
                yielded_so_far.add(hash_value)
                yield completion
