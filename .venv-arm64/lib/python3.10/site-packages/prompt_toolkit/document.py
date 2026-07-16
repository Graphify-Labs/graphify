"""
The `Document` that implements all the text operations/querying.
"""

from __future__ import annotations

import bisect
import re
import string
import weakref
from typing import Callable, Dict, Iterable, List, NoReturn, Pattern, cast

from .clipboard import ClipboardData
from .filters import vi_mode
from .selection import PasteMode, SelectionState, SelectionType

__all__ = [
    "Document",
]


# Regex for finding "words" in documents. (We consider a group of alnum
# characters a word, but also a group of special characters a word, as long as
# it doesn't contain a space.)
# (This is a 'word' in Vi.)
_FIND_WORD_RE = re.compile(r"([a-zA-Z0-9_]+|[^a-zA-Z0-9_\s]+)")
_FIND_CURRENT_WORD_RE = re.compile(r"^([a-zA-Z0-9_]+|[^a-zA-Z0-9_\s]+)")
_FIND_CURRENT_WORD_INCLUDE_TRAILING_WHITESPACE_RE = re.compile(
    r"^(([a-zA-Z0-9_]+|[^a-zA-Z0-9_\s]+)\s*)"
)

# Regex for finding "WORDS" in documents.
# (This is a 'WORD in Vi.)
_FIND_BIG_WORD_RE = re.compile(r"([^\s]+)")
_FIND_CURRENT_BIG_WORD_RE = re.compile(r"^([^\s]+)")
_FIND_CURRENT_BIG_WORD_INCLUDE_TRAILING_WHITESPACE_RE = re.compile(r"^([^\s]+\s*)")

# Share the Document._cache between all Document instances.
# (Document instances are considered immutable. That means that if another
# `Document` is constructed with the same text, it should have the same
# `_DocumentCache`.)
_text_to_document_cache: dict[str, _DocumentCache] = cast(
    Dict[str, "_DocumentCache"],
    weakref.WeakValueDictionary(),  # Maps document.text to DocumentCache instance.
)


class _ImmutableLineList(List[str]):
    """
    Some protection for our 'lines' list, which is assumed to be immutable in the cache.
    (Useful for detecting obvious bugs.)
    """

    def _error(self, *a: object, **kw: object) -> NoReturn:
        raise NotImplementedError("Attempt to modify an immutable list.")

    __setitem__ = _error
    append = _error
    clear = _error
    extend = _error
    insert = _error
    pop = _error
    remove = _error
    reverse = _error
    sort = _error


class _DocumentCache:
    def __init__(self) -> None:
        #: List of lines for the Document text.
        self.lines: _ImmutableLineList | None = None

        #: List of index positions, pointing to the start of all the lines.
        self.line_indexes: list[int] | None = None


class Document:
    """
    This is a immutable class around the text and cursor position, and contains
    methods for querying this data, e.g. to give the text before the cursor.

    This class is usually instantiated by a :class:`~prompt_toolkit.buffer.Buffer`
    object, and accessed as the `document` property of that class.

    :param text: string
    :param cursor_position: int
    :param selection: :class:`.SelectionState`
    """

    __slots__ = ("_text", "_cursor_position", "_selection", "_cache")

    def __init__(
        self,
        text: str = "",
        cursor_position: int | None = None,
        selection: SelectionState | None = None,
    ) -> None:
        # Check cursor position. It can also be right after the end. (Where we
        # insert text.)
        assert cursor_position is None or cursor_position <= len(text), AssertionError(
            f"cursor_position={cursor_position!r}, len_text={len(text)!r}"
        )

        # By default, if no cursor position was given, make sure to put the
        # cursor position is at the end of the document. This is what makes
        # sense in most places.
        if cursor_position is None:
            cursor_position = len(text)

        # Keep these attributes private. A `Document` really has to be
        # considered to be immutable, because otherwise the caching will break
        # things. Because of that, we wrap these into read-only properties.
        self._text = text
        self._cursor_position = cursor_position
        self._selection = selection

        # Cache for lines/indexes. (Shared with other Document instances that
        # contain the same text.
        try:
            self._cache = _text_to_document_cache[self.text]
        except KeyError:
            self._cache = _DocumentCache()
            _text_to_document_cache[self.text] = self._cache

        # XX: For some reason, above, we can't use 'WeakValueDictionary.setdefault'.
        #     This fails in Pypy3. `self._cache` becomes None, because that's what
        #     'setdefault' returns.
        # self._cache = _text_to_document_cache.setdefault(self.text, _DocumentCache())
        # assert self._cache

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.text!r}, {self.cursor_position!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Document):
            return False

        return (
            self.text == other.text
            and self.cursor_position == other.cursor_position
            and self.selection == other.selection
        )

    @property
    def text(self) -> str:
        "The document text."
        return self._text

    @property
    def cursor_position(self) -> int:
        "The document cursor position."
        return self._cursor_position

    @property
    def selection(self) -> SelectionState | None:
        ":class:`.SelectionState` object."
        return self._selection

    @property
    def current_char(self) -> str:
        """Return character under cursor or an empty string."""
        return self._get_char_relative_to_cursor(0) or ""

    @property
    def char_before_cursor(self) -> str:
        """Return character before the cursor or an empty string."""
        return self._get_char_relative_to_cursor(-1) or ""

    @property
    def text_before_cursor(self) -> str:
        return self.text[: self.cursor_position :]

    @property
    def text_after_cursor(self) -> str:
        return self.text[self.cursor_position :]

    @property
    def current_line_before_cursor(self) -> str:
        """Text from the start of the line until the cursor."""
        _, _, text = self.text_before_cursor.rpartition("\n")
        return text

    @property
    def current_line_after_cursor(self) -> str:
        """Text from the cursor until the end of the line."""
        text, _, _ = self.text_after_cursor.partition("\n")
        return text

    @property
    def lines(self) -> list[str]:
        """
        Array of all the lines.
        """
        # Cache, because this one is reused very often.
        if self._cache.lines is None:
            self._cache.lines = _ImmutableLineList(self.text.split("\n"))

        return self._cache.lines

    @property
    def _line_start_indexes(self) -> list[int]:
        """
        Array pointing to the start indexes of all the lines.
        """
        # Cache, because this is often reused. (If it is used, it's often used
        # many times. And this has to be fast for editing big documents!)
        if self._cache.line_indexes is None:
            # Create list of line lengths.
            line_lengths = map(len, self.lines)

            # Calculate cumulative sums.
            indexes = [0]
            append = indexes.append
            pos = 0

            for line_length in line_lengths:
                pos += line_length + 1
                append(pos)

            # Remove the last item. (This is not a new line.)
            if len(indexes) > 1:
                indexes.pop()

            self._cache.line_indexes = indexes

        return self._cache.line_indexes

    @property
    def lines_from_current(self) -> list[str]:
        """
        Array of the lines starting from the current line, until the last line.
        """
        return self.lines[self.cursor_position_row :]

    @property
    def line_count(self) -> int:
        r"""Return the number of lines in this document. If the document ends
        with a trailing \n, that counts as the beginning of a new line."""
        return len(self.lines)

    @property
    def current_line(self) -> str:
        """Return the text on the line where the cursor is. (when the input
        consists of just one line, it equals `text`."""
        return self.current_line_before_cursor + self.current_line_after_cursor

    @property
    def leading_whitespace_in_current_line(self) -> str:
        """The leading whitespace in the left margin of the current line."""
        current_line = self.current_line
        length = len(current_line) - len(current_line.lstrip())
        return current_line[:length]

    def _get_char_relative_to_cursor(self, offset: int = 0) -> str:
        """
        Return character relative to cursor position, or empty string
        """
        try:
            return self.text[self.cursor_position + offset]
        except IndexError:
            return ""

    @property
    def on_first_line(self) -> bool:
        """
        True when we are at the first line.
        """
        return self.cursor_position_row == 0

    @property
    def on_last_line(self) -> bool:
        """
        True when we are at the last line.
        """
        return self.cursor_position_row == self.line_count - 1

    @property
    def cursor_position_row(self) -> int:
        """
        Current row. (0-based.)
        """
        row, _ = self._find_line_start_index(self.cursor_position)
        return row

    @property
    def cursor_position_col(self) -> int:
        """
        Current column. (0-based.)
        """
        # (Don't use self.text_before_cursor to calculate this. Creating
        # substrings and doing rsplit is too expensive for getting the cursor
        # position.)
        _, line_start_index = self._find_line_start_index(self.cursor_position)
        return self.cursor_position - line_start_index

    def _find_line_start_index(self, index: int) -> tuple[int, int]:
        """
        For the index of a character at a certain line, calculate the index of
        the first character on that line.

        Return (row, index) tuple.
        """
        indexes = self._line_start_indexes

        pos = bisect.bisect_right(indexes, index) - 1
        return pos, indexes[pos]

    def translate_index_to_position(self, index: int) -> tuple[int, int]:
        """
        Given an index for the text, return the corresponding (row, col) tuple.
        (0-based. Returns (0, 0) for index=0.)
        """
        # Find start of this line.
        row, row_index = self._find_line_start_index(index)
        col = index - row_index

        return row, col

    def translate_row_col_to_index(self, row: int, col: int) -> int:
        """
        Given a (row, col) tuple, return the corresponding index.
        (Row and col params are 0-based.)

        Negative row/col values are turned into zero.
        """
        try:
            result = self._line_start_indexes[row]
            line = self.lines[row]
        except IndexError:
            if row < 0:
                result = self._line_start_indexes[0]
                line = self.lines[0]
            else:
                result = self._line_start_indexes[-1]
                line = self.lines[-1]

        result += max(0, min(col, len(line)))

        # Keep in range. (len(self.text) is included, because the cursor can be
        # right after the end of the text as well.)
        result = max(0, min(result, len(self.text)))
        return result

    @property
    def is_cursor_at_the_end(self) -> bool:
        """True when the cursor is at the end of the text."""
        return self.cursor_position == len(self.text)

    @property
    def is_cursor_at_the_end_of_line(self) -> bool:
        """True when the cursor is at the end of this line."""
        return self.current_char in ("\n", "")

    def has_match_at_current_position(self, sub: str) -> bool:
        """
        `True` when this substring is found at the cursor position.
        """
        return self.text.find(sub, self.cursor_position) == self.cursor_position

    def find(
        self,
        sub: str,
        in_current_line: bool = False,
        include_current_position: bool = False,
        ignore_case: bool = False,
        count: int = 1,
    ) -> int | None:
        """
        Find `text` after the cursor, return position relative to the cursor
        position. Return `None` if nothing was found.

        :param count: Find the n-th occurrence.
        """
        assert isinstance(ignore_case, bool)

        if in_current_line:
            text = self.current_line_after_cursor
        else:
            text = self.text_after_cursor

        if not include_current_position:
            if len(text) == 0:
                return None  # (Otherwise, we always get a match for the empty string.)
            else:
                text = text[1:]

        flags = re.IGNORECASE if ignore_case else 0
        iterator = re.finditer(re.escape(sub), text, flags)

        try:
            for i, match in enumerate(iterator):
                if i + 1 == count:
                    if include_current_position:
                        return match.start(0)
                    else:
                        return match.start(0) + 1
        except StopIteration:
            pass
        return None

    def find_all(self, sub: str, ignore_case: bool = False) -> list[int]:
        """
        Find all occurrences of the substring. Return a list of absolute
        positions in the document.
        """
        flags = re.IGNORECASE if ignore_case else 0
        return [a.start() for a in re.finditer(re.escape(sub), self.text, flags)]

    def find_backwards(
        self,
        sub: str,
        in_current_line: bool = False,
        ignore_case: bool = False,
        count: int = 1,
    ) -> int | None:
        """
        Find `text` before the cursor, return position relative to the cursor
        position. Return `None` if nothing was found.

        :param count: Find the n-th occurrence.
        """
        if in_current_line:
            before_cursor = self.current_line_before_cursor[::-1]
        else:
            before_cursor = self.text_before_cursor[::-1]

        flags = re.IGNORECASE if ignore_case else 0
        iterator = re.finditer(re.escape(sub[::-1]), before_cursor, flags)

        try:
            for i, match in enumerate(iterator):
                if i + 1 == count:
                    return -match.start(0) - len(sub)
        except StopIteration:
            pass
        return None

    def get_word_before_cursor(
        self, WORD: bool = False, pattern: Pattern[str] | None = None
    ) -> str:
        """
        Give the word before the cursor.
        If we have whitespace before the cursor this returns an empty string.

        :param pattern: (None or compiled regex). When given, use this regex
            pattern.
        """
        if self._is_word_before_cursor_complete(WORD=WORD, pattern=pattern):
            # Space before the cursor or no text before cursor.
            return ""

        text_before_cursor = self.text_before_cursor
        start = self.find_start_of_previous_word(WORD=WORD, pattern=pattern) or 0

        return text_before_cursor[len(text_before_cursor) + start :]

    def _is_word_before_cursor_complete(
        self, WORD: bool = False, pattern: Pattern[str] | None = None
    ) -> bool:
        if pattern:
            return self.find_start_of_previous_word(WORD=WORD, pattern=pattern) is None
        else:
            return (
                self.text_before_cursor == "" or self.text_before_cursor[-1:].isspace()
            )

    def find_start_of_previous_word(
        self, count: int = 1, WORD: bool = False, pattern: Pattern[str] | None = None
    ) -> int | None:
        """
        Return an index relative to the cursor position pointing to the start
        of the previous word. Return `None` if nothing was found.

        :param pattern: (None or compiled regex). When given, use this regex
            pattern.
        """
        assert not (WORD and pattern)

        # Reverse the text before the cursor, in order to do an efficient
        # backwards search.
        text_before_cursor = self.text_before_cursor[::-1]

        if pattern:
            regex = pattern
        elif WORD:
            regex = _FIND_BIG_WORD_RE
        else:
            regex = _FIND_WORD_RE

        iterator = regex.finditer(text_before_cursor)

        try:
            for i, match in enumerate(iterator):
                if i + 1 == count:
                    return -match.end(0)
        except StopIteration:
            pass
        return None

    def find_boundaries_of_current_word(
        self,
        WORD: bool = False,
        include_leading_whitespace: bool = False,
        include_trailing_whitespace: bool = False,
    ) -> tuple[int, int]:
        """
        Return the relative boundaries (startpos, endpos) of the current word under the
        cursor. (This is at the current line, because line boundaries obviously
        don't belong to any word.)
        If not on a word, this returns (0,0)
        """
        text_before_cursor = self.current_line_before_cursor[::-1]
        text_after_cursor = self.current_line_after_cursor

        def get_regex(include_whitespace: bool) -> Pattern[str]:
            return {
                (False, False): _FIND_CURRENT_WORD_RE,
                (False, True): _FIND_CURRENT_WORD_INCLUDE_TRAILING_WHITESPACE_RE,
                (True, False): _FIND_CURRENT_BIG_WORD_RE,
                (True, True): _FIND_CURRENT_BIG_WORD_INCLUDE_TRAILING_WHITESPACE_RE,
            }[(WORD, include_whitespace)]

        match_before = get_regex(include_leading_whitespace).search(text_before_cursor)
        match_after = get_regex(include_trailing_whitespace).search(text_after_cursor)

        # When there is a match before and after, and we're not looking for
        # WORDs, make sure that both the part before and after the cursor are
        # either in the [a-zA-Z_] alphabet or not. Otherwise, drop the part
        # before the cursor.
        if not WORD and match_before and match_after:
            c1 = self.text[self.cursor_position - 1]
            c2 = self.text[self.cursor_position]
            alphabet = string.ascii_letters + "0123456789_"

            if (c1 in alphabet) != (c2 in alphabet):
                match_before = None

        return (
            -match_before.end(1) if match_before else 0,
            match_after.end(1) if match_after else 0,
        )

    def get_word_under_cursor(self, WORD: bool = False) -> str:
        """
        Return the word, currently below the cursor.
        This returns an empty string when the cursor is on a whitespace region.
        """
        start, end = self.find_boundaries_of_current_word(WORD=WORD)
        return self.text[self.cursor_position + start : self.cursor_position + end]

    def find_next_word_beginning(
        self, count: int = 1, WORD: bool = False
    ) -> int | None:
        """
        Return an index relative to the cursor position pointing to the start
        of the next word. Return `None` if nothing was found.
        """
        if count < 0:
            return self.find_previous_word_beginning(count=-count, WORD=WORD)

        regex = _FIND_BIG_WORD_RE if WORD else _FIND_WORD_RE
        iterator = regex.finditer(self.text_after_cursor)

        try:
            for i, match in enumerate(iterator):
                # Take first match, unless it's the word on which we're right now.
                if i == 0 and match.start(1) == 0:
                    count += 1

                if i + 1 == count:
                    return match.start(1)
        except StopIteration:
            pass
        return None

    def find_next_word_ending(
        self, include_current_position: bool = False, count: int = 1, WORD: bool = False
    ) -> int | None:
        """
        Return an index relative to the cursor position pointing to the end
        of the next word. Return `None` if nothing was found.
        """
        if count < 0:
            return self.find_previous_word_ending(count=-count, WORD=WORD)

        if include_current_position:
            text = self.text_after_cursor
        else:
            text = self.text_after_cursor[1:]

        regex = _FIND_BIG_WORD_RE if WORD else _FIND_WORD_RE
        iterable = regex.finditer(text)

        try:
            for i, match in enumerate(iterable):
                if i + 1 == count:
                    value = match.end(1)

                    if include_current_position:
                        return value
                    else:
                        return value + 1

        except StopIteration:
            pass
        return None

    def find_previous_word_beginning(
        self, count: int = 1, WORD: bool = False
    ) -> int | None:
        """
        Return an index relative to the cursor position pointing to the start
        of the previous word. Return `None` if nothing was found.
        """
        if count < 0:
            return self.find_next_word_beginning(count=-count, WORD=WORD)

        regex = _FIND_BIG_WORD_RE if WORD else _FIND_WORD_RE
        iterator = regex.finditer(self.text_before_cursor[::-1])

        try:
            for i, match in enumerate(iterator):
                if i + 1 == count:
                    return -match.end(1)
        except StopIteration:
            pass
        return None

    def find_previous_word_ending(
        self, count: int = 1, WORD: bool = False
    ) -> int | None:
        """
        Return an index relative to the cursor position pointing to the end
        of the previous word. Return `None` if nothing was found.
        """
        if count < 0:
            return self.find_next_word_ending(count=-count, WORD=WORD)

        text_before_cursor = self.text_after_cursor[:1] + self.text_before_cursor[::-1]

        regex = _FIND_BIG_WORD_RE if WORD else _FIND_WORD_RE
        iterator = regex.finditer(text_before_cursor)

        try:
            for i, match in enumerate(iterator):
                # Take first match, unless it's the word on which we're right now.
                if i == 0 and match.start(1) == 0:
                    count += 1

                if i + 1 == count:
                    return -match.start(1) + 1
        except StopIteration:
            pass
        return None

    def find_next_matching_line(
        self, match_func: Callable[[str], bool], count: int = 1
    ) -> int | None:
        """
        Look downwards for empty lines.
        Return the line index, relative to the current line.
        """
        result = None

        for index, line in enumerate(self.lines[self.cursor_position_row + 1 :]):
            if match_func(line):
                result = 1 + index
                count -= 1

            if count == 0:
                break

        return result

    def find_previous_matching_line(
        self, match_func: Callable[[str], bool], count: int = 1
    ) -> int | None:
        """
        Look upwards for empty lines.
        Return the line index, relative to the current line.
        """
        result = None

        for index, line in enumerate(self.lines[: self.cursor_position_row][::-1]):
            if match_func(line):
                result = -1 - index
                count -= 1

            if count == 0:
                break

        return result

    def get_cursor_left_position(self, count: int = 1) -> int:
        """
        Relative position for cursor left.
        """
        if count < 0:
            return self.get_cursor_right_position(-count)

        return -min(self.cursor_position_col, count)

    def get_cursor_right_position(self, count: int = 1) -> int:
        """
        Relative position for cursor_right.
        """
        if count < 0:
            return self.get_cursor_left_position(-count)

        return min(count, len(self.current_line_after_cursor))

    def get_cursor_up_position(
        self, count: int = 1, preferred_column: int | None = None
    ) -> int:
        """
        Return the relative cursor position (character index) where we would be if the
        user pressed the arrow-up button.

        :param preferred_column: When given, go to this column instead of
                                 staying at the current column.
        """
        assert count >= 1
        column = (
            self.cursor_position_col if preferred_column is None else preferred_column
        )

        return (
            self.translate_row_col_to_index(
                max(0, self.cursor_position_row - count), column
            )
            - self.cursor_position
        )

    def get_cursor_down_position(
        self, count: int = 1, preferred_column: int | None = None
    ) -> int:
        """
        Return the relative cursor position (character index) where we would be if the
        user pressed the arrow-down button.

        :param preferred_column: When given, go to this column instead of
                                 staying at the current column.
        """
        assert count >= 1
        column = (
            self.cursor_position_col if preferred_column is None else preferred_column
        )

        return (
            self.translate_row_col_to_index(self.cursor_position_row + count, column)
            - self.cursor_position
        )

    def find_enclosing_bracket_right(
        self, left_ch: str, right_ch: str, end_pos: int | None = None
    ) -> int | None:
        """
        Find the right bracket enclosing current position. Return the relative
        position to the cursor position.

        When `end_pos` is given, don't look past the position.
        """
        if self.current_char == right_ch:
            return 0

        if end_pos is None:
            end_pos = len(self.text)
        else:
            end_pos = min(len(self.text), end_pos)

        stack = 1

        # Look forward.
        for i in range(self.cursor_position + 1, end_pos):
            c = self.text[i]

            if c == left_ch:
                stack += 1
            elif c == right_ch:
                stack -= 1

            if stack == 0:
                return i - self.cursor_position

        return None

    def find_enclosing_bracket_left(
        self, left_ch: str, right_ch: str, start_pos: int | None = None
    ) -> int | None:
        """
        Find the left bracket enclosing current position. Return the relative
        position to the cursor position.

        When `start_pos` is given, don't look past the position.
        """
        if self.current_char == left_ch:
            return 0

        if start_pos is None:
            start_pos = 0
        else:
            start_pos = max(0, start_pos)

        stack = 1

        # Look backward.
        for i in range(self.cursor_position - 1, start_pos - 1, -1):
            c = self.text[i]

            if c == right_ch:
                stack += 1
            elif c == left_ch:
                stack -= 1

            if stack == 0:
                return i - self.cursor_position

        return None

    def find_matching_bracket_position(
        self, start_pos: int | None = None, end_pos: int | None = None
    ) -> int:
        """
        Return relative cursor position of matching [, (, { or < bracket.

        When `start_pos` or `end_pos` are given. Don't look past the positions.
        """

        # Look for a match.
        for pair in "()", "[]", "{}", "<>":
            A = pair[0]
            B = pair[1]
            if self.current_char == A:
                return self.find_enclosing_bracket_right(A, B, end_pos=end_pos) or 0
            elif self.current_char == B:
                return self.find_enclosing_bracket_left(A, B, start_pos=start_pos) or 0

        return 0

    def get_start_of_document_position(self) -> int:
        """Relative position for the start of the document."""
        return -self.cursor_position

    def get_end_of_document_position(self) -> int:
        """Relative position for the end of the document."""
        return len(self.text) - self.cursor_position

    def get_start_of_line_position(self, after_whitespace: bool = False) -> int:
        """Relative position for the start of this line."""
        if after_whitespace:
            current_line = self.current_line
            return (
                len(current_line)
                - len(current_line.lstrip())
                - self.cursor_position_col
            )
        else:
            return -len(self.current_line_before_cursor)

    def get_end_of_line_position(self) -> int:
        """Relative position for the end of this line."""
        return len(self.current_line_after_cursor)

    def last_non_blank_of_current_line_position(self) -> int:
        """
        Relative position for the last non blank character of this line.
        """
        return len(self.current_line.rstrip()) - self.cursor_position_col - 1

    def get_column_cursor_position(self, column: int) -> int:
        """
        Return the relative cursor position for this column at the current
        line. (It will stay between the boundaries of the line in case of a
        larger number.)
        """
        line_length = len(self.current_line)
        current_column = self.cursor_position_col
        column = max(0, min(line_length, column))

        return column - current_column

    def selection_range(
        self,
    ) -> tuple[
        int, int
    ]:  # XXX: shouldn't this return `None` if there is no selection???
        """
        Return (from, to) tuple of the selection.
        start and end position are included.

        This doesn't take the selection type into account. Use
        `selection_ranges` instead.
        """
        if self.selection:
            from_, to = sorted(
                [self.cursor_position, self.selection.original_cursor_position]
            )
        else:
            from_, to = self.cursor_position, self.cursor_position

        return from_, to

    def selection_ranges(self) -> Iterable[tuple[int, int]]:
        """
        Return a list of `(from, to)` tuples for the selection or none if
        nothing was selected. The upper boundary is not included.

        This will yield several (from, to) tuples in case of a BLOCK selection.
        This will return zero ranges, like (8,8) for empty lines in a block
        selection.
        """
        if self.selection:
            from_, to = sorted(
                [self.cursor_position, self.selection.original_cursor_position]
            )

            if self.selection.type == SelectionType.BLOCK:
                from_line, from_column = self.translate_index_to_position(from_)
                to_line, to_column = self.translate_index_to_position(to)
                from_column, to_column = sorted([from_column, to_column])
                lines = self.lines

                if vi_mode():
                    to_column += 1

                for l in range(from_line, to_line + 1):
                    line_length = len(lines[l])

                    if from_column <= line_length:
                        yield (
                            self.translate_row_col_to_index(l, from_column),
                            self.translate_row_col_to_index(
                                l, min(line_length, to_column)
                            ),
                        )
            else:
                # In case of a LINES selection, go to the start/end of the lines.
                if self.selection.type == SelectionType.LINES:
                    from_ = max(0, self.text.rfind("\n", 0, from_) + 1)

                    if self.text.find("\n", to) >= 0:
                        to = self.text.find("\n", to)
                    else:
                        to = len(self.text) - 1

                # In Vi mode, the upper boundary is always included. For Emacs,
                # that's not the case.
                if vi_mode():
                    to += 1

                yield from_, to

    def selection_range_at_line(self, row: int) -> tuple[int, int] | None:
        """
        If the selection spans a portion of the given line, return a (from, to) tuple.

        The returned upper boundary is not included in the selection, so
        `(0, 0)` is an empty selection.  `(0, 1)`, is a one character selection.

        Returns None if the selection doesn't cover this line at all.
        """
        if self.selection:
            line = self.lines[row]

            row_start = self.translate_row_col_to_index(row, 0)
            row_end = self.translate_row_col_to_index(row, len(line))

            from_, to = sorted(
                [self.cursor_position, self.selection.original_cursor_position]
            )

            # Take the intersection of the current line and the selection.
            intersection_start = max(row_start, from_)
            intersection_end = min(row_end, to)

            if intersection_start <= intersection_end:
                if self.selection.type == SelectionType.LINES:
                    intersection_start = row_start
                    intersection_end = row_end

                elif self.selection.type == SelectionType.BLOCK:
                    _, col1 = self.translate_index_to_position(from_)
                    _, col2 = self.translate_index_to_position(to)
                    col1, col2 = sorted([col1, col2])

                    if col1 > len(line):
                        return None  # Block selection doesn't cross this line.

                    intersection_start = self.translate_row_col_to_index(row, col1)
                    intersection_end = self.translate_row_col_to_index(row, col2)

                _, from_column = self.translate_index_to_position(intersection_start)
                _, to_column = self.translate_index_to_position(intersection_end)

                # In Vi mode, the upper boundary is always included. For Emacs
                # mode, that's not the case.
                if vi_mode():
                    to_column += 1

                return from_column, to_column
        return None

    def cut_selection(self) -> tuple[Document, ClipboardData]:
        """
        Return a (:class:`.Document`, :class:`.ClipboardData`) tuple, where the
        document represents the new document when the selection is cut, and the
        clipboard data, represents whatever has to be put on the clipboard.
        """
        if self.selection:
            cut_parts = []
            remaining_parts = []
            new_cursor_position = self.cursor_position

            last_to = 0
            for from_, to in self.selection_ranges():
                if last_to == 0:
                    new_cursor_position = from_

                remaining_parts.append(self.text[last_to:from_])
                cut_parts.append(self.text[from_:to])
                last_to = to

            remaining_parts.append(self.text[last_to:])

            cut_text = "\n".join(cut_parts)
            remaining_text = "".join(remaining_parts)

            # In case of a LINES selection, don't include the trailing newline.
            if self.selection.type == SelectionType.LINES and cut_text.endswith("\n"):
                cut_text = cut_text[:-1]

            return (
                Document(text=remaining_text, cursor_position=new_cursor_position),
                ClipboardData(cut_text, self.selection.type),
            )
        else:
            return self, ClipboardData("")

    def paste_clipboard_data(
        self,
        data: ClipboardData,
        paste_mode: PasteMode = PasteMode.EMACS,
        count: int = 1,
    ) -> Document:
        """
        Return a new :class:`.Document` instance which contains the result if
        we would paste this data at the current cursor position.

        :param paste_mode: Where to paste. (Before/after/emacs.)
        :param count: When >1, Paste multiple times.
        """
        before = paste_mode == PasteMode.VI_BEFORE
        after = paste_mode == PasteMode.VI_AFTER

        if data.type == SelectionType.CHARACTERS:
            if after:
                new_text = (
                    self.text[: self.cursor_position + 1]
                    + data.text * count
                    + self.text[self.cursor_position + 1 :]
                )
            else:
                new_text = (
                    self.text_before_cursor + data.text * count + self.text_after_cursor
                )

            new_cursor_position = self.cursor_position + len(data.text) * count
            if before:
                new_cursor_position -= 1

        elif data.type == SelectionType.LINES:
            l = self.cursor_position_row
            if before:
                lines = self.lines[:l] + [data.text] * count + self.lines[l:]
                new_text = "\n".join(lines)
                new_cursor_position = len("".join(self.lines[:l])) + l
            else:
                lines = self.lines[: l + 1] + [data.text] * count + self.lines[l + 1 :]
                new_cursor_position = len("".join(self.lines[: l + 1])) + l + 1
                new_text = "\n".join(lines)

        elif data.type == SelectionType.BLOCK:
            lines = self.lines[:]
            start_line = self.cursor_position_row
            start_column = self.cursor_position_col + (0 if before else 1)

            for i, line in enumerate(data.text.split("\n")):
                index = i + start_line
                if index >= len(lines):
                    lines.append("")

                lines[index] = lines[index].ljust(start_column)
                lines[index] = (
                    lines[index][:start_column]
                    + line * count
                    + lines[index][start_column:]
                )

            new_text = "\n".join(lines)
            new_cursor_position = self.cursor_position + (0 if before else 1)

        return Document(text=new_text, cursor_position=new_cursor_position)

    def empty_line_count_at_the_end(self) -> int:
        """
        Return number of empty lines at the end of the document.
        """
        count = 0
        for line in self.lines[::-1]:
            if not line or line.isspace():
                count += 1
            else:
                break

        return count

    def start_of_paragraph(self, count: int = 1, before: bool = False) -> int:
        """
        Return the start of the current paragraph. (Relative cursor position.)
        """

        def match_func(text: str) -> bool:
            return not text or text.isspace()

        line_index = self.find_previous_matching_line(
            match_func=match_func, count=count
        )

        if line_index:
            add = 0 if before else 1
            return min(0, self.get_cursor_up_position(count=-line_index) + add)
        else:
            return -self.cursor_position

    def end_of_paragraph(self, count: int = 1, after: bool = False) -> int:
        """
        Return the end of the current paragraph. (Relative cursor position.)
        """

        def match_func(text: str) -> bool:
            return not text or text.isspace()

        line_index = self.find_next_matching_line(match_func=match_func, count=count)

        if line_index:
            add = 0 if after else 1
            return max(0, self.get_cursor_down_position(count=line_index) - add)
        else:
            return len(self.text_after_cursor)

    # Modifiers.

    def insert_after(self, text: str) -> Document:
        """
        Create a new document, with this text inserted after the buffer.
        It keeps selection ranges and cursor position in sync.
        """
        return Document(
            text=self.text + text,
            cursor_position=self.cursor_position,
            selection=self.selection,
        )

    def insert_before(self, text: str) -> Document:
        """
        Create a new document, with this text inserted before the buffer.
        It keeps selection ranges and cursor position in sync.
        """
        selection_state = self.selection

        if selection_state:
            selection_state = SelectionState(
                original_cursor_position=selection_state.original_cursor_position
                + len(text),
                type=selection_state.type,
            )

        return Document(
            text=text + self.text,
            cursor_position=self.cursor_position + len(text),
            selection=selection_state,
        )
