# pylint: disable=function-redefined
from __future__ import annotations

from prompt_toolkit.application.current import get_app
from prompt_toolkit.buffer import Buffer, indent, unindent
from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.filters import (
    Condition,
    emacs_insert_mode,
    emacs_mode,
    has_arg,
    has_selection,
    in_paste_mode,
    is_multiline,
    is_read_only,
    shift_selection_mode,
    vi_search_direction_reversed,
)
from prompt_toolkit.key_binding.key_bindings import Binding
from prompt_toolkit.key_binding.key_processor import KeyPressEvent
from prompt_toolkit.keys import Keys
from prompt_toolkit.selection import SelectionType

from ..key_bindings import ConditionalKeyBindings, KeyBindings, KeyBindingsBase
from .named_commands import get_by_name

__all__ = [
    "load_emacs_bindings",
    "load_emacs_search_bindings",
    "load_emacs_shift_selection_bindings",
]

E = KeyPressEvent


@Condition
def is_returnable() -> bool:
    return get_app().current_buffer.is_returnable


@Condition
def is_arg() -> bool:
    return get_app().key_processor.arg == "-"


def load_emacs_bindings() -> KeyBindingsBase:
    """
    Some e-macs extensions.
    """
    # Overview of Readline emacs commands:
    # http://www.catonmat.net/download/readline-emacs-editing-mode-cheat-sheet.pdf
    key_bindings = KeyBindings()
    handle = key_bindings.add

    insert_mode = emacs_insert_mode

    @handle("escape")
    def _esc(event: E) -> None:
        """
        By default, ignore escape key.

        (If we don't put this here, and Esc is followed by a key which sequence
        is not handled, we'll insert an Escape character in the input stream.
        Something we don't want and happens to easily in emacs mode.
        Further, people can always use ControlQ to do a quoted insert.)
        """
        pass

    handle("c-a")(get_by_name("beginning-of-line"))
    handle("c-b")(get_by_name("backward-char"))
    handle("c-delete", filter=insert_mode)(get_by_name("kill-word"))
    handle("c-e")(get_by_name("end-of-line"))
    handle("c-f")(get_by_name("forward-char"))
    handle("c-left")(get_by_name("backward-word"))
    handle("c-right")(get_by_name("forward-word"))
    handle("c-x", "r", "y", filter=insert_mode)(get_by_name("yank"))
    handle("c-y", filter=insert_mode)(get_by_name("yank"))
    handle("escape", "b")(get_by_name("backward-word"))
    handle("escape", "c", filter=insert_mode)(get_by_name("capitalize-word"))
    handle("escape", "d", filter=insert_mode)(get_by_name("kill-word"))
    handle("escape", "f")(get_by_name("forward-word"))
    handle("escape", "l", filter=insert_mode)(get_by_name("downcase-word"))
    handle("escape", "u", filter=insert_mode)(get_by_name("uppercase-word"))
    handle("escape", "y", filter=insert_mode)(get_by_name("yank-pop"))
    handle("escape", "backspace", filter=insert_mode)(get_by_name("backward-kill-word"))
    handle("escape", "\\", filter=insert_mode)(get_by_name("delete-horizontal-space"))

    handle("c-home")(get_by_name("beginning-of-buffer"))
    handle("c-end")(get_by_name("end-of-buffer"))

    handle("c-_", save_before=(lambda e: False), filter=insert_mode)(
        get_by_name("undo")
    )

    handle("c-x", "c-u", save_before=(lambda e: False), filter=insert_mode)(
        get_by_name("undo")
    )

    handle("escape", "<", filter=~has_selection)(get_by_name("beginning-of-history"))
    handle("escape", ">", filter=~has_selection)(get_by_name("end-of-history"))

    handle("escape", ".", filter=insert_mode)(get_by_name("yank-last-arg"))
    handle("escape", "_", filter=insert_mode)(get_by_name("yank-last-arg"))
    handle("escape", "c-y", filter=insert_mode)(get_by_name("yank-nth-arg"))
    handle("escape", "#", filter=insert_mode)(get_by_name("insert-comment"))
    handle("c-o")(get_by_name("operate-and-get-next"))

    # ControlQ does a quoted insert. Not that for vt100 terminals, you have to
    # disable flow control by running ``stty -ixon``, otherwise Ctrl-Q and
    # Ctrl-S are captured by the terminal.
    handle("c-q", filter=~has_selection)(get_by_name("quoted-insert"))

    handle("c-x", "(")(get_by_name("start-kbd-macro"))
    handle("c-x", ")")(get_by_name("end-kbd-macro"))
    handle("c-x", "e")(get_by_name("call-last-kbd-macro"))

    @handle("c-n")
    def _next(event: E) -> None:
        "Next line."
        event.current_buffer.auto_down()

    @handle("c-p")
    def _prev(event: E) -> None:
        "Previous line."
        event.current_buffer.auto_up(count=event.arg)

    def handle_digit(c: str) -> None:
        """
        Handle input of arguments.
        The first number needs to be preceded by escape.
        """

        @handle(c, filter=has_arg)
        @handle("escape", c)
        def _(event: E) -> None:
            event.append_to_arg_count(c)

    for c in "0123456789":
        handle_digit(c)

    @handle("escape", "-", filter=~has_arg)
    def _meta_dash(event: E) -> None:
        """"""
        if event._arg is None:
            event.append_to_arg_count("-")

    @handle("-", filter=is_arg)
    def _dash(event: E) -> None:
        """
        When '-' is typed again, after exactly '-' has been given as an
        argument, ignore this.
        """
        event.app.key_processor.arg = "-"

    # Meta + Enter: always accept input.
    handle("escape", "enter", filter=insert_mode & is_returnable)(
        get_by_name("accept-line")
    )

    # Enter: accept input in single line mode.
    handle("enter", filter=insert_mode & is_returnable & ~is_multiline)(
        get_by_name("accept-line")
    )

    def character_search(buff: Buffer, char: str, count: int) -> None:
        if count < 0:
            match = buff.document.find_backwards(
                char, in_current_line=True, count=-count
            )
        else:
            match = buff.document.find(char, in_current_line=True, count=count)

        if match is not None:
            buff.cursor_position += match

    @handle("c-]", Keys.Any)
    def _goto_char(event: E) -> None:
        "When Ctl-] + a character is pressed. go to that character."
        # Also named 'character-search'
        character_search(event.current_buffer, event.data, event.arg)

    @handle("escape", "c-]", Keys.Any)
    def _goto_char_backwards(event: E) -> None:
        "Like Ctl-], but backwards."
        # Also named 'character-search-backward'
        character_search(event.current_buffer, event.data, -event.arg)

    @handle("escape", "a")
    def _prev_sentence(event: E) -> None:
        "Previous sentence."
        # TODO:

    @handle("escape", "e")
    def _end_of_sentence(event: E) -> None:
        "Move to end of sentence."
        # TODO:

    @handle("escape", "t", filter=insert_mode)
    def _swap_characters(event: E) -> None:
        """
        Swap the last two words before the cursor.
        """
        # TODO

    @handle("escape", "*", filter=insert_mode)
    def _insert_all_completions(event: E) -> None:
        """
        `meta-*`: Insert all possible completions of the preceding text.
        """
        buff = event.current_buffer

        # List all completions.
        complete_event = CompleteEvent(text_inserted=False, completion_requested=True)
        completions = list(
            buff.completer.get_completions(buff.document, complete_event)
        )

        # Insert them.
        text_to_insert = " ".join(c.text for c in completions)
        buff.insert_text(text_to_insert)

    @handle("c-x", "c-x")
    def _toggle_start_end(event: E) -> None:
        """
        Move cursor back and forth between the start and end of the current
        line.
        """
        buffer = event.current_buffer

        if buffer.document.is_cursor_at_the_end_of_line:
            buffer.cursor_position += buffer.document.get_start_of_line_position(
                after_whitespace=False
            )
        else:
            buffer.cursor_position += buffer.document.get_end_of_line_position()

    @handle("c-@")  # Control-space or Control-@
    def _start_selection(event: E) -> None:
        """
        Start of the selection (if the current buffer is not empty).
        """
        # Take the current cursor position as the start of this selection.
        buff = event.current_buffer
        if buff.text:
            buff.start_selection(selection_type=SelectionType.CHARACTERS)

    @handle("c-g", filter=~has_selection)
    def _cancel(event: E) -> None:
        """
        Control + G: Cancel completion menu and validation state.
        """
        event.current_buffer.complete_state = None
        event.current_buffer.validation_error = None

    @handle("c-g", filter=has_selection)
    def _cancel_selection(event: E) -> None:
        """
        Cancel selection.
        """
        event.current_buffer.exit_selection()

    @handle("c-w", filter=has_selection)
    @handle("c-x", "r", "k", filter=has_selection)
    def _cut(event: E) -> None:
        """
        Cut selected text.
        """
        data = event.current_buffer.cut_selection()
        event.app.clipboard.set_data(data)

    @handle("escape", "w", filter=has_selection)
    def _copy(event: E) -> None:
        """
        Copy selected text.
        """
        data = event.current_buffer.copy_selection()
        event.app.clipboard.set_data(data)

    @handle("escape", "left")
    def _start_of_word(event: E) -> None:
        """
        Cursor to start of previous word.
        """
        buffer = event.current_buffer
        buffer.cursor_position += (
            buffer.document.find_previous_word_beginning(count=event.arg) or 0
        )

    @handle("escape", "right")
    def _start_next_word(event: E) -> None:
        """
        Cursor to start of next word.
        """
        buffer = event.current_buffer
        buffer.cursor_position += (
            buffer.document.find_next_word_beginning(count=event.arg)
            or buffer.document.get_end_of_document_position()
        )

    @handle("escape", "/", filter=insert_mode)
    def _complete(event: E) -> None:
        """
        M-/: Complete.
        """
        b = event.current_buffer
        if b.complete_state:
            b.complete_next()
        else:
            b.start_completion(select_first=True)

    @handle("c-c", ">", filter=has_selection)
    def _indent(event: E) -> None:
        """
        Indent selected text.
        """
        buffer = event.current_buffer

        buffer.cursor_position += buffer.document.get_start_of_line_position(
            after_whitespace=True
        )

        from_, to = buffer.document.selection_range()
        from_, _ = buffer.document.translate_index_to_position(from_)
        to, _ = buffer.document.translate_index_to_position(to)

        indent(buffer, from_, to + 1, count=event.arg)

    @handle("c-c", "<", filter=has_selection)
    def _unindent(event: E) -> None:
        """
        Unindent selected text.
        """
        buffer = event.current_buffer

        from_, to = buffer.document.selection_range()
        from_, _ = buffer.document.translate_index_to_position(from_)
        to, _ = buffer.document.translate_index_to_position(to)

        unindent(buffer, from_, to + 1, count=event.arg)

    return ConditionalKeyBindings(key_bindings, emacs_mode)


def load_emacs_search_bindings() -> KeyBindingsBase:
    key_bindings = KeyBindings()
    handle = key_bindings.add
    from . import search

    # NOTE: We don't bind 'Escape' to 'abort_search'. The reason is that we
    #       want Alt+Enter to accept input directly in incremental search mode.
    #       Instead, we have double escape.

    handle("c-r")(search.start_reverse_incremental_search)
    handle("c-s")(search.start_forward_incremental_search)

    handle("c-c")(search.abort_search)
    handle("c-g")(search.abort_search)
    handle("c-r")(search.reverse_incremental_search)
    handle("c-s")(search.forward_incremental_search)
    handle("up")(search.reverse_incremental_search)
    handle("down")(search.forward_incremental_search)
    handle("enter")(search.accept_search)

    # Handling of escape.
    handle("escape", eager=True)(search.accept_search)

    # Like Readline, it's more natural to accept the search when escape has
    # been pressed, however instead the following two bindings could be used
    # instead.
    # #handle('escape', 'escape', eager=True)(search.abort_search)
    # #handle('escape', 'enter', eager=True)(search.accept_search_and_accept_input)

    # If Read-only: also include the following key bindings:

    # '/' and '?' key bindings for searching, just like Vi mode.
    handle("?", filter=is_read_only & ~vi_search_direction_reversed)(
        search.start_reverse_incremental_search
    )
    handle("/", filter=is_read_only & ~vi_search_direction_reversed)(
        search.start_forward_incremental_search
    )
    handle("?", filter=is_read_only & vi_search_direction_reversed)(
        search.start_forward_incremental_search
    )
    handle("/", filter=is_read_only & vi_search_direction_reversed)(
        search.start_reverse_incremental_search
    )

    @handle("n", filter=is_read_only)
    def _jump_next(event: E) -> None:
        "Jump to next match."
        event.current_buffer.apply_search(
            event.app.current_search_state,
            include_current_position=False,
            count=event.arg,
        )

    @handle("N", filter=is_read_only)
    def _jump_prev(event: E) -> None:
        "Jump to previous match."
        event.current_buffer.apply_search(
            ~event.app.current_search_state,
            include_current_position=False,
            count=event.arg,
        )

    return ConditionalKeyBindings(key_bindings, emacs_mode)


def load_emacs_shift_selection_bindings() -> KeyBindingsBase:
    """
    Bindings to select text with shift + cursor movements
    """

    key_bindings = KeyBindings()
    handle = key_bindings.add

    def unshift_move(event: E) -> None:
        """
        Used for the shift selection mode. When called with
        a shift + movement key press event, moves the cursor
        as if shift is not pressed.
        """
        key = event.key_sequence[0].key

        if key == Keys.ShiftUp:
            event.current_buffer.auto_up(count=event.arg)
            return
        if key == Keys.ShiftDown:
            event.current_buffer.auto_down(count=event.arg)
            return

        # the other keys are handled through their readline command
        key_to_command: dict[Keys | str, str] = {
            Keys.ShiftLeft: "backward-char",
            Keys.ShiftRight: "forward-char",
            Keys.ShiftHome: "beginning-of-line",
            Keys.ShiftEnd: "end-of-line",
            Keys.ControlShiftLeft: "backward-word",
            Keys.ControlShiftRight: "forward-word",
            Keys.ControlShiftHome: "beginning-of-buffer",
            Keys.ControlShiftEnd: "end-of-buffer",
        }

        try:
            # Both the dict lookup and `get_by_name` can raise KeyError.
            binding = get_by_name(key_to_command[key])
        except KeyError:
            pass
        else:  # (`else` is not really needed here.)
            if isinstance(binding, Binding):
                # (It should always be a binding here)
                binding.call(event)

    @handle("s-left", filter=~has_selection)
    @handle("s-right", filter=~has_selection)
    @handle("s-up", filter=~has_selection)
    @handle("s-down", filter=~has_selection)
    @handle("s-home", filter=~has_selection)
    @handle("s-end", filter=~has_selection)
    @handle("c-s-left", filter=~has_selection)
    @handle("c-s-right", filter=~has_selection)
    @handle("c-s-home", filter=~has_selection)
    @handle("c-s-end", filter=~has_selection)
    def _start_selection(event: E) -> None:
        """
        Start selection with shift + movement.
        """
        # Take the current cursor position as the start of this selection.
        buff = event.current_buffer
        if buff.text:
            buff.start_selection(selection_type=SelectionType.CHARACTERS)

            if buff.selection_state is not None:
                # (`selection_state` should never be `None`, it is created by
                # `start_selection`.)
                buff.selection_state.enter_shift_mode()

            # Then move the cursor
            original_position = buff.cursor_position
            unshift_move(event)
            if buff.cursor_position == original_position:
                # Cursor didn't actually move - so cancel selection
                # to avoid having an empty selection
                buff.exit_selection()

    @handle("s-left", filter=shift_selection_mode)
    @handle("s-right", filter=shift_selection_mode)
    @handle("s-up", filter=shift_selection_mode)
    @handle("s-down", filter=shift_selection_mode)
    @handle("s-home", filter=shift_selection_mode)
    @handle("s-end", filter=shift_selection_mode)
    @handle("c-s-left", filter=shift_selection_mode)
    @handle("c-s-right", filter=shift_selection_mode)
    @handle("c-s-home", filter=shift_selection_mode)
    @handle("c-s-end", filter=shift_selection_mode)
    def _extend_selection(event: E) -> None:
        """
        Extend the selection
        """
        # Just move the cursor, like shift was not pressed
        unshift_move(event)
        buff = event.current_buffer

        if buff.selection_state is not None:
            if buff.cursor_position == buff.selection_state.original_cursor_position:
                # selection is now empty, so cancel selection
                buff.exit_selection()

    @handle(Keys.Any, filter=shift_selection_mode)
    def _replace_selection(event: E) -> None:
        """
        Replace selection by what is typed
        """
        event.current_buffer.cut_selection()
        get_by_name("self-insert").call(event)

    @handle("enter", filter=shift_selection_mode & is_multiline)
    def _newline(event: E) -> None:
        """
        A newline replaces the selection
        """
        event.current_buffer.cut_selection()
        event.current_buffer.newline(copy_margin=not in_paste_mode())

    @handle("backspace", filter=shift_selection_mode)
    def _delete(event: E) -> None:
        """
        Delete selection.
        """
        event.current_buffer.cut_selection()

    @handle("c-y", filter=shift_selection_mode)
    def _yank(event: E) -> None:
        """
        In shift selection mode, yanking (pasting) replace the selection.
        """
        buff = event.current_buffer
        if buff.selection_state:
            buff.cut_selection()
        get_by_name("yank").call(event)

    # moving the cursor in shift selection mode cancels the selection
    @handle("left", filter=shift_selection_mode)
    @handle("right", filter=shift_selection_mode)
    @handle("up", filter=shift_selection_mode)
    @handle("down", filter=shift_selection_mode)
    @handle("home", filter=shift_selection_mode)
    @handle("end", filter=shift_selection_mode)
    @handle("c-left", filter=shift_selection_mode)
    @handle("c-right", filter=shift_selection_mode)
    @handle("c-home", filter=shift_selection_mode)
    @handle("c-end", filter=shift_selection_mode)
    def _cancel(event: E) -> None:
        """
        Cancel selection.
        """
        event.current_buffer.exit_selection()
        # we then process the cursor movement
        key_press = event.key_sequence[0]
        event.key_processor.feed(key_press, first=True)

    return ConditionalKeyBindings(key_bindings, emacs_mode)
