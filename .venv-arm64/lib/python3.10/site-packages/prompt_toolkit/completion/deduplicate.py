from __future__ import annotations

from typing import Iterable

from prompt_toolkit.document import Document

from .base import CompleteEvent, Completer, Completion

__all__ = ["DeduplicateCompleter"]


class DeduplicateCompleter(Completer):
    """
    Wrapper around a completer that removes duplicates. Only the first unique
    completions are kept.

    Completions are considered to be a duplicate if they result in the same
    document text when they would be applied.
    """

    def __init__(self, completer: Completer) -> None:
        self.completer = completer

    def get_completions(
        self, document: Document, complete_event: CompleteEvent
    ) -> Iterable[Completion]:
        # Keep track of the document strings we'd get after applying any completion.
        found_so_far: set[str] = set()

        for completion in self.completer.get_completions(document, complete_event):
            text_if_applied = (
                document.text[: document.cursor_position + completion.start_position]
                + completion.text
                + document.text[document.cursor_position :]
            )

            if text_if_applied == document.text:
                # Don't include completions that don't have any effect at all.
                continue

            if text_if_applied in found_so_far:
                continue

            found_so_far.add(text_if_applied)
            yield completion
