"""
Data structures for the Buffer.
It holds the text, cursor position, history, etc...
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shlex
import shutil
import subprocess
import tempfile
from collections import deque
from enum import Enum
from functools import wraps
from typing import Any, Callable, Coroutine, Iterable, TypeVar, cast

from .application.current import get_app
from .application.run_in_terminal import run_in_terminal
from .auto_suggest import AutoSuggest, Suggestion
from .cache import FastDictCache
from .clipboard import ClipboardData
from .completion import (
    CompleteEvent,
    Completer,
    Completion,
    DummyCompleter,
    get_common_complete_suffix,
)
from .document import Document
from .eventloop import aclosing
from .filters import FilterOrBool, to_filter
from .history import History, InMemoryHistory
from .search import SearchDirection, SearchState
from .selection import PasteMode, SelectionState, SelectionType
from .utils import Event, to_str
from .validation import ValidationError, Validator

__all__ = [
    "EditReadOnlyBuffer",
    "Buffer",
    "CompletionState",
    "indent",
    "unindent",
    "reshape_text",
]

logger = logging.getLogger(__name__)


class EditReadOnlyBuffer(Exception):
    "Attempt editing of read-only :class:`.Buffer`."


class ValidationState(Enum):
    "The validation state of a buffer. This is set after the validation."

    VALID = "VALID"
    INVALID = "INVALID"
    UNKNOWN = "UNKNOWN"


class CompletionState:
    """
    Immutable class that contains a completion state.
    """

    def __init__(
        self,
        original_document: Document,
        completions: list[Completion] | None = None,
        complete_index: int | None = None,
    ) -> None:
        #: Document as it was when the completion started.
        self.original_document = original_document

        #: List of all the current Completion instances which are possible at
        #: this point.
        self.completions = completions or []

        #: Position in the `completions` array.
        #: This can be `None` to indicate "no completion", the original text.
        self.complete_index = complete_index  # Position in the `_completions` array.

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.original_document!r}, <{len(self.completions)!r}> completions, index={self.complete_index!r})"

    def go_to_index(self, index: int | None) -> None:
        """
        Create a new :class:`.CompletionState` object with the new index.

        When `index` is `None` deselect the completion.
        """
        if self.completions:
            assert index is None or 0 <= index < len(self.completions)
            self.complete_index = index

    def new_text_and_position(self) -> tuple[str, int]:
        """
        Return (new_text, new_cursor_position) for this completion.
        """
        if self.complete_index is None:
            return self.original_document.text, self.original_document.cursor_position
        else:
            original_text_before_cursor = self.original_document.text_before_cursor
            original_text_after_cursor = self.original_document.text_after_cursor

            c = self.completions[self.complete_index]
            if c.start_position == 0:
                before = original_text_before_cursor
            else:
                before = original_text_before_cursor[: c.start_position]

            new_text = before + c.text + original_text_after_cursor
            new_cursor_position = len(before) + len(c.text)
            return new_text, new_cursor_position

    @property
    def current_completion(self) -> Completion | None:
        """
        Return the current completion, or return `None` when no completion is
        selected.
        """
        if self.complete_index is not None:
            return self.completions[self.complete_index]
        return None


_QUOTED_WORDS_RE = re.compile(r"""(\s+|".*?"|'.*?')""")


class YankNthArgState:
    """
    For yank-last-arg/yank-nth-arg: Keep track of where we are in the history.
    """

    def __init__(
        self, history_position: int = 0, n: int = -1, previous_inserted_word: str = ""
    ) -> None:
        self.history_position = history_position
        self.previous_inserted_word = previous_inserted_word
        self.n = n

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(history_position={self.history_position!r}, n={self.n!r}, previous_inserted_word={self.previous_inserted_word!r})"


BufferEventHandler = Callable[["Buffer"], None]
BufferAcceptHandler = Callable[["Buffer"], bool]


class Buffer:
    """
    The core data structure that holds the text and cursor position of the
    current input line and implements all text manipulations on top of it. It
    also implements the history, undo stack and the completion state.

    :param completer: :class:`~prompt_toolkit.completion.Completer` instance.
    :param history: :class:`~prompt_toolkit.history.History` instance.
    :param tempfile_suffix: The tempfile suffix (extension) to be used for the
        "open in editor" function. For a Python REPL, this would be ".py", so
        that the editor knows the syntax highlighting to use. This can also be
        a callable that returns a string.
    :param tempfile: For more advanced tempfile situations where you need
        control over the subdirectories and filename. For a Git Commit Message,
        this would be ".git/COMMIT_EDITMSG", so that the editor knows the syntax
        highlighting to use. This can also be a callable that returns a string.
    :param name: Name for this buffer. E.g. DEFAULT_BUFFER. This is mostly
        useful for key bindings where we sometimes prefer to refer to a buffer
        by their name instead of by reference.
    :param accept_handler: Called when the buffer input is accepted. (Usually
        when the user presses `enter`.) The accept handler receives this
        `Buffer` as input and should return True when the buffer text should be
        kept instead of calling reset.

        In case of a `PromptSession` for instance, we want to keep the text,
        because we will exit the application, and only reset it during the next
        run.
    :param max_number_of_completions: Never display more than this number of
        completions, even when the completer can produce more (limited by
        default to 10k for performance).

    Events:

    :param on_text_changed: When the buffer text changes. (Callable or None.)
    :param on_text_insert: When new text is inserted. (Callable or None.)
    :param on_cursor_position_changed: When the cursor moves. (Callable or None.)
    :param on_completions_changed: When the completions were changed. (Callable or None.)
    :param on_suggestion_set: When an auto-suggestion text has been set. (Callable or None.)

    Filters:

    :param complete_while_typing: :class:`~prompt_toolkit.filters.Filter`
        or `bool`. Decide whether or not to do asynchronous autocompleting while
        typing.
    :param validate_while_typing: :class:`~prompt_toolkit.filters.Filter`
        or `bool`. Decide whether or not to do asynchronous validation while
        typing.
    :param enable_history_search: :class:`~prompt_toolkit.filters.Filter` or
        `bool` to indicate when up-arrow partial string matching is enabled. It
        is advised to not enable this at the same time as
        `complete_while_typing`, because when there is an autocompletion found,
        the up arrows usually browse through the completions, rather than
        through the history.
    :param read_only: :class:`~prompt_toolkit.filters.Filter`. When True,
        changes will not be allowed.
    :param multiline: :class:`~prompt_toolkit.filters.Filter` or `bool`. When
        not set, pressing `Enter` will call the `accept_handler`.  Otherwise,
        pressing `Esc-Enter` is required.
    """

    def __init__(
        self,
        completer: Completer | None = None,
        auto_suggest: AutoSuggest | None = None,
        history: History | None = None,
        validator: Validator | None = None,
        tempfile_suffix: str | Callable[[], str] = "",
        tempfile: str | Callable[[], str] = "",
        name: str = "",
        complete_while_typing: FilterOrBool = False,
        validate_while_typing: FilterOrBool = False,
        enable_history_search: FilterOrBool = False,
        document: Document | None = None,
        accept_handler: BufferAcceptHandler | None = None,
        read_only: FilterOrBool = False,
        multiline: FilterOrBool = True,
        max_number_of_completions: int = 10000,
        on_text_changed: BufferEventHandler | None = None,
        on_text_insert: BufferEventHandler | None = None,
        on_cursor_position_changed: BufferEventHandler | None = None,
        on_completions_changed: BufferEventHandler | None = None,
        on_suggestion_set: BufferEventHandler | None = None,
    ) -> None:
        # Accept both filters and booleans as input.
        enable_history_search = to_filter(enable_history_search)
        complete_while_typing = to_filter(complete_while_typing)
        validate_while_typing = to_filter(validate_while_typing)
        read_only = to_filter(read_only)
        multiline = to_filter(multiline)

        self.completer = completer or DummyCompleter()
        self.auto_suggest = auto_suggest
        self.validator = validator
        self.tempfile_suffix = tempfile_suffix
        self.tempfile = tempfile
        self.name = name
        self.accept_handler = accept_handler

        # Filters. (Usually, used by the key bindings to drive the buffer.)
        self.complete_while_typing = complete_while_typing
        self.validate_while_typing = validate_while_typing
        self.enable_history_search = enable_history_search
        self.read_only = read_only
        self.multiline = multiline
        self.max_number_of_completions = max_number_of_completions

        # Text width. (For wrapping, used by the Vi 'gq' operator.)
        self.text_width = 0

        #: The command buffer history.
        # Note that we shouldn't use a lazy 'or' here. bool(history) could be
        # False when empty.
        self.history = InMemoryHistory() if history is None else history

        self.__cursor_position = 0

        # Events
        self.on_text_changed: Event[Buffer] = Event(self, on_text_changed)
        self.on_text_insert: Event[Buffer] = Event(self, on_text_insert)
        self.on_cursor_position_changed: Event[Buffer] = Event(
            self, on_cursor_position_changed
        )
        self.on_completions_changed: Event[Buffer] = Event(self, on_completions_changed)
        self.on_suggestion_set: Event[Buffer] = Event(self, on_suggestion_set)

        # Document cache. (Avoid creating new Document instances.)
        self._document_cache: FastDictCache[
            tuple[str, int, SelectionState | None], Document
        ] = FastDictCache(Document, size=10)

        # Create completer / auto suggestion / validation coroutines.
        self._async_suggester = self._create_auto_suggest_coroutine()
        self._async_completer = self._create_completer_coroutine()
        self._async_validator = self._create_auto_validate_coroutine()

        # Asyncio task for populating the history.
        self._load_history_task: asyncio.Future[None] | None = None

        # Reset other attributes.
        self.reset(document=document)

    def __repr__(self) -> str:
        if len(self.text) < 15:
            text = self.text
        else:
            text = self.text[:12] + "..."

        return f"<Buffer(name={self.name!r}, text={text!r}) at {id(self)!r}>"

    def reset(
        self, document: Document | None = None, append_to_history: bool = False
    ) -> None:
        """
        :param append_to_history: Append current input to history first.
        """
        if append_to_history:
            self.append_to_history()

        document = document or Document()

        self.__cursor_position = document.cursor_position

        # `ValidationError` instance. (Will be set when the input is wrong.)
        self.validation_error: ValidationError | None = None
        self.validation_state: ValidationState | None = ValidationState.UNKNOWN

        # State of the selection.
        self.selection_state: SelectionState | None = None

        # Multiple cursor mode. (When we press 'I' or 'A' in visual-block mode,
        # we can insert text on multiple lines at once. This is implemented by
        # using multiple cursors.)
        self.multiple_cursor_positions: list[int] = []

        # When doing consecutive up/down movements, prefer to stay at this column.
        self.preferred_column: int | None = None

        # State of complete browser
        # For interactive completion through Ctrl-N/Ctrl-P.
        self.complete_state: CompletionState | None = None

        # State of Emacs yank-nth-arg completion.
        self.yank_nth_arg_state: YankNthArgState | None = None  # for yank-nth-arg.

        # Remember the document that we had *right before* the last paste
        # operation. This is used for rotating through the kill ring.
        self.document_before_paste: Document | None = None

        # Current suggestion.
        self.suggestion: Suggestion | None = None

        # The history search text. (Used for filtering the history when we
        # browse through it.)
        self.history_search_text: str | None = None

        # Undo/redo stacks (stack of `(text, cursor_position)`).
        self._undo_stack: list[tuple[str, int]] = []
        self._redo_stack: list[tuple[str, int]] = []

        # Cancel history loader. If history loading was still ongoing.
        # Cancel the `_load_history_task`, so that next repaint of the
        # `BufferControl` we will repopulate it.
        if self._load_history_task is not None:
            self._load_history_task.cancel()
        self._load_history_task = None

        #: The working lines. Similar to history, except that this can be
        #: modified. The user can press arrow_up and edit previous entries.
        #: Ctrl-C should reset this, and copy the whole history back in here.
        #: Enter should process the current command and append to the real
        #: history.
        self._working_lines: deque[str] = deque([document.text])
        self.__working_index = 0

    def load_history_if_not_yet_loaded(self) -> None:
        """
        Create task for populating the buffer history (if not yet done).

        Note::

            This needs to be called from within the event loop of the
            application, because history loading is async, and we need to be
            sure the right event loop is active. Therefor, we call this method
            in the `BufferControl.create_content`.

            There are situations where prompt_toolkit applications are created
            in one thread, but will later run in a different thread (Ptpython
            is one example. The REPL runs in a separate thread, in order to
            prevent interfering with a potential different event loop in the
            main thread. The REPL UI however is still created in the main
            thread.) We could decide to not support creating prompt_toolkit
            objects in one thread and running the application in a different
            thread, but history loading is the only place where it matters, and
            this solves it.
        """
        if self._load_history_task is None:

            async def load_history() -> None:
                async for item in self.history.load():
                    self._working_lines.appendleft(item)
                    self.__working_index += 1

            self._load_history_task = get_app().create_background_task(load_history())

            def load_history_done(f: asyncio.Future[None]) -> None:
                """
                Handle `load_history` result when either done, cancelled, or
                when an exception was raised.
                """
                try:
                    f.result()
                except asyncio.CancelledError:
                    # Ignore cancellation. But handle it, so that we don't get
                    # this traceback.
                    pass
                except GeneratorExit:
                    # Probably not needed, but we had situations where
                    # `GeneratorExit` was raised in `load_history` during
                    # cancellation.
                    pass
                except BaseException:
                    # Log error if something goes wrong. (We don't have a
                    # caller to which we can propagate this exception.)
                    logger.exception("Loading history failed")

            self._load_history_task.add_done_callback(load_history_done)

    # <getters/setters>

    def _set_text(self, value: str) -> bool:
        """set text at current working_index. Return whether it changed."""
        working_index = self.working_index
        working_lines = self._working_lines

        original_value = working_lines[working_index]
        working_lines[working_index] = value

        # Return True when this text has been changed.
        if len(value) != len(original_value):
            # For Python 2, it seems that when two strings have a different
            # length and one is a prefix of the other, Python still scans
            # character by character to see whether the strings are different.
            # (Some benchmarking showed significant differences for big
            # documents. >100,000 of lines.)
            return True
        elif value != original_value:
            return True
        return False

    def _set_cursor_position(self, value: int) -> bool:
        """Set cursor position. Return whether it changed."""
        original_position = self.__cursor_position
        self.__cursor_position = max(0, value)

        return self.__cursor_position != original_position

    @property
    def text(self) -> str:
        return self._working_lines[self.working_index]

    @text.setter
    def text(self, value: str) -> None:
        """
        Setting text. (When doing this, make sure that the cursor_position is
        valid for this text. text/cursor_position should be consistent at any time,
        otherwise set a Document instead.)
        """
        # Ensure cursor position remains within the size of the text.
        if self.cursor_position > len(value):
            self.cursor_position = len(value)

        # Don't allow editing of read-only buffers.
        if self.read_only():
            raise EditReadOnlyBuffer()

        changed = self._set_text(value)

        if changed:
            self._text_changed()

            # Reset history search text.
            # (Note that this doesn't need to happen when working_index
            #  changes, which is when we traverse the history. That's why we
            #  don't do this in `self._text_changed`.)
            self.history_search_text = None

    @property
    def cursor_position(self) -> int:
        return self.__cursor_position

    @cursor_position.setter
    def cursor_position(self, value: int) -> None:
        """
        Setting cursor position.
        """
        assert isinstance(value, int)

        # Ensure cursor position is within the size of the text.
        if value > len(self.text):
            value = len(self.text)
        if value < 0:
            value = 0

        changed = self._set_cursor_position(value)

        if changed:
            self._cursor_position_changed()

    @property
    def working_index(self) -> int:
        return self.__working_index

    @working_index.setter
    def working_index(self, value: int) -> None:
        if self.__working_index != value:
            self.__working_index = value
            # Make sure to reset the cursor position, otherwise we end up in
            # situations where the cursor position is out of the bounds of the
            # text.
            self.cursor_position = 0
            self._text_changed()

    def _text_changed(self) -> None:
        # Remove any validation errors and complete state.
        self.validation_error = None
        self.validation_state = ValidationState.UNKNOWN
        self.complete_state = None
        self.yank_nth_arg_state = None
        self.document_before_paste = None
        self.selection_state = None
        self.suggestion = None
        self.preferred_column = None

        # fire 'on_text_changed' event.
        self.on_text_changed.fire()

        # Input validation.
        # (This happens on all change events, unlike auto completion, also when
        # deleting text.)
        if self.validator and self.validate_while_typing():
            get_app().create_background_task(self._async_validator())

    def _cursor_position_changed(self) -> None:
        # Remove any complete state.
        # (Input validation should only be undone when the cursor position
        # changes.)
        self.complete_state = None
        self.yank_nth_arg_state = None
        self.document_before_paste = None

        # Unset preferred_column. (Will be set after the cursor movement, if
        # required.)
        self.preferred_column = None

        # Note that the cursor position can change if we have a selection the
        # new position of the cursor determines the end of the selection.

        # fire 'on_cursor_position_changed' event.
        self.on_cursor_position_changed.fire()

    @property
    def document(self) -> Document:
        """
        Return :class:`~prompt_toolkit.document.Document` instance from the
        current text, cursor position and selection state.
        """
        return self._document_cache[
            self.text, self.cursor_position, self.selection_state
        ]

    @document.setter
    def document(self, value: Document) -> None:
        """
        Set :class:`~prompt_toolkit.document.Document` instance.

        This will set both the text and cursor position at the same time, but
        atomically. (Change events will be triggered only after both have been set.)
        """
        self.set_document(value)

    def set_document(self, value: Document, bypass_readonly: bool = False) -> None:
        """
        Set :class:`~prompt_toolkit.document.Document` instance. Like the
        ``document`` property, but accept an ``bypass_readonly`` argument.

        :param bypass_readonly: When True, don't raise an
                                :class:`.EditReadOnlyBuffer` exception, even
                                when the buffer is read-only.

        .. warning::

            When this buffer is read-only and `bypass_readonly` was not passed,
            the `EditReadOnlyBuffer` exception will be caught by the
            `KeyProcessor` and is silently suppressed. This is important to
            keep in mind when writing key bindings, because it won't do what
            you expect, and there won't be a stack trace. Use try/finally
            around this function if you need some cleanup code.
        """
        # Don't allow editing of read-only buffers.
        if not bypass_readonly and self.read_only():
            raise EditReadOnlyBuffer()

        # Set text and cursor position first.
        text_changed = self._set_text(value.text)
        cursor_position_changed = self._set_cursor_position(value.cursor_position)

        # Now handle change events. (We do this when text/cursor position is
        # both set and consistent.)
        if text_changed:
            self._text_changed()
            self.history_search_text = None

        if cursor_position_changed:
            self._cursor_position_changed()

    @property
    def is_returnable(self) -> bool:
        """
        True when there is something handling accept.
        """
        return bool(self.accept_handler)

    # End of <getters/setters>

    def save_to_undo_stack(self, clear_redo_stack: bool = True) -> None:
        """
        Safe current state (input text and cursor position), so that we can
        restore it by calling undo.
        """
        # Safe if the text is different from the text at the top of the stack
        # is different. If the text is the same, just update the cursor position.
        if self._undo_stack and self._undo_stack[-1][0] == self.text:
            self._undo_stack[-1] = (self._undo_stack[-1][0], self.cursor_position)
        else:
            self._undo_stack.append((self.text, self.cursor_position))

        # Saving anything to the undo stack, clears the redo stack.
        if clear_redo_stack:
            self._redo_stack = []

    def transform_lines(
        self,
        line_index_iterator: Iterable[int],
        transform_callback: Callable[[str], str],
    ) -> str:
        """
        Transforms the text on a range of lines.
        When the iterator yield an index not in the range of lines that the
        document contains, it skips them silently.

        To uppercase some lines::

            new_text = transform_lines(range(5,10), lambda text: text.upper())

        :param line_index_iterator: Iterator of line numbers (int)
        :param transform_callback: callable that takes the original text of a
                                   line, and return the new text for this line.

        :returns: The new text.
        """
        # Split lines
        lines = self.text.split("\n")

        # Apply transformation
        for index in line_index_iterator:
            try:
                lines[index] = transform_callback(lines[index])
            except IndexError:
                pass

        return "\n".join(lines)

    def transform_current_line(self, transform_callback: Callable[[str], str]) -> None:
        """
        Apply the given transformation function to the current line.

        :param transform_callback: callable that takes a string and return a new string.
        """
        document = self.document
        a = document.cursor_position + document.get_start_of_line_position()
        b = document.cursor_position + document.get_end_of_line_position()
        self.text = (
            document.text[:a]
            + transform_callback(document.text[a:b])
            + document.text[b:]
        )

    def transform_region(
        self, from_: int, to: int, transform_callback: Callable[[str], str]
    ) -> None:
        """
        Transform a part of the input string.

        :param from_: (int) start position.
        :param to: (int) end position.
        :param transform_callback: Callable which accepts a string and returns
            the transformed string.
        """
        assert from_ < to

        self.text = "".join(
            [
                self.text[:from_]
                + transform_callback(self.text[from_:to])
                + self.text[to:]
            ]
        )

    def cursor_left(self, count: int = 1) -> None:
        self.cursor_position += self.document.get_cursor_left_position(count=count)

    def cursor_right(self, count: int = 1) -> None:
        self.cursor_position += self.document.get_cursor_right_position(count=count)

    def cursor_up(self, count: int = 1) -> None:
        """(for multiline edit). Move cursor to the previous line."""
        original_column = self.preferred_column or self.document.cursor_position_col
        self.cursor_position += self.document.get_cursor_up_position(
            count=count, preferred_column=original_column
        )

        # Remember the original column for the next up/down movement.
        self.preferred_column = original_column

    def cursor_down(self, count: int = 1) -> None:
        """(for multiline edit). Move cursor to the next line."""
        original_column = self.preferred_column or self.document.cursor_position_col
        self.cursor_position += self.document.get_cursor_down_position(
            count=count, preferred_column=original_column
        )

        # Remember the original column for the next up/down movement.
        self.preferred_column = original_column

    def auto_up(
        self, count: int = 1, go_to_start_of_line_if_history_changes: bool = False
    ) -> None:
        """
        If we're not on the first line (of a multiline input) go a line up,
        otherwise go back in history. (If nothing is selected.)
        """
        if self.complete_state:
            self.complete_previous(count=count)
        elif self.document.cursor_position_row > 0:
            self.cursor_up(count=count)
        elif not self.selection_state:
            self.history_backward(count=count)

            # Go to the start of the line?
            if go_to_start_of_line_if_history_changes:
                self.cursor_position += self.document.get_start_of_line_position()

    def auto_down(
        self, count: int = 1, go_to_start_of_line_if_history_changes: bool = False
    ) -> None:
        """
        If we're not on the last line (of a multiline input) go a line down,
        otherwise go forward in history. (If nothing is selected.)
        """
        if self.complete_state:
            self.complete_next(count=count)
        elif self.document.cursor_position_row < self.document.line_count - 1:
            self.cursor_down(count=count)
        elif not self.selection_state:
            self.history_forward(count=count)

            # Go to the start of the line?
            if go_to_start_of_line_if_history_changes:
                self.cursor_position += self.document.get_start_of_line_position()

    def delete_before_cursor(self, count: int = 1) -> str:
        """
        Delete specified number of characters before cursor and return the
        deleted text.
        """
        assert count >= 0
        deleted = ""

        if self.cursor_position > 0:
            deleted = self.text[self.cursor_position - count : self.cursor_position]

            new_text = (
                self.text[: self.cursor_position - count]
                + self.text[self.cursor_position :]
            )
            new_cursor_position = self.cursor_position - len(deleted)

            # Set new Document atomically.
            self.document = Document(new_text, new_cursor_position)

        return deleted

    def delete(self, count: int = 1) -> str:
        """
        Delete specified number of characters and Return the deleted text.
        """
        if self.cursor_position < len(self.text):
            deleted = self.document.text_after_cursor[:count]
            self.text = (
                self.text[: self.cursor_position]
                + self.text[self.cursor_position + len(deleted) :]
            )
            return deleted
        else:
            return ""

    def join_next_line(self, separator: str = " ") -> None:
        """
        Join the next line to the current one by deleting the line ending after
        the current line.
        """
        if not self.document.on_last_line:
            self.cursor_position += self.document.get_end_of_line_position()
            self.delete()

            # Remove spaces.
            self.text = (
                self.document.text_before_cursor
                + separator
                + self.document.text_after_cursor.lstrip(" ")
            )

    def join_selected_lines(self, separator: str = " ") -> None:
        """
        Join the selected lines.
        """
        assert self.selection_state

        # Get lines.
        from_, to = sorted(
            [self.cursor_position, self.selection_state.original_cursor_position]
        )

        before = self.text[:from_]
        lines = self.text[from_:to].splitlines()
        after = self.text[to:]

        # Replace leading spaces with just one space.
        lines = [l.lstrip(" ") + separator for l in lines]

        # Set new document.
        self.document = Document(
            text=before + "".join(lines) + after,
            cursor_position=len(before + "".join(lines[:-1])) - 1,
        )

    def swap_characters_before_cursor(self) -> None:
        """
        Swap the last two characters before the cursor.
        """
        pos = self.cursor_position

        if pos >= 2:
            a = self.text[pos - 2]
            b = self.text[pos - 1]

            self.text = self.text[: pos - 2] + b + a + self.text[pos:]

    def go_to_history(self, index: int) -> None:
        """
        Go to this item in the history.
        """
        if index < len(self._working_lines):
            self.working_index = index
            self.cursor_position = len(self.text)

    def complete_next(self, count: int = 1, disable_wrap_around: bool = False) -> None:
        """
        Browse to the next completions.
        (Does nothing if there are no completion.)
        """
        index: int | None

        if self.complete_state:
            completions_count = len(self.complete_state.completions)

            if self.complete_state.complete_index is None:
                index = 0
            elif self.complete_state.complete_index == completions_count - 1:
                index = None

                if disable_wrap_around:
                    return
            else:
                index = min(
                    completions_count - 1, self.complete_state.complete_index + count
                )
            self.go_to_completion(index)

    def complete_previous(
        self, count: int = 1, disable_wrap_around: bool = False
    ) -> None:
        """
        Browse to the previous completions.
        (Does nothing if there are no completion.)
        """
        index: int | None

        if self.complete_state:
            if self.complete_state.complete_index == 0:
                index = None

                if disable_wrap_around:
                    return
            elif self.complete_state.complete_index is None:
                index = len(self.complete_state.completions) - 1
            else:
                index = max(0, self.complete_state.complete_index - count)

            self.go_to_completion(index)

    def cancel_completion(self) -> None:
        """
        Cancel completion, go back to the original text.
        """
        if self.complete_state:
            self.go_to_completion(None)
            self.complete_state = None

    def _set_completions(self, completions: list[Completion]) -> CompletionState:
        """
        Start completions. (Generate list of completions and initialize.)

        By default, no completion will be selected.
        """
        self.complete_state = CompletionState(
            original_document=self.document, completions=completions
        )

        # Trigger event. This should eventually invalidate the layout.
        self.on_completions_changed.fire()

        return self.complete_state

    def start_history_lines_completion(self) -> None:
        """
        Start a completion based on all the other lines in the document and the
        history.
        """
        found_completions: set[str] = set()
        completions = []

        # For every line of the whole history, find matches with the current line.
        current_line = self.document.current_line_before_cursor.lstrip()

        for i, string in enumerate(self._working_lines):
            for j, l in enumerate(string.split("\n")):
                l = l.strip()
                if l and l.startswith(current_line):
                    # When a new line has been found.
                    if l not in found_completions:
                        found_completions.add(l)

                        # Create completion.
                        if i == self.working_index:
                            display_meta = "Current, line %s" % (j + 1)
                        else:
                            display_meta = f"History {i + 1}, line {j + 1}"

                        completions.append(
                            Completion(
                                text=l,
                                start_position=-len(current_line),
                                display_meta=display_meta,
                            )
                        )

        self._set_completions(completions=completions[::-1])
        self.go_to_completion(0)

    def go_to_completion(self, index: int | None) -> None:
        """
        Select a completion from the list of current completions.
        """
        assert self.complete_state

        # Set new completion
        state = self.complete_state
        state.go_to_index(index)

        # Set text/cursor position
        new_text, new_cursor_position = state.new_text_and_position()
        self.document = Document(new_text, new_cursor_position)

        # (changing text/cursor position will unset complete_state.)
        self.complete_state = state

    def apply_completion(self, completion: Completion) -> None:
        """
        Insert a given completion.
        """
        # If there was already a completion active, cancel that one.
        if self.complete_state:
            self.go_to_completion(None)
        self.complete_state = None

        # Insert text from the given completion.
        self.delete_before_cursor(-completion.start_position)
        self.insert_text(completion.text)

    def _set_history_search(self) -> None:
        """
        Set `history_search_text`.
        (The text before the cursor will be used for filtering the history.)
        """
        if self.enable_history_search():
            if self.history_search_text is None:
                self.history_search_text = self.document.text_before_cursor
        else:
            self.history_search_text = None

    def _history_matches(self, i: int) -> bool:
        """
        True when the current entry matches the history search.
        (when we don't have history search, it's also True.)
        """
        return self.history_search_text is None or self._working_lines[i].startswith(
            self.history_search_text
        )

    def history_forward(self, count: int = 1) -> None:
        """
        Move forwards through the history.

        :param count: Amount of items to move forward.
        """
        self._set_history_search()

        # Go forward in history.
        found_something = False

        for i in range(self.working_index + 1, len(self._working_lines)):
            if self._history_matches(i):
                self.working_index = i
                count -= 1
                found_something = True
            if count == 0:
                break

        # If we found an entry, move cursor to the end of the first line.
        if found_something:
            self.cursor_position = 0
            self.cursor_position += self.document.get_end_of_line_position()

    def history_backward(self, count: int = 1) -> None:
        """
        Move backwards through history.
        """
        self._set_history_search()

        # Go back in history.
        found_something = False

        for i in range(self.working_index - 1, -1, -1):
            if self._history_matches(i):
                self.working_index = i
                count -= 1
                found_something = True
            if count == 0:
                break

        # If we move to another entry, move cursor to the end of the line.
        if found_something:
            self.cursor_position = len(self.text)

    def yank_nth_arg(self, n: int | None = None, _yank_last_arg: bool = False) -> None:
        """
        Pick nth word from previous history entry (depending on current
        `yank_nth_arg_state`) and insert it at current position. Rotate through
        history if called repeatedly. If no `n` has been given, take the first
        argument. (The second word.)

        :param n: (None or int), The index of the word from the previous line
            to take.
        """
        assert n is None or isinstance(n, int)
        history_strings = self.history.get_strings()

        if not len(history_strings):
            return

        # Make sure we have a `YankNthArgState`.
        if self.yank_nth_arg_state is None:
            state = YankNthArgState(n=-1 if _yank_last_arg else 1)
        else:
            state = self.yank_nth_arg_state

        if n is not None:
            state.n = n

        # Get new history position.
        new_pos = state.history_position - 1
        if -new_pos > len(history_strings):
            new_pos = -1

        # Take argument from line.
        line = history_strings[new_pos]

        words = [w.strip() for w in _QUOTED_WORDS_RE.split(line)]
        words = [w for w in words if w]
        try:
            word = words[state.n]
        except IndexError:
            word = ""

        # Insert new argument.
        if state.previous_inserted_word:
            self.delete_before_cursor(len(state.previous_inserted_word))
        self.insert_text(word)

        # Save state again for next completion. (Note that the 'insert'
        # operation from above clears `self.yank_nth_arg_state`.)
        state.previous_inserted_word = word
        state.history_position = new_pos
        self.yank_nth_arg_state = state

    def yank_last_arg(self, n: int | None = None) -> None:
        """
        Like `yank_nth_arg`, but if no argument has been given, yank the last
        word by default.
        """
        self.yank_nth_arg(n=n, _yank_last_arg=True)

    def start_selection(
        self, selection_type: SelectionType = SelectionType.CHARACTERS
    ) -> None:
        """
        Take the current cursor position as the start of this selection.
        """
        self.selection_state = SelectionState(self.cursor_position, selection_type)

    def copy_selection(self, _cut: bool = False) -> ClipboardData:
        """
        Copy selected text and return :class:`.ClipboardData` instance.

        Notice that this doesn't store the copied data on the clipboard yet.
        You can store it like this:

        .. code:: python

            data = buffer.copy_selection()
            get_app().clipboard.set_data(data)
        """
        new_document, clipboard_data = self.document.cut_selection()
        if _cut:
            self.document = new_document

        self.selection_state = None
        return clipboard_data

    def cut_selection(self) -> ClipboardData:
        """
        Delete selected text and return :class:`.ClipboardData` instance.
        """
        return self.copy_selection(_cut=True)

    def paste_clipboard_data(
        self,
        data: ClipboardData,
        paste_mode: PasteMode = PasteMode.EMACS,
        count: int = 1,
    ) -> None:
        """
        Insert the data from the clipboard.
        """
        assert isinstance(data, ClipboardData)
        assert paste_mode in (PasteMode.VI_BEFORE, PasteMode.VI_AFTER, PasteMode.EMACS)

        original_document = self.document
        self.document = self.document.paste_clipboard_data(
            data, paste_mode=paste_mode, count=count
        )

        # Remember original document. This assignment should come at the end,
        # because assigning to 'document' will erase it.
        self.document_before_paste = original_document

    def newline(self, copy_margin: bool = True) -> None:
        """
        Insert a line ending at the current position.
        """
        if copy_margin:
            self.insert_text("\n" + self.document.leading_whitespace_in_current_line)
        else:
            self.insert_text("\n")

    def insert_line_above(self, copy_margin: bool = True) -> None:
        """
        Insert a new line above the current one.
        """
        if copy_margin:
            insert = self.document.leading_whitespace_in_current_line + "\n"
        else:
            insert = "\n"

        self.cursor_position += self.document.get_start_of_line_position()
        self.insert_text(insert)
        self.cursor_position -= 1

    def insert_line_below(self, copy_margin: bool = True) -> None:
        """
        Insert a new line below the current one.
        """
        if copy_margin:
            insert = "\n" + self.document.leading_whitespace_in_current_line
        else:
            insert = "\n"

        self.cursor_position += self.document.get_end_of_line_position()
        self.insert_text(insert)

    def insert_text(
        self,
        data: str,
        overwrite: bool = False,
        move_cursor: bool = True,
        fire_event: bool = True,
    ) -> None:
        """
        Insert characters at cursor position.

        :param fire_event: Fire `on_text_insert` event. This is mainly used to
            trigger autocompletion while typing.
        """
        # Original text & cursor position.
        otext = self.text
        ocpos = self.cursor_position

        # In insert/text mode.
        if overwrite:
            # Don't overwrite the newline itself. Just before the line ending,
            # it should act like insert mode.
            overwritten_text = otext[ocpos : ocpos + len(data)]
            if "\n" in overwritten_text:
                overwritten_text = overwritten_text[: overwritten_text.find("\n")]

            text = otext[:ocpos] + data + otext[ocpos + len(overwritten_text) :]
        else:
            text = otext[:ocpos] + data + otext[ocpos:]

        if move_cursor:
            cpos = self.cursor_position + len(data)
        else:
            cpos = self.cursor_position

        # Set new document.
        # (Set text and cursor position at the same time. Otherwise, setting
        # the text will fire a change event before the cursor position has been
        # set. It works better to have this atomic.)
        self.document = Document(text, cpos)

        # Fire 'on_text_insert' event.
        if fire_event:  # XXX: rename to `start_complete`.
            self.on_text_insert.fire()

            # Only complete when "complete_while_typing" is enabled.
            if self.completer and self.complete_while_typing():
                get_app().create_background_task(self._async_completer())

            # Call auto_suggest.
            if self.auto_suggest:
                get_app().create_background_task(self._async_suggester())

    def undo(self) -> None:
        # Pop from the undo-stack until we find a text that if different from
        # the current text. (The current logic of `save_to_undo_stack` will
        # cause that the top of the undo stack is usually the same as the
        # current text, so in that case we have to pop twice.)
        while self._undo_stack:
            text, pos = self._undo_stack.pop()

            if text != self.text:
                # Push current text to redo stack.
                self._redo_stack.append((self.text, self.cursor_position))

                # Set new text/cursor_position.
                self.document = Document(text, cursor_position=pos)
                break

    def redo(self) -> None:
        if self._redo_stack:
            # Copy current state on undo stack.
            self.save_to_undo_stack(clear_redo_stack=False)

            # Pop state from redo stack.
            text, pos = self._redo_stack.pop()
            self.document = Document(text, cursor_position=pos)

    def validate(self, set_cursor: bool = False) -> bool:
        """
        Returns `True` if valid.

        :param set_cursor: Set the cursor position, if an error was found.
        """
        # Don't call the validator again, if it was already called for the
        # current input.
        if self.validation_state != ValidationState.UNKNOWN:
            return self.validation_state == ValidationState.VALID

        # Call validator.
        if self.validator:
            try:
                self.validator.validate(self.document)
            except ValidationError as e:
                # Set cursor position (don't allow invalid values.)
                if set_cursor:
                    self.cursor_position = min(
                        max(0, e.cursor_position), len(self.text)
                    )

                self.validation_state = ValidationState.INVALID
                self.validation_error = e
                return False

        # Handle validation result.
        self.validation_state = ValidationState.VALID
        self.validation_error = None
        return True

    async def _validate_async(self) -> None:
        """
        Asynchronous version of `validate()`.
        This one doesn't set the cursor position.

        We have both variants, because a synchronous version is required.
        Handling the ENTER key needs to be completely synchronous, otherwise
        stuff like type-ahead is going to give very weird results. (People
        could type input while the ENTER key is still processed.)

        An asynchronous version is required if we have `validate_while_typing`
        enabled.
        """
        while True:
            # Don't call the validator again, if it was already called for the
            # current input.
            if self.validation_state != ValidationState.UNKNOWN:
                return

            # Call validator.
            error = None
            document = self.document

            if self.validator:
                try:
                    await self.validator.validate_async(self.document)
                except ValidationError as e:
                    error = e

                # If the document changed during the validation, try again.
                if self.document != document:
                    continue

            # Handle validation result.
            if error:
                self.validation_state = ValidationState.INVALID
            else:
                self.validation_state = ValidationState.VALID

            self.validation_error = error
            get_app().invalidate()  # Trigger redraw (display error).

    def append_to_history(self) -> None:
        """
        Append the current input to the history.
        """
        # Save at the tail of the history. (But don't if the last entry the
        # history is already the same.)
        if self.text:
            history_strings = self.history.get_strings()
            if not len(history_strings) or history_strings[-1] != self.text:
                self.history.append_string(self.text)

    def _search(
        self,
        search_state: SearchState,
        include_current_position: bool = False,
        count: int = 1,
    ) -> tuple[int, int] | None:
        """
        Execute search. Return (working_index, cursor_position) tuple when this
        search is applied. Returns `None` when this text cannot be found.
        """
        assert count > 0

        text = search_state.text
        direction = search_state.direction
        ignore_case = search_state.ignore_case()

        def search_once(
            working_index: int, document: Document
        ) -> tuple[int, Document] | None:
            """
            Do search one time.
            Return (working_index, document) or `None`
            """
            if direction == SearchDirection.FORWARD:
                # Try find at the current input.
                new_index = document.find(
                    text,
                    include_current_position=include_current_position,
                    ignore_case=ignore_case,
                )

                if new_index is not None:
                    return (
                        working_index,
                        Document(document.text, document.cursor_position + new_index),
                    )
                else:
                    # No match, go forward in the history. (Include len+1 to wrap around.)
                    # (Here we should always include all cursor positions, because
                    # it's a different line.)
                    for i in range(working_index + 1, len(self._working_lines) + 1):
                        i %= len(self._working_lines)

                        document = Document(self._working_lines[i], 0)
                        new_index = document.find(
                            text, include_current_position=True, ignore_case=ignore_case
                        )
                        if new_index is not None:
                            return (i, Document(document.text, new_index))
            else:
                # Try find at the current input.
                new_index = document.find_backwards(text, ignore_case=ignore_case)

                if new_index is not None:
                    return (
                        working_index,
                        Document(document.text, document.cursor_position + new_index),
                    )
                else:
                    # No match, go back in the history. (Include -1 to wrap around.)
                    for i in range(working_index - 1, -2, -1):
                        i %= len(self._working_lines)

                        document = Document(
                            self._working_lines[i], len(self._working_lines[i])
                        )
                        new_index = document.find_backwards(
                            text, ignore_case=ignore_case
                        )
                        if new_index is not None:
                            return (
                                i,
                                Document(document.text, len(document.text) + new_index),
                            )
            return None

        # Do 'count' search iterations.
        working_index = self.working_index
        document = self.document
        for _ in range(count):
            result = search_once(working_index, document)
            if result is None:
                return None  # Nothing found.
            else:
                working_index, document = result

        return (working_index, document.cursor_position)

    def document_for_search(self, search_state: SearchState) -> Document:
        """
        Return a :class:`~prompt_toolkit.document.Document` instance that has
        the text/cursor position for this search, if we would apply it. This
        will be used in the
        :class:`~prompt_toolkit.layout.BufferControl` to display feedback while
        searching.
        """
        search_result = self._search(search_state, include_current_position=True)

        if search_result is None:
            return self.document
        else:
            working_index, cursor_position = search_result

            # Keep selection, when `working_index` was not changed.
            if working_index == self.working_index:
                selection = self.selection_state
            else:
                selection = None

            return Document(
                self._working_lines[working_index], cursor_position, selection=selection
            )

    def get_search_position(
        self,
        search_state: SearchState,
        include_current_position: bool = True,
        count: int = 1,
    ) -> int:
        """
        Get the cursor position for this search.
        (This operation won't change the `working_index`. It's won't go through
        the history. Vi text objects can't span multiple items.)
        """
        search_result = self._search(
            search_state, include_current_position=include_current_position, count=count
        )

        if search_result is None:
            return self.cursor_position
        else:
            working_index, cursor_position = search_result
            return cursor_position

    def apply_search(
        self,
        search_state: SearchState,
        include_current_position: bool = True,
        count: int = 1,
    ) -> None:
        """
        Apply search. If something is found, set `working_index` and
        `cursor_position`.
        """
        search_result = self._search(
            search_state, include_current_position=include_current_position, count=count
        )

        if search_result is not None:
            working_index, cursor_position = search_result
            self.working_index = working_index
            self.cursor_position = cursor_position

    def exit_selection(self) -> None:
        self.selection_state = None

    def _editor_simple_tempfile(self) -> tuple[str, Callable[[], None]]:
        """
        Simple (file) tempfile implementation.
        Return (tempfile, cleanup_func).
        """
        suffix = to_str(self.tempfile_suffix)
        descriptor, filename = tempfile.mkstemp(suffix)

        os.write(descriptor, self.text.encode("utf-8"))
        os.close(descriptor)

        def cleanup() -> None:
            os.unlink(filename)

        return filename, cleanup

    def _editor_complex_tempfile(self) -> tuple[str, Callable[[], None]]:
        # Complex (directory) tempfile implementation.
        headtail = to_str(self.tempfile)
        if not headtail:
            # Revert to simple case.
            return self._editor_simple_tempfile()
        headtail = str(headtail)

        # Try to make according to tempfile logic.
        head, tail = os.path.split(headtail)
        if os.path.isabs(head):
            head = head[1:]

        dirpath = tempfile.mkdtemp()
        if head:
            dirpath = os.path.join(dirpath, head)
        # Assume there is no issue creating dirs in this temp dir.
        os.makedirs(dirpath)

        # Open the filename and write current text.
        filename = os.path.join(dirpath, tail)
        with open(filename, "w", encoding="utf-8") as fh:
            fh.write(self.text)

        def cleanup() -> None:
            shutil.rmtree(dirpath)

        return filename, cleanup

    def open_in_editor(self, validate_and_handle: bool = False) -> asyncio.Task[None]:
        """
        Open code in editor.

        This returns a future, and runs in a thread executor.
        """
        if self.read_only():
            raise EditReadOnlyBuffer()

        # Write current text to temporary file
        if self.tempfile:
            filename, cleanup_func = self._editor_complex_tempfile()
        else:
            filename, cleanup_func = self._editor_simple_tempfile()

        async def run() -> None:
            try:
                # Open in editor
                # (We need to use `run_in_terminal`, because not all editors go to
                # the alternate screen buffer, and some could influence the cursor
                # position.)
                success = await run_in_terminal(
                    lambda: self._open_file_in_editor(filename), in_executor=True
                )

                # Read content again.
                if success:
                    with open(filename, "rb") as f:
                        text = f.read().decode("utf-8")

                        # Drop trailing newline. (Editors are supposed to add it at the
                        # end, but we don't need it.)
                        if text.endswith("\n"):
                            text = text[:-1]

                        self.document = Document(text=text, cursor_position=len(text))

                    # Accept the input.
                    if validate_and_handle:
                        self.validate_and_handle()

            finally:
                # Clean up temp dir/file.
                cleanup_func()

        return get_app().create_background_task(run())

    def _open_file_in_editor(self, filename: str) -> bool:
        """
        Call editor executable.

        Return True when we received a zero return code.
        """
        # If the 'VISUAL' or 'EDITOR' environment variable has been set, use that.
        # Otherwise, fall back to the first available editor that we can find.
        visual = os.environ.get("VISUAL")
        editor = os.environ.get("EDITOR")

        editors = [
            visual,
            editor,
            # Order of preference.
            "/usr/bin/editor",
            "/usr/bin/nano",
            "/usr/bin/pico",
            "/usr/bin/vi",
            "/usr/bin/emacs",
        ]

        for e in editors:
            if e:
                try:
                    # Use 'shlex.split()', because $VISUAL can contain spaces
                    # and quotes.
                    returncode = subprocess.call(shlex.split(e) + [filename])
                    return returncode == 0

                except OSError:
                    # Executable does not exist, try the next one.
                    pass

        return False

    def start_completion(
        self,
        select_first: bool = False,
        select_last: bool = False,
        insert_common_part: bool = False,
        complete_event: CompleteEvent | None = None,
    ) -> None:
        """
        Start asynchronous autocompletion of this buffer.
        (This will do nothing if a previous completion was still in progress.)
        """
        # Only one of these options can be selected.
        assert select_first + select_last + insert_common_part <= 1

        get_app().create_background_task(
            self._async_completer(
                select_first=select_first,
                select_last=select_last,
                insert_common_part=insert_common_part,
                complete_event=complete_event
                or CompleteEvent(completion_requested=True),
            )
        )

    def _create_completer_coroutine(self) -> Callable[..., Coroutine[Any, Any, None]]:
        """
        Create function for asynchronous autocompletion.

        (This consumes the asynchronous completer generator, which possibly
        runs the completion algorithm in another thread.)
        """

        def completion_does_nothing(document: Document, completion: Completion) -> bool:
            """
            Return `True` if applying this completion doesn't have any effect.
            (When it doesn't insert any new text.
            """
            text_before_cursor = document.text_before_cursor
            replaced_text = text_before_cursor[
                len(text_before_cursor) + completion.start_position :
            ]
            return replaced_text == completion.text

        @_only_one_at_a_time
        async def async_completer(
            select_first: bool = False,
            select_last: bool = False,
            insert_common_part: bool = False,
            complete_event: CompleteEvent | None = None,
        ) -> None:
            document = self.document
            complete_event = complete_event or CompleteEvent(text_inserted=True)

            # Don't complete when we already have completions.
            if self.complete_state or not self.completer:
                return

            # Create an empty CompletionState.
            complete_state = CompletionState(original_document=self.document)
            self.complete_state = complete_state

            def proceed() -> bool:
                """Keep retrieving completions. Input text has not yet changed
                while generating completions."""
                return self.complete_state == complete_state

            refresh_needed = asyncio.Event()

            async def refresh_while_loading() -> None:
                """Background loop to refresh the UI at most 3 times a second
                while the completion are loading. Calling
                `on_completions_changed.fire()` for every completion that we
                receive is too expensive when there are many completions. (We
                could tune `Application.max_render_postpone_time` and
                `Application.min_redraw_interval`, but having this here is a
                better approach.)
                """
                while True:
                    self.on_completions_changed.fire()
                    refresh_needed.clear()
                    await asyncio.sleep(0.3)
                    await refresh_needed.wait()

            refresh_task = asyncio.ensure_future(refresh_while_loading())
            try:
                # Load.
                async with aclosing(
                    self.completer.get_completions_async(document, complete_event)
                ) as async_generator:
                    async for completion in async_generator:
                        complete_state.completions.append(completion)
                        refresh_needed.set()

                        # If the input text changes, abort.
                        if not proceed():
                            break

                        # Always stop at 10k completions.
                        if (
                            len(complete_state.completions)
                            >= self.max_number_of_completions
                        ):
                            break
            finally:
                refresh_task.cancel()

                # Refresh one final time after we got everything.
                self.on_completions_changed.fire()

            completions = complete_state.completions

            # When there is only one completion, which has nothing to add, ignore it.
            if len(completions) == 1 and completion_does_nothing(
                document, completions[0]
            ):
                del completions[:]

            # Set completions if the text was not yet changed.
            if proceed():
                # When no completions were found, or when the user selected
                # already a completion by using the arrow keys, don't do anything.
                if (
                    not self.complete_state
                    or self.complete_state.complete_index is not None
                ):
                    return

                # When there are no completions, reset completion state anyway.
                if not completions:
                    self.complete_state = None
                    # Render the ui if the completion menu was shown
                    # it is needed especially if there is one completion and it was deleted.
                    self.on_completions_changed.fire()
                    return

                # Select first/last or insert common part, depending on the key
                # binding. (For this we have to wait until all completions are
                # loaded.)

                if select_first:
                    self.go_to_completion(0)

                elif select_last:
                    self.go_to_completion(len(completions) - 1)

                elif insert_common_part:
                    common_part = get_common_complete_suffix(document, completions)
                    if common_part:
                        # Insert the common part, update completions.
                        self.insert_text(common_part)
                        if len(completions) > 1:
                            # (Don't call `async_completer` again, but
                            # recalculate completions. See:
                            # https://github.com/ipython/ipython/issues/9658)
                            completions[:] = [
                                c.new_completion_from_position(len(common_part))
                                for c in completions
                            ]

                            self._set_completions(completions=completions)
                        else:
                            self.complete_state = None
                    else:
                        # When we were asked to insert the "common"
                        # prefix, but there was no common suffix but
                        # still exactly one match, then select the
                        # first. (It could be that we have a completion
                        # which does * expansion, like '*.py', with
                        # exactly one match.)
                        if len(completions) == 1:
                            self.go_to_completion(0)

            else:
                # If the last operation was an insert, (not a delete), restart
                # the completion coroutine.

                if self.document.text_before_cursor == document.text_before_cursor:
                    return  # Nothing changed.

                if self.document.text_before_cursor.startswith(
                    document.text_before_cursor
                ):
                    raise _Retry

        return async_completer

    def _create_auto_suggest_coroutine(self) -> Callable[[], Coroutine[Any, Any, None]]:
        """
        Create function for asynchronous auto suggestion.
        (This can be in another thread.)
        """

        @_only_one_at_a_time
        async def async_suggestor() -> None:
            document = self.document

            # Don't suggest when we already have a suggestion.
            if self.suggestion or not self.auto_suggest:
                return

            suggestion = await self.auto_suggest.get_suggestion_async(self, document)

            # Set suggestion only if the text was not yet changed.
            if self.document == document:
                # Set suggestion and redraw interface.
                self.suggestion = suggestion
                self.on_suggestion_set.fire()
            else:
                # Otherwise, restart thread.
                raise _Retry

        return async_suggestor

    def _create_auto_validate_coroutine(
        self,
    ) -> Callable[[], Coroutine[Any, Any, None]]:
        """
        Create a function for asynchronous validation while typing.
        (This can be in another thread.)
        """

        @_only_one_at_a_time
        async def async_validator() -> None:
            await self._validate_async()

        return async_validator

    def validate_and_handle(self) -> None:
        """
        Validate buffer and handle the accept action.
        """
        valid = self.validate(set_cursor=True)

        # When the validation succeeded, accept the input.
        if valid:
            if self.accept_handler:
                keep_text = self.accept_handler(self)
            else:
                keep_text = False

            self.append_to_history()

            if not keep_text:
                self.reset()


_T = TypeVar("_T", bound=Callable[..., Coroutine[Any, Any, None]])


def _only_one_at_a_time(coroutine: _T) -> _T:
    """
    Decorator that only starts the coroutine only if the previous call has
    finished. (Used to make sure that we have only one autocompleter, auto
    suggestor and validator running at a time.)

    When the coroutine raises `_Retry`, it is restarted.
    """
    running = False

    @wraps(coroutine)
    async def new_coroutine(*a: Any, **kw: Any) -> Any:
        nonlocal running

        # Don't start a new function, if the previous is still in progress.
        if running:
            return

        running = True

        try:
            while True:
                try:
                    await coroutine(*a, **kw)
                except _Retry:
                    continue
                else:
                    return None
        finally:
            running = False

    return cast(_T, new_coroutine)


class _Retry(Exception):
    "Retry in `_only_one_at_a_time`."


def indent(buffer: Buffer, from_row: int, to_row: int, count: int = 1) -> None:
    """
    Indent text of a :class:`.Buffer` object.
    """
    current_row = buffer.document.cursor_position_row
    current_col = buffer.document.cursor_position_col
    line_range = range(from_row, to_row)

    # Apply transformation.
    indent_content = "    " * count
    new_text = buffer.transform_lines(line_range, lambda l: indent_content + l)
    buffer.document = Document(
        new_text, Document(new_text).translate_row_col_to_index(current_row, 0)
    )

    # Place cursor in the same position in text after indenting
    buffer.cursor_position += current_col + len(indent_content)


def unindent(buffer: Buffer, from_row: int, to_row: int, count: int = 1) -> None:
    """
    Unindent text of a :class:`.Buffer` object.
    """
    current_row = buffer.document.cursor_position_row
    current_col = buffer.document.cursor_position_col
    line_range = range(from_row, to_row)

    indent_content = "    " * count

    def transform(text: str) -> str:
        remove = indent_content
        if text.startswith(remove):
            return text[len(remove) :]
        else:
            return text.lstrip()

    # Apply transformation.
    new_text = buffer.transform_lines(line_range, transform)
    buffer.document = Document(
        new_text, Document(new_text).translate_row_col_to_index(current_row, 0)
    )

    # Place cursor in the same position in text after dedent
    buffer.cursor_position += current_col - len(indent_content)


def reshape_text(buffer: Buffer, from_row: int, to_row: int) -> None:
    """
    Reformat text, taking the width into account.
    `to_row` is included.
    (Vi 'gq' operator.)
    """
    lines = buffer.text.splitlines(True)
    lines_before = lines[:from_row]
    lines_after = lines[to_row + 1 :]
    lines_to_reformat = lines[from_row : to_row + 1]

    if lines_to_reformat:
        # Take indentation from the first line.
        match = re.search(r"^\s*", lines_to_reformat[0])
        length = match.end() if match else 0  # `match` can't be None, actually.

        indent = lines_to_reformat[0][:length].replace("\n", "")

        # Now, take all the 'words' from the lines to be reshaped.
        words = "".join(lines_to_reformat).split()

        # And reshape.
        width = (buffer.text_width or 80) - len(indent)
        reshaped_text = [indent]
        current_width = 0
        for w in words:
            if current_width:
                if len(w) + current_width + 1 > width:
                    reshaped_text.append("\n")
                    reshaped_text.append(indent)
                    current_width = 0
                else:
                    reshaped_text.append(" ")
                    current_width += 1

            reshaped_text.append(w)
            current_width += len(w)

        if reshaped_text[-1] != "\n":
            reshaped_text.append("\n")

        # Apply result.
        buffer.document = Document(
            text="".join(lines_before + reshaped_text + lines_after),
            cursor_position=len("".join(lines_before + reshaped_text)),
        )
