from __future__ import annotations

import re
from typing import Callable, Iterable, NamedTuple, Sequence

from prompt_toolkit.document import Document
from prompt_toolkit.filters import FilterOrBool, to_filter
from prompt_toolkit.formatted_text import AnyFormattedText, StyleAndTextTuples

from .base import CompleteEvent, Completer, Completion
from .word_completer import WordCompleter

__all__ = [
    "FuzzyCompleter",
    "FuzzyWordCompleter",
]


class FuzzyCompleter(Completer):
    """
    Fuzzy completion.
    This wraps any other completer and turns it into a fuzzy completer.

    If the list of words is: ["leopard" , "gorilla", "dinosaur", "cat", "bee"]
    Then trying to complete "oar" would yield "leopard" and "dinosaur", but not
    the others, because they match the regular expression 'o.*a.*r'.
    Similar, in another application "djm" could expand to "django_migrations".

    The results are sorted by relevance, which is defined as the start position
    and the length of the match.

    Notice that this is not really a tool to work around spelling mistakes,
    like what would be possible with difflib. The purpose is rather to have a
    quicker or more intuitive way to filter the given completions, especially
    when many completions have a common prefix.

    Fuzzy algorithm is based on this post:
    https://blog.amjith.com/fuzzyfinder-in-10-lines-of-python

    :param completer: A :class:`~.Completer` instance.
    :param WORD: When True, use WORD characters.
    :param pattern: Regex pattern which selects the characters before the
        cursor that are considered for the fuzzy matching.
    :param enable_fuzzy: (bool or `Filter`) Enabled the fuzzy behavior. For
        easily turning fuzzyness on or off according to a certain condition.
    """

    def __init__(
        self,
        completer: Completer,
        WORD: bool = False,
        pattern: str | None = None,
        enable_fuzzy: FilterOrBool = True,
    ) -> None:
        assert pattern is None or pattern.startswith("^")

        self.completer = completer
        self.pattern = pattern
        self.WORD = WORD
        self.pattern = pattern
        self.enable_fuzzy = to_filter(enable_fuzzy)

    def get_completions(
        self, document: Document, complete_event: CompleteEvent
    ) -> Iterable[Completion]:
        if self.enable_fuzzy():
            return self._get_fuzzy_completions(document, complete_event)
        else:
            return self.completer.get_completions(document, complete_event)

    def _get_pattern(self) -> str:
        if self.pattern:
            return self.pattern
        if self.WORD:
            return r"[^\s]+"
        return "^[a-zA-Z0-9_]*"

    def _get_fuzzy_completions(
        self, document: Document, complete_event: CompleteEvent
    ) -> Iterable[Completion]:
        word_before_cursor = document.get_word_before_cursor(
            pattern=re.compile(self._get_pattern())
        )

        # Get completions
        document2 = Document(
            text=document.text[: document.cursor_position - len(word_before_cursor)],
            cursor_position=document.cursor_position - len(word_before_cursor),
        )

        inner_completions = list(
            self.completer.get_completions(document2, complete_event)
        )

        fuzzy_matches: list[_FuzzyMatch] = []

        if word_before_cursor == "":
            # If word before the cursor is an empty string, consider all
            # completions, without filtering everything with an empty regex
            # pattern.
            fuzzy_matches = [_FuzzyMatch(0, 0, compl) for compl in inner_completions]
        else:
            pat = ".*?".join(map(re.escape, word_before_cursor))
            pat = f"(?=({pat}))"  # lookahead regex to manage overlapping matches
            regex = re.compile(pat, re.IGNORECASE)
            for compl in inner_completions:
                matches = list(regex.finditer(compl.text))
                if matches:
                    # Prefer the match, closest to the left, then shortest.
                    best = min(matches, key=lambda m: (m.start(), len(m.group(1))))
                    fuzzy_matches.append(
                        _FuzzyMatch(len(best.group(1)), best.start(), compl)
                    )

            def sort_key(fuzzy_match: _FuzzyMatch) -> tuple[int, int]:
                "Sort by start position, then by the length of the match."
                return fuzzy_match.start_pos, fuzzy_match.match_length

            fuzzy_matches = sorted(fuzzy_matches, key=sort_key)

        for match in fuzzy_matches:
            # Include these completions, but set the correct `display`
            # attribute and `start_position`.
            yield Completion(
                text=match.completion.text,
                start_position=match.completion.start_position
                - len(word_before_cursor),
                # We access to private `_display_meta` attribute, because that one is lazy.
                display_meta=match.completion._display_meta,
                display=self._get_display(match, word_before_cursor),
                style=match.completion.style,
            )

    def _get_display(
        self, fuzzy_match: _FuzzyMatch, word_before_cursor: str
    ) -> AnyFormattedText:
        """
        Generate formatted text for the display label.
        """

        def get_display() -> AnyFormattedText:
            m = fuzzy_match
            word = m.completion.text

            if m.match_length == 0:
                # No highlighting when we have zero length matches (no input text).
                # In this case, use the original display text (which can include
                # additional styling or characters).
                return m.completion.display

            result: StyleAndTextTuples = []

            # Text before match.
            result.append(("class:fuzzymatch.outside", word[: m.start_pos]))

            # The match itself.
            characters = list(word_before_cursor)

            for c in word[m.start_pos : m.start_pos + m.match_length]:
                classname = "class:fuzzymatch.inside"
                if characters and c.lower() == characters[0].lower():
                    classname += ".character"
                    del characters[0]

                result.append((classname, c))

            # Text after match.
            result.append(
                ("class:fuzzymatch.outside", word[m.start_pos + m.match_length :])
            )

            return result

        return get_display()


class FuzzyWordCompleter(Completer):
    """
    Fuzzy completion on a list of words.

    (This is basically a `WordCompleter` wrapped in a `FuzzyCompleter`.)

    :param words: List of words or callable that returns a list of words.
    :param meta_dict: Optional dict mapping words to their meta-information.
    :param WORD: When True, use WORD characters.
    """

    def __init__(
        self,
        words: Sequence[str] | Callable[[], Sequence[str]],
        meta_dict: dict[str, str] | None = None,
        WORD: bool = False,
    ) -> None:
        self.words = words
        self.meta_dict = meta_dict or {}
        self.WORD = WORD

        self.word_completer = WordCompleter(
            words=self.words, WORD=self.WORD, meta_dict=self.meta_dict
        )

        self.fuzzy_completer = FuzzyCompleter(self.word_completer, WORD=self.WORD)

    def get_completions(
        self, document: Document, complete_event: CompleteEvent
    ) -> Iterable[Completion]:
        return self.fuzzy_completer.get_completions(document, complete_event)


class _FuzzyMatch(NamedTuple):
    match_length: int
    start_pos: int
    completion: Completion
