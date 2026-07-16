"""
Parser for VT100 input stream.
"""

from __future__ import annotations

import re
from typing import Callable, Dict, Generator

from ..key_binding.key_processor import KeyPress
from ..keys import Keys
from .ansi_escape_sequences import ANSI_SEQUENCES

__all__ = [
    "Vt100Parser",
]


# Regex matching any CPR response
# (Note that we use '\Z' instead of '$', because '$' could include a trailing
# newline.)
_cpr_response_re = re.compile("^" + re.escape("\x1b[") + r"\d+;\d+R\Z")

# Mouse events:
# Typical: "Esc[MaB*"  Urxvt: "Esc[96;14;13M" and for Xterm SGR: "Esc[<64;85;12M"
_mouse_event_re = re.compile("^" + re.escape("\x1b[") + r"(<?[\d;]+[mM]|M...)\Z")

# Regex matching any valid prefix of a CPR response.
# (Note that it doesn't contain the last character, the 'R'. The prefix has to
# be shorter.)
_cpr_response_prefix_re = re.compile("^" + re.escape("\x1b[") + r"[\d;]*\Z")

_mouse_event_prefix_re = re.compile("^" + re.escape("\x1b[") + r"(<?[\d;]*|M.{0,2})\Z")


class _Flush:
    """Helper object to indicate flush operation to the parser."""

    pass


class _IsPrefixOfLongerMatchCache(Dict[str, bool]):
    """
    Dictionary that maps input sequences to a boolean indicating whether there is
    any key that start with this characters.
    """

    def __missing__(self, prefix: str) -> bool:
        # (hard coded) If this could be a prefix of a CPR response, return
        # True.
        if _cpr_response_prefix_re.match(prefix) or _mouse_event_prefix_re.match(
            prefix
        ):
            result = True
        else:
            # If this could be a prefix of anything else, also return True.
            result = any(
                v
                for k, v in ANSI_SEQUENCES.items()
                if k.startswith(prefix) and k != prefix
            )

        self[prefix] = result
        return result


_IS_PREFIX_OF_LONGER_MATCH_CACHE = _IsPrefixOfLongerMatchCache()


class Vt100Parser:
    """
    Parser for VT100 input stream.
    Data can be fed through the `feed` method and the given callback will be
    called with KeyPress objects.

    ::

        def callback(key):
            pass
        i = Vt100Parser(callback)
        i.feed('data\x01...')

    :attr feed_key_callback: Function that will be called when a key is parsed.
    """

    # Lookup table of ANSI escape sequences for a VT100 terminal
    # Hint: in order to know what sequences your terminal writes to stdin, run
    #       "od -c" and start typing.
    def __init__(self, feed_key_callback: Callable[[KeyPress], None]) -> None:
        self.feed_key_callback = feed_key_callback
        self.reset()

    def reset(self, request: bool = False) -> None:
        self._in_bracketed_paste = False
        self._start_parser()

    def _start_parser(self) -> None:
        """
        Start the parser coroutine.
        """
        self._input_parser = self._input_parser_generator()
        self._input_parser.send(None)  # type: ignore

    def _get_match(self, prefix: str) -> None | Keys | tuple[Keys, ...]:
        """
        Return the key (or keys) that maps to this prefix.
        """
        # (hard coded) If we match a CPR response, return Keys.CPRResponse.
        # (This one doesn't fit in the ANSI_SEQUENCES, because it contains
        # integer variables.)
        if _cpr_response_re.match(prefix):
            return Keys.CPRResponse

        elif _mouse_event_re.match(prefix):
            return Keys.Vt100MouseEvent

        # Otherwise, use the mappings.
        try:
            return ANSI_SEQUENCES[prefix]
        except KeyError:
            return None

    def _input_parser_generator(self) -> Generator[None, str | _Flush, None]:
        """
        Coroutine (state machine) for the input parser.
        """
        prefix = ""
        retry = False
        flush = False

        while True:
            flush = False

            if retry:
                retry = False
            else:
                # Get next character.
                c = yield

                if isinstance(c, _Flush):
                    flush = True
                else:
                    prefix += c

            # If we have some data, check for matches.
            if prefix:
                is_prefix_of_longer_match = _IS_PREFIX_OF_LONGER_MATCH_CACHE[prefix]
                match = self._get_match(prefix)

                # Exact matches found, call handlers..
                if (flush or not is_prefix_of_longer_match) and match:
                    self._call_handler(match, prefix)
                    prefix = ""

                # No exact match found.
                elif (flush or not is_prefix_of_longer_match) and not match:
                    found = False
                    retry = True

                    # Loop over the input, try the longest match first and
                    # shift.
                    for i in range(len(prefix), 0, -1):
                        match = self._get_match(prefix[:i])
                        if match:
                            self._call_handler(match, prefix[:i])
                            prefix = prefix[i:]
                            found = True

                    if not found:
                        self._call_handler(prefix[0], prefix[0])
                        prefix = prefix[1:]

    def _call_handler(
        self, key: str | Keys | tuple[Keys, ...], insert_text: str
    ) -> None:
        """
        Callback to handler.
        """
        if isinstance(key, tuple):
            # Received ANSI sequence that corresponds with multiple keys
            # (probably alt+something). Handle keys individually, but only pass
            # data payload to first KeyPress (so that we won't insert it
            # multiple times).
            for i, k in enumerate(key):
                self._call_handler(k, insert_text if i == 0 else "")
        else:
            if key == Keys.BracketedPaste:
                self._in_bracketed_paste = True
                self._paste_buffer = ""
            else:
                self.feed_key_callback(KeyPress(key, insert_text))

    def feed(self, data: str) -> None:
        """
        Feed the input stream.

        :param data: Input string (unicode).
        """
        # Handle bracketed paste. (We bypass the parser that matches all other
        # key presses and keep reading input until we see the end mark.)
        # This is much faster then parsing character by character.
        if self._in_bracketed_paste:
            self._paste_buffer += data
            end_mark = "\x1b[201~"

            if end_mark in self._paste_buffer:
                end_index = self._paste_buffer.index(end_mark)

                # Feed content to key bindings.
                paste_content = self._paste_buffer[:end_index]
                self.feed_key_callback(KeyPress(Keys.BracketedPaste, paste_content))

                # Quit bracketed paste mode and handle remaining input.
                self._in_bracketed_paste = False
                remaining = self._paste_buffer[end_index + len(end_mark) :]
                self._paste_buffer = ""

                self.feed(remaining)

        # Handle normal input character by character.
        else:
            for i, c in enumerate(data):
                if self._in_bracketed_paste:
                    # Quit loop and process from this position when the parser
                    # entered bracketed paste.
                    self.feed(data[i:])
                    break
                else:
                    self._input_parser.send(c)

    def flush(self) -> None:
        """
        Flush the buffer of the input stream.

        This will allow us to handle the escape key (or maybe meta) sooner.
        The input received by the escape key is actually the same as the first
        characters of e.g. Arrow-Up, so without knowing what follows the escape
        sequence, we don't know whether escape has been pressed, or whether
        it's something else. This flush function should be called after a
        timeout, and processes everything that's still in the buffer as-is, so
        without assuming any characters will follow.
        """
        self._input_parser.send(_Flush())

    def feed_and_flush(self, data: str) -> None:
        """
        Wrapper around ``feed`` and ``flush``.
        """
        self.feed(data)
        self.flush()
