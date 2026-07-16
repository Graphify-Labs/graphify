# pylint: disable=function-redefined
from __future__ import annotations

from prompt_toolkit.application.current import get_app
from prompt_toolkit.filters import (
    Condition,
    emacs_insert_mode,
    has_selection,
    in_paste_mode,
    is_multiline,
    vi_insert_mode,
)
from prompt_toolkit.key_binding.key_processor import KeyPress, KeyPressEvent
from prompt_toolkit.keys import Keys

from ..key_bindings import KeyBindings
from .named_commands import get_by_name

__all__ = [
    "load_basic_bindings",
]

E = KeyPressEvent


def if_no_repeat(event: E) -> bool:
    """Callable that returns True when the previous event was delivered to
    another handler."""
    return not event.is_repeat


@Condition
def has_text_before_cursor() -> bool:
    return bool(get_app().current_buffer.text)


@Condition
def in_quoted_insert() -> bool:
    return get_app().quoted_insert


def load_basic_bindings() -> KeyBindings:
    key_bindings = KeyBindings()
    insert_mode = vi_insert_mode | emacs_insert_mode
    handle = key_bindings.add

    @handle("c-a")
    @handle("c-b")
    @handle("c-c")
    @handle("c-d")
    @handle("c-e")
    @handle("c-f")
    @handle("c-g")
    @handle("c-h")
    @handle("c-i")
    @handle("c-j")
    @handle("c-k")
    @handle("c-l")
    @handle("c-m")
    @handle("c-n")
    @handle("c-o")
    @handle("c-p")
    @handle("c-q")
    @handle("c-r")
    @handle("c-s")
    @handle("c-t")
    @handle("c-u")
    @handle("c-v")
    @handle("c-w")
    @handle("c-x")
    @handle("c-y")
    @handle("c-z")
    @handle("f1")
    @handle("f2")
    @handle("f3")
    @handle("f4")
    @handle("f5")
    @handle("f6")
    @handle("f7")
    @handle("f8")
    @handle("f9")
    @handle("f10")
    @handle("f11")
    @handle("f12")
    @handle("f13")
    @handle("f14")
    @handle("f15")
    @handle("f16")
    @handle("f17")
    @handle("f18")
    @handle("f19")
    @handle("f20")
    @handle("f21")
    @handle("f22")
    @handle("f23")
    @handle("f24")
    @handle("c-@")  # Also c-space.
    @handle("c-\\")
    @handle("c-]")
    @handle("c-^")
    @handle("c-_")
    @handle("backspace")
    @handle("up")
    @handle("down")
    @handle("right")
    @handle("left")
    @handle("s-up")
    @handle("s-down")
    @handle("s-right")
    @handle("s-left")
    @handle("home")
    @handle("end")
    @handle("s-home")
    @handle("s-end")
    @handle("delete")
    @handle("s-delete")
    @handle("c-delete")
    @handle("pageup")
    @handle("pagedown")
    @handle("s-tab")
    @handle("tab")
    @handle("c-s-left")
    @handle("c-s-right")
    @handle("c-s-home")
    @handle("c-s-end")
    @handle("c-left")
    @handle("c-right")
    @handle("c-up")
    @handle("c-down")
    @handle("c-home")
    @handle("c-end")
    @handle("insert")
    @handle("s-insert")
    @handle("c-insert")
    @handle("<sigint>")
    @handle(Keys.Ignore)
    def _ignore(event: E) -> None:
        """
        First, for any of these keys, Don't do anything by default. Also don't
        catch them in the 'Any' handler which will insert them as data.

        If people want to insert these characters as a literal, they can always
        do by doing a quoted insert. (ControlQ in emacs mode, ControlV in Vi
        mode.)
        """
        pass

    # Readline-style bindings.
    handle("home")(get_by_name("beginning-of-line"))
    handle("end")(get_by_name("end-of-line"))
    handle("left")(get_by_name("backward-char"))
    handle("right")(get_by_name("forward-char"))
    handle("c-up")(get_by_name("previous-history"))
    handle("c-down")(get_by_name("next-history"))
    handle("c-l")(get_by_name("clear-screen"))

    handle("c-k", filter=insert_mode)(get_by_name("kill-line"))
    handle("c-u", filter=insert_mode)(get_by_name("unix-line-discard"))
    handle("backspace", filter=insert_mode, save_before=if_no_repeat)(
        get_by_name("backward-delete-char")
    )
    handle("delete", filter=insert_mode, save_before=if_no_repeat)(
        get_by_name("delete-char")
    )
    handle("c-delete", filter=insert_mode, save_before=if_no_repeat)(
        get_by_name("delete-char")
    )
    handle(Keys.Any, filter=insert_mode, save_before=if_no_repeat)(
        get_by_name("self-insert")
    )
    handle("c-t", filter=insert_mode)(get_by_name("transpose-chars"))
    handle("c-i", filter=insert_mode)(get_by_name("menu-complete"))
    handle("s-tab", filter=insert_mode)(get_by_name("menu-complete-backward"))

    # Control-W should delete, using whitespace as separator, while M-Del
    # should delete using [^a-zA-Z0-9] as a boundary.
    handle("c-w", filter=insert_mode)(get_by_name("unix-word-rubout"))

    handle("pageup", filter=~has_selection)(get_by_name("previous-history"))
    handle("pagedown", filter=~has_selection)(get_by_name("next-history"))

    # CTRL keys.

    handle("c-d", filter=has_text_before_cursor & insert_mode)(
        get_by_name("delete-char")
    )

    @handle("enter", filter=insert_mode & is_multiline)
    def _newline(event: E) -> None:
        """
        Newline (in case of multiline input.
        """
        event.current_buffer.newline(copy_margin=not in_paste_mode())

    @handle("c-j")
    def _newline2(event: E) -> None:
        r"""
        By default, handle \n as if it were a \r (enter).
        (It appears that some terminals send \n instead of \r when pressing
        enter. - at least the Linux subsystem for Windows.)
        """
        event.key_processor.feed(KeyPress(Keys.ControlM, "\r"), first=True)

    # Delete the word before the cursor.

    @handle("up")
    def _go_up(event: E) -> None:
        event.current_buffer.auto_up(count=event.arg)

    @handle("down")
    def _go_down(event: E) -> None:
        event.current_buffer.auto_down(count=event.arg)

    @handle("delete", filter=has_selection)
    def _cut(event: E) -> None:
        data = event.current_buffer.cut_selection()
        event.app.clipboard.set_data(data)

    # Global bindings.

    @handle("c-z")
    def _insert_ctrl_z(event: E) -> None:
        """
        By default, control-Z should literally insert Ctrl-Z.
        (Ansi Ctrl-Z, code 26 in MSDOS means End-Of-File.
        In a Python REPL for instance, it's possible to type
        Control-Z followed by enter to quit.)

        When the system bindings are loaded and suspend-to-background is
        supported, that will override this binding.
        """
        event.current_buffer.insert_text(event.data)

    @handle(Keys.BracketedPaste)
    def _paste(event: E) -> None:
        """
        Pasting from clipboard.
        """
        data = event.data

        # Be sure to use \n as line ending.
        # Some terminals (Like iTerm2) seem to paste \r\n line endings in a
        # bracketed paste. See: https://github.com/ipython/ipython/issues/9737
        data = data.replace("\r\n", "\n")
        data = data.replace("\r", "\n")

        event.current_buffer.insert_text(data)

    @handle(Keys.Any, filter=in_quoted_insert, eager=True)
    def _insert_text(event: E) -> None:
        """
        Handle quoted insert.
        """
        event.current_buffer.insert_text(event.data, overwrite=False)
        event.app.quoted_insert = False

    return key_bindings
