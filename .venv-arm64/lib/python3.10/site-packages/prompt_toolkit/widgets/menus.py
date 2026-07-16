from __future__ import annotations

from typing import Callable, Iterable, Sequence

from prompt_toolkit.application.current import get_app
from prompt_toolkit.filters import Condition
from prompt_toolkit.formatted_text.base import OneStyleAndTextTuple, StyleAndTextTuples
from prompt_toolkit.key_binding.key_bindings import KeyBindings, KeyBindingsBase
from prompt_toolkit.key_binding.key_processor import KeyPressEvent
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout.containers import (
    AnyContainer,
    ConditionalContainer,
    Container,
    Float,
    FloatContainer,
    HSplit,
    Window,
)
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.mouse_events import MouseEvent, MouseEventType
from prompt_toolkit.utils import get_cwidth
from prompt_toolkit.widgets import Shadow

from .base import Border

__all__ = [
    "MenuContainer",
    "MenuItem",
]

E = KeyPressEvent


class MenuContainer:
    """
    :param floats: List of extra Float objects to display.
    :param menu_items: List of `MenuItem` objects.
    """

    def __init__(
        self,
        body: AnyContainer,
        menu_items: list[MenuItem],
        floats: list[Float] | None = None,
        key_bindings: KeyBindingsBase | None = None,
    ) -> None:
        self.body = body
        self.menu_items = menu_items
        self.selected_menu = [0]

        # Key bindings.
        kb = KeyBindings()

        @Condition
        def in_main_menu() -> bool:
            return len(self.selected_menu) == 1

        @Condition
        def in_sub_menu() -> bool:
            return len(self.selected_menu) > 1

        # Navigation through the main menu.

        @kb.add("left", filter=in_main_menu)
        def _left(event: E) -> None:
            self.selected_menu[0] = max(0, self.selected_menu[0] - 1)

        @kb.add("right", filter=in_main_menu)
        def _right(event: E) -> None:
            self.selected_menu[0] = min(
                len(self.menu_items) - 1, self.selected_menu[0] + 1
            )

        @kb.add("down", filter=in_main_menu)
        def _down(event: E) -> None:
            self.selected_menu.append(0)

        @kb.add("c-c", filter=in_main_menu)
        @kb.add("c-g", filter=in_main_menu)
        def _cancel(event: E) -> None:
            "Leave menu."
            event.app.layout.focus_last()

        # Sub menu navigation.

        @kb.add("left", filter=in_sub_menu)
        @kb.add("c-g", filter=in_sub_menu)
        @kb.add("c-c", filter=in_sub_menu)
        def _back(event: E) -> None:
            "Go back to parent menu."
            if len(self.selected_menu) > 1:
                self.selected_menu.pop()

        @kb.add("right", filter=in_sub_menu)
        def _submenu(event: E) -> None:
            "go into sub menu."
            if self._get_menu(len(self.selected_menu) - 1).children:
                self.selected_menu.append(0)

            # If This item does not have a sub menu. Go up in the parent menu.
            elif (
                len(self.selected_menu) == 2
                and self.selected_menu[0] < len(self.menu_items) - 1
            ):
                self.selected_menu = [
                    min(len(self.menu_items) - 1, self.selected_menu[0] + 1)
                ]
                if self.menu_items[self.selected_menu[0]].children:
                    self.selected_menu.append(0)

        @kb.add("up", filter=in_sub_menu)
        def _up_in_submenu(event: E) -> None:
            "Select previous (enabled) menu item or return to main menu."
            # Look for previous enabled items in this sub menu.
            menu = self._get_menu(len(self.selected_menu) - 2)
            index = self.selected_menu[-1]

            previous_indexes = [
                i
                for i, item in enumerate(menu.children)
                if i < index and not item.disabled
            ]

            if previous_indexes:
                self.selected_menu[-1] = previous_indexes[-1]
            elif len(self.selected_menu) == 2:
                # Return to main menu.
                self.selected_menu.pop()

        @kb.add("down", filter=in_sub_menu)
        def _down_in_submenu(event: E) -> None:
            "Select next (enabled) menu item."
            menu = self._get_menu(len(self.selected_menu) - 2)
            index = self.selected_menu[-1]

            next_indexes = [
                i
                for i, item in enumerate(menu.children)
                if i > index and not item.disabled
            ]

            if next_indexes:
                self.selected_menu[-1] = next_indexes[0]

        @kb.add("enter")
        def _click(event: E) -> None:
            "Click the selected menu item."
            item = self._get_menu(len(self.selected_menu) - 1)
            if item.handler:
                event.app.layout.focus_last()
                item.handler()

        # Controls.
        self.control = FormattedTextControl(
            self._get_menu_fragments, key_bindings=kb, focusable=True, show_cursor=False
        )

        self.window = Window(height=1, content=self.control, style="class:menu-bar")

        submenu = self._submenu(0)
        submenu2 = self._submenu(1)
        submenu3 = self._submenu(2)

        @Condition
        def has_focus() -> bool:
            return get_app().layout.current_window == self.window

        self.container = FloatContainer(
            content=HSplit(
                [
                    # The titlebar.
                    self.window,
                    # The 'body', like defined above.
                    body,
                ]
            ),
            floats=[
                Float(
                    xcursor=True,
                    ycursor=True,
                    content=ConditionalContainer(
                        content=Shadow(body=submenu), filter=has_focus
                    ),
                ),
                Float(
                    attach_to_window=submenu,
                    xcursor=True,
                    ycursor=True,
                    allow_cover_cursor=True,
                    content=ConditionalContainer(
                        content=Shadow(body=submenu2),
                        filter=has_focus
                        & Condition(lambda: len(self.selected_menu) >= 1),
                    ),
                ),
                Float(
                    attach_to_window=submenu2,
                    xcursor=True,
                    ycursor=True,
                    allow_cover_cursor=True,
                    content=ConditionalContainer(
                        content=Shadow(body=submenu3),
                        filter=has_focus
                        & Condition(lambda: len(self.selected_menu) >= 2),
                    ),
                ),
                # --
            ]
            + (floats or []),
            key_bindings=key_bindings,
        )

    def _get_menu(self, level: int) -> MenuItem:
        menu = self.menu_items[self.selected_menu[0]]

        for i, index in enumerate(self.selected_menu[1:]):
            if i < level:
                try:
                    menu = menu.children[index]
                except IndexError:
                    return MenuItem("debug")

        return menu

    def _get_menu_fragments(self) -> StyleAndTextTuples:
        focused = get_app().layout.has_focus(self.window)

        # This is called during the rendering. When we discover that this
        # widget doesn't have the focus anymore. Reset menu state.
        if not focused:
            self.selected_menu = [0]

        # Generate text fragments for the main menu.
        def one_item(i: int, item: MenuItem) -> Iterable[OneStyleAndTextTuple]:
            def mouse_handler(mouse_event: MouseEvent) -> None:
                hover = mouse_event.event_type == MouseEventType.MOUSE_MOVE
                if (
                    mouse_event.event_type == MouseEventType.MOUSE_DOWN
                    or hover
                    and focused
                ):
                    # Toggle focus.
                    app = get_app()
                    if not hover:
                        if app.layout.has_focus(self.window):
                            if self.selected_menu == [i]:
                                app.layout.focus_last()
                        else:
                            app.layout.focus(self.window)
                    self.selected_menu = [i]

            yield ("class:menu-bar", " ", mouse_handler)
            if i == self.selected_menu[0] and focused:
                yield ("[SetMenuPosition]", "", mouse_handler)
                style = "class:menu-bar.selected-item"
            else:
                style = "class:menu-bar"
            yield style, item.text, mouse_handler

        result: StyleAndTextTuples = []
        for i, item in enumerate(self.menu_items):
            result.extend(one_item(i, item))

        return result

    def _submenu(self, level: int = 0) -> Window:
        def get_text_fragments() -> StyleAndTextTuples:
            result: StyleAndTextTuples = []
            if level < len(self.selected_menu):
                menu = self._get_menu(level)
                if menu.children:
                    result.append(("class:menu", Border.TOP_LEFT))
                    result.append(("class:menu", Border.HORIZONTAL * (menu.width + 4)))
                    result.append(("class:menu", Border.TOP_RIGHT))
                    result.append(("", "\n"))
                    try:
                        selected_item = self.selected_menu[level + 1]
                    except IndexError:
                        selected_item = -1

                    def one_item(
                        i: int, item: MenuItem
                    ) -> Iterable[OneStyleAndTextTuple]:
                        def mouse_handler(mouse_event: MouseEvent) -> None:
                            if item.disabled:
                                # The arrow keys can't interact with menu items that are disabled.
                                # The mouse shouldn't be able to either.
                                return
                            hover = mouse_event.event_type == MouseEventType.MOUSE_MOVE
                            if (
                                mouse_event.event_type == MouseEventType.MOUSE_UP
                                or hover
                            ):
                                app = get_app()
                                if not hover and item.handler:
                                    app.layout.focus_last()
                                    item.handler()
                                else:
                                    self.selected_menu = self.selected_menu[
                                        : level + 1
                                    ] + [i]

                        if i == selected_item:
                            yield ("[SetCursorPosition]", "")
                            style = "class:menu-bar.selected-item"
                        else:
                            style = ""

                        yield ("class:menu", Border.VERTICAL)
                        if item.text == "-":
                            yield (
                                style + "class:menu-border",
                                f"{Border.HORIZONTAL * (menu.width + 3)}",
                                mouse_handler,
                            )
                        else:
                            yield (
                                style,
                                f" {item.text}".ljust(menu.width + 3),
                                mouse_handler,
                            )

                        if item.children:
                            yield (style, ">", mouse_handler)
                        else:
                            yield (style, " ", mouse_handler)

                        if i == selected_item:
                            yield ("[SetMenuPosition]", "")
                        yield ("class:menu", Border.VERTICAL)

                        yield ("", "\n")

                    for i, item in enumerate(menu.children):
                        result.extend(one_item(i, item))

                    result.append(("class:menu", Border.BOTTOM_LEFT))
                    result.append(("class:menu", Border.HORIZONTAL * (menu.width + 4)))
                    result.append(("class:menu", Border.BOTTOM_RIGHT))
            return result

        return Window(FormattedTextControl(get_text_fragments), style="class:menu")

    @property
    def floats(self) -> list[Float] | None:
        return self.container.floats

    def __pt_container__(self) -> Container:
        return self.container


class MenuItem:
    def __init__(
        self,
        text: str = "",
        handler: Callable[[], None] | None = None,
        children: list[MenuItem] | None = None,
        shortcut: Sequence[Keys | str] | None = None,
        disabled: bool = False,
    ) -> None:
        self.text = text
        self.handler = handler
        self.children = children or []
        self.shortcut = shortcut
        self.disabled = disabled
        self.selected_item = 0

    @property
    def width(self) -> int:
        if self.children:
            return max(get_cwidth(c.text) for c in self.children)
        else:
            return 0
