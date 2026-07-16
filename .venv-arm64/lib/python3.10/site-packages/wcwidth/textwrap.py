"""
Sequence-aware text wrapping functions.

This module provides functions for wrapping text that may contain terminal escape sequences, with
proper handling of Unicode grapheme clusters and character display widths.
"""

from __future__ import annotations

# std imports
import secrets
import textwrap

from typing import TYPE_CHECKING, Optional

# local
from ._width import width as wcwidth_width
from .grapheme import iter_graphemes
from .hyperlink import HyperlinkParams
from .sgr_state import propagate_sgr as _propagate_sgr
from .escape_sequences import ZERO_WIDTH_PATTERN, iter_sequences

if TYPE_CHECKING:  # pragma: no cover
    from typing import Any, Literal


class SequenceTextWrapper(textwrap.TextWrapper):
    """
    Sequence-aware text wrapper extending :class:`textwrap.TextWrapper`.

    This wrapper properly handles terminal escape sequences and Unicode grapheme clusters when
    calculating text width for wrapping.

    This implementation is based on the SequenceTextWrapper from the 'blessed' library, with
    contributions from Avram Lubkin and grayjk.

    The key difference from the blessed implementation is the addition of grapheme cluster support
    via :func:`~.iter_graphemes`, providing width calculation for ZWJ emoji sequences, VS-16 emojis
    and variations, regional indicator flags, and combining characters.

    OSC 8 hyperlinks are handled specially: when a hyperlink must span multiple lines, each line
    receives complete open/close sequences with a shared ``id`` parameter, ensuring terminals
    treat the fragments as a single hyperlink for hover underlining. If the original hyperlink
    already has an ``id`` parameter, it is preserved; otherwise, one is generated.
    """

    def __init__(self, width: int = 70, *,
                 control_codes: Literal['parse', 'strict', 'ignore'] = 'parse',
                 tabsize: int = 8,
                 ambiguous_width: int = 1,
                 term_program: bool | str = False,
                 **kwargs: Any) -> None:
        """
        Initialize the wrapper.

        :param width: Maximum line width in display cells.
        :param control_codes: How to handle control sequences (see :func:`~.width`).
        :param tabsize: Tab stop width for tab expansion.
        :param ambiguous_width: Width to use for East Asian Ambiguous (A) characters.
        :param term_program: Terminal software identifier for table correction.
            ``False`` (default) disables override lookup.  ``True`` reads the
            ``TERM_PROGRAM`` or ``TERM`` environment variable for auto-detection.
            Accepts a canonical terminal name matching :func:`list_term_programs`,
            such as from XTVERSION_, ENQ_, or ``TERM_PROGRAM``.

            .. versionadded:: 0.8.0
        :param kwargs: Additional arguments passed to :class:`textwrap.TextWrapper`.
        """
        super().__init__(width=width, **kwargs)
        self.control_codes = control_codes
        self.tabsize = tabsize
        self.ambiguous_width = ambiguous_width
        self.term_program = term_program

    @staticmethod
    def _next_hyperlink_id() -> str:
        """Generate unique hyperlink id as 8-character hex string."""
        return secrets.token_hex(4)

    def _width(self, text: str) -> int:
        """Measure text width accounting for sequences."""
        return wcwidth_width(text, control_codes=self.control_codes, tabsize=self.tabsize,
                             ambiguous_width=self.ambiguous_width,
                             term_program=self.term_program)

    def _strip_sequences(self, text: str) -> str:
        """Strip all terminal sequences from text."""
        result = []
        for segment, is_seq in iter_sequences(text):
            if not is_seq:
                result.append(segment)
        return ''.join(result)

    def _extract_sequences(self, text: str) -> str:
        """Extract only terminal sequences from text."""
        result = []
        for segment, is_seq in iter_sequences(text):
            if is_seq:
                result.append(segment)
        return ''.join(result)

    def _split(self, text: str) -> list[str]:  # pylint: disable=too-many-locals
        r"""
        Sequence-aware variant of :meth:`textwrap.TextWrapper._split`.

        This method ensures that terminal escape sequences don't interfere with the text splitting
        logic, particularly for hyphen-based word breaking. It builds a position mapping from
        stripped text to original text, calls the parent's _split on stripped text, then maps chunks
        back.

        OSC hyperlink sequences are treated as word boundaries::

            >>> wrap('foo \x1b]8;;https://example.com\x07link\x1b]8;;\x07 bar', 6)
            ['foo', '\x1b]8;;https://example.com\x07link\x1b]8;;\x07', 'bar']

        Both BEL (``\x07``) and ST (``\x1b\\``) terminators are supported.
        """
        # pylint: disable=too-many-locals,too-many-branches
        # Build a mapping from stripped text positions to original text positions.
        #
        # Track where each character ENDS so that sequences between characters
        # attach to the following text (not preceding text). This ensures sequences
        # aren't lost when whitespace is dropped.
        #
        # char_end[i] = position in original text right after the i-th stripped char
        char_end: list[int] = []
        stripped_text = ''
        original_pos = 0
        prev_was_hyperlink_close = False

        for segment, is_seq in iter_sequences(text):
            if not is_seq:
                # Conditionally insert space after hyperlink close to force word boundary
                if prev_was_hyperlink_close and segment and not segment[0].isspace():
                    stripped_text += ' '
                    char_end.append(original_pos)
                for char in segment:
                    original_pos += 1
                    char_end.append(original_pos)
                    stripped_text += char
                prev_was_hyperlink_close = False
            else:
                is_hyperlink_close = segment.startswith(('\x1b]8;;\x1b\\', '\x1b]8;;\x07'))

                # Conditionally insert space before OSC sequences to artificially create word
                # boundary, but *not* before hyperlink close sequences, to ensure hyperlink is
                # terminated on the same line.
                if (segment.startswith('\x1b]') and stripped_text and not
                        stripped_text[-1].isspace()):
                    if not is_hyperlink_close:
                        stripped_text += ' '
                        char_end.append(original_pos)

                # Escape sequences advance position but don't add to stripped text
                original_pos += len(segment)
                prev_was_hyperlink_close = is_hyperlink_close

        # Add sentinel for final position
        char_end.append(original_pos)

        # Use parent's _split on the stripped text
        # pylint: disable-next=protected-access
        stripped_chunks = textwrap.TextWrapper._split(self, stripped_text)

        # Handle text that contains only sequences (no visible characters).
        # Return the sequences as a single chunk to preserve them.
        if not stripped_chunks and text:
            return [text]

        # Map the chunks back to the original text with sequences
        result: list[str] = []
        stripped_pos = 0
        num_chunks = len(stripped_chunks)

        for idx, chunk in enumerate(stripped_chunks):
            chunk_len = len(chunk)

            # Start is where previous character ended (or 0 for first chunk)
            start_orig = 0 if stripped_pos == 0 else char_end[stripped_pos - 1]

            # End is where next character starts. For last chunk, use sentinel
            # to include any trailing sequences.
            if idx == num_chunks - 1:
                end_orig = char_end[-1]  # sentinel includes trailing sequences
            else:
                end_orig = char_end[stripped_pos + chunk_len - 1]

            # Extract the corresponding portion from the original text
            # Skip empty chunks (from virtual spaces inserted at OSC boundaries)
            if start_orig != end_orig:
                result.append(text[start_orig:end_orig])
            stripped_pos += chunk_len

        return result

    def _wrap_chunks(self, chunks: list[str]) -> list[str]:  # pylint: disable=too-many-branches
        """
        Wrap chunks into lines using sequence-aware width.

        Override TextWrapper._wrap_chunks to use _width instead of len. Follows stdlib's algorithm:
        greedily fill lines, handle long words.  Also handle OSC hyperlink processing. When
        hyperlinks span multiple lines, each line gets complete open/close sequences with matching
        id parameters for hover underlining continuity per OSC 8 spec.
        """
        # pylint: disable=too-many-branches,too-many-statements,too-complex,too-many-locals
        # pylint: disable=too-many-nested-blocks
        # the hyperlink code in particular really pushes the complexity rating of this method.
        # preferring to keep it "all in one method" because of so much local state and manipulation.
        if not chunks:
            return []

        if self.max_lines is not None:
            if self.max_lines > 1:
                indent = self.subsequent_indent
            else:
                indent = self.initial_indent
            if (self._width(indent)
                    + self._width(self.placeholder.lstrip())
                    > self.width):
                raise ValueError("placeholder too large for max width")

        lines: list[str] = []
        is_first_line = True

        hyperlink_state: Optional[HyperlinkParams] = None
        # Track the id we're using for the current hyperlink continuation
        current_hyperlink_id: Optional[str] = None

        # Arrange in reverse order so items can be efficiently popped
        chunks = list(reversed(chunks))

        while chunks:
            current_line: list[str] = []
            current_width = 0

            # Get the indent and available width for current line
            indent = self.initial_indent if is_first_line else self.subsequent_indent
            line_width = self.width - self._width(indent)

            # If continuing a hyperlink from previous line, prepend open sequence
            if hyperlink_state is not None:
                open_seq = HyperlinkParams(
                    url=hyperlink_state.url,
                    params=hyperlink_state.params,
                    terminator=hyperlink_state.terminator,
                ).make_open()
                chunks[-1] = open_seq + chunks[-1]

            # Drop leading whitespace (except at very start)
            # When dropping, transfer any sequences to the next chunk.
            # Only drop if there's actual whitespace text, not if it's only sequences.
            stripped = self._strip_sequences(chunks[-1])
            if self.drop_whitespace and lines and stripped and not stripped.strip():
                sequences = self._extract_sequences(chunks[-1])
                del chunks[-1]
                if sequences and chunks:
                    chunks[-1] = sequences + chunks[-1]

            # Greedily add chunks that fit
            while chunks:
                chunk = chunks[-1]
                chunk_width = self._width(chunk)

                if current_width + chunk_width <= line_width:
                    current_line.append(chunks.pop())
                    current_width += chunk_width
                else:
                    break

            # Handle chunk that's too long for any line
            if chunks and self._width(chunks[-1]) > line_width:
                self._handle_long_word(
                    chunks, current_line, current_width, line_width
                )
                current_width = self._width(''.join(current_line))
                # Remove any empty chunks left by _handle_long_word
                while chunks and not chunks[-1]:
                    del chunks[-1]

            # Drop trailing whitespace
            # When dropping, transfer any sequences to the previous chunk.
            # Only drop if there's actual whitespace text, not if it's only sequences.
            stripped_last = self._strip_sequences(current_line[-1]) if current_line else ''
            if (self.drop_whitespace and current_line and
                    stripped_last and not stripped_last.strip()):
                sequences = self._extract_sequences(current_line[-1])
                current_width -= self._width(current_line[-1])
                del current_line[-1]
                if sequences and current_line:
                    current_line[-1] = current_line[-1] + sequences

            if current_line:
                # Check whether this is a normal append or max_lines
                # truncation. Matches stdlib textwrap precedence:
                # normal if max_lines not set, not yet reached, or no
                # remaining visible content that would need truncation.
                no_more_content = (
                    not chunks or
                    self.drop_whitespace and
                    len(chunks) == 1 and
                    not self._strip_sequences(chunks[0]).strip()
                )
                if (self.max_lines is None or
                        len(lines) + 1 < self.max_lines or
                        no_more_content
                        and current_width <= line_width):
                    line_content = ''.join(current_line)

                    # Track hyperlink state through this line's content
                    new_state = self._track_hyperlink_state(line_content, hyperlink_state)

                    # If we end inside a hyperlink, append close sequence
                    if new_state is not None:
                        # Ensure we have an id for continuation
                        if current_hyperlink_id is None:
                            if 'id=' in new_state.params:
                                current_hyperlink_id = new_state.params
                            elif new_state.params:
                                # Prepend id to existing params. Per OSC 8 spec, params can have
                                # multiple key=value pairs separated by ':'.
                                current_hyperlink_id = (
                                    f'id={self._next_hyperlink_id()}:{new_state.params}')
                            else:
                                current_hyperlink_id = f'id={self._next_hyperlink_id()}'
                        line_content += HyperlinkParams(
                            terminator=new_state.terminator, url='').make_close()

                        # Also need to inject the id into the opening
                        # sequence if it didn't have one
                        if 'id=' not in new_state.params:
                            # Find and replace the original open sequence with one that has id
                            old_open = HyperlinkParams(
                                url=new_state.url,
                                params=new_state.params,
                                terminator=new_state.terminator,
                            ).make_open()
                            new_open = HyperlinkParams(
                                url=new_state.url,
                                params=current_hyperlink_id,
                                terminator=new_state.terminator,
                            ).make_open()
                            line_content = line_content.replace(old_open, new_open, 1)

                        # Update state for next line, using computed id
                        hyperlink_state = HyperlinkParams(
                            new_state.url, current_hyperlink_id, new_state.terminator)
                    else:
                        hyperlink_state = None
                        current_hyperlink_id = None  # Reset id when hyperlink closes

                    # Strip trailing whitespace when drop_whitespace is enabled
                    # (matches CPython #140627 fix behavior)
                    if self.drop_whitespace:
                        line_content = line_content.rstrip()
                    lines.append(indent + line_content)
                    is_first_line = False
                else:
                    # max_lines reached with remaining content.
                    # pop chunks until placeholder fits, then break.
                    placeholder_w = self._width(self.placeholder)
                    while current_line:
                        last_text = self._strip_sequences(current_line[-1])
                        if (last_text.strip()
                                and current_width + placeholder_w <= line_width):
                            line_content = ''.join(current_line)
                            new_state = self._track_hyperlink_state(
                                line_content, hyperlink_state)
                            if new_state is not None:
                                line_content += HyperlinkParams(
                                    terminator=new_state.terminator, url='').make_close()
                            lines.append(indent + line_content + self.placeholder)
                            break
                        current_width -= self._width(current_line[-1])
                        del current_line[-1]
                    else:
                        if lines:
                            prev_line = self._rstrip_visible(lines[-1])
                            if (self._width(prev_line) + placeholder_w
                                    <= self.width):
                                lines[-1] = prev_line + self.placeholder
                                break
                        lines.append(indent + self.placeholder.lstrip())
                    break

        return lines

    def _track_hyperlink_state(
            self, text: str,
            state: Optional[HyperlinkParams]) -> Optional[HyperlinkParams]:
        """
        Track hyperlink state through text.

        :param text: Text to scan for hyperlink sequences.
        :param state: Current state or None if outside hyperlink.
        :returns: Updated state after processing text.
        """
        for segment, is_seq in iter_sequences(text):
            if is_seq:
                parsed_link = HyperlinkParams.parse(segment)
                if parsed_link is not None and parsed_link.url:  # has URL = open
                    state = parsed_link
                elif segment.startswith(('\x1b]8;;\x1b\\', '\x1b]8;;\x07')):  # close
                    state = None
        return state

    def _handle_long_word(self, reversed_chunks: list[str],
                          cur_line: list[str], cur_len: int,
                          width: int) -> None:
        """
        Sequence-aware :meth:`textwrap.TextWrapper._handle_long_word`.

        This method ensures that word boundaries are not broken mid-sequence, and respects grapheme
        cluster boundaries when breaking long words.
        """
        if width < 1:
            space_left = 1
        else:
            space_left = width - cur_len

        chunk = reversed_chunks[-1]

        if self.break_long_words:
            break_at_hyphen = False
            hyphen_end = 0

            # Handle break_on_hyphens: find last hyphen within space_left
            if self.break_on_hyphens:
                # Strip sequences to find hyphen in logical text
                stripped = self._strip_sequences(chunk)
                if len(stripped) > space_left:
                    # Find last hyphen in the portion that fits
                    hyphen_pos = stripped.rfind('-', 0, space_left)
                    if hyphen_pos > 0 and any(c != '-' for c in stripped[:hyphen_pos]):
                        # Map back to original position including sequences
                        hyphen_end = self._map_stripped_pos_to_original(chunk, hyphen_pos + 1)
                        break_at_hyphen = True

            # Break at grapheme boundaries to avoid splitting multi-codepoint characters
            if break_at_hyphen:
                actual_end = hyphen_end
            else:
                actual_end = self._find_break_position(chunk, space_left)
                # If no progress possible (e.g., wide char exceeds line width),
                # force at least one grapheme to avoid infinite loop.
                # Only force when cur_line is empty; if line has content,
                # appending nothing is safe and the line will be committed.
                if actual_end == 0 and not cur_line:
                    actual_end = self._find_first_grapheme_end(chunk)
            cur_line.append(chunk[:actual_end])
            reversed_chunks[-1] = chunk[actual_end:]

        elif not cur_line:
            cur_line.append(reversed_chunks.pop())

    def _map_stripped_pos_to_original(self, text: str, stripped_pos: int) -> int:
        """Map a position in stripped text back to original text position."""
        stripped_idx = 0
        original_idx = 0

        for segment, is_seq in iter_sequences(text):
            if is_seq:
                original_idx += len(segment)
            elif stripped_idx + len(segment) > stripped_pos:
                # Position is within this segment
                return original_idx + (stripped_pos - stripped_idx)
            else:
                stripped_idx += len(segment)
                original_idx += len(segment)

        # Caller guarantees stripped_pos < total stripped chars, so we always
        # return from within the loop. This line satisfies the type checker.
        return original_idx  # pragma: no cover

    def _find_break_position(self, text: str, max_width: int) -> int:
        """Find string index in text that fits within max_width cells."""
        idx = 0
        width_so_far = 0

        while idx < len(text):
            char = text[idx]

            # Skip escape sequences (they don't add width)
            if char == '\x1b':
                match = ZERO_WIDTH_PATTERN.match(text, idx)
                if match:
                    idx = match.end()
                    continue

            # Get grapheme (use start= to avoid slice allocation)
            grapheme = next(iter_graphemes(text, start=idx))

            grapheme_width = self._width(grapheme)
            if width_so_far + grapheme_width > max_width:
                return idx  # Found break point

            width_so_far += grapheme_width
            idx += len(grapheme)

        # Caller guarantees chunk_width > max_width, so a grapheme always
        # exceeds and we return from within the loop. Type checker requires this.
        return idx  # pragma: no cover

    def _find_first_grapheme_end(self, text: str) -> int:
        """Find the end position of the first grapheme."""
        return len(next(iter_graphemes(text)))

    def _rstrip_visible(self, text: str) -> str:
        """Strip trailing visible whitespace, preserving trailing sequences."""
        segments = list(iter_sequences(text))
        last_vis = -1
        for i, (segment, is_seq) in enumerate(segments):
            if not is_seq and segment.rstrip():
                last_vis = i
        if last_vis == -1:
            return ''
        result = []
        for i, (segment, is_seq) in enumerate(segments):
            if i < last_vis:
                result.append(segment)
            elif i == last_vis:
                result.append(segment.rstrip())
            elif is_seq:
                result.append(segment)
        return ''.join(result)


def wrap(text: str, width: int = 70, *,
         control_codes: Literal['parse', 'strict', 'ignore'] = 'parse',
         tabsize: int = 8,
         expand_tabs: bool = True,
         replace_whitespace: bool = True,
         ambiguous_width: int = 1,
         term_program: bool | str = False,
         initial_indent: str = '',
         subsequent_indent: str = '',
         fix_sentence_endings: bool = False,
         break_long_words: bool = True,
         break_on_hyphens: bool = True,
         drop_whitespace: bool = True,
         max_lines: Optional[int] = None,
         placeholder: str = ' [...]',
         propagate_sgr: bool = True) -> list[str]:
    r"""
    Wrap text to fit within given width, returning a list of wrapped lines.

    Like :func:`textwrap.wrap`, but measures width in display cells rather than
    characters, correctly handling wide characters, combining marks, and terminal
    escape sequences.

    :param text: Text to wrap, may contain terminal sequences.
    :param width: Maximum line width in display cells.
    :param control_codes: How to handle terminal sequences (see :func:`~.width`).
    :param tabsize: Tab stop width for tab expansion.
    :param expand_tabs: If True (default), tab characters are expanded
        to spaces using ``tabsize``.
    :param replace_whitespace: If True (default), each whitespace character
        is replaced with a single space after tab expansion. When False,
        control whitespace like ``\n`` has zero display width (unlike
        :func:`textwrap.wrap` which counts ``len()``), so wrap points
        may differ from stdlib for non-space whitespace characters.
    :param ambiguous_width: Width to use for East Asian Ambiguous (A)
        characters. Default is ``1`` (narrow). Set to ``2`` for CJK contexts.
    :param term_program: Terminal software identifier for table correction.
        ``False`` (default) disables override lookup.  ``True`` reads the
        ``TERM_PROGRAM`` or ``TERM`` environment variable for auto-detection.
        Accepts a canonical terminal name matching :func:`list_term_programs`,
        such as from XTVERSION_, ENQ_, or ``TERM_PROGRAM``.

        .. versionadded:: 0.8.0
    :param initial_indent: String prepended to first line.
    :param subsequent_indent: String prepended to subsequent lines.
    :param fix_sentence_endings: If True, ensure sentences are always
        separated by exactly two spaces.
    :param break_long_words: If True, break words longer than width.
    :param break_on_hyphens: If True, allow breaking at hyphens.
    :param drop_whitespace: If True (default), whitespace at the beginning
        and end of each line (after wrapping but before indenting) is dropped.
        Set to False to preserve whitespace.
    :param max_lines: If set, output contains at most this many lines, with
        ``placeholder`` appended to the last line if the text was truncated.
    :param placeholder: String appended to the last line when text is
        truncated by ``max_lines``. Default is ``' [...]'``.
    :param propagate_sgr: If True (default), SGR (terminal styling) sequences
        are propagated across wrapped lines. Each line ends with a reset
        sequence and the next line begins with the active style restored.
    :returns: List of wrapped lines without trailing newlines.

    SGR (terminal styling) sequences are propagated across wrapped lines
    by default. Each line ends with a reset sequence and the next line
    begins with the active style restored::

        >>> wrap('\x1b[1;34mHello world\x1b[0m', width=6)
        ['\x1b[1;34mHello\x1b[0m', '\x1b[1;34mworld\x1b[0m']

    Set ``propagate_sgr=False`` to disable this behavior.

    Like :func:`textwrap.wrap`, newlines in the input text are treated as
    whitespace and collapsed. To preserve paragraph breaks, wrap each
    paragraph separately::

        >>> text = 'First line.\nSecond line.'
        >>> wrap(text, 40)  # newline collapsed to space
        ['First line. Second line.']
        >>> [line for para in text.split('\n')
        ...  for line in (wrap(para, 40) if para else [''])]
        ['First line.', 'Second line.']

    .. seealso::

       :func:`textwrap.wrap`, :class:`textwrap.TextWrapper`
           Standard library text wrapping (character-based).

       :class:`.SequenceTextWrapper`
           Class interface for advanced wrapping options.

    .. versionadded:: 0.3.0

    .. versionchanged:: 0.5.0
       Added ``propagate_sgr`` parameter (default True).

    .. versionchanged:: 0.6.0
       Added ``expand_tabs``, ``replace_whitespace``, ``fix_sentence_endings``,
       ``drop_whitespace``, ``max_lines``, and ``placeholder`` parameters.

    Example::

        >>> from wcwidth import wrap
        >>> wrap('hello world', 5)
        ['hello', 'world']
        >>> wrap('中文字符', 4)  # CJK characters (2 cells each)
        ['中文', '字符']
    """
    # pylint: disable=too-many-arguments,too-many-locals
    wrapper = SequenceTextWrapper(
        width=width,
        control_codes=control_codes,
        tabsize=tabsize,
        expand_tabs=expand_tabs,
        replace_whitespace=replace_whitespace,
        ambiguous_width=ambiguous_width,
        term_program=term_program,
        initial_indent=initial_indent,
        subsequent_indent=subsequent_indent,
        fix_sentence_endings=fix_sentence_endings,
        break_long_words=break_long_words,
        break_on_hyphens=break_on_hyphens,
        drop_whitespace=drop_whitespace,
        max_lines=max_lines,
        placeholder=placeholder,
    )
    lines = wrapper.wrap(text)

    if propagate_sgr:
        lines = _propagate_sgr(lines)

    return lines
