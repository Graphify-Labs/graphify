"""
Processors are little transformation blocks that transform the fragments list
from a buffer before the BufferControl will render it to the screen.

They can insert fragments before or after, or highlight fragments by replacing the
fragment types.
"""

from __future__ import annotations

import re
from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING, Callable, Hashable, cast

from prompt_toolkit.application.current import get_app
from prompt_toolkit.cache import SimpleCache
from prompt_toolkit.document import Document
from prompt_toolkit.filters import FilterOrBool, to_filter, vi_insert_multiple_mode
from prompt_toolkit.formatted_text import (
    AnyFormattedText,
    StyleAndTextTuples,
    to_formatted_text,
)
from prompt_toolkit.formatted_text.utils import fragment_list_len, fragment_list_to_text
from prompt_toolkit.search import SearchDirection
from prompt_toolkit.utils import to_int, to_str

from .utils import explode_text_fragments

if TYPE_CHECKING:
    from .controls import BufferControl, UIContent

__all__ = [
    "Processor",
    "TransformationInput",
    "Transformation",
    "DummyProcessor",
    "HighlightSearchProcessor",
    "HighlightIncrementalSearchProcessor",
    "HighlightSelectionProcessor",
    "PasswordProcessor",
    "HighlightMatchingBracketProcessor",
    "DisplayMultipleCursors",
    "BeforeInput",
    "ShowArg",
    "AfterInput",
    "AppendAutoSuggestion",
    "ConditionalProcessor",
    "ShowLeadingWhiteSpaceProcessor",
    "ShowTrailingWhiteSpaceProcessor",
    "TabsProcessor",
    "ReverseSearchProcessor",
    "DynamicProcessor",
    "merge_processors",
]


class Processor(metaclass=ABCMeta):
    """
    Manipulate the fragments for a given line in a
    :class:`~prompt_toolkit.layout.controls.BufferControl`.
    """

    @abstractmethod
    def apply_transformation(
        self, transformation_input: TransformationInput
    ) -> Transformation:
        """
        Apply transformation. Returns a :class:`.Transformation` instance.

        :param transformation_input: :class:`.TransformationInput` object.
        """
        return Transformation(transformation_input.fragments)


SourceToDisplay = Callable[[int], int]
DisplayToSource = Callable[[int], int]


class TransformationInput:
    """
    :param buffer_control: :class:`.BufferControl` instance.
    :param lineno: The number of the line to which we apply the processor.
    :param source_to_display: A function that returns the position in the
        `fragments` for any position in the source string. (This takes
        previous processors into account.)
    :param fragments: List of fragments that we can transform. (Received from the
        previous processor.)
    :param get_line: Optional ; a callable that returns the fragments of another
        line in the  current buffer; This can be used to create processors capable
        of affecting transforms across multiple lines.
    """

    def __init__(
        self,
        buffer_control: BufferControl,
        document: Document,
        lineno: int,
        source_to_display: SourceToDisplay,
        fragments: StyleAndTextTuples,
        width: int,
        height: int,
        get_line: Callable[[int], StyleAndTextTuples] | None = None,
    ) -> None:
        self.buffer_control = buffer_control
        self.document = document
        self.lineno = lineno
        self.source_to_display = source_to_display
        self.fragments = fragments
        self.width = width
        self.height = height
        self.get_line = get_line

    def unpack(
        self,
    ) -> tuple[
        BufferControl, Document, int, SourceToDisplay, StyleAndTextTuples, int, int
    ]:
        return (
            self.buffer_control,
            self.document,
            self.lineno,
            self.source_to_display,
            self.fragments,
            self.width,
            self.height,
        )


class Transformation:
    """
    Transformation result, as returned by :meth:`.Processor.apply_transformation`.

    Important: Always make sure that the length of `document.text` is equal to
               the length of all the text in `fragments`!

    :param fragments: The transformed fragments. To be displayed, or to pass to
        the next processor.
    :param source_to_display: Cursor position transformation from original
        string to transformed string.
    :param display_to_source: Cursor position transformed from source string to
        original string.
    """

    def __init__(
        self,
        fragments: StyleAndTextTuples,
        source_to_display: SourceToDisplay | None = None,
        display_to_source: DisplayToSource | None = None,
    ) -> None:
        self.fragments = fragments
        self.source_to_display = source_to_display or (lambda i: i)
        self.display_to_source = display_to_source or (lambda i: i)


class DummyProcessor(Processor):
    """
    A `Processor` that doesn't do anything.
    """

    def apply_transformation(
        self, transformation_input: TransformationInput
    ) -> Transformation:
        return Transformation(transformation_input.fragments)


class HighlightSearchProcessor(Processor):
    """
    Processor that highlights search matches in the document.
    Note that this doesn't support multiline search matches yet.

    The style classes 'search' and 'search.current' will be applied to the
    content.
    """

    _classname = "search"
    _classname_current = "search.current"

    def _get_search_text(self, buffer_control: BufferControl) -> str:
        """
        The text we are searching for.
        """
        return buffer_control.search_state.text

    def apply_transformation(
        self, transformation_input: TransformationInput
    ) -> Transformation:
        (
            buffer_control,
            document,
            lineno,
            source_to_display,
            fragments,
            _,
            _,
        ) = transformation_input.unpack()

        search_text = self._get_search_text(buffer_control)
        searchmatch_fragment = f" class:{self._classname} "
        searchmatch_current_fragment = f" class:{self._classname_current} "

        if search_text and not get_app().is_done:
            # For each search match, replace the style string.
            line_text = fragment_list_to_text(fragments)
            fragments = explode_text_fragments(fragments)

            if buffer_control.search_state.ignore_case():
                flags = re.IGNORECASE
            else:
                flags = re.RegexFlag(0)

            # Get cursor column.
            cursor_column: int | None
            if document.cursor_position_row == lineno:
                cursor_column = source_to_display(document.cursor_position_col)
            else:
                cursor_column = None

            for match in re.finditer(re.escape(search_text), line_text, flags=flags):
                if cursor_column is not None:
                    on_cursor = match.start() <= cursor_column < match.end()
                else:
                    on_cursor = False

                for i in range(match.start(), match.end()):
                    old_fragment, text, *_ = fragments[i]
                    if on_cursor:
                        fragments[i] = (
                            old_fragment + searchmatch_current_fragment,
                            fragments[i][1],
                        )
                    else:
                        fragments[i] = (
                            old_fragment + searchmatch_fragment,
                            fragments[i][1],
                        )

        return Transformation(fragments)


class HighlightIncrementalSearchProcessor(HighlightSearchProcessor):
    """
    Highlight the search terms that are used for highlighting the incremental
    search. The style class 'incsearch' will be applied to the content.

    Important: this requires the `preview_search=True` flag to be set for the
    `BufferControl`. Otherwise, the cursor position won't be set to the search
    match while searching, and nothing happens.
    """

    _classname = "incsearch"
    _classname_current = "incsearch.current"

    def _get_search_text(self, buffer_control: BufferControl) -> str:
        """
        The text we are searching for.
        """
        # When the search buffer has focus, take that text.
        search_buffer = buffer_control.search_buffer
        if search_buffer is not None and search_buffer.text:
            return search_buffer.text
        return ""


class HighlightSelectionProcessor(Processor):
    """
    Processor that highlights the selection in the document.
    """

    def apply_transformation(
        self, transformation_input: TransformationInput
    ) -> Transformation:
        (
            buffer_control,
            document,
            lineno,
            source_to_display,
            fragments,
            _,
            _,
        ) = transformation_input.unpack()

        selected_fragment = " class:selected "

        # In case of selection, highlight all matches.
        selection_at_line = document.selection_range_at_line(lineno)

        if selection_at_line:
            from_, to = selection_at_line
            from_ = source_to_display(from_)
            to = source_to_display(to)

            fragments = explode_text_fragments(fragments)

            if from_ == 0 and to == 0 and len(fragments) == 0:
                # When this is an empty line, insert a space in order to
                # visualize the selection.
                return Transformation([(selected_fragment, " ")])
            else:
                for i in range(from_, to):
                    if i < len(fragments):
                        old_fragment, old_text, *_ = fragments[i]
                        fragments[i] = (old_fragment + selected_fragment, old_text)
                    elif i == len(fragments):
                        fragments.append((selected_fragment, " "))

        return Transformation(fragments)


class PasswordProcessor(Processor):
    """
    Processor that masks the input. (For passwords.)

    :param char: (string) Character to be used. "*" by default.
    """

    def __init__(self, char: str = "*") -> None:
        self.char = char

    def apply_transformation(self, ti: TransformationInput) -> Transformation:
        fragments: StyleAndTextTuples = cast(
            StyleAndTextTuples,
            [
                (style, self.char * len(text), *handler)
                for style, text, *handler in ti.fragments
            ],
        )

        return Transformation(fragments)


class HighlightMatchingBracketProcessor(Processor):
    """
    When the cursor is on or right after a bracket, it highlights the matching
    bracket.

    :param max_cursor_distance: Only highlight matching brackets when the
        cursor is within this distance. (From inside a `Processor`, we can't
        know which lines will be visible on the screen. But we also don't want
        to scan the whole document for matching brackets on each key press, so
        we limit to this value.)
    """

    _closing_braces = "])}>"

    def __init__(
        self, chars: str = "[](){}<>", max_cursor_distance: int = 1000
    ) -> None:
        self.chars = chars
        self.max_cursor_distance = max_cursor_distance

        self._positions_cache: SimpleCache[Hashable, list[tuple[int, int]]] = (
            SimpleCache(maxsize=8)
        )

    def _get_positions_to_highlight(self, document: Document) -> list[tuple[int, int]]:
        """
        Return a list of (row, col) tuples that need to be highlighted.
        """
        pos: int | None

        # Try for the character under the cursor.
        if document.current_char and document.current_char in self.chars:
            pos = document.find_matching_bracket_position(
                start_pos=document.cursor_position - self.max_cursor_distance,
                end_pos=document.cursor_position + self.max_cursor_distance,
            )

        # Try for the character before the cursor.
        elif (
            document.char_before_cursor
            and document.char_before_cursor in self._closing_braces
            and document.char_before_cursor in self.chars
        ):
            document = Document(document.text, document.cursor_position - 1)

            pos = document.find_matching_bracket_position(
                start_pos=document.cursor_position - self.max_cursor_distance,
                end_pos=document.cursor_position + self.max_cursor_distance,
            )
        else:
            pos = None

        # Return a list of (row, col) tuples that need to be highlighted.
        if pos:
            pos += document.cursor_position  # pos is relative.
            row, col = document.translate_index_to_position(pos)
            return [
                (row, col),
                (document.cursor_position_row, document.cursor_position_col),
            ]
        else:
            return []

    def apply_transformation(
        self, transformation_input: TransformationInput
    ) -> Transformation:
        (
            buffer_control,
            document,
            lineno,
            source_to_display,
            fragments,
            _,
            _,
        ) = transformation_input.unpack()

        # When the application is in the 'done' state, don't highlight.
        if get_app().is_done:
            return Transformation(fragments)

        # Get the highlight positions.
        key = (get_app().render_counter, document.text, document.cursor_position)
        positions = self._positions_cache.get(
            key, lambda: self._get_positions_to_highlight(document)
        )

        # Apply if positions were found at this line.
        if positions:
            for row, col in positions:
                if row == lineno:
                    col = source_to_display(col)
                    fragments = explode_text_fragments(fragments)
                    style, text, *_ = fragments[col]

                    if col == document.cursor_position_col:
                        style += " class:matching-bracket.cursor "
                    else:
                        style += " class:matching-bracket.other "

                    fragments[col] = (style, text)

        return Transformation(fragments)


class DisplayMultipleCursors(Processor):
    """
    When we're in Vi block insert mode, display all the cursors.
    """

    def apply_transformation(
        self, transformation_input: TransformationInput
    ) -> Transformation:
        (
            buffer_control,
            document,
            lineno,
            source_to_display,
            fragments,
            _,
            _,
        ) = transformation_input.unpack()

        buff = buffer_control.buffer

        if vi_insert_multiple_mode():
            cursor_positions = buff.multiple_cursor_positions
            fragments = explode_text_fragments(fragments)

            # If any cursor appears on the current line, highlight that.
            start_pos = document.translate_row_col_to_index(lineno, 0)
            end_pos = start_pos + len(document.lines[lineno])

            fragment_suffix = " class:multiple-cursors"

            for p in cursor_positions:
                if start_pos <= p <= end_pos:
                    column = source_to_display(p - start_pos)

                    # Replace fragment.
                    try:
                        style, text, *_ = fragments[column]
                    except IndexError:
                        # Cursor needs to be displayed after the current text.
                        fragments.append((fragment_suffix, " "))
                    else:
                        style += fragment_suffix
                        fragments[column] = (style, text)

            return Transformation(fragments)
        else:
            return Transformation(fragments)


class BeforeInput(Processor):
    """
    Insert text before the input.

    :param text: This can be either plain text or formatted text
        (or a callable that returns any of those).
    :param style: style to be applied to this prompt/prefix.
    """

    def __init__(self, text: AnyFormattedText, style: str = "") -> None:
        self.text = text
        self.style = style

    def apply_transformation(self, ti: TransformationInput) -> Transformation:
        source_to_display: SourceToDisplay | None
        display_to_source: DisplayToSource | None

        if ti.lineno == 0:
            # Get fragments.
            fragments_before = to_formatted_text(self.text, self.style)
            fragments = fragments_before + ti.fragments

            shift_position = fragment_list_len(fragments_before)
            source_to_display = lambda i: i + shift_position
            display_to_source = lambda i: i - shift_position
        else:
            fragments = ti.fragments
            source_to_display = None
            display_to_source = None

        return Transformation(
            fragments,
            source_to_display=source_to_display,
            display_to_source=display_to_source,
        )

    def __repr__(self) -> str:
        return f"BeforeInput({self.text!r}, {self.style!r})"


class ShowArg(BeforeInput):
    """
    Display the 'arg' in front of the input.

    This was used by the `PromptSession`, but now it uses the
    `Window.get_line_prefix` function instead.
    """

    def __init__(self) -> None:
        super().__init__(self._get_text_fragments)

    def _get_text_fragments(self) -> StyleAndTextTuples:
        app = get_app()
        if app.key_processor.arg is None:
            return []
        else:
            arg = app.key_processor.arg

            return [
                ("class:prompt.arg", "(arg: "),
                ("class:prompt.arg.text", str(arg)),
                ("class:prompt.arg", ") "),
            ]

    def __repr__(self) -> str:
        return "ShowArg()"


class AfterInput(Processor):
    """
    Insert text after the input.

    :param text: This can be either plain text or formatted text
        (or a callable that returns any of those).
    :param style: style to be applied to this prompt/prefix.
    """

    def __init__(self, text: AnyFormattedText, style: str = "") -> None:
        self.text = text
        self.style = style

    def apply_transformation(self, ti: TransformationInput) -> Transformation:
        # Insert fragments after the last line.
        if ti.lineno == ti.document.line_count - 1:
            # Get fragments.
            fragments_after = to_formatted_text(self.text, self.style)
            return Transformation(fragments=ti.fragments + fragments_after)
        else:
            return Transformation(fragments=ti.fragments)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.text!r}, style={self.style!r})"


class AppendAutoSuggestion(Processor):
    """
    Append the auto suggestion to the input.
    (The user can then press the right arrow the insert the suggestion.)
    """

    def __init__(self, style: str = "class:auto-suggestion") -> None:
        self.style = style

    def apply_transformation(self, ti: TransformationInput) -> Transformation:
        # Insert fragments after the last line.
        if ti.lineno == ti.document.line_count - 1:
            buffer = ti.buffer_control.buffer

            if buffer.suggestion and ti.document.is_cursor_at_the_end:
                suggestion = buffer.suggestion.text
            else:
                suggestion = ""

            return Transformation(fragments=ti.fragments + [(self.style, suggestion)])
        else:
            return Transformation(fragments=ti.fragments)


class ShowLeadingWhiteSpaceProcessor(Processor):
    """
    Make leading whitespace visible.

    :param get_char: Callable that returns one character.
    """

    def __init__(
        self,
        get_char: Callable[[], str] | None = None,
        style: str = "class:leading-whitespace",
    ) -> None:
        def default_get_char() -> str:
            if "\xb7".encode(get_app().output.encoding(), "replace") == b"?":
                return "."
            else:
                return "\xb7"

        self.style = style
        self.get_char = get_char or default_get_char

    def apply_transformation(self, ti: TransformationInput) -> Transformation:
        fragments = ti.fragments

        # Walk through all te fragments.
        if fragments and fragment_list_to_text(fragments).startswith(" "):
            t = (self.style, self.get_char())
            fragments = explode_text_fragments(fragments)

            for i in range(len(fragments)):
                if fragments[i][1] == " ":
                    fragments[i] = t
                else:
                    break

        return Transformation(fragments)


class ShowTrailingWhiteSpaceProcessor(Processor):
    """
    Make trailing whitespace visible.

    :param get_char: Callable that returns one character.
    """

    def __init__(
        self,
        get_char: Callable[[], str] | None = None,
        style: str = "class:training-whitespace",
    ) -> None:
        def default_get_char() -> str:
            if "\xb7".encode(get_app().output.encoding(), "replace") == b"?":
                return "."
            else:
                return "\xb7"

        self.style = style
        self.get_char = get_char or default_get_char

    def apply_transformation(self, ti: TransformationInput) -> Transformation:
        fragments = ti.fragments

        if fragments and fragments[-1][1].endswith(" "):
            t = (self.style, self.get_char())
            fragments = explode_text_fragments(fragments)

            # Walk backwards through all te fragments and replace whitespace.
            for i in range(len(fragments) - 1, -1, -1):
                char = fragments[i][1]
                if char == " ":
                    fragments[i] = t
                else:
                    break

        return Transformation(fragments)


class TabsProcessor(Processor):
    """
    Render tabs as spaces (instead of ^I) or make them visible (for instance,
    by replacing them with dots.)

    :param tabstop: Horizontal space taken by a tab. (`int` or callable that
        returns an `int`).
    :param char1: Character or callable that returns a character (text of
        length one). This one is used for the first space taken by the tab.
    :param char2: Like `char1`, but for the rest of the space.
    """

    def __init__(
        self,
        tabstop: int | Callable[[], int] = 4,
        char1: str | Callable[[], str] = "|",
        char2: str | Callable[[], str] = "\u2508",
        style: str = "class:tab",
    ) -> None:
        self.char1 = char1
        self.char2 = char2
        self.tabstop = tabstop
        self.style = style

    def apply_transformation(self, ti: TransformationInput) -> Transformation:
        tabstop = to_int(self.tabstop)
        style = self.style

        # Create separator for tabs.
        separator1 = to_str(self.char1)
        separator2 = to_str(self.char2)

        # Transform fragments.
        fragments = explode_text_fragments(ti.fragments)

        position_mappings = {}
        result_fragments: StyleAndTextTuples = []
        pos = 0

        for i, fragment_and_text in enumerate(fragments):
            position_mappings[i] = pos

            if fragment_and_text[1] == "\t":
                # Calculate how many characters we have to insert.
                count = tabstop - (pos % tabstop)
                if count == 0:
                    count = tabstop

                # Insert tab.
                result_fragments.append((style, separator1))
                result_fragments.append((style, separator2 * (count - 1)))
                pos += count
            else:
                result_fragments.append(fragment_and_text)
                pos += 1

        position_mappings[len(fragments)] = pos
        # Add `pos+1` to mapping, because the cursor can be right after the
        # line as well.
        position_mappings[len(fragments) + 1] = pos + 1

        def source_to_display(from_position: int) -> int:
            "Maps original cursor position to the new one."
            return position_mappings[from_position]

        def display_to_source(display_pos: int) -> int:
            "Maps display cursor position to the original one."
            position_mappings_reversed = {v: k for k, v in position_mappings.items()}

            while display_pos >= 0:
                try:
                    return position_mappings_reversed[display_pos]
                except KeyError:
                    display_pos -= 1
            return 0

        return Transformation(
            result_fragments,
            source_to_display=source_to_display,
            display_to_source=display_to_source,
        )


class ReverseSearchProcessor(Processor):
    """
    Process to display the "(reverse-i-search)`...`:..." stuff around
    the search buffer.

    Note: This processor is meant to be applied to the BufferControl that
    contains the search buffer, it's not meant for the original input.
    """

    _excluded_input_processors: list[type[Processor]] = [
        HighlightSearchProcessor,
        HighlightSelectionProcessor,
        BeforeInput,
        AfterInput,
    ]

    def _get_main_buffer(self, buffer_control: BufferControl) -> BufferControl | None:
        from prompt_toolkit.layout.controls import BufferControl

        prev_control = get_app().layout.search_target_buffer_control
        if (
            isinstance(prev_control, BufferControl)
            and prev_control.search_buffer_control == buffer_control
        ):
            return prev_control
        return None

    def _content(
        self, main_control: BufferControl, ti: TransformationInput
    ) -> UIContent:
        from prompt_toolkit.layout.controls import BufferControl

        # Emulate the BufferControl through which we are searching.
        # For this we filter out some of the input processors.
        excluded_processors = tuple(self._excluded_input_processors)

        def filter_processor(item: Processor) -> Processor | None:
            """Filter processors from the main control that we want to disable
            here. This returns either an accepted processor or None."""
            # For a `_MergedProcessor`, check each individual processor, recursively.
            if isinstance(item, _MergedProcessor):
                accepted_processors = [filter_processor(p) for p in item.processors]
                return merge_processors(
                    [p for p in accepted_processors if p is not None]
                )

            # For a `ConditionalProcessor`, check the body.
            elif isinstance(item, ConditionalProcessor):
                p = filter_processor(item.processor)
                if p:
                    return ConditionalProcessor(p, item.filter)

            # Otherwise, check the processor itself.
            else:
                if not isinstance(item, excluded_processors):
                    return item

            return None

        filtered_processor = filter_processor(
            merge_processors(main_control.input_processors or [])
        )
        highlight_processor = HighlightIncrementalSearchProcessor()

        if filtered_processor:
            new_processors = [filtered_processor, highlight_processor]
        else:
            new_processors = [highlight_processor]

        from .controls import SearchBufferControl

        assert isinstance(ti.buffer_control, SearchBufferControl)

        buffer_control = BufferControl(
            buffer=main_control.buffer,
            input_processors=new_processors,
            include_default_input_processors=False,
            lexer=main_control.lexer,
            preview_search=True,
            search_buffer_control=ti.buffer_control,
        )

        return buffer_control.create_content(ti.width, ti.height, preview_search=True)

    def apply_transformation(self, ti: TransformationInput) -> Transformation:
        from .controls import SearchBufferControl

        assert isinstance(ti.buffer_control, SearchBufferControl), (
            "`ReverseSearchProcessor` should be applied to a `SearchBufferControl` only."
        )

        source_to_display: SourceToDisplay | None
        display_to_source: DisplayToSource | None

        main_control = self._get_main_buffer(ti.buffer_control)

        if ti.lineno == 0 and main_control:
            content = self._content(main_control, ti)

            # Get the line from the original document for this search.
            line_fragments = content.get_line(content.cursor_position.y)

            if main_control.search_state.direction == SearchDirection.FORWARD:
                direction_text = "i-search"
            else:
                direction_text = "reverse-i-search"

            fragments_before: StyleAndTextTuples = [
                ("class:prompt.search", "("),
                ("class:prompt.search", direction_text),
                ("class:prompt.search", ")`"),
            ]

            fragments = (
                fragments_before
                + [
                    ("class:prompt.search.text", fragment_list_to_text(ti.fragments)),
                    ("", "': "),
                ]
                + line_fragments
            )

            shift_position = fragment_list_len(fragments_before)
            source_to_display = lambda i: i + shift_position
            display_to_source = lambda i: i - shift_position
        else:
            source_to_display = None
            display_to_source = None
            fragments = ti.fragments

        return Transformation(
            fragments,
            source_to_display=source_to_display,
            display_to_source=display_to_source,
        )


class ConditionalProcessor(Processor):
    """
    Processor that applies another processor, according to a certain condition.
    Example::

        # Create a function that returns whether or not the processor should
        # currently be applied.
        def highlight_enabled():
            return true_or_false

        # Wrapped it in a `ConditionalProcessor` for usage in a `BufferControl`.
        BufferControl(input_processors=[
            ConditionalProcessor(HighlightSearchProcessor(),
                                 Condition(highlight_enabled))])

    :param processor: :class:`.Processor` instance.
    :param filter: :class:`~prompt_toolkit.filters.Filter` instance.
    """

    def __init__(self, processor: Processor, filter: FilterOrBool) -> None:
        self.processor = processor
        self.filter = to_filter(filter)

    def apply_transformation(
        self, transformation_input: TransformationInput
    ) -> Transformation:
        # Run processor when enabled.
        if self.filter():
            return self.processor.apply_transformation(transformation_input)
        else:
            return Transformation(transformation_input.fragments)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(processor={self.processor!r}, filter={self.filter!r})"


class DynamicProcessor(Processor):
    """
    Processor class that dynamically returns any Processor.

    :param get_processor: Callable that returns a :class:`.Processor` instance.
    """

    def __init__(self, get_processor: Callable[[], Processor | None]) -> None:
        self.get_processor = get_processor

    def apply_transformation(self, ti: TransformationInput) -> Transformation:
        processor = self.get_processor() or DummyProcessor()
        return processor.apply_transformation(ti)


def merge_processors(processors: list[Processor]) -> Processor:
    """
    Merge multiple `Processor` objects into one.
    """
    if len(processors) == 0:
        return DummyProcessor()

    if len(processors) == 1:
        return processors[0]  # Nothing to merge.

    return _MergedProcessor(processors)


class _MergedProcessor(Processor):
    """
    Processor that groups multiple other `Processor` objects, but exposes an
    API as if it is one `Processor`.
    """

    def __init__(self, processors: list[Processor]):
        self.processors = processors

    def apply_transformation(self, ti: TransformationInput) -> Transformation:
        source_to_display_functions = [ti.source_to_display]
        display_to_source_functions = []
        fragments = ti.fragments

        def source_to_display(i: int) -> int:
            """Translate x position from the buffer to the x position in the
            processor fragments list."""
            for f in source_to_display_functions:
                i = f(i)
            return i

        for p in self.processors:
            transformation = p.apply_transformation(
                TransformationInput(
                    ti.buffer_control,
                    ti.document,
                    ti.lineno,
                    source_to_display,
                    fragments,
                    ti.width,
                    ti.height,
                    ti.get_line,
                )
            )
            fragments = transformation.fragments
            display_to_source_functions.append(transformation.display_to_source)
            source_to_display_functions.append(transformation.source_to_display)

        def display_to_source(i: int) -> int:
            for f in reversed(display_to_source_functions):
                i = f(i)
            return i

        # In the case of a nested _MergedProcessor, each processor wants to
        # receive a 'source_to_display' function (as part of the
        # TransformationInput) that has everything in the chain before
        # included, because it can be called as part of the
        # `apply_transformation` function. However, this first
        # `source_to_display` should not be part of the output that we are
        # returning. (This is the most consistent with `display_to_source`.)
        del source_to_display_functions[:1]

        return Transformation(fragments, source_to_display, display_to_source)
