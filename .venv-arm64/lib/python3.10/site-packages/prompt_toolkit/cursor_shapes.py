from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Union

from prompt_toolkit.enums import EditingMode
from prompt_toolkit.key_binding.vi_state import InputMode

if TYPE_CHECKING:
    from .application import Application

__all__ = [
    "CursorShape",
    "CursorShapeConfig",
    "SimpleCursorShapeConfig",
    "ModalCursorShapeConfig",
    "DynamicCursorShapeConfig",
    "to_cursor_shape_config",
]


class CursorShape(Enum):
    # Default value that should tell the output implementation to never send
    # cursor shape escape sequences. This is the default right now, because
    # before this `CursorShape` functionality was introduced into
    # prompt_toolkit itself, people had workarounds to send cursor shapes
    # escapes into the terminal, by monkey patching some of prompt_toolkit's
    # internals. We don't want the default prompt_toolkit implementation to
    # interfere with that. E.g., IPython patches the `ViState.input_mode`
    # property. See: https://github.com/ipython/ipython/pull/13501/files
    _NEVER_CHANGE = "_NEVER_CHANGE"

    BLOCK = "BLOCK"
    BEAM = "BEAM"
    UNDERLINE = "UNDERLINE"
    BLINKING_BLOCK = "BLINKING_BLOCK"
    BLINKING_BEAM = "BLINKING_BEAM"
    BLINKING_UNDERLINE = "BLINKING_UNDERLINE"


class CursorShapeConfig(ABC):
    @abstractmethod
    def get_cursor_shape(self, application: Application[Any]) -> CursorShape:
        """
        Return the cursor shape to be used in the current state.
        """


AnyCursorShapeConfig = Union[CursorShape, CursorShapeConfig, None]


class SimpleCursorShapeConfig(CursorShapeConfig):
    """
    Always show the given cursor shape.
    """

    def __init__(self, cursor_shape: CursorShape = CursorShape._NEVER_CHANGE) -> None:
        self.cursor_shape = cursor_shape

    def get_cursor_shape(self, application: Application[Any]) -> CursorShape:
        return self.cursor_shape


class ModalCursorShapeConfig(CursorShapeConfig):
    """
    Show cursor shape according to the current input mode.
    """

    def get_cursor_shape(self, application: Application[Any]) -> CursorShape:
        if application.editing_mode == EditingMode.VI:
            if application.vi_state.input_mode in {
                InputMode.NAVIGATION,
            }:
                return CursorShape.BLOCK
            if application.vi_state.input_mode in {
                InputMode.INSERT,
                InputMode.INSERT_MULTIPLE,
            }:
                return CursorShape.BEAM
            if application.vi_state.input_mode in {
                InputMode.REPLACE,
                InputMode.REPLACE_SINGLE,
            }:
                return CursorShape.UNDERLINE
        elif application.editing_mode == EditingMode.EMACS:
            # like vi's INSERT
            return CursorShape.BEAM

        # Default
        return CursorShape.BLOCK


class DynamicCursorShapeConfig(CursorShapeConfig):
    def __init__(
        self, get_cursor_shape_config: Callable[[], AnyCursorShapeConfig]
    ) -> None:
        self.get_cursor_shape_config = get_cursor_shape_config

    def get_cursor_shape(self, application: Application[Any]) -> CursorShape:
        return to_cursor_shape_config(self.get_cursor_shape_config()).get_cursor_shape(
            application
        )


def to_cursor_shape_config(value: AnyCursorShapeConfig) -> CursorShapeConfig:
    """
    Take a `CursorShape` instance or `CursorShapeConfig` and turn it into a
    `CursorShapeConfig`.
    """
    if value is None:
        return SimpleCursorShapeConfig()

    if isinstance(value, CursorShape):
        return SimpleCursorShapeConfig(value)

    return value
