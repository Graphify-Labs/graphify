"""
Key bindings which are also known by GNU Readline by the given names.

See: http://www.delorie.com/gnu/docs/readline/rlman_13.html
"""

from __future__ import annotations

from typing import Callable, TypeVar, Union, cast

from prompt_toolkit.document import Document
from prompt_toolkit.enums import EditingMode
from prompt_toolkit.key_binding.key_bindings import Binding, key_binding
from prompt_toolkit.key_binding.key_processor import KeyPress, KeyPressEvent
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout.controls import BufferControl
from prompt_toolkit.search import SearchDirection
from prompt_toolkit.selection import PasteMode

from .completion import display_completions_like_readline, generate_completions

__all__ = [
    "get_by_name",
]


# Typing.
_Handler = Callable[[KeyPressEvent], None]
_HandlerOrBinding = Union[_Handler, Binding]
_T = TypeVar("_T", bound=_HandlerOrBinding)
E = KeyPressEvent


# Registry that maps the Readline command names to their handlers.
_readline_commands: dict[str, Binding] = {}


def register(name: str) -> Callable[[_T], _T]:
    """
    Store handler in the `_readline_commands` dictionary.
    """

    def decorator(handler: _T) -> _T:
        "`handler` is a callable or Binding."
        if isinstance(handler, Binding):
            _readline_commands[name] = handler
        else:
            _readline_commands[name] = key_binding()(cast(_Handler, handler))

        return handler

    return decorator


def get_by_name(name: str) -> Binding:
    """
    Return the handler for the (Readline) command with the given name.
    """
    try:
        return _readline_commands[name]
    except KeyError as e:
        raise KeyError(f"Unknown Readline command: {name!r}") from e


#
# Commands for moving
# See: http://www.delorie.com/gnu/docs/readline/rlman_14.html
#


@register("beginning-of-buffer")
def beginning_of_buffer(event: E) -> None:
    """
    Move to the start of the buffer.
    """
    buff = event.current_buffer
    buff.cursor_position = 0


@register("end-of-buffer")
def end_of_buffer(event: E) -> None:
    """
    Move to the end of the buffer.
    """
    buff = event.current_buffer
    buff.cursor_position = len(buff.text)


@register("beginning-of-line")
def beginning_of_line(event: E) -> None:
    """
    Move to the start of the current line.
    """
    buff = event.current_buffer
    buff.cursor_position += buff.document.get_start_of_line_position(
        after_whitespace=False
    )


@register("end-of-line")
def end_of_line(event: E) -> None:
    """
    Move to the end of the line.
    """
    buff = event.current_buffer
    buff.cursor_position += buff.document.get_end_of_line_position()


@register("forward-char")
def forward_char(event: E) -> None:
    """
    Move forward a character.
    """
    buff = event.current_buffer
    buff.cursor_position += buff.document.get_cursor_right_position(count=event.arg)


@register("backward-char")
def backward_char(event: E) -> None:
    "Move back a character."
    buff = event.current_buffer
    buff.cursor_position += buff.document.get_cursor_left_position(count=event.arg)


@register("forward-word")
def forward_word(event: E) -> None:
    """
    Move forward to the end of the next word. Words are composed of letters and
    digits.
    """
    buff = event.current_buffer
    pos = buff.document.find_next_word_ending(count=event.arg)

    if pos:
        buff.cursor_position += pos


@register("backward-word")
def backward_word(event: E) -> None:
    """
    Move back to the start of the current or previous word. Words are composed
    of letters and digits.
    """
    buff = event.current_buffer
    pos = buff.document.find_previous_word_beginning(count=event.arg)

    if pos:
        buff.cursor_position += pos


@register("clear-screen")
def clear_screen(event: E) -> None:
    """
    Clear the screen and redraw everything at the top of the screen.
    """
    event.app.renderer.clear()


@register("redraw-current-line")
def redraw_current_line(event: E) -> None:
    """
    Refresh the current line.
    (Readline defines this command, but prompt-toolkit doesn't have it.)
    """
    pass


#
# Commands for manipulating the history.
# See: http://www.delorie.com/gnu/docs/readline/rlman_15.html
#


@register("accept-line")
def accept_line(event: E) -> None:
    """
    Accept the line regardless of where the cursor is.
    """
    event.current_buffer.validate_and_handle()


@register("previous-history")
def previous_history(event: E) -> None:
    """
    Move `back` through the history list, fetching the previous command.
    """
    event.current_buffer.history_backward(count=event.arg)


@register("next-history")
def next_history(event: E) -> None:
    """
    Move `forward` through the history list, fetching the next command.
    """
    event.current_buffer.history_forward(count=event.arg)


@register("beginning-of-history")
def beginning_of_history(event: E) -> None:
    """
    Move to the first line in the history.
    """
    event.current_buffer.go_to_history(0)


@register("end-of-history")
def end_of_history(event: E) -> None:
    """
    Move to the end of the input history, i.e., the line currently being entered.
    """
    event.current_buffer.history_forward(count=10**100)
    buff = event.current_buffer
    buff.go_to_history(len(buff._working_lines) - 1)


@register("reverse-search-history")
def reverse_search_history(event: E) -> None:
    """
    Search backward starting at the current line and moving `up` through
    the history as necessary. This is an incremental search.
    """
    control = event.app.layout.current_control

    if isinstance(control, BufferControl) and control.search_buffer_control:
        event.app.current_search_state.direction = SearchDirection.BACKWARD
        event.app.layout.current_control = control.search_buffer_control


#
# Commands for changing text
#


@register("end-of-file")
def end_of_file(event: E) -> None:
    """
    Exit.
    """
    event.app.exit()


@register("delete-char")
def delete_char(event: E) -> None:
    """
    Delete character before the cursor.
    """
    deleted = event.current_buffer.delete(count=event.arg)
    if not deleted:
        event.app.output.bell()


@register("backward-delete-char")
def backward_delete_char(event: E) -> None:
    """
    Delete the character behind the cursor.
    """
    if event.arg < 0:
        # When a negative argument has been given, this should delete in front
        # of the cursor.
        deleted = event.current_buffer.delete(count=-event.arg)
    else:
        deleted = event.current_buffer.delete_before_cursor(count=event.arg)

    if not deleted:
        event.app.output.bell()


@register("self-insert")
def self_insert(event: E) -> None:
    """
    Insert yourself.
    """
    event.current_buffer.insert_text(event.data * event.arg)


@register("transpose-chars")
def transpose_chars(event: E) -> None:
    """
    Emulate Emacs transpose-char behavior: at the beginning of the buffer,
    do nothing.  At the end of a line or buffer, swap the characters before
    the cursor.  Otherwise, move the cursor right, and then swap the
    characters before the cursor.
    """
    b = event.current_buffer
    p = b.cursor_position
    if p == 0:
        return
    elif p == len(b.text) or b.text[p] == "\n":
        b.swap_characters_before_cursor()
    else:
        b.cursor_position += b.document.get_cursor_right_position()
        b.swap_characters_before_cursor()


@register("uppercase-word")
def uppercase_word(event: E) -> None:
    """
    Uppercase the current (or following) word.
    """
    buff = event.current_buffer

    for i in range(event.arg):
        pos = buff.document.find_next_word_ending()
        words = buff.document.text_after_cursor[:pos]
        buff.insert_text(words.upper(), overwrite=True)


@register("downcase-word")
def downcase_word(event: E) -> None:
    """
    Lowercase the current (or following) word.
    """
    buff = event.current_buffer

    for i in range(event.arg):  # XXX: not DRY: see meta_c and meta_u!!
        pos = buff.document.find_next_word_ending()
        words = buff.document.text_after_cursor[:pos]
        buff.insert_text(words.lower(), overwrite=True)


@register("capitalize-word")
def capitalize_word(event: E) -> None:
    """
    Capitalize the current (or following) word.
    """
    buff = event.current_buffer

    for i in range(event.arg):
        pos = buff.document.find_next_word_ending()
        words = buff.document.text_after_cursor[:pos]
        buff.insert_text(words.title(), overwrite=True)


@register("quoted-insert")
def quoted_insert(event: E) -> None:
    """
    Add the next character typed to the line verbatim. This is how to insert
    key sequences like C-q, for example.
    """
    event.app.quoted_insert = True


#
# Killing and yanking.
#


@register("kill-line")
def kill_line(event: E) -> None:
    """
    Kill the text from the cursor to the end of the line.

    If we are at the end of the line, this should remove the newline.
    (That way, it is possible to delete multiple lines by executing this
    command multiple times.)
    """
    buff = event.current_buffer
    if event.arg < 0:
        deleted = buff.delete_before_cursor(
            count=-buff.document.get_start_of_line_position()
        )
    else:
        if buff.document.current_char == "\n":
            deleted = buff.delete(1)
        else:
            deleted = buff.delete(count=buff.document.get_end_of_line_position())
    event.app.clipboard.set_text(deleted)


@register("kill-word")
def kill_word(event: E) -> None:
    """
    Kill from point to the end of the current word, or if between words, to the
    end of the next word. Word boundaries are the same as forward-word.
    """
    buff = event.current_buffer
    pos = buff.document.find_next_word_ending(count=event.arg)

    if pos:
        deleted = buff.delete(count=pos)

        if event.is_repeat:
            deleted = event.app.clipboard.get_data().text + deleted

        event.app.clipboard.set_text(deleted)


@register("unix-word-rubout")
def unix_word_rubout(event: E, WORD: bool = True) -> None:
    """
    Kill the word behind point, using whitespace as a word boundary.
    Usually bound to ControlW.
    """
    buff = event.current_buffer
    pos = buff.document.find_start_of_previous_word(count=event.arg, WORD=WORD)

    if pos is None:
        # Nothing found? delete until the start of the document.  (The
        # input starts with whitespace and no words were found before the
        # cursor.)
        pos = -buff.cursor_position

    if pos:
        deleted = buff.delete_before_cursor(count=-pos)

        # If the previous key press was also Control-W, concatenate deleted
        # text.
        if event.is_repeat:
            deleted += event.app.clipboard.get_data().text

        event.app.clipboard.set_text(deleted)
    else:
        # Nothing to delete. Bell.
        event.app.output.bell()


@register("backward-kill-word")
def backward_kill_word(event: E) -> None:
    """
    Kills the word before point, using "not a letter nor a digit" as a word boundary.
    Usually bound to M-Del or M-Backspace.
    """
    unix_word_rubout(event, WORD=False)


@register("delete-horizontal-space")
def delete_horizontal_space(event: E) -> None:
    """
    Delete all spaces and tabs around point.
    """
    buff = event.current_buffer
    text_before_cursor = buff.document.text_before_cursor
    text_after_cursor = buff.document.text_after_cursor

    delete_before = len(text_before_cursor) - len(text_before_cursor.rstrip("\t "))
    delete_after = len(text_after_cursor) - len(text_after_cursor.lstrip("\t "))

    buff.delete_before_cursor(count=delete_before)
    buff.delete(count=delete_after)


@register("unix-line-discard")
def unix_line_discard(event: E) -> None:
    """
    Kill backward from the cursor to the beginning of the current line.
    """
    buff = event.current_buffer

    if buff.document.cursor_position_col == 0 and buff.document.cursor_position > 0:
        buff.delete_before_cursor(count=1)
    else:
        deleted = buff.delete_before_cursor(
            count=-buff.document.get_start_of_line_position()
        )
        event.app.clipboard.set_text(deleted)


@register("yank")
def yank(event: E) -> None:
    """
    Paste before cursor.
    """
    event.current_buffer.paste_clipboard_data(
        event.app.clipboard.get_data(), count=event.arg, paste_mode=PasteMode.EMACS
    )


@register("yank-nth-arg")
def yank_nth_arg(event: E) -> None:
    """
    Insert the first argument of the previous command. With an argument, insert
    the nth word from the previous command (start counting at 0).
    """
    n = event.arg if event.arg_present else None
    event.current_buffer.yank_nth_arg(n)


@register("yank-last-arg")
def yank_last_arg(event: E) -> None:
    """
    Like `yank_nth_arg`, but if no argument has been given, yank the last word
    of each line.
    """
    n = event.arg if event.arg_present else None
    event.current_buffer.yank_last_arg(n)


@register("yank-pop")
def yank_pop(event: E) -> None:
    """
    Rotate the kill ring, and yank the new top. Only works following yank or
    yank-pop.
    """
    buff = event.current_buffer
    doc_before_paste = buff.document_before_paste
    clipboard = event.app.clipboard

    if doc_before_paste is not None:
        buff.document = doc_before_paste
        clipboard.rotate()
        buff.paste_clipboard_data(clipboard.get_data(), paste_mode=PasteMode.EMACS)


#
# Completion.
#


@register("complete")
def complete(event: E) -> None:
    """
    Attempt to perform completion.
    """
    display_completions_like_readline(event)


@register("menu-complete")
def menu_complete(event: E) -> None:
    """
    Generate completions, or go to the next completion. (This is the default
    way of completing input in prompt_toolkit.)
    """
    generate_completions(event)


@register("menu-complete-backward")
def menu_complete_backward(event: E) -> None:
    """
    Move backward through the list of possible completions.
    """
    event.current_buffer.complete_previous()


#
# Keyboard macros.
#


@register("start-kbd-macro")
def start_kbd_macro(event: E) -> None:
    """
    Begin saving the characters typed into the current keyboard macro.
    """
    event.app.emacs_state.start_macro()


@register("end-kbd-macro")
def end_kbd_macro(event: E) -> None:
    """
    Stop saving the characters typed into the current keyboard macro and save
    the definition.
    """
    event.app.emacs_state.end_macro()


@register("call-last-kbd-macro")
@key_binding(record_in_macro=False)
def call_last_kbd_macro(event: E) -> None:
    """
    Re-execute the last keyboard macro defined, by making the characters in the
    macro appear as if typed at the keyboard.

    Notice that we pass `record_in_macro=False`. This ensures that the 'c-x e'
    key sequence doesn't appear in the recording itself. This function inserts
    the body of the called macro back into the KeyProcessor, so these keys will
    be added later on to the macro of their handlers have `record_in_macro=True`.
    """
    # Insert the macro.
    macro = event.app.emacs_state.macro

    if macro:
        event.app.key_processor.feed_multiple(macro, first=True)


@register("print-last-kbd-macro")
def print_last_kbd_macro(event: E) -> None:
    """
    Print the last keyboard macro.
    """

    # TODO: Make the format suitable for the inputrc file.
    def print_macro() -> None:
        macro = event.app.emacs_state.macro
        if macro:
            for k in macro:
                print(k)

    from prompt_toolkit.application.run_in_terminal import run_in_terminal

    run_in_terminal(print_macro)


#
# Miscellaneous Commands.
#


@register("undo")
def undo(event: E) -> None:
    """
    Incremental undo.
    """
    event.current_buffer.undo()


@register("insert-comment")
def insert_comment(event: E) -> None:
    """
    Without numeric argument, comment all lines.
    With numeric argument, uncomment all lines.
    In any case accept the input.
    """
    buff = event.current_buffer

    # Transform all lines.
    if event.arg != 1:

        def change(line: str) -> str:
            return line[1:] if line.startswith("#") else line

    else:

        def change(line: str) -> str:
            return "#" + line

    buff.document = Document(
        text="\n".join(map(change, buff.text.splitlines())), cursor_position=0
    )

    # Accept input.
    buff.validate_and_handle()


@register("vi-editing-mode")
def vi_editing_mode(event: E) -> None:
    """
    Switch to Vi editing mode.
    """
    event.app.editing_mode = EditingMode.VI


@register("emacs-editing-mode")
def emacs_editing_mode(event: E) -> None:
    """
    Switch to Emacs editing mode.
    """
    event.app.editing_mode = EditingMode.EMACS


@register("prefix-meta")
def prefix_meta(event: E) -> None:
    """
    Metafy the next character typed. This is for keyboards without a meta key.

    Sometimes people also want to bind other keys to Meta, e.g. 'jj'::

        key_bindings.add_key_binding('j', 'j', filter=ViInsertMode())(prefix_meta)
    """
    # ('first' should be true, because we want to insert it at the current
    # position in the queue.)
    event.app.key_processor.feed(KeyPress(Keys.Escape), first=True)


@register("operate-and-get-next")
def operate_and_get_next(event: E) -> None:
    """
    Accept the current line for execution and fetch the next line relative to
    the current line from the history for editing.
    """
    buff = event.current_buffer
    new_index = buff.working_index + 1

    # Accept the current input. (This will also redraw the interface in the
    # 'done' state.)
    buff.validate_and_handle()

    # Set the new index at the start of the next run.
    def set_working_index() -> None:
        if new_index < len(buff._working_lines):
            buff.working_index = new_index

    event.app.pre_run_callables.append(set_working_index)


@register("edit-and-execute-command")
def edit_and_execute(event: E) -> None:
    """
    Invoke an editor on the current command line, and accept the result.
    """
    buff = event.current_buffer
    buff.open_in_editor(validate_and_handle=True)
