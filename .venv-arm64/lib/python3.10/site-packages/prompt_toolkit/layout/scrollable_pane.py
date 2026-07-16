from __future__ import annotations

from prompt_toolkit.data_structures import Point
from prompt_toolkit.filters import FilterOrBool, to_filter
from prompt_toolkit.key_binding import KeyBindingsBase
from prompt_toolkit.mouse_events import MouseEvent

from .containers import Container, ScrollOffsets
from .dimension import AnyDimension, Dimension, sum_layout_dimensions, to_dimension
from .mouse_handlers import MouseHandler, MouseHandlers
from .screen import Char, Screen, WritePosition

__all__ = ["ScrollablePane"]

# Never go beyond this height, because performance will degrade.
MAX_AVAILABLE_HEIGHT = 10_000


class ScrollablePane(Container):
    """
    Container widget that exposes a larger virtual screen to its content and
    displays it in a vertical scrollbale region.

    Typically this is wrapped in a large `HSplit` container. Make sure in that
    case to not specify a `height` dimension of the `HSplit`, so that it will
    scale according to the content.

    .. note::

        If you want to display a completion menu for widgets in this
        `ScrollablePane`, then it's still a good practice to use a
        `FloatContainer` with a `CompletionsMenu` in a `Float` at the top-level
        of the layout hierarchy, rather then nesting a `FloatContainer` in this
        `ScrollablePane`. (Otherwise, it's possible that the completion menu
        is clipped.)

    :param content: The content container.
    :param scrolloffset: Try to keep the cursor within this distance from the
        top/bottom (left/right offset is not used).
    :param keep_cursor_visible: When `True`, automatically scroll the pane so
        that the cursor (of the focused window) is always visible.
    :param keep_focused_window_visible: When `True`, automatically scroll the
        pane so that the focused window is visible, or as much visible as
        possible if it doesn't completely fit the screen.
    :param max_available_height: Always constraint the height to this amount
        for performance reasons.
    :param width: When given, use this width instead of looking at the children.
    :param height: When given, use this height instead of looking at the children.
    :param show_scrollbar: When `True` display a scrollbar on the right.
    """

    def __init__(
        self,
        content: Container,
        scroll_offsets: ScrollOffsets | None = None,
        keep_cursor_visible: FilterOrBool = True,
        keep_focused_window_visible: FilterOrBool = True,
        max_available_height: int = MAX_AVAILABLE_HEIGHT,
        width: AnyDimension = None,
        height: AnyDimension = None,
        show_scrollbar: FilterOrBool = True,
        display_arrows: FilterOrBool = True,
        up_arrow_symbol: str = "^",
        down_arrow_symbol: str = "v",
    ) -> None:
        self.content = content
        self.scroll_offsets = scroll_offsets or ScrollOffsets(top=1, bottom=1)
        self.keep_cursor_visible = to_filter(keep_cursor_visible)
        self.keep_focused_window_visible = to_filter(keep_focused_window_visible)
        self.max_available_height = max_available_height
        self.width = width
        self.height = height
        self.show_scrollbar = to_filter(show_scrollbar)
        self.display_arrows = to_filter(display_arrows)
        self.up_arrow_symbol = up_arrow_symbol
        self.down_arrow_symbol = down_arrow_symbol

        self.vertical_scroll = 0

    def __repr__(self) -> str:
        return f"ScrollablePane({self.content!r})"

    def reset(self) -> None:
        self.content.reset()

    def preferred_width(self, max_available_width: int) -> Dimension:
        if self.width is not None:
            return to_dimension(self.width)

        # We're only scrolling vertical. So the preferred width is equal to
        # that of the content.
        content_width = self.content.preferred_width(max_available_width)

        # If a scrollbar needs to be displayed, add +1 to the content width.
        if self.show_scrollbar():
            return sum_layout_dimensions([Dimension.exact(1), content_width])

        return content_width

    def preferred_height(self, width: int, max_available_height: int) -> Dimension:
        if self.height is not None:
            return to_dimension(self.height)

        # Prefer a height large enough so that it fits all the content. If not,
        # we'll make the pane scrollable.
        if self.show_scrollbar():
            # If `show_scrollbar` is set. Always reserve space for the scrollbar.
            width -= 1

        dimension = self.content.preferred_height(width, self.max_available_height)

        # Only take 'preferred' into account. Min/max can be anything.
        return Dimension(min=0, preferred=dimension.preferred)

    def write_to_screen(
        self,
        screen: Screen,
        mouse_handlers: MouseHandlers,
        write_position: WritePosition,
        parent_style: str,
        erase_bg: bool,
        z_index: int | None,
    ) -> None:
        """
        Render scrollable pane content.

        This works by rendering on an off-screen canvas, and copying over the
        visible region.
        """
        show_scrollbar = self.show_scrollbar()

        if show_scrollbar:
            virtual_width = write_position.width - 1
        else:
            virtual_width = write_position.width

        # Compute preferred height again.
        virtual_height = self.content.preferred_height(
            virtual_width, self.max_available_height
        ).preferred

        # Ensure virtual height is at least the available height.
        virtual_height = max(virtual_height, write_position.height)
        virtual_height = min(virtual_height, self.max_available_height)

        # First, write the content to a virtual screen, then copy over the
        # visible part to the real screen.
        temp_screen = Screen(default_char=Char(char=" ", style=parent_style))
        temp_screen.show_cursor = screen.show_cursor
        temp_write_position = WritePosition(
            xpos=0, ypos=0, width=virtual_width, height=virtual_height
        )

        temp_mouse_handlers = MouseHandlers()

        self.content.write_to_screen(
            temp_screen,
            temp_mouse_handlers,
            temp_write_position,
            parent_style,
            erase_bg,
            z_index,
        )
        temp_screen.draw_all_floats()

        # If anything in the virtual screen is focused, move vertical scroll to
        from prompt_toolkit.application import get_app

        focused_window = get_app().layout.current_window

        try:
            visible_win_write_pos = temp_screen.visible_windows_to_write_positions[
                focused_window
            ]
        except KeyError:
            pass  # No window focused here. Don't scroll.
        else:
            # Make sure this window is visible.
            self._make_window_visible(
                write_position.height,
                virtual_height,
                visible_win_write_pos,
                temp_screen.cursor_positions.get(focused_window),
            )

        # Copy over virtual screen and zero width escapes to real screen.
        self._copy_over_screen(screen, temp_screen, write_position, virtual_width)

        # Copy over mouse handlers.
        self._copy_over_mouse_handlers(
            mouse_handlers, temp_mouse_handlers, write_position, virtual_width
        )

        # Set screen.width/height.
        ypos = write_position.ypos
        xpos = write_position.xpos

        screen.width = max(screen.width, xpos + virtual_width)
        screen.height = max(screen.height, ypos + write_position.height)

        # Copy over window write positions.
        self._copy_over_write_positions(screen, temp_screen, write_position)

        if temp_screen.show_cursor:
            screen.show_cursor = True

        # Copy over cursor positions, if they are visible.
        for window, point in temp_screen.cursor_positions.items():
            if (
                0 <= point.x < write_position.width
                and self.vertical_scroll
                <= point.y
                < write_position.height + self.vertical_scroll
            ):
                screen.cursor_positions[window] = Point(
                    x=point.x + xpos, y=point.y + ypos - self.vertical_scroll
                )

        # Copy over menu positions, but clip them to the visible area.
        for window, point in temp_screen.menu_positions.items():
            screen.menu_positions[window] = self._clip_point_to_visible_area(
                Point(x=point.x + xpos, y=point.y + ypos - self.vertical_scroll),
                write_position,
            )

        # Draw scrollbar.
        if show_scrollbar:
            self._draw_scrollbar(
                write_position,
                virtual_height,
                screen,
            )

    def _clip_point_to_visible_area(
        self, point: Point, write_position: WritePosition
    ) -> Point:
        """
        Ensure that the cursor and menu positions always are always reported
        """
        if point.x < write_position.xpos:
            point = point._replace(x=write_position.xpos)
        if point.y < write_position.ypos:
            point = point._replace(y=write_position.ypos)
        if point.x >= write_position.xpos + write_position.width:
            point = point._replace(x=write_position.xpos + write_position.width - 1)
        if point.y >= write_position.ypos + write_position.height:
            point = point._replace(y=write_position.ypos + write_position.height - 1)

        return point

    def _copy_over_screen(
        self,
        screen: Screen,
        temp_screen: Screen,
        write_position: WritePosition,
        virtual_width: int,
    ) -> None:
        """
        Copy over visible screen content and "zero width escape sequences".
        """
        ypos = write_position.ypos
        xpos = write_position.xpos

        for y in range(write_position.height):
            temp_row = temp_screen.data_buffer[y + self.vertical_scroll]
            row = screen.data_buffer[y + ypos]
            temp_zero_width_escapes = temp_screen.zero_width_escapes[
                y + self.vertical_scroll
            ]
            zero_width_escapes = screen.zero_width_escapes[y + ypos]

            for x in range(virtual_width):
                row[x + xpos] = temp_row[x]

                if x in temp_zero_width_escapes:
                    zero_width_escapes[x + xpos] = temp_zero_width_escapes[x]

    def _copy_over_mouse_handlers(
        self,
        mouse_handlers: MouseHandlers,
        temp_mouse_handlers: MouseHandlers,
        write_position: WritePosition,
        virtual_width: int,
    ) -> None:
        """
        Copy over mouse handlers from virtual screen to real screen.

        Note: we take `virtual_width` because we don't want to copy over mouse
              handlers that we possibly have behind the scrollbar.
        """
        ypos = write_position.ypos
        xpos = write_position.xpos

        # Cache mouse handlers when wrapping them. Very often the same mouse
        # handler is registered for many positions.
        mouse_handler_wrappers: dict[MouseHandler, MouseHandler] = {}

        def wrap_mouse_handler(handler: MouseHandler) -> MouseHandler:
            "Wrap mouse handler. Translate coordinates in `MouseEvent`."
            if handler not in mouse_handler_wrappers:

                def new_handler(event: MouseEvent) -> None:
                    new_event = MouseEvent(
                        position=Point(
                            x=event.position.x - xpos,
                            y=event.position.y + self.vertical_scroll - ypos,
                        ),
                        event_type=event.event_type,
                        button=event.button,
                        modifiers=event.modifiers,
                    )
                    handler(new_event)

                mouse_handler_wrappers[handler] = new_handler
            return mouse_handler_wrappers[handler]

        # Copy handlers.
        mouse_handlers_dict = mouse_handlers.mouse_handlers
        temp_mouse_handlers_dict = temp_mouse_handlers.mouse_handlers

        for y in range(write_position.height):
            if y in temp_mouse_handlers_dict:
                temp_mouse_row = temp_mouse_handlers_dict[y + self.vertical_scroll]
                mouse_row = mouse_handlers_dict[y + ypos]
                for x in range(virtual_width):
                    if x in temp_mouse_row:
                        mouse_row[x + xpos] = wrap_mouse_handler(temp_mouse_row[x])

    def _copy_over_write_positions(
        self, screen: Screen, temp_screen: Screen, write_position: WritePosition
    ) -> None:
        """
        Copy over window write positions.
        """
        ypos = write_position.ypos
        xpos = write_position.xpos

        for win, write_pos in temp_screen.visible_windows_to_write_positions.items():
            screen.visible_windows_to_write_positions[win] = WritePosition(
                xpos=write_pos.xpos + xpos,
                ypos=write_pos.ypos + ypos - self.vertical_scroll,
                # TODO: if the window is only partly visible, then truncate width/height.
                #       This could be important if we have nested ScrollablePanes.
                height=write_pos.height,
                width=write_pos.width,
            )

    def is_modal(self) -> bool:
        return self.content.is_modal()

    def get_key_bindings(self) -> KeyBindingsBase | None:
        return self.content.get_key_bindings()

    def get_children(self) -> list[Container]:
        return [self.content]

    def _make_window_visible(
        self,
        visible_height: int,
        virtual_height: int,
        visible_win_write_pos: WritePosition,
        cursor_position: Point | None,
    ) -> None:
        """
        Scroll the scrollable pane, so that this window becomes visible.

        :param visible_height: Height of this `ScrollablePane` that is rendered.
        :param virtual_height: Height of the virtual, temp screen.
        :param visible_win_write_pos: `WritePosition` of the nested window on the
            temp screen.
        :param cursor_position: The location of the cursor position of this
            window on the temp screen.
        """
        # Start with maximum allowed scroll range, and then reduce according to
        # the focused window and cursor position.
        min_scroll = 0
        max_scroll = virtual_height - visible_height

        if self.keep_cursor_visible():
            # Reduce min/max scroll according to the cursor in the focused window.
            if cursor_position is not None:
                offsets = self.scroll_offsets
                cpos_min_scroll = (
                    cursor_position.y - visible_height + 1 + offsets.bottom
                )
                cpos_max_scroll = cursor_position.y - offsets.top
                min_scroll = max(min_scroll, cpos_min_scroll)
                max_scroll = max(0, min(max_scroll, cpos_max_scroll))

        if self.keep_focused_window_visible():
            # Reduce min/max scroll according to focused window position.
            # If the window is small enough, bot the top and bottom of the window
            # should be visible.
            if visible_win_write_pos.height <= visible_height:
                window_min_scroll = (
                    visible_win_write_pos.ypos
                    + visible_win_write_pos.height
                    - visible_height
                )
                window_max_scroll = visible_win_write_pos.ypos
            else:
                # Window does not fit on the screen. Make sure at least the whole
                # screen is occupied with this window, and nothing else is shown.
                window_min_scroll = visible_win_write_pos.ypos
                window_max_scroll = (
                    visible_win_write_pos.ypos
                    + visible_win_write_pos.height
                    - visible_height
                )

            min_scroll = max(min_scroll, window_min_scroll)
            max_scroll = min(max_scroll, window_max_scroll)

        if min_scroll > max_scroll:
            min_scroll = max_scroll  # Should not happen.

        # Finally, properly clip the vertical scroll.
        if self.vertical_scroll > max_scroll:
            self.vertical_scroll = max_scroll
        if self.vertical_scroll < min_scroll:
            self.vertical_scroll = min_scroll

    def _draw_scrollbar(
        self, write_position: WritePosition, content_height: int, screen: Screen
    ) -> None:
        """
        Draw the scrollbar on the screen.

        Note: There is some code duplication with the `ScrollbarMargin`
              implementation.
        """

        window_height = write_position.height
        display_arrows = self.display_arrows()

        if display_arrows:
            window_height -= 2

        try:
            fraction_visible = write_position.height / float(content_height)
            fraction_above = self.vertical_scroll / float(content_height)

            scrollbar_height = int(
                min(window_height, max(1, window_height * fraction_visible))
            )
            scrollbar_top = int(window_height * fraction_above)
        except ZeroDivisionError:
            return
        else:

            def is_scroll_button(row: int) -> bool:
                "True if we should display a button on this row."
                return scrollbar_top <= row <= scrollbar_top + scrollbar_height

            xpos = write_position.xpos + write_position.width - 1
            ypos = write_position.ypos
            data_buffer = screen.data_buffer

            # Up arrow.
            if display_arrows:
                data_buffer[ypos][xpos] = Char(
                    self.up_arrow_symbol, "class:scrollbar.arrow"
                )
                ypos += 1

            # Scrollbar body.
            scrollbar_background = "class:scrollbar.background"
            scrollbar_background_start = "class:scrollbar.background,scrollbar.start"
            scrollbar_button = "class:scrollbar.button"
            scrollbar_button_end = "class:scrollbar.button,scrollbar.end"

            for i in range(window_height):
                style = ""
                if is_scroll_button(i):
                    if not is_scroll_button(i + 1):
                        # Give the last cell a different style, because we want
                        # to underline this.
                        style = scrollbar_button_end
                    else:
                        style = scrollbar_button
                else:
                    if is_scroll_button(i + 1):
                        style = scrollbar_background_start
                    else:
                        style = scrollbar_background

                data_buffer[ypos][xpos] = Char(" ", style)
                ypos += 1

            # Down arrow
            if display_arrows:
                data_buffer[ypos][xpos] = Char(
                    self.down_arrow_symbol, "class:scrollbar.arrow"
                )
