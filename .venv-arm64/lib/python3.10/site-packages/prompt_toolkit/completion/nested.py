"""
Nestedcompleter for completion of hierarchical data structures.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Set, Union

from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.completion.word_completer import WordCompleter
from prompt_toolkit.document import Document

__all__ = ["NestedCompleter"]

# NestedDict = Mapping[str, Union['NestedDict', Set[str], None, Completer]]
NestedDict = Mapping[str, Union[Any, Set[str], None, Completer]]


class NestedCompleter(Completer):
    """
    Completer which wraps around several other completers, and calls any the
    one that corresponds with the first word of the input.

    By combining multiple `NestedCompleter` instances, we can achieve multiple
    hierarchical levels of autocompletion. This is useful when `WordCompleter`
    is not sufficient.

    If you need multiple levels, check out the `from_nested_dict` classmethod.
    """

    def __init__(
        self, options: dict[str, Completer | None], ignore_case: bool = True
    ) -> None:
        self.options = options
        self.ignore_case = ignore_case

    def __repr__(self) -> str:
        return f"NestedCompleter({self.options!r}, ignore_case={self.ignore_case!r})"

    @classmethod
    def from_nested_dict(cls, data: NestedDict) -> NestedCompleter:
        """
        Create a `NestedCompleter`, starting from a nested dictionary data
        structure, like this:

        .. code::

            data = {
                'show': {
                    'version': None,
                    'interfaces': None,
                    'clock': None,
                    'ip': {'interface': {'brief'}}
                },
                'exit': None
                'enable': None
            }

        The value should be `None` if there is no further completion at some
        point. If all values in the dictionary are None, it is also possible to
        use a set instead.

        Values in this data structure can be a completers as well.
        """
        options: dict[str, Completer | None] = {}
        for key, value in data.items():
            if isinstance(value, Completer):
                options[key] = value
            elif isinstance(value, dict):
                options[key] = cls.from_nested_dict(value)
            elif isinstance(value, set):
                options[key] = cls.from_nested_dict(dict.fromkeys(value))
            else:
                assert value is None
                options[key] = None

        return cls(options)

    def get_completions(
        self, document: Document, complete_event: CompleteEvent
    ) -> Iterable[Completion]:
        # Split document.
        text = document.text_before_cursor.lstrip()
        stripped_len = len(document.text_before_cursor) - len(text)

        # If there is a space, check for the first term, and use a
        # subcompleter.
        if " " in text:
            first_term = text.split()[0]
            completer = self.options.get(first_term)

            # If we have a sub completer, use this for the completions.
            if completer is not None:
                remaining_text = text[len(first_term) :].lstrip()
                move_cursor = len(text) - len(remaining_text) + stripped_len

                new_document = Document(
                    remaining_text,
                    cursor_position=document.cursor_position - move_cursor,
                )

                yield from completer.get_completions(new_document, complete_event)

        # No space in the input: behave exactly like `WordCompleter`.
        else:
            completer = WordCompleter(
                list(self.options.keys()), ignore_case=self.ignore_case
            )
            yield from completer.get_completions(document, complete_event)
