from __future__ import annotations

from prompt_toolkit.key_binding.key_processor import KeyPressEvent

__all__ = [
    "focus_next",
    "focus_previous",
]

E = KeyPressEvent


def focus_next(event: E) -> None:
    """
    Focus the next visible Window.
    (Often bound to the `Tab` key.)
    """
    event.app.layout.focus_next()


def focus_previous(event: E) -> None:
    """
    Focus the previous visible Window.
    (Often bound to the `BackTab` key.)
    """
    event.app.layout.focus_previous()
