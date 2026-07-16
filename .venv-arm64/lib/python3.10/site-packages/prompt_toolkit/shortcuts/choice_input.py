from __future__ import annotations

from typing import Generic, Sequence, TypeVar

from prompt_toolkit.application import Application
from prompt_toolkit.filters import (
    Condition,
    FilterOrBool,
    is_done,
    renderer_height_is_known,
    to_filter,
)
from prompt_toolkit.formatted_text import AnyFormattedText
from prompt_toolkit.key_binding.key_bindings import (
    DynamicKeyBindings,
    KeyBindings,
    KeyBindingsBase,
    merge_key_bindings,
)
from prompt_toolkit.key_binding.key_processor import KeyPressEvent
from prompt_toolkit.layout import (
    AnyContainer,
    ConditionalContainer,
    HSplit,
    Layout,
    Window,
)
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.styles import BaseStyle, Style
from prompt_toolkit.utils import suspend_to_background_supported
from prompt_toolkit.widgets import Box, Frame, Label, RadioList

__all__ = [
    "ChoiceInput",
    "choice",
]

_T = TypeVar("_T")
E = KeyPressEvent


def create_default_choice_input_style() -> BaseStyle:
    return Style.from_dict(
        {
            "frame.border": "#884444",
            "selected-option": "bold",
        }
    )


class ChoiceInput(Generic[_T]):
    """
    Input selection prompt. Ask the user to choose among a set of options.

    Example usage::

        input_selection = ChoiceInput(
            message="Please select a dish:",
            options=[
                ("pizza", "Pizza with mushrooms"),
                ("salad", "Salad with tomatoes"),
                ("sushi", "Sushi"),
            ],
            default="pizza",
        )
        result = input_selection.prompt()

    :param message: Plain text or formatted text to be shown before the options.
    :param options: Sequence of ``(value, label)`` tuples. The labels can be
        formatted text.
    :param default: Default value. If none is given, the first option is
        considered the default.
    :param mouse_support: Enable mouse support.
    :param style: :class:`.Style` instance for the color scheme.
    :param symbol: Symbol to be displayed in front of the selected choice.
    :param bottom_toolbar: Formatted text or callable that returns formatted
        text to be displayed at the bottom of the screen.
    :param show_frame: `bool` or
        :class:`~prompt_toolkit.filters.Filter`. When True, surround the input
        with a frame.
    :param enable_interrupt: `bool` or
        :class:`~prompt_toolkit.filters.Filter`. When True, raise
        the ``interrupt_exception`` (``KeyboardInterrupt`` by default) when
        control-c has been pressed.
    :param interrupt_exception: The exception type that will be raised when
        there is a keyboard interrupt (control-c keypress).
    """

    def __init__(
        self,
        *,
        message: AnyFormattedText,
        options: Sequence[tuple[_T, AnyFormattedText]],
        default: _T | None = None,
        mouse_support: bool = False,
        style: BaseStyle | None = None,
        symbol: str = ">",
        bottom_toolbar: AnyFormattedText = None,
        show_frame: FilterOrBool = False,
        enable_suspend: FilterOrBool = False,
        enable_interrupt: FilterOrBool = True,
        interrupt_exception: type[BaseException] = KeyboardInterrupt,
        key_bindings: KeyBindingsBase | None = None,
    ) -> None:
        if style is None:
            style = create_default_choice_input_style()

        self.message = message
        self.default = default
        self.options = options
        self.mouse_support = mouse_support
        self.style = style
        self.symbol = symbol
        self.show_frame = show_frame
        self.enable_suspend = enable_suspend
        self.interrupt_exception = interrupt_exception
        self.enable_interrupt = enable_interrupt
        self.bottom_toolbar = bottom_toolbar
        self.key_bindings = key_bindings

    def _create_application(self) -> Application[_T]:
        radio_list = RadioList(
            values=self.options,
            default=self.default,
            select_on_focus=True,
            open_character="",
            select_character=self.symbol,
            close_character="",
            show_cursor=False,
            show_numbers=True,
            container_style="class:input-selection",
            default_style="class:option",
            selected_style="",
            checked_style="class:selected-option",
            number_style="class:number",
            show_scrollbar=False,
        )
        container: AnyContainer = HSplit(
            [
                Box(
                    Label(text=self.message, dont_extend_height=True),
                    padding_top=0,
                    padding_left=1,
                    padding_right=1,
                    padding_bottom=0,
                ),
                Box(
                    radio_list,
                    padding_top=0,
                    padding_left=3,
                    padding_right=1,
                    padding_bottom=0,
                ),
            ]
        )

        @Condition
        def show_frame_filter() -> bool:
            return to_filter(self.show_frame)()

        show_bottom_toolbar = (
            Condition(lambda: self.bottom_toolbar is not None)
            & ~is_done
            & renderer_height_is_known
        )

        container = ConditionalContainer(
            Frame(container),
            alternative_content=container,
            filter=show_frame_filter,
        )

        bottom_toolbar = ConditionalContainer(
            Window(
                FormattedTextControl(
                    lambda: self.bottom_toolbar, style="class:bottom-toolbar.text"
                ),
                style="class:bottom-toolbar",
                dont_extend_height=True,
                height=Dimension(min=1),
            ),
            filter=show_bottom_toolbar,
        )

        layout = Layout(
            HSplit(
                [
                    container,
                    # Add an empty window between the selection input and the
                    # bottom toolbar, if the bottom toolbar is visible, in
                    # order to allow the bottom toolbar to be displayed at the
                    # bottom of the screen.
                    ConditionalContainer(Window(), filter=show_bottom_toolbar),
                    bottom_toolbar,
                ]
            ),
            focused_element=radio_list,
        )

        kb = KeyBindings()

        @kb.add("enter", eager=True)
        def _accept_input(event: E) -> None:
            "Accept input when enter has been pressed."
            event.app.exit(result=radio_list.current_value, style="class:accepted")

        @Condition
        def enable_interrupt() -> bool:
            return to_filter(self.enable_interrupt)()

        @kb.add("c-c", filter=enable_interrupt)
        @kb.add("<sigint>", filter=enable_interrupt)
        def _keyboard_interrupt(event: E) -> None:
            "Abort when Control-C has been pressed."
            event.app.exit(exception=self.interrupt_exception(), style="class:aborting")

        suspend_supported = Condition(suspend_to_background_supported)

        @Condition
        def enable_suspend() -> bool:
            return to_filter(self.enable_suspend)()

        @kb.add("c-z", filter=suspend_supported & enable_suspend)
        def _suspend(event: E) -> None:
            """
            Suspend process to background.
            """
            event.app.suspend_to_background()

        return Application(
            layout=layout,
            full_screen=False,
            mouse_support=self.mouse_support,
            key_bindings=merge_key_bindings(
                [kb, DynamicKeyBindings(lambda: self.key_bindings)]
            ),
            style=self.style,
        )

    def prompt(self) -> _T:
        return self._create_application().run()

    async def prompt_async(self) -> _T:
        return await self._create_application().run_async()


def choice(
    message: AnyFormattedText,
    *,
    options: Sequence[tuple[_T, AnyFormattedText]],
    default: _T | None = None,
    mouse_support: bool = False,
    style: BaseStyle | None = None,
    symbol: str = ">",
    bottom_toolbar: AnyFormattedText = None,
    show_frame: bool = False,
    enable_suspend: FilterOrBool = False,
    enable_interrupt: FilterOrBool = True,
    interrupt_exception: type[BaseException] = KeyboardInterrupt,
    key_bindings: KeyBindingsBase | None = None,
) -> _T:
    """
    Choice selection prompt. Ask the user to choose among a set of options.

    Example usage::

        result = choice(
            message="Please select a dish:",
            options=[
                ("pizza", "Pizza with mushrooms"),
                ("salad", "Salad with tomatoes"),
                ("sushi", "Sushi"),
            ],
            default="pizza",
        )

    :param message: Plain text or formatted text to be shown before the options.
    :param options: Sequence of ``(value, label)`` tuples. The labels can be
        formatted text.
    :param default: Default value. If none is given, the first option is
        considered the default.
    :param mouse_support: Enable mouse support.
    :param style: :class:`.Style` instance for the color scheme.
    :param symbol: Symbol to be displayed in front of the selected choice.
    :param bottom_toolbar: Formatted text or callable that returns formatted
        text to be displayed at the bottom of the screen.
    :param show_frame: `bool` or
        :class:`~prompt_toolkit.filters.Filter`. When True, surround the input
        with a frame.
    :param enable_interrupt: `bool` or
        :class:`~prompt_toolkit.filters.Filter`. When True, raise
        the ``interrupt_exception`` (``KeyboardInterrupt`` by default) when
        control-c has been pressed.
    :param interrupt_exception: The exception type that will be raised when
        there is a keyboard interrupt (control-c keypress).
    """
    return ChoiceInput[_T](
        message=message,
        options=options,
        default=default,
        mouse_support=mouse_support,
        style=style,
        symbol=symbol,
        bottom_toolbar=bottom_toolbar,
        show_frame=show_frame,
        enable_suspend=enable_suspend,
        enable_interrupt=enable_interrupt,
        interrupt_exception=interrupt_exception,
        key_bindings=key_bindings,
    ).prompt()
