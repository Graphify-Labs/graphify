"""
Collection of reusable components for building full screen applications.
"""

from __future__ import annotations

from typing import Sequence

from prompt_toolkit.filters import has_completions, has_focus
from prompt_toolkit.formatted_text import AnyFormattedText
from prompt_toolkit.key_binding.bindings.focus import focus_next, focus_previous
from prompt_toolkit.key_binding.key_bindings import KeyBindings
from prompt_toolkit.layout.containers import (
    AnyContainer,
    DynamicContainer,
    HSplit,
    VSplit,
)
from prompt_toolkit.layout.dimension import AnyDimension
from prompt_toolkit.layout.dimension import Dimension as D

from .base import Box, Button, Frame, Shadow

__all__ = [
    "Dialog",
]


class Dialog:
    """
    Simple dialog window. This is the base for input dialogs, message dialogs
    and confirmation dialogs.

    Changing the title and body of the dialog is possible at runtime by
    assigning to the `body` and `title` attributes of this class.

    :param body: Child container object.
    :param title: Text to be displayed in the heading of the dialog.
    :param buttons: A list of `Button` widgets, displayed at the bottom.
    """

    def __init__(
        self,
        body: AnyContainer,
        title: AnyFormattedText = "",
        buttons: Sequence[Button] | None = None,
        modal: bool = True,
        width: AnyDimension = None,
        with_background: bool = False,
    ) -> None:
        self.body = body
        self.title = title

        buttons = buttons or []

        # When a button is selected, handle left/right key bindings.
        buttons_kb = KeyBindings()
        if len(buttons) > 1:
            first_selected = has_focus(buttons[0])
            last_selected = has_focus(buttons[-1])

            buttons_kb.add("left", filter=~first_selected)(focus_previous)
            buttons_kb.add("right", filter=~last_selected)(focus_next)

        frame_body: AnyContainer
        if buttons:
            frame_body = HSplit(
                [
                    # Add optional padding around the body.
                    Box(
                        body=DynamicContainer(lambda: self.body),
                        padding=D(preferred=1, max=1),
                        padding_bottom=0,
                    ),
                    # The buttons.
                    Box(
                        body=VSplit(buttons, padding=1, key_bindings=buttons_kb),
                        height=D(min=1, max=3, preferred=3),
                    ),
                ]
            )
        else:
            frame_body = body

        # Key bindings for whole dialog.
        kb = KeyBindings()
        kb.add("tab", filter=~has_completions)(focus_next)
        kb.add("s-tab", filter=~has_completions)(focus_previous)

        frame = Shadow(
            body=Frame(
                title=lambda: self.title,
                body=frame_body,
                style="class:dialog.body",
                width=(None if with_background is None else width),
                key_bindings=kb,
                modal=modal,
            )
        )

        self.container: Box | Shadow
        if with_background:
            self.container = Box(body=frame, style="class:dialog", width=width)
        else:
            self.container = frame

    def __pt_container__(self) -> AnyContainer:
        return self.container
