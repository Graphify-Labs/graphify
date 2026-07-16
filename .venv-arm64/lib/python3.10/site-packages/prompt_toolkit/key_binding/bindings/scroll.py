"""
Key bindings, for scrolling up and down through pages.

This are separate bindings, because GNU readline doesn't have them, but
they are very useful for navigating through long multiline buffers, like in
Vi, Emacs, etc...
"""

from __future__ import annotations

from prompt_toolkit.key_binding.key_processor import KeyPressEvent

__all__ = [
    "scroll_forward",
    "scroll_backward",
    "scroll_half_page_up",
    "scroll_half_page_down",
    "scroll_one_line_up",
    "scroll_one_line_down",
]

E = KeyPressEvent


def scroll_forward(event: E, half: bool = False) -> None:
    """
    Scroll window down.
    """
    w = event.app.layout.current_window
    b = event.app.current_buffer

    if w and w.render_info:
        info = w.render_info
        ui_content = info.ui_content

        # Height to scroll.
        scroll_height = info.window_height
        if half:
            scroll_height //= 2

        # Calculate how many lines is equivalent to that vertical space.
        y = b.document.cursor_position_row + 1
        height = 0
        while y < ui_content.line_count:
            line_height = info.get_height_for_line(y)

            if height + line_height < scroll_height:
                height += line_height
                y += 1
            else:
                break

        b.cursor_position = b.document.translate_row_col_to_index(y, 0)


def scroll_backward(event: E, half: bool = False) -> None:
    """
    Scroll window up.
    """
    w = event.app.layout.current_window
    b = event.app.current_buffer

    if w and w.render_info:
        info = w.render_info

        # Height to scroll.
        scroll_height = info.window_height
        if half:
            scroll_height //= 2

        # Calculate how many lines is equivalent to that vertical space.
        y = max(0, b.document.cursor_position_row - 1)
        height = 0
        while y > 0:
            line_height = info.get_height_for_line(y)

            if height + line_height < scroll_height:
                height += line_height
                y -= 1
            else:
                break

        b.cursor_position = b.document.translate_row_col_to_index(y, 0)


def scroll_half_page_down(event: E) -> None:
    """
    Same as ControlF, but only scroll half a page.
    """
    scroll_forward(event, half=True)


def scroll_half_page_up(event: E) -> None:
    """
    Same as ControlB, but only scroll half a page.
    """
    scroll_backward(event, half=True)


def scroll_one_line_down(event: E) -> None:
    """
    scroll_offset += 1
    """
    w = event.app.layout.current_window
    b = event.app.current_buffer

    if w:
        # When the cursor is at the top, move to the next line. (Otherwise, only scroll.)
        if w.render_info:
            info = w.render_info

            if w.vertical_scroll < info.content_height - info.window_height:
                if info.cursor_position.y <= info.configured_scroll_offsets.top:
                    b.cursor_position += b.document.get_cursor_down_position()

                w.vertical_scroll += 1


def scroll_one_line_up(event: E) -> None:
    """
    scroll_offset -= 1
    """
    w = event.app.layout.current_window
    b = event.app.current_buffer

    if w:
        # When the cursor is at the bottom, move to the previous line. (Otherwise, only scroll.)
        if w.render_info:
            info = w.render_info

            if w.vertical_scroll > 0:
                first_line_height = info.get_height_for_line(info.first_visible_line())

                cursor_up = info.cursor_position.y - (
                    info.window_height
                    - 1
                    - first_line_height
                    - info.configured_scroll_offsets.bottom
                )

                # Move cursor up, as many steps as the height of the first line.
                # TODO: not entirely correct yet, in case of line wrapping and many long lines.
                for _ in range(max(0, cursor_up)):
                    b.cursor_position += b.document.get_cursor_up_position()

                # Scroll window
                w.vertical_scroll -= 1


def scroll_page_down(event: E) -> None:
    """
    Scroll page down. (Prefer the cursor at the top of the page, after scrolling.)
    """
    w = event.app.layout.current_window
    b = event.app.current_buffer

    if w and w.render_info:
        # Scroll down one page.
        line_index = max(w.render_info.last_visible_line(), w.vertical_scroll + 1)
        w.vertical_scroll = line_index

        b.cursor_position = b.document.translate_row_col_to_index(line_index, 0)
        b.cursor_position += b.document.get_start_of_line_position(
            after_whitespace=True
        )


def scroll_page_up(event: E) -> None:
    """
    Scroll page up. (Prefer the cursor at the bottom of the page, after scrolling.)
    """
    w = event.app.layout.current_window
    b = event.app.current_buffer

    if w and w.render_info:
        # Put cursor at the first visible line. (But make sure that the cursor
        # moves at least one line up.)
        line_index = max(
            0,
            min(w.render_info.first_visible_line(), b.document.cursor_position_row - 1),
        )

        b.cursor_position = b.document.translate_row_col_to_index(line_index, 0)
        b.cursor_position += b.document.get_start_of_line_position(
            after_whitespace=True
        )

        # Set the scroll offset. We can safely set it to zero; the Window will
        # make sure that it scrolls at least until the cursor becomes visible.
        w.vertical_scroll = 0
