# pylint: disable=function-redefined
from __future__ import annotations

import codecs
import string
from enum import Enum
from itertools import accumulate
from typing import Callable, Iterable, Tuple, TypeVar

from prompt_toolkit.application.current import get_app
from prompt_toolkit.buffer import Buffer, indent, reshape_text, unindent
from prompt_toolkit.clipboard import ClipboardData
from prompt_toolkit.document import Document
from prompt_toolkit.filters import (
    Always,
    Condition,
    Filter,
    has_arg,
    is_read_only,
    is_searching,
)
from prompt_toolkit.filters.app import (
    in_paste_mode,
    is_multiline,
    vi_digraph_mode,
    vi_insert_mode,
    vi_insert_multiple_mode,
    vi_mode,
    vi_navigation_mode,
    vi_recording_macro,
    vi_replace_mode,
    vi_replace_single_mode,
    vi_search_direction_reversed,
    vi_selection_mode,
    vi_waiting_for_text_object_mode,
)
from prompt_toolkit.input.vt100_parser import Vt100Parser
from prompt_toolkit.key_binding.digraphs import DIGRAPHS
from prompt_toolkit.key_binding.key_processor import KeyPress, KeyPressEvent
from prompt_toolkit.key_binding.vi_state import CharacterFind, InputMode
from prompt_toolkit.keys import Keys
from prompt_toolkit.search import SearchDirection
from prompt_toolkit.selection import PasteMode, SelectionState, SelectionType

from ..key_bindings import ConditionalKeyBindings, KeyBindings, KeyBindingsBase
from .named_commands import get_by_name

__all__ = [
    "load_vi_bindings",
    "load_vi_search_bindings",
]

E = KeyPressEvent

ascii_lowercase = string.ascii_lowercase

vi_register_names = ascii_lowercase + "0123456789"


class TextObjectType(Enum):
    EXCLUSIVE = "EXCLUSIVE"
    INCLUSIVE = "INCLUSIVE"
    LINEWISE = "LINEWISE"
    BLOCK = "BLOCK"


class TextObject:
    """
    Return struct for functions wrapped in ``text_object``.
    Both `start` and `end` are relative to the current cursor position.
    """

    def __init__(
        self, start: int, end: int = 0, type: TextObjectType = TextObjectType.EXCLUSIVE
    ):
        self.start = start
        self.end = end
        self.type = type

    @property
    def selection_type(self) -> SelectionType:
        if self.type == TextObjectType.LINEWISE:
            return SelectionType.LINES
        if self.type == TextObjectType.BLOCK:
            return SelectionType.BLOCK
        else:
            return SelectionType.CHARACTERS

    def sorted(self) -> tuple[int, int]:
        """
        Return a (start, end) tuple where start <= end.
        """
        if self.start < self.end:
            return self.start, self.end
        else:
            return self.end, self.start

    def operator_range(self, document: Document) -> tuple[int, int]:
        """
        Return a (start, end) tuple with start <= end that indicates the range
        operators should operate on.
        `buffer` is used to get start and end of line positions.

        This should return something that can be used in a slice, so the `end`
        position is *not* included.
        """
        start, end = self.sorted()
        doc = document

        if (
            self.type == TextObjectType.EXCLUSIVE
            and doc.translate_index_to_position(end + doc.cursor_position)[1] == 0
        ):
            # If the motion is exclusive and the end of motion is on the first
            # column, the end position becomes end of previous line.
            end -= 1
        if self.type == TextObjectType.INCLUSIVE:
            end += 1
        if self.type == TextObjectType.LINEWISE:
            # Select whole lines
            row, col = doc.translate_index_to_position(start + doc.cursor_position)
            start = doc.translate_row_col_to_index(row, 0) - doc.cursor_position
            row, col = doc.translate_index_to_position(end + doc.cursor_position)
            end = (
                doc.translate_row_col_to_index(row, len(doc.lines[row]))
                - doc.cursor_position
            )
        return start, end

    def get_line_numbers(self, buffer: Buffer) -> tuple[int, int]:
        """
        Return a (start_line, end_line) pair.
        """
        # Get absolute cursor positions from the text object.
        from_, to = self.operator_range(buffer.document)
        from_ += buffer.cursor_position
        to += buffer.cursor_position

        # Take the start of the lines.
        from_, _ = buffer.document.translate_index_to_position(from_)
        to, _ = buffer.document.translate_index_to_position(to)

        return from_, to

    def cut(self, buffer: Buffer) -> tuple[Document, ClipboardData]:
        """
        Turn text object into `ClipboardData` instance.
        """
        from_, to = self.operator_range(buffer.document)

        from_ += buffer.cursor_position
        to += buffer.cursor_position

        # For Vi mode, the SelectionState does include the upper position,
        # while `self.operator_range` does not. So, go one to the left, unless
        # we're in the line mode, then we don't want to risk going to the
        # previous line, and missing one line in the selection.
        if self.type != TextObjectType.LINEWISE:
            to -= 1

        document = Document(
            buffer.text,
            to,
            SelectionState(original_cursor_position=from_, type=self.selection_type),
        )

        new_document, clipboard_data = document.cut_selection()
        return new_document, clipboard_data


# Typevar for any text object function:
TextObjectFunction = Callable[[E], TextObject]
_TOF = TypeVar("_TOF", bound=TextObjectFunction)


def create_text_object_decorator(
    key_bindings: KeyBindings,
) -> Callable[..., Callable[[_TOF], _TOF]]:
    """
    Create a decorator that can be used to register Vi text object implementations.
    """

    def text_object_decorator(
        *keys: Keys | str,
        filter: Filter = Always(),
        no_move_handler: bool = False,
        no_selection_handler: bool = False,
        eager: bool = False,
    ) -> Callable[[_TOF], _TOF]:
        """
        Register a text object function.

        Usage::

            @text_object('w', filter=..., no_move_handler=False)
            def handler(event):
                # Return a text object for this key.
                return TextObject(...)

        :param no_move_handler: Disable the move handler in navigation mode.
            (It's still active in selection mode.)
        """

        def decorator(text_object_func: _TOF) -> _TOF:
            @key_bindings.add(
                *keys, filter=vi_waiting_for_text_object_mode & filter, eager=eager
            )
            def _apply_operator_to_text_object(event: E) -> None:
                # Arguments are multiplied.
                vi_state = event.app.vi_state
                event._arg = str((vi_state.operator_arg or 1) * (event.arg or 1))

                # Call the text object handler.
                text_obj = text_object_func(event)

                # Get the operator function.
                # (Should never be None here, given the
                # `vi_waiting_for_text_object_mode` filter state.)
                operator_func = vi_state.operator_func

                if text_obj is not None and operator_func is not None:
                    # Call the operator function with the text object.
                    operator_func(event, text_obj)

                # Clear operator.
                event.app.vi_state.operator_func = None
                event.app.vi_state.operator_arg = None

            # Register a move operation. (Doesn't need an operator.)
            if not no_move_handler:

                @key_bindings.add(
                    *keys,
                    filter=~vi_waiting_for_text_object_mode
                    & filter
                    & vi_navigation_mode,
                    eager=eager,
                )
                def _move_in_navigation_mode(event: E) -> None:
                    """
                    Move handler for navigation mode.
                    """
                    text_object = text_object_func(event)
                    event.current_buffer.cursor_position += text_object.start

            # Register a move selection operation.
            if not no_selection_handler:

                @key_bindings.add(
                    *keys,
                    filter=~vi_waiting_for_text_object_mode
                    & filter
                    & vi_selection_mode,
                    eager=eager,
                )
                def _move_in_selection_mode(event: E) -> None:
                    """
                    Move handler for selection mode.
                    """
                    text_object = text_object_func(event)
                    buff = event.current_buffer
                    selection_state = buff.selection_state

                    if selection_state is None:
                        return  # Should not happen, because of the `vi_selection_mode` filter.

                    # When the text object has both a start and end position, like 'i(' or 'iw',
                    # Turn this into a selection, otherwise the cursor.
                    if text_object.end:
                        # Take selection positions from text object.
                        start, end = text_object.operator_range(buff.document)
                        start += buff.cursor_position
                        end += buff.cursor_position

                        selection_state.original_cursor_position = start
                        buff.cursor_position = end

                        # Take selection type from text object.
                        if text_object.type == TextObjectType.LINEWISE:
                            selection_state.type = SelectionType.LINES
                        else:
                            selection_state.type = SelectionType.CHARACTERS
                    else:
                        event.current_buffer.cursor_position += text_object.start

            # Make it possible to chain @text_object decorators.
            return text_object_func

        return decorator

    return text_object_decorator


# Typevar for any operator function:
OperatorFunction = Callable[[E, TextObject], None]
_OF = TypeVar("_OF", bound=OperatorFunction)


def create_operator_decorator(
    key_bindings: KeyBindings,
) -> Callable[..., Callable[[_OF], _OF]]:
    """
    Create a decorator that can be used for registering Vi operators.
    """

    def operator_decorator(
        *keys: Keys | str, filter: Filter = Always(), eager: bool = False
    ) -> Callable[[_OF], _OF]:
        """
        Register a Vi operator.

        Usage::

            @operator('d', filter=...)
            def handler(event, text_object):
                # Do something with the text object here.
        """

        def decorator(operator_func: _OF) -> _OF:
            @key_bindings.add(
                *keys,
                filter=~vi_waiting_for_text_object_mode & filter & vi_navigation_mode,
                eager=eager,
            )
            def _operator_in_navigation(event: E) -> None:
                """
                Handle operator in navigation mode.
                """
                # When this key binding is matched, only set the operator
                # function in the ViState. We should execute it after a text
                # object has been received.
                event.app.vi_state.operator_func = operator_func
                event.app.vi_state.operator_arg = event.arg

            @key_bindings.add(
                *keys,
                filter=~vi_waiting_for_text_object_mode & filter & vi_selection_mode,
                eager=eager,
            )
            def _operator_in_selection(event: E) -> None:
                """
                Handle operator in selection mode.
                """
                buff = event.current_buffer
                selection_state = buff.selection_state

                if selection_state is not None:
                    # Create text object from selection.
                    if selection_state.type == SelectionType.LINES:
                        text_obj_type = TextObjectType.LINEWISE
                    elif selection_state.type == SelectionType.BLOCK:
                        text_obj_type = TextObjectType.BLOCK
                    else:
                        text_obj_type = TextObjectType.INCLUSIVE

                    text_object = TextObject(
                        selection_state.original_cursor_position - buff.cursor_position,
                        type=text_obj_type,
                    )

                    # Execute operator.
                    operator_func(event, text_object)

                    # Quit selection mode.
                    buff.selection_state = None

            return operator_func

        return decorator

    return operator_decorator


@Condition
def is_returnable() -> bool:
    return get_app().current_buffer.is_returnable


@Condition
def in_block_selection() -> bool:
    buff = get_app().current_buffer
    return bool(
        buff.selection_state and buff.selection_state.type == SelectionType.BLOCK
    )


@Condition
def digraph_symbol_1_given() -> bool:
    return get_app().vi_state.digraph_symbol1 is not None


@Condition
def search_buffer_is_empty() -> bool:
    "Returns True when the search buffer is empty."
    return get_app().current_buffer.text == ""


@Condition
def tilde_operator() -> bool:
    return get_app().vi_state.tilde_operator


def load_vi_bindings() -> KeyBindingsBase:
    """
    Vi extensions.

    # Overview of Readline Vi commands:
    # http://www.catonmat.net/download/bash-vi-editing-mode-cheat-sheet.pdf
    """
    # Note: Some key bindings have the "~IsReadOnly()" filter added. This
    #       prevents the handler to be executed when the focus is on a
    #       read-only buffer.
    #       This is however only required for those that change the ViState to
    #       INSERT mode. The `Buffer` class itself throws the
    #       `EditReadOnlyBuffer` exception for any text operations which is
    #       handled correctly. There is no need to add "~IsReadOnly" to all key
    #       bindings that do text manipulation.

    key_bindings = KeyBindings()
    handle = key_bindings.add

    # (Note: Always take the navigation bindings in read-only mode, even when
    #  ViState says different.)

    TransformFunction = Tuple[Tuple[str, ...], Filter, Callable[[str], str]]

    vi_transform_functions: list[TransformFunction] = [
        # Rot 13 transformation
        (
            ("g", "?"),
            Always(),
            lambda string: codecs.encode(string, "rot_13"),
        ),
        # To lowercase
        (("g", "u"), Always(), lambda string: string.lower()),
        # To uppercase.
        (("g", "U"), Always(), lambda string: string.upper()),
        # Swap case.
        (("g", "~"), Always(), lambda string: string.swapcase()),
        (
            ("~",),
            tilde_operator,
            lambda string: string.swapcase(),
        ),
    ]

    # Insert a character literally (quoted insert).
    handle("c-v", filter=vi_insert_mode)(get_by_name("quoted-insert"))

    @handle("escape")
    def _back_to_navigation(event: E) -> None:
        """
        Escape goes to vi navigation mode.
        """
        buffer = event.current_buffer
        vi_state = event.app.vi_state

        if vi_state.input_mode in (InputMode.INSERT, InputMode.REPLACE):
            buffer.cursor_position += buffer.document.get_cursor_left_position()

        vi_state.input_mode = InputMode.NAVIGATION

        if bool(buffer.selection_state):
            buffer.exit_selection()

    @handle("k", filter=vi_selection_mode)
    def _up_in_selection(event: E) -> None:
        """
        Arrow up in selection mode.
        """
        event.current_buffer.cursor_up(count=event.arg)

    @handle("j", filter=vi_selection_mode)
    def _down_in_selection(event: E) -> None:
        """
        Arrow down in selection mode.
        """
        event.current_buffer.cursor_down(count=event.arg)

    @handle("up", filter=vi_navigation_mode)
    @handle("c-p", filter=vi_navigation_mode)
    def _up_in_navigation(event: E) -> None:
        """
        Arrow up and ControlP in navigation mode go up.
        """
        event.current_buffer.auto_up(count=event.arg)

    @handle("k", filter=vi_navigation_mode)
    def _go_up(event: E) -> None:
        """
        Go up, but if we enter a new history entry, move to the start of the
        line.
        """
        event.current_buffer.auto_up(
            count=event.arg, go_to_start_of_line_if_history_changes=True
        )

    @handle("down", filter=vi_navigation_mode)
    @handle("c-n", filter=vi_navigation_mode)
    def _go_down(event: E) -> None:
        """
        Arrow down and Control-N in navigation mode.
        """
        event.current_buffer.auto_down(count=event.arg)

    @handle("j", filter=vi_navigation_mode)
    def _go_down2(event: E) -> None:
        """
        Go down, but if we enter a new history entry, go to the start of the line.
        """
        event.current_buffer.auto_down(
            count=event.arg, go_to_start_of_line_if_history_changes=True
        )

    @handle("backspace", filter=vi_navigation_mode)
    def _go_left(event: E) -> None:
        """
        In navigation-mode, move cursor.
        """
        event.current_buffer.cursor_position += (
            event.current_buffer.document.get_cursor_left_position(count=event.arg)
        )

    @handle("c-n", filter=vi_insert_mode)
    def _complete_next(event: E) -> None:
        b = event.current_buffer

        if b.complete_state:
            b.complete_next()
        else:
            b.start_completion(select_first=True)

    @handle("c-p", filter=vi_insert_mode)
    def _complete_prev(event: E) -> None:
        """
        Control-P: To previous completion.
        """
        b = event.current_buffer

        if b.complete_state:
            b.complete_previous()
        else:
            b.start_completion(select_last=True)

    @handle("c-g", filter=vi_insert_mode)
    @handle("c-y", filter=vi_insert_mode)
    def _accept_completion(event: E) -> None:
        """
        Accept current completion.
        """
        event.current_buffer.complete_state = None

    @handle("c-e", filter=vi_insert_mode)
    def _cancel_completion(event: E) -> None:
        """
        Cancel completion. Go back to originally typed text.
        """
        event.current_buffer.cancel_completion()

    # In navigation mode, pressing enter will always return the input.
    handle("enter", filter=vi_navigation_mode & is_returnable)(
        get_by_name("accept-line")
    )

    # In insert mode, also accept input when enter is pressed, and the buffer
    # has been marked as single line.
    handle("enter", filter=is_returnable & ~is_multiline)(get_by_name("accept-line"))

    @handle("enter", filter=~is_returnable & vi_navigation_mode)
    def _start_of_next_line(event: E) -> None:
        """
        Go to the beginning of next line.
        """
        b = event.current_buffer
        b.cursor_down(count=event.arg)
        b.cursor_position += b.document.get_start_of_line_position(
            after_whitespace=True
        )

    # ** In navigation mode **

    # List of navigation commands: http://hea-www.harvard.edu/~fine/Tech/vi.html

    @handle("insert", filter=vi_navigation_mode)
    def _insert_mode(event: E) -> None:
        """
        Pressing the Insert key.
        """
        event.app.vi_state.input_mode = InputMode.INSERT

    @handle("insert", filter=vi_insert_mode)
    def _navigation_mode(event: E) -> None:
        """
        Pressing the Insert key.
        """
        event.app.vi_state.input_mode = InputMode.NAVIGATION

    @handle("a", filter=vi_navigation_mode & ~is_read_only)
    # ~IsReadOnly, because we want to stay in navigation mode for
    # read-only buffers.
    def _a(event: E) -> None:
        event.current_buffer.cursor_position += (
            event.current_buffer.document.get_cursor_right_position()
        )
        event.app.vi_state.input_mode = InputMode.INSERT

    @handle("A", filter=vi_navigation_mode & ~is_read_only)
    def _A(event: E) -> None:
        event.current_buffer.cursor_position += (
            event.current_buffer.document.get_end_of_line_position()
        )
        event.app.vi_state.input_mode = InputMode.INSERT

    @handle("C", filter=vi_navigation_mode & ~is_read_only)
    def _change_until_end_of_line(event: E) -> None:
        """
        Change to end of line.
        Same as 'c$' (which is implemented elsewhere.)
        """
        buffer = event.current_buffer

        deleted = buffer.delete(count=buffer.document.get_end_of_line_position())
        event.app.clipboard.set_text(deleted)
        event.app.vi_state.input_mode = InputMode.INSERT

    @handle("c", "c", filter=vi_navigation_mode & ~is_read_only)
    @handle("S", filter=vi_navigation_mode & ~is_read_only)
    def _change_current_line(event: E) -> None:  # TODO: implement 'arg'
        """
        Change current line
        """
        buffer = event.current_buffer

        # We copy the whole line.
        data = ClipboardData(buffer.document.current_line, SelectionType.LINES)
        event.app.clipboard.set_data(data)

        # But we delete after the whitespace
        buffer.cursor_position += buffer.document.get_start_of_line_position(
            after_whitespace=True
        )
        buffer.delete(count=buffer.document.get_end_of_line_position())
        event.app.vi_state.input_mode = InputMode.INSERT

    @handle("D", filter=vi_navigation_mode)
    def _delete_until_end_of_line(event: E) -> None:
        """
        Delete from cursor position until the end of the line.
        """
        buffer = event.current_buffer
        deleted = buffer.delete(count=buffer.document.get_end_of_line_position())
        event.app.clipboard.set_text(deleted)

    @handle("d", "d", filter=vi_navigation_mode)
    def _delete_line(event: E) -> None:
        """
        Delete line. (Or the following 'n' lines.)
        """
        buffer = event.current_buffer

        # Split string in before/deleted/after text.
        lines = buffer.document.lines

        before = "\n".join(lines[: buffer.document.cursor_position_row])
        deleted = "\n".join(
            lines[
                buffer.document.cursor_position_row : buffer.document.cursor_position_row
                + event.arg
            ]
        )
        after = "\n".join(lines[buffer.document.cursor_position_row + event.arg :])

        # Set new text.
        if before and after:
            before = before + "\n"

        # Set text and cursor position.
        buffer.document = Document(
            text=before + after,
            # Cursor At the start of the first 'after' line, after the leading whitespace.
            cursor_position=len(before) + len(after) - len(after.lstrip(" ")),
        )

        # Set clipboard data
        event.app.clipboard.set_data(ClipboardData(deleted, SelectionType.LINES))

    @handle("x", filter=vi_selection_mode)
    def _cut(event: E) -> None:
        """
        Cut selection.
        ('x' is not an operator.)
        """
        clipboard_data = event.current_buffer.cut_selection()
        event.app.clipboard.set_data(clipboard_data)

    @handle("i", filter=vi_navigation_mode & ~is_read_only)
    def _i(event: E) -> None:
        event.app.vi_state.input_mode = InputMode.INSERT

    @handle("I", filter=vi_navigation_mode & ~is_read_only)
    def _I(event: E) -> None:
        event.app.vi_state.input_mode = InputMode.INSERT
        event.current_buffer.cursor_position += (
            event.current_buffer.document.get_start_of_line_position(
                after_whitespace=True
            )
        )

    @handle("I", filter=in_block_selection & ~is_read_only)
    def insert_in_block_selection(event: E, after: bool = False) -> None:
        """
        Insert in block selection mode.
        """
        buff = event.current_buffer

        # Store all cursor positions.
        positions = []

        if after:

            def get_pos(from_to: tuple[int, int]) -> int:
                return from_to[1]

        else:

            def get_pos(from_to: tuple[int, int]) -> int:
                return from_to[0]

        for i, from_to in enumerate(buff.document.selection_ranges()):
            positions.append(get_pos(from_to))
            if i == 0:
                buff.cursor_position = get_pos(from_to)

        buff.multiple_cursor_positions = positions

        # Go to 'INSERT_MULTIPLE' mode.
        event.app.vi_state.input_mode = InputMode.INSERT_MULTIPLE
        buff.exit_selection()

    @handle("A", filter=in_block_selection & ~is_read_only)
    def _append_after_block(event: E) -> None:
        insert_in_block_selection(event, after=True)

    @handle("J", filter=vi_navigation_mode & ~is_read_only)
    def _join(event: E) -> None:
        """
        Join lines.
        """
        for i in range(event.arg):
            event.current_buffer.join_next_line()

    @handle("g", "J", filter=vi_navigation_mode & ~is_read_only)
    def _join_nospace(event: E) -> None:
        """
        Join lines without space.
        """
        for i in range(event.arg):
            event.current_buffer.join_next_line(separator="")

    @handle("J", filter=vi_selection_mode & ~is_read_only)
    def _join_selection(event: E) -> None:
        """
        Join selected lines.
        """
        event.current_buffer.join_selected_lines()

    @handle("g", "J", filter=vi_selection_mode & ~is_read_only)
    def _join_selection_nospace(event: E) -> None:
        """
        Join selected lines without space.
        """
        event.current_buffer.join_selected_lines(separator="")

    @handle("p", filter=vi_navigation_mode)
    def _paste(event: E) -> None:
        """
        Paste after
        """
        event.current_buffer.paste_clipboard_data(
            event.app.clipboard.get_data(),
            count=event.arg,
            paste_mode=PasteMode.VI_AFTER,
        )

    @handle("P", filter=vi_navigation_mode)
    def _paste_before(event: E) -> None:
        """
        Paste before
        """
        event.current_buffer.paste_clipboard_data(
            event.app.clipboard.get_data(),
            count=event.arg,
            paste_mode=PasteMode.VI_BEFORE,
        )

    @handle('"', Keys.Any, "p", filter=vi_navigation_mode)
    def _paste_register(event: E) -> None:
        """
        Paste from named register.
        """
        c = event.key_sequence[1].data
        if c in vi_register_names:
            data = event.app.vi_state.named_registers.get(c)
            if data:
                event.current_buffer.paste_clipboard_data(
                    data, count=event.arg, paste_mode=PasteMode.VI_AFTER
                )

    @handle('"', Keys.Any, "P", filter=vi_navigation_mode)
    def _paste_register_before(event: E) -> None:
        """
        Paste (before) from named register.
        """
        c = event.key_sequence[1].data
        if c in vi_register_names:
            data = event.app.vi_state.named_registers.get(c)
            if data:
                event.current_buffer.paste_clipboard_data(
                    data, count=event.arg, paste_mode=PasteMode.VI_BEFORE
                )

    @handle("r", filter=vi_navigation_mode)
    def _replace(event: E) -> None:
        """
        Go to 'replace-single'-mode.
        """
        event.app.vi_state.input_mode = InputMode.REPLACE_SINGLE

    @handle("R", filter=vi_navigation_mode)
    def _replace_mode(event: E) -> None:
        """
        Go to 'replace'-mode.
        """
        event.app.vi_state.input_mode = InputMode.REPLACE

    @handle("s", filter=vi_navigation_mode & ~is_read_only)
    def _substitute(event: E) -> None:
        """
        Substitute with new text
        (Delete character(s) and go to insert mode.)
        """
        text = event.current_buffer.delete(count=event.arg)
        event.app.clipboard.set_text(text)
        event.app.vi_state.input_mode = InputMode.INSERT

    @handle("u", filter=vi_navigation_mode, save_before=(lambda e: False))
    def _undo(event: E) -> None:
        for i in range(event.arg):
            event.current_buffer.undo()

    @handle("V", filter=vi_navigation_mode)
    def _visual_line(event: E) -> None:
        """
        Start lines selection.
        """
        event.current_buffer.start_selection(selection_type=SelectionType.LINES)

    @handle("c-v", filter=vi_navigation_mode)
    def _visual_block(event: E) -> None:
        """
        Enter block selection mode.
        """
        event.current_buffer.start_selection(selection_type=SelectionType.BLOCK)

    @handle("V", filter=vi_selection_mode)
    def _visual_line2(event: E) -> None:
        """
        Exit line selection mode, or go from non line selection mode to line
        selection mode.
        """
        selection_state = event.current_buffer.selection_state

        if selection_state is not None:
            if selection_state.type != SelectionType.LINES:
                selection_state.type = SelectionType.LINES
            else:
                event.current_buffer.exit_selection()

    @handle("v", filter=vi_navigation_mode)
    def _visual(event: E) -> None:
        """
        Enter character selection mode.
        """
        event.current_buffer.start_selection(selection_type=SelectionType.CHARACTERS)

    @handle("v", filter=vi_selection_mode)
    def _visual2(event: E) -> None:
        """
        Exit character selection mode, or go from non-character-selection mode
        to character selection mode.
        """
        selection_state = event.current_buffer.selection_state

        if selection_state is not None:
            if selection_state.type != SelectionType.CHARACTERS:
                selection_state.type = SelectionType.CHARACTERS
            else:
                event.current_buffer.exit_selection()

    @handle("c-v", filter=vi_selection_mode)
    def _visual_block2(event: E) -> None:
        """
        Exit block selection mode, or go from non block selection mode to block
        selection mode.
        """
        selection_state = event.current_buffer.selection_state

        if selection_state is not None:
            if selection_state.type != SelectionType.BLOCK:
                selection_state.type = SelectionType.BLOCK
            else:
                event.current_buffer.exit_selection()

    @handle("a", "w", filter=vi_selection_mode)
    @handle("a", "W", filter=vi_selection_mode)
    def _visual_auto_word(event: E) -> None:
        """
        Switch from visual linewise mode to visual characterwise mode.
        """
        buffer = event.current_buffer

        if (
            buffer.selection_state
            and buffer.selection_state.type == SelectionType.LINES
        ):
            buffer.selection_state.type = SelectionType.CHARACTERS

    @handle("x", filter=vi_navigation_mode)
    def _delete(event: E) -> None:
        """
        Delete character.
        """
        buff = event.current_buffer
        count = min(event.arg, len(buff.document.current_line_after_cursor))
        if count:
            text = event.current_buffer.delete(count=count)
            event.app.clipboard.set_text(text)

    @handle("X", filter=vi_navigation_mode)
    def _delete_before_cursor(event: E) -> None:
        buff = event.current_buffer
        count = min(event.arg, len(buff.document.current_line_before_cursor))
        if count:
            text = event.current_buffer.delete_before_cursor(count=count)
            event.app.clipboard.set_text(text)

    @handle("y", "y", filter=vi_navigation_mode)
    @handle("Y", filter=vi_navigation_mode)
    def _yank_line(event: E) -> None:
        """
        Yank the whole line.
        """
        text = "\n".join(event.current_buffer.document.lines_from_current[: event.arg])
        event.app.clipboard.set_data(ClipboardData(text, SelectionType.LINES))

    @handle("+", filter=vi_navigation_mode)
    def _next_line(event: E) -> None:
        """
        Move to first non whitespace of next line
        """
        buffer = event.current_buffer
        buffer.cursor_position += buffer.document.get_cursor_down_position(
            count=event.arg
        )
        buffer.cursor_position += buffer.document.get_start_of_line_position(
            after_whitespace=True
        )

    @handle("-", filter=vi_navigation_mode)
    def _prev_line(event: E) -> None:
        """
        Move to first non whitespace of previous line
        """
        buffer = event.current_buffer
        buffer.cursor_position += buffer.document.get_cursor_up_position(
            count=event.arg
        )
        buffer.cursor_position += buffer.document.get_start_of_line_position(
            after_whitespace=True
        )

    @handle(">", ">", filter=vi_navigation_mode)
    @handle("c-t", filter=vi_insert_mode)
    def _indent(event: E) -> None:
        """
        Indent lines.
        """
        buffer = event.current_buffer
        current_row = buffer.document.cursor_position_row
        indent(buffer, current_row, current_row + event.arg)

    @handle("<", "<", filter=vi_navigation_mode)
    @handle("c-d", filter=vi_insert_mode)
    def _unindent(event: E) -> None:
        """
        Unindent lines.
        """
        current_row = event.current_buffer.document.cursor_position_row
        unindent(event.current_buffer, current_row, current_row + event.arg)

    @handle("O", filter=vi_navigation_mode & ~is_read_only)
    def _open_above(event: E) -> None:
        """
        Open line above and enter insertion mode
        """
        event.current_buffer.insert_line_above(copy_margin=not in_paste_mode())
        event.app.vi_state.input_mode = InputMode.INSERT

    @handle("o", filter=vi_navigation_mode & ~is_read_only)
    def _open_below(event: E) -> None:
        """
        Open line below and enter insertion mode
        """
        event.current_buffer.insert_line_below(copy_margin=not in_paste_mode())
        event.app.vi_state.input_mode = InputMode.INSERT

    @handle("~", filter=vi_navigation_mode)
    def _reverse_case(event: E) -> None:
        """
        Reverse case of current character and move cursor forward.
        """
        buffer = event.current_buffer
        c = buffer.document.current_char

        if c is not None and c != "\n":
            buffer.insert_text(c.swapcase(), overwrite=True)

    @handle("g", "u", "u", filter=vi_navigation_mode & ~is_read_only)
    def _lowercase_line(event: E) -> None:
        """
        Lowercase current line.
        """
        buff = event.current_buffer
        buff.transform_current_line(lambda s: s.lower())

    @handle("g", "U", "U", filter=vi_navigation_mode & ~is_read_only)
    def _uppercase_line(event: E) -> None:
        """
        Uppercase current line.
        """
        buff = event.current_buffer
        buff.transform_current_line(lambda s: s.upper())

    @handle("g", "~", "~", filter=vi_navigation_mode & ~is_read_only)
    def _swapcase_line(event: E) -> None:
        """
        Swap case of the current line.
        """
        buff = event.current_buffer
        buff.transform_current_line(lambda s: s.swapcase())

    @handle("#", filter=vi_navigation_mode)
    def _prev_occurrence(event: E) -> None:
        """
        Go to previous occurrence of this word.
        """
        b = event.current_buffer
        search_state = event.app.current_search_state

        search_state.text = b.document.get_word_under_cursor()
        search_state.direction = SearchDirection.BACKWARD

        b.apply_search(search_state, count=event.arg, include_current_position=False)

    @handle("*", filter=vi_navigation_mode)
    def _next_occurrence(event: E) -> None:
        """
        Go to next occurrence of this word.
        """
        b = event.current_buffer
        search_state = event.app.current_search_state

        search_state.text = b.document.get_word_under_cursor()
        search_state.direction = SearchDirection.FORWARD

        b.apply_search(search_state, count=event.arg, include_current_position=False)

    @handle("(", filter=vi_navigation_mode)
    def _begin_of_sentence(event: E) -> None:
        # TODO: go to begin of sentence.
        # XXX: should become text_object.
        pass

    @handle(")", filter=vi_navigation_mode)
    def _end_of_sentence(event: E) -> None:
        # TODO: go to end of sentence.
        # XXX: should become text_object.
        pass

    operator = create_operator_decorator(key_bindings)
    text_object = create_text_object_decorator(key_bindings)

    @handle(Keys.Any, filter=vi_waiting_for_text_object_mode)
    def _unknown_text_object(event: E) -> None:
        """
        Unknown key binding while waiting for a text object.
        """
        event.app.output.bell()

    #
    # *** Operators ***
    #

    def create_delete_and_change_operators(
        delete_only: bool, with_register: bool = False
    ) -> None:
        """
        Delete and change operators.

        :param delete_only: Create an operator that deletes, but doesn't go to insert mode.
        :param with_register: Copy the deleted text to this named register instead of the clipboard.
        """
        handler_keys: Iterable[str]
        if with_register:
            handler_keys = ('"', Keys.Any, "cd"[delete_only])
        else:
            handler_keys = "cd"[delete_only]

        @operator(*handler_keys, filter=~is_read_only)
        def delete_or_change_operator(event: E, text_object: TextObject) -> None:
            clipboard_data = None
            buff = event.current_buffer

            if text_object:
                new_document, clipboard_data = text_object.cut(buff)
                buff.document = new_document

            # Set deleted/changed text to clipboard or named register.
            if clipboard_data and clipboard_data.text:
                if with_register:
                    reg_name = event.key_sequence[1].data
                    if reg_name in vi_register_names:
                        event.app.vi_state.named_registers[reg_name] = clipboard_data
                else:
                    event.app.clipboard.set_data(clipboard_data)

            # Only go back to insert mode in case of 'change'.
            if not delete_only:
                event.app.vi_state.input_mode = InputMode.INSERT

    create_delete_and_change_operators(False, False)
    create_delete_and_change_operators(False, True)
    create_delete_and_change_operators(True, False)
    create_delete_and_change_operators(True, True)

    def create_transform_handler(
        filter: Filter, transform_func: Callable[[str], str], *a: str
    ) -> None:
        @operator(*a, filter=filter & ~is_read_only)
        def _(event: E, text_object: TextObject) -> None:
            """
            Apply transformation (uppercase, lowercase, rot13, swap case).
            """
            buff = event.current_buffer
            start, end = text_object.operator_range(buff.document)

            if start < end:
                # Transform.
                buff.transform_region(
                    buff.cursor_position + start,
                    buff.cursor_position + end,
                    transform_func,
                )

                # Move cursor
                buff.cursor_position += text_object.end or text_object.start

    for k, f, func in vi_transform_functions:
        create_transform_handler(f, func, *k)

    @operator("y")
    def _yank(event: E, text_object: TextObject) -> None:
        """
        Yank operator. (Copy text.)
        """
        _, clipboard_data = text_object.cut(event.current_buffer)
        if clipboard_data.text:
            event.app.clipboard.set_data(clipboard_data)

    @operator('"', Keys.Any, "y")
    def _yank_to_register(event: E, text_object: TextObject) -> None:
        """
        Yank selection to named register.
        """
        c = event.key_sequence[1].data
        if c in vi_register_names:
            _, clipboard_data = text_object.cut(event.current_buffer)
            event.app.vi_state.named_registers[c] = clipboard_data

    @operator(">")
    def _indent_text_object(event: E, text_object: TextObject) -> None:
        """
        Indent.
        """
        buff = event.current_buffer
        from_, to = text_object.get_line_numbers(buff)
        indent(buff, from_, to + 1, count=event.arg)

    @operator("<")
    def _unindent_text_object(event: E, text_object: TextObject) -> None:
        """
        Unindent.
        """
        buff = event.current_buffer
        from_, to = text_object.get_line_numbers(buff)
        unindent(buff, from_, to + 1, count=event.arg)

    @operator("g", "q")
    def _reshape(event: E, text_object: TextObject) -> None:
        """
        Reshape text.
        """
        buff = event.current_buffer
        from_, to = text_object.get_line_numbers(buff)
        reshape_text(buff, from_, to)

    #
    # *** Text objects ***
    #

    @text_object("b")
    def _b(event: E) -> TextObject:
        """
        Move one word or token left.
        """
        return TextObject(
            event.current_buffer.document.find_start_of_previous_word(count=event.arg)
            or 0
        )

    @text_object("B")
    def _B(event: E) -> TextObject:
        """
        Move one non-blank word left
        """
        return TextObject(
            event.current_buffer.document.find_start_of_previous_word(
                count=event.arg, WORD=True
            )
            or 0
        )

    @text_object("$")
    def _dollar(event: E) -> TextObject:
        """
        'c$', 'd$' and '$':  Delete/change/move until end of line.
        """
        return TextObject(event.current_buffer.document.get_end_of_line_position())

    @text_object("w")
    def _word_forward(event: E) -> TextObject:
        """
        'word' forward. 'cw', 'dw', 'w': Delete/change/move one word.
        """
        return TextObject(
            event.current_buffer.document.find_next_word_beginning(count=event.arg)
            or event.current_buffer.document.get_end_of_document_position()
        )

    @text_object("W")
    def _WORD_forward(event: E) -> TextObject:
        """
        'WORD' forward. 'cW', 'dW', 'W': Delete/change/move one WORD.
        """
        return TextObject(
            event.current_buffer.document.find_next_word_beginning(
                count=event.arg, WORD=True
            )
            or event.current_buffer.document.get_end_of_document_position()
        )

    @text_object("e")
    def _end_of_word(event: E) -> TextObject:
        """
        End of 'word': 'ce', 'de', 'e'
        """
        end = event.current_buffer.document.find_next_word_ending(count=event.arg)
        return TextObject(end - 1 if end else 0, type=TextObjectType.INCLUSIVE)

    @text_object("E")
    def _end_of_WORD(event: E) -> TextObject:
        """
        End of 'WORD': 'cE', 'dE', 'E'
        """
        end = event.current_buffer.document.find_next_word_ending(
            count=event.arg, WORD=True
        )
        return TextObject(end - 1 if end else 0, type=TextObjectType.INCLUSIVE)

    @text_object("i", "w", no_move_handler=True)
    def _inner_word(event: E) -> TextObject:
        """
        Inner 'word': ciw and diw
        """
        start, end = event.current_buffer.document.find_boundaries_of_current_word()
        return TextObject(start, end)

    @text_object("a", "w", no_move_handler=True)
    def _a_word(event: E) -> TextObject:
        """
        A 'word': caw and daw
        """
        start, end = event.current_buffer.document.find_boundaries_of_current_word(
            include_trailing_whitespace=True
        )
        return TextObject(start, end)

    @text_object("i", "W", no_move_handler=True)
    def _inner_WORD(event: E) -> TextObject:
        """
        Inner 'WORD': ciW and diW
        """
        start, end = event.current_buffer.document.find_boundaries_of_current_word(
            WORD=True
        )
        return TextObject(start, end)

    @text_object("a", "W", no_move_handler=True)
    def _a_WORD(event: E) -> TextObject:
        """
        A 'WORD': caw and daw
        """
        start, end = event.current_buffer.document.find_boundaries_of_current_word(
            WORD=True, include_trailing_whitespace=True
        )
        return TextObject(start, end)

    @text_object("a", "p", no_move_handler=True)
    def _paragraph(event: E) -> TextObject:
        """
        Auto paragraph.
        """
        start = event.current_buffer.document.start_of_paragraph()
        end = event.current_buffer.document.end_of_paragraph(count=event.arg)
        return TextObject(start, end)

    @text_object("^")
    def _start_of_line(event: E) -> TextObject:
        """'c^', 'd^' and '^': Soft start of line, after whitespace."""
        return TextObject(
            event.current_buffer.document.get_start_of_line_position(
                after_whitespace=True
            )
        )

    @text_object("0")
    def _hard_start_of_line(event: E) -> TextObject:
        """
        'c0', 'd0': Hard start of line, before whitespace.
        (The move '0' key is implemented elsewhere, because a '0' could also change the `arg`.)
        """
        return TextObject(
            event.current_buffer.document.get_start_of_line_position(
                after_whitespace=False
            )
        )

    def create_ci_ca_handles(
        ci_start: str, ci_end: str, inner: bool, key: str | None = None
    ) -> None:
        # TODO: 'dat', 'dit', (tags (like xml)
        """
        Delete/Change string between this start and stop character. But keep these characters.
        This implements all the ci", ci<, ci{, ci(, di", di<, ca", ca<, ... combinations.
        """

        def handler(event: E) -> TextObject:
            if ci_start == ci_end:
                # Quotes
                start = event.current_buffer.document.find_backwards(
                    ci_start, in_current_line=False
                )
                end = event.current_buffer.document.find(ci_end, in_current_line=False)
            else:
                # Brackets
                start = event.current_buffer.document.find_enclosing_bracket_left(
                    ci_start, ci_end
                )
                end = event.current_buffer.document.find_enclosing_bracket_right(
                    ci_start, ci_end
                )

            if start is not None and end is not None:
                offset = 0 if inner else 1
                return TextObject(start + 1 - offset, end + offset)
            else:
                # Nothing found.
                return TextObject(0)

        if key is None:
            text_object("ai"[inner], ci_start, no_move_handler=True)(handler)
            text_object("ai"[inner], ci_end, no_move_handler=True)(handler)
        else:
            text_object("ai"[inner], key, no_move_handler=True)(handler)

    for inner in (False, True):
        for ci_start, ci_end in [
            ('"', '"'),
            ("'", "'"),
            ("`", "`"),
            ("[", "]"),
            ("<", ">"),
            ("{", "}"),
            ("(", ")"),
        ]:
            create_ci_ca_handles(ci_start, ci_end, inner)

        create_ci_ca_handles("(", ")", inner, "b")  # 'dab', 'dib'
        create_ci_ca_handles("{", "}", inner, "B")  # 'daB', 'diB'

    @text_object("{")
    def _previous_section(event: E) -> TextObject:
        """
        Move to previous blank-line separated section.
        Implements '{', 'c{', 'd{', 'y{'
        """
        index = event.current_buffer.document.start_of_paragraph(
            count=event.arg, before=True
        )
        return TextObject(index)

    @text_object("}")
    def _next_section(event: E) -> TextObject:
        """
        Move to next blank-line separated section.
        Implements '}', 'c}', 'd}', 'y}'
        """
        index = event.current_buffer.document.end_of_paragraph(
            count=event.arg, after=True
        )
        return TextObject(index)

    @text_object("f", Keys.Any)
    def _find_next_occurrence(event: E) -> TextObject:
        """
        Go to next occurrence of character. Typing 'fx' will move the
        cursor to the next occurrence of character. 'x'.
        """
        event.app.vi_state.last_character_find = CharacterFind(event.data, False)
        match = event.current_buffer.document.find(
            event.data, in_current_line=True, count=event.arg
        )
        if match:
            return TextObject(match, type=TextObjectType.INCLUSIVE)
        else:
            return TextObject(0)

    @text_object("F", Keys.Any)
    def _find_previous_occurrence(event: E) -> TextObject:
        """
        Go to previous occurrence of character. Typing 'Fx' will move the
        cursor to the previous occurrence of character. 'x'.
        """
        event.app.vi_state.last_character_find = CharacterFind(event.data, True)
        return TextObject(
            event.current_buffer.document.find_backwards(
                event.data, in_current_line=True, count=event.arg
            )
            or 0
        )

    @text_object("t", Keys.Any)
    def _t(event: E) -> TextObject:
        """
        Move right to the next occurrence of c, then one char backward.
        """
        event.app.vi_state.last_character_find = CharacterFind(event.data, False)
        match = event.current_buffer.document.find(
            event.data, in_current_line=True, count=event.arg
        )
        if match:
            return TextObject(match - 1, type=TextObjectType.INCLUSIVE)
        else:
            return TextObject(0)

    @text_object("T", Keys.Any)
    def _T(event: E) -> TextObject:
        """
        Move left to the previous occurrence of c, then one char forward.
        """
        event.app.vi_state.last_character_find = CharacterFind(event.data, True)
        match = event.current_buffer.document.find_backwards(
            event.data, in_current_line=True, count=event.arg
        )
        return TextObject(match + 1 if match else 0)

    def repeat(reverse: bool) -> None:
        """
        Create ',' and ';' commands.
        """

        @text_object("," if reverse else ";")
        def _(event: E) -> TextObject:
            """
            Repeat the last 'f'/'F'/'t'/'T' command.
            """
            pos: int | None = 0
            vi_state = event.app.vi_state

            type = TextObjectType.EXCLUSIVE

            if vi_state.last_character_find:
                char = vi_state.last_character_find.character
                backwards = vi_state.last_character_find.backwards

                if reverse:
                    backwards = not backwards

                if backwards:
                    pos = event.current_buffer.document.find_backwards(
                        char, in_current_line=True, count=event.arg
                    )
                else:
                    pos = event.current_buffer.document.find(
                        char, in_current_line=True, count=event.arg
                    )
                    type = TextObjectType.INCLUSIVE
            if pos:
                return TextObject(pos, type=type)
            else:
                return TextObject(0)

    repeat(True)
    repeat(False)

    @text_object("h")
    @text_object("left")
    def _left(event: E) -> TextObject:
        """
        Implements 'ch', 'dh', 'h': Cursor left.
        """
        return TextObject(
            event.current_buffer.document.get_cursor_left_position(count=event.arg)
        )

    @text_object("j", no_move_handler=True, no_selection_handler=True)
    # Note: We also need `no_selection_handler`, because we in
    #       selection mode, we prefer the other 'j' binding that keeps
    #       `buffer.preferred_column`.
    def _down(event: E) -> TextObject:
        """
        Implements 'cj', 'dj', 'j', ... Cursor up.
        """
        return TextObject(
            event.current_buffer.document.get_cursor_down_position(count=event.arg),
            type=TextObjectType.LINEWISE,
        )

    @text_object("k", no_move_handler=True, no_selection_handler=True)
    def _up(event: E) -> TextObject:
        """
        Implements 'ck', 'dk', 'k', ... Cursor up.
        """
        return TextObject(
            event.current_buffer.document.get_cursor_up_position(count=event.arg),
            type=TextObjectType.LINEWISE,
        )

    @text_object("l")
    @text_object(" ")
    @text_object("right")
    def _right(event: E) -> TextObject:
        """
        Implements 'cl', 'dl', 'l', 'c ', 'd ', ' '. Cursor right.
        """
        return TextObject(
            event.current_buffer.document.get_cursor_right_position(count=event.arg)
        )

    @text_object("H")
    def _top_of_screen(event: E) -> TextObject:
        """
        Moves to the start of the visible region. (Below the scroll offset.)
        Implements 'cH', 'dH', 'H'.
        """
        w = event.app.layout.current_window
        b = event.current_buffer

        if w and w.render_info:
            # When we find a Window that has BufferControl showing this window,
            # move to the start of the visible area.
            pos = (
                b.document.translate_row_col_to_index(
                    w.render_info.first_visible_line(after_scroll_offset=True), 0
                )
                - b.cursor_position
            )

        else:
            # Otherwise, move to the start of the input.
            pos = -len(b.document.text_before_cursor)
        return TextObject(pos, type=TextObjectType.LINEWISE)

    @text_object("M")
    def _middle_of_screen(event: E) -> TextObject:
        """
        Moves cursor to the vertical center of the visible region.
        Implements 'cM', 'dM', 'M'.
        """
        w = event.app.layout.current_window
        b = event.current_buffer

        if w and w.render_info:
            # When we find a Window that has BufferControl showing this window,
            # move to the center of the visible area.
            pos = (
                b.document.translate_row_col_to_index(
                    w.render_info.center_visible_line(), 0
                )
                - b.cursor_position
            )

        else:
            # Otherwise, move to the start of the input.
            pos = -len(b.document.text_before_cursor)
        return TextObject(pos, type=TextObjectType.LINEWISE)

    @text_object("L")
    def _end_of_screen(event: E) -> TextObject:
        """
        Moves to the end of the visible region. (Above the scroll offset.)
        """
        w = event.app.layout.current_window
        b = event.current_buffer

        if w and w.render_info:
            # When we find a Window that has BufferControl showing this window,
            # move to the end of the visible area.
            pos = (
                b.document.translate_row_col_to_index(
                    w.render_info.last_visible_line(before_scroll_offset=True), 0
                )
                - b.cursor_position
            )

        else:
            # Otherwise, move to the end of the input.
            pos = len(b.document.text_after_cursor)
        return TextObject(pos, type=TextObjectType.LINEWISE)

    @text_object("n", no_move_handler=True)
    def _search_next(event: E) -> TextObject:
        """
        Search next.
        """
        buff = event.current_buffer
        search_state = event.app.current_search_state

        cursor_position = buff.get_search_position(
            search_state, include_current_position=False, count=event.arg
        )
        return TextObject(cursor_position - buff.cursor_position)

    @handle("n", filter=vi_navigation_mode)
    def _search_next2(event: E) -> None:
        """
        Search next in navigation mode. (This goes through the history.)
        """
        search_state = event.app.current_search_state

        event.current_buffer.apply_search(
            search_state, include_current_position=False, count=event.arg
        )

    @text_object("N", no_move_handler=True)
    def _search_previous(event: E) -> TextObject:
        """
        Search previous.
        """
        buff = event.current_buffer
        search_state = event.app.current_search_state

        cursor_position = buff.get_search_position(
            ~search_state, include_current_position=False, count=event.arg
        )
        return TextObject(cursor_position - buff.cursor_position)

    @handle("N", filter=vi_navigation_mode)
    def _search_previous2(event: E) -> None:
        """
        Search previous in navigation mode. (This goes through the history.)
        """
        search_state = event.app.current_search_state

        event.current_buffer.apply_search(
            ~search_state, include_current_position=False, count=event.arg
        )

    @handle("z", "+", filter=vi_navigation_mode | vi_selection_mode)
    @handle("z", "t", filter=vi_navigation_mode | vi_selection_mode)
    @handle("z", "enter", filter=vi_navigation_mode | vi_selection_mode)
    def _scroll_top(event: E) -> None:
        """
        Scrolls the window to makes the current line the first line in the visible region.
        """
        b = event.current_buffer
        event.app.layout.current_window.vertical_scroll = b.document.cursor_position_row

    @handle("z", "-", filter=vi_navigation_mode | vi_selection_mode)
    @handle("z", "b", filter=vi_navigation_mode | vi_selection_mode)
    def _scroll_bottom(event: E) -> None:
        """
        Scrolls the window to makes the current line the last line in the visible region.
        """
        # We can safely set the scroll offset to zero; the Window will make
        # sure that it scrolls at least enough to make the cursor visible
        # again.
        event.app.layout.current_window.vertical_scroll = 0

    @handle("z", "z", filter=vi_navigation_mode | vi_selection_mode)
    def _scroll_center(event: E) -> None:
        """
        Center Window vertically around cursor.
        """
        w = event.app.layout.current_window
        b = event.current_buffer

        if w and w.render_info:
            info = w.render_info

            # Calculate the offset that we need in order to position the row
            # containing the cursor in the center.
            scroll_height = info.window_height // 2

            y = max(0, b.document.cursor_position_row - 1)
            height = 0
            while y > 0:
                line_height = info.get_height_for_line(y)

                if height + line_height < scroll_height:
                    height += line_height
                    y -= 1
                else:
                    break

            w.vertical_scroll = y

    @text_object("%")
    def _goto_corresponding_bracket(event: E) -> TextObject:
        """
        Implements 'c%', 'd%', '%, 'y%' (Move to corresponding bracket.)
        If an 'arg' has been given, go this this % position in the file.
        """
        buffer = event.current_buffer

        if event._arg:
            # If 'arg' has been given, the meaning of % is to go to the 'x%'
            # row in the file.
            if 0 < event.arg <= 100:
                absolute_index = buffer.document.translate_row_col_to_index(
                    int((event.arg * buffer.document.line_count - 1) / 100), 0
                )
                return TextObject(
                    absolute_index - buffer.document.cursor_position,
                    type=TextObjectType.LINEWISE,
                )
            else:
                return TextObject(0)  # Do nothing.

        else:
            # Move to the corresponding opening/closing bracket (()'s, []'s and {}'s).
            match = buffer.document.find_matching_bracket_position()
            if match:
                return TextObject(match, type=TextObjectType.INCLUSIVE)
            else:
                return TextObject(0)

    @text_object("|")
    def _to_column(event: E) -> TextObject:
        """
        Move to the n-th column (you may specify the argument n by typing it on
        number keys, for example, 20|).
        """
        return TextObject(
            event.current_buffer.document.get_column_cursor_position(event.arg - 1)
        )

    @text_object("g", "g")
    def _goto_first_line(event: E) -> TextObject:
        """
        Go to the start of the very first line.
        Implements 'gg', 'cgg', 'ygg'
        """
        d = event.current_buffer.document

        if event._arg:
            # Move to the given line.
            return TextObject(
                d.translate_row_col_to_index(event.arg - 1, 0) - d.cursor_position,
                type=TextObjectType.LINEWISE,
            )
        else:
            # Move to the top of the input.
            return TextObject(
                d.get_start_of_document_position(), type=TextObjectType.LINEWISE
            )

    @text_object("g", "_")
    def _goto_last_line(event: E) -> TextObject:
        """
        Go to last non-blank of line.
        'g_', 'cg_', 'yg_', etc..
        """
        return TextObject(
            event.current_buffer.document.last_non_blank_of_current_line_position(),
            type=TextObjectType.INCLUSIVE,
        )

    @text_object("g", "e")
    def _ge(event: E) -> TextObject:
        """
        Go to last character of previous word.
        'ge', 'cge', 'yge', etc..
        """
        prev_end = event.current_buffer.document.find_previous_word_ending(
            count=event.arg
        )
        return TextObject(
            prev_end - 1 if prev_end is not None else 0, type=TextObjectType.INCLUSIVE
        )

    @text_object("g", "E")
    def _gE(event: E) -> TextObject:
        """
        Go to last character of previous WORD.
        'gE', 'cgE', 'ygE', etc..
        """
        prev_end = event.current_buffer.document.find_previous_word_ending(
            count=event.arg, WORD=True
        )
        return TextObject(
            prev_end - 1 if prev_end is not None else 0, type=TextObjectType.INCLUSIVE
        )

    @text_object("g", "m")
    def _gm(event: E) -> TextObject:
        """
        Like g0, but half a screenwidth to the right. (Or as much as possible.)
        """
        w = event.app.layout.current_window
        buff = event.current_buffer

        if w and w.render_info:
            width = w.render_info.window_width
            start = buff.document.get_start_of_line_position(after_whitespace=False)
            start += int(min(width / 2, len(buff.document.current_line)))

            return TextObject(start, type=TextObjectType.INCLUSIVE)
        return TextObject(0)

    @text_object("G")
    def _last_line(event: E) -> TextObject:
        """
        Go to the end of the document. (If no arg has been given.)
        """
        buf = event.current_buffer
        return TextObject(
            buf.document.translate_row_col_to_index(buf.document.line_count - 1, 0)
            - buf.cursor_position,
            type=TextObjectType.LINEWISE,
        )

    #
    # *** Other ***
    #

    @handle("G", filter=has_arg)
    def _to_nth_history_line(event: E) -> None:
        """
        If an argument is given, move to this line in the  history. (for
        example, 15G)
        """
        event.current_buffer.go_to_history(event.arg - 1)

    for n in "123456789":

        @handle(
            n,
            filter=vi_navigation_mode
            | vi_selection_mode
            | vi_waiting_for_text_object_mode,
        )
        def _arg(event: E) -> None:
            """
            Always handle numerics in navigation mode as arg.
            """
            event.append_to_arg_count(event.data)

    @handle(
        "0",
        filter=(
            vi_navigation_mode | vi_selection_mode | vi_waiting_for_text_object_mode
        )
        & has_arg,
    )
    def _0_arg(event: E) -> None:
        """
        Zero when an argument was already give.
        """
        event.append_to_arg_count(event.data)

    @handle(Keys.Any, filter=vi_replace_mode)
    def _insert_text(event: E) -> None:
        """
        Insert data at cursor position.
        """
        event.current_buffer.insert_text(event.data, overwrite=True)

    @handle(Keys.Any, filter=vi_replace_single_mode)
    def _replace_single(event: E) -> None:
        """
        Replace single character at cursor position.
        """
        event.current_buffer.insert_text(event.data, overwrite=True)
        event.current_buffer.cursor_position -= 1
        event.app.vi_state.input_mode = InputMode.NAVIGATION

    @handle(
        Keys.Any,
        filter=vi_insert_multiple_mode,
        save_before=(lambda e: not e.is_repeat),
    )
    def _insert_text_multiple_cursors(event: E) -> None:
        """
        Insert data at multiple cursor positions at once.
        (Usually a result of pressing 'I' or 'A' in block-selection mode.)
        """
        buff = event.current_buffer
        original_text = buff.text

        # Construct new text.
        text = []
        p = 0

        for p2 in buff.multiple_cursor_positions:
            text.append(original_text[p:p2])
            text.append(event.data)
            p = p2

        text.append(original_text[p:])

        # Shift all cursor positions.
        new_cursor_positions = [
            pos + i + 1 for i, pos in enumerate(buff.multiple_cursor_positions)
        ]

        # Set result.
        buff.text = "".join(text)
        buff.multiple_cursor_positions = new_cursor_positions
        buff.cursor_position += 1

    @handle("backspace", filter=vi_insert_multiple_mode)
    def _delete_before_multiple_cursors(event: E) -> None:
        """
        Backspace, using multiple cursors.
        """
        buff = event.current_buffer
        original_text = buff.text

        # Construct new text.
        deleted_something = False
        text = []
        p = 0

        for p2 in buff.multiple_cursor_positions:
            if p2 > 0 and original_text[p2 - 1] != "\n":  # Don't delete across lines.
                text.append(original_text[p : p2 - 1])
                deleted_something = True
            else:
                text.append(original_text[p:p2])
            p = p2

        text.append(original_text[p:])

        if deleted_something:
            # Shift all cursor positions.
            lengths = [len(part) for part in text[:-1]]
            new_cursor_positions = list(accumulate(lengths))

            # Set result.
            buff.text = "".join(text)
            buff.multiple_cursor_positions = new_cursor_positions
            buff.cursor_position -= 1
        else:
            event.app.output.bell()

    @handle("delete", filter=vi_insert_multiple_mode)
    def _delete_after_multiple_cursors(event: E) -> None:
        """
        Delete, using multiple cursors.
        """
        buff = event.current_buffer
        original_text = buff.text

        # Construct new text.
        deleted_something = False
        text = []
        new_cursor_positions = []
        p = 0

        for p2 in buff.multiple_cursor_positions:
            text.append(original_text[p:p2])
            if p2 >= len(original_text) or original_text[p2] == "\n":
                # Don't delete across lines.
                p = p2
            else:
                p = p2 + 1
                deleted_something = True

        text.append(original_text[p:])

        if deleted_something:
            # Shift all cursor positions.
            lengths = [len(part) for part in text[:-1]]
            new_cursor_positions = list(accumulate(lengths))

            # Set result.
            buff.text = "".join(text)
            buff.multiple_cursor_positions = new_cursor_positions
        else:
            event.app.output.bell()

    @handle("left", filter=vi_insert_multiple_mode)
    def _left_multiple(event: E) -> None:
        """
        Move all cursors to the left.
        (But keep all cursors on the same line.)
        """
        buff = event.current_buffer
        new_positions = []

        for p in buff.multiple_cursor_positions:
            if buff.document.translate_index_to_position(p)[1] > 0:
                p -= 1
            new_positions.append(p)

        buff.multiple_cursor_positions = new_positions

        if buff.document.cursor_position_col > 0:
            buff.cursor_position -= 1

    @handle("right", filter=vi_insert_multiple_mode)
    def _right_multiple(event: E) -> None:
        """
        Move all cursors to the right.
        (But keep all cursors on the same line.)
        """
        buff = event.current_buffer
        new_positions = []

        for p in buff.multiple_cursor_positions:
            row, column = buff.document.translate_index_to_position(p)
            if column < len(buff.document.lines[row]):
                p += 1
            new_positions.append(p)

        buff.multiple_cursor_positions = new_positions

        if not buff.document.is_cursor_at_the_end_of_line:
            buff.cursor_position += 1

    @handle("up", filter=vi_insert_multiple_mode)
    @handle("down", filter=vi_insert_multiple_mode)
    def _updown_multiple(event: E) -> None:
        """
        Ignore all up/down key presses when in multiple cursor mode.
        """

    @handle("c-x", "c-l", filter=vi_insert_mode)
    def _complete_line(event: E) -> None:
        """
        Pressing the ControlX - ControlL sequence in Vi mode does line
        completion based on the other lines in the document and the history.
        """
        event.current_buffer.start_history_lines_completion()

    @handle("c-x", "c-f", filter=vi_insert_mode)
    def _complete_filename(event: E) -> None:
        """
        Complete file names.
        """
        # TODO
        pass

    @handle("c-k", filter=vi_insert_mode | vi_replace_mode)
    def _digraph(event: E) -> None:
        """
        Go into digraph mode.
        """
        event.app.vi_state.waiting_for_digraph = True

    @handle(Keys.Any, filter=vi_digraph_mode & ~digraph_symbol_1_given)
    def _digraph1(event: E) -> None:
        """
        First digraph symbol.
        """
        event.app.vi_state.digraph_symbol1 = event.data

    @handle(Keys.Any, filter=vi_digraph_mode & digraph_symbol_1_given)
    def _create_digraph(event: E) -> None:
        """
        Insert digraph.
        """
        try:
            # Lookup.
            code: tuple[str, str] = (
                event.app.vi_state.digraph_symbol1 or "",
                event.data,
            )
            if code not in DIGRAPHS:
                code = code[::-1]  # Try reversing.
            symbol = DIGRAPHS[code]
        except KeyError:
            # Unknown digraph.
            event.app.output.bell()
        else:
            # Insert digraph.
            overwrite = event.app.vi_state.input_mode == InputMode.REPLACE
            event.current_buffer.insert_text(chr(symbol), overwrite=overwrite)
            event.app.vi_state.waiting_for_digraph = False
        finally:
            event.app.vi_state.waiting_for_digraph = False
            event.app.vi_state.digraph_symbol1 = None

    @handle("c-o", filter=vi_insert_mode | vi_replace_mode)
    def _quick_normal_mode(event: E) -> None:
        """
        Go into normal mode for one single action.
        """
        event.app.vi_state.temporary_navigation_mode = True

    @handle("q", Keys.Any, filter=vi_navigation_mode & ~vi_recording_macro)
    def _start_macro(event: E) -> None:
        """
        Start recording macro.
        """
        c = event.key_sequence[1].data
        if c in vi_register_names:
            vi_state = event.app.vi_state

            vi_state.recording_register = c
            vi_state.current_recording = ""

    @handle("q", filter=vi_navigation_mode & vi_recording_macro)
    def _stop_macro(event: E) -> None:
        """
        Stop recording macro.
        """
        vi_state = event.app.vi_state

        # Store and stop recording.
        if vi_state.recording_register:
            vi_state.named_registers[vi_state.recording_register] = ClipboardData(
                vi_state.current_recording
            )
            vi_state.recording_register = None
            vi_state.current_recording = ""

    @handle("@", Keys.Any, filter=vi_navigation_mode, record_in_macro=False)
    def _execute_macro(event: E) -> None:
        """
        Execute macro.

        Notice that we pass `record_in_macro=False`. This ensures that the `@x`
        keys don't appear in the recording itself. This function inserts the
        body of the called macro back into the KeyProcessor, so these keys will
        be added later on to the macro of their handlers have
        `record_in_macro=True`.
        """
        # Retrieve macro.
        c = event.key_sequence[1].data
        try:
            macro = event.app.vi_state.named_registers[c]
        except KeyError:
            return

        # Expand macro (which is a string in the register), in individual keys.
        # Use vt100 parser for this.
        keys: list[KeyPress] = []

        parser = Vt100Parser(keys.append)
        parser.feed(macro.text)
        parser.flush()

        # Now feed keys back to the input processor.
        for _ in range(event.arg):
            event.app.key_processor.feed_multiple(keys, first=True)

    return ConditionalKeyBindings(key_bindings, vi_mode)


def load_vi_search_bindings() -> KeyBindingsBase:
    key_bindings = KeyBindings()
    handle = key_bindings.add
    from . import search

    # Vi-style forward search.
    handle(
        "/",
        filter=(vi_navigation_mode | vi_selection_mode) & ~vi_search_direction_reversed,
    )(search.start_forward_incremental_search)
    handle(
        "?",
        filter=(vi_navigation_mode | vi_selection_mode) & vi_search_direction_reversed,
    )(search.start_forward_incremental_search)
    handle("c-s")(search.start_forward_incremental_search)

    # Vi-style backward search.
    handle(
        "?",
        filter=(vi_navigation_mode | vi_selection_mode) & ~vi_search_direction_reversed,
    )(search.start_reverse_incremental_search)
    handle(
        "/",
        filter=(vi_navigation_mode | vi_selection_mode) & vi_search_direction_reversed,
    )(search.start_reverse_incremental_search)
    handle("c-r")(search.start_reverse_incremental_search)

    # Apply the search. (At the / or ? prompt.)
    handle("enter", filter=is_searching)(search.accept_search)

    handle("c-r", filter=is_searching)(search.reverse_incremental_search)
    handle("c-s", filter=is_searching)(search.forward_incremental_search)

    handle("c-c")(search.abort_search)
    handle("c-g")(search.abort_search)
    handle("backspace", filter=search_buffer_is_empty)(search.abort_search)

    # Handle escape. This should accept the search, just like readline.
    # `abort_search` would be a meaningful alternative.
    handle("escape")(search.accept_search)

    return ConditionalKeyBindings(key_bindings, vi_mode)
