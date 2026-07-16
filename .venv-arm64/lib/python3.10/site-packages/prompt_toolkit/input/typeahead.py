r"""
Store input key strokes if we did read more than was required.

The input classes `Vt100Input` and `Win32Input` read the input text in chunks
of a few kilobytes. This means that if we read input from stdin, it could be
that we read a couple of lines (with newlines in between) at once.

This creates a problem: potentially, we read too much from stdin. Sometimes
people paste several lines at once because they paste input in a REPL and
expect each input() call to process one line. Or they rely on type ahead
because the application can't keep up with the processing.

However, we need to read input in bigger chunks. We need this mostly to support
pasting of larger chunks of text. We don't want everything to become
unresponsive because we:
  - read one character;
  - parse one character;
  - call the key binding, which does a string operation with one character;
  - and render the user interface.
Doing text operations on single characters is very inefficient in Python, so we
prefer to work on bigger chunks of text. This is why we have to read the input
in bigger chunks.

Further, line buffering is also not an option, because it doesn't work well in
the architecture. We use lower level Posix APIs, that work better with the
event loop and so on. In fact, there is also nothing that defines that only \n
can accept the input, you could create a key binding for any key to accept the
input.

To support type ahead, this module will store all the key strokes that were
read too early, so that they can be feed into to the next `prompt()` call or to
the next prompt_toolkit `Application`.
"""

from __future__ import annotations

from collections import defaultdict

from ..key_binding import KeyPress
from .base import Input

__all__ = [
    "store_typeahead",
    "get_typeahead",
    "clear_typeahead",
]

_buffer: dict[str, list[KeyPress]] = defaultdict(list)


def store_typeahead(input_obj: Input, key_presses: list[KeyPress]) -> None:
    """
    Insert typeahead key presses for the given input.
    """
    global _buffer
    key = input_obj.typeahead_hash()
    _buffer[key].extend(key_presses)


def get_typeahead(input_obj: Input) -> list[KeyPress]:
    """
    Retrieve typeahead and reset the buffer for this input.
    """
    global _buffer

    key = input_obj.typeahead_hash()
    result = _buffer[key]
    _buffer[key] = []
    return result


def clear_typeahead(input_obj: Input) -> None:
    """
    Clear typeahead buffer.
    """
    global _buffer
    key = input_obj.typeahead_hash()
    _buffer[key] = []
