from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Callable

from prompt_toolkit.clipboard import ClipboardData

if TYPE_CHECKING:
    from .bindings.vi import TextObject
    from .key_processor import KeyPressEvent

__all__ = [
    "InputMode",
    "CharacterFind",
    "ViState",
]


class InputMode(str, Enum):
    value: str

    INSERT = "vi-insert"
    INSERT_MULTIPLE = "vi-insert-multiple"
    NAVIGATION = "vi-navigation"  # Normal mode.
    REPLACE = "vi-replace"
    REPLACE_SINGLE = "vi-replace-single"


class CharacterFind:
    def __init__(self, character: str, backwards: bool = False) -> None:
        self.character = character
        self.backwards = backwards


class ViState:
    """
    Mutable class to hold the state of the Vi navigation.
    """

    def __init__(self) -> None:
        #: None or CharacterFind instance. (This is used to repeat the last
        #: search in Vi mode, by pressing the 'n' or 'N' in navigation mode.)
        self.last_character_find: CharacterFind | None = None

        # When an operator is given and we are waiting for text object,
        # -- e.g. in the case of 'dw', after the 'd' --, an operator callback
        # is set here.
        self.operator_func: None | (Callable[[KeyPressEvent, TextObject], None]) = None
        self.operator_arg: int | None = None

        #: Named registers. Maps register name (e.g. 'a') to
        #: :class:`ClipboardData` instances.
        self.named_registers: dict[str, ClipboardData] = {}

        #: The Vi mode we're currently in to.
        self.__input_mode = InputMode.INSERT

        #: Waiting for digraph.
        self.waiting_for_digraph = False
        self.digraph_symbol1: str | None = None  # (None or a symbol.)

        #: When true, make ~ act as an operator.
        self.tilde_operator = False

        #: Register in which we are recording a macro.
        #: `None` when not recording anything.
        # Note that the recording is only stored in the register after the
        # recording is stopped. So we record in a separate `current_recording`
        # variable.
        self.recording_register: str | None = None
        self.current_recording: str = ""

        # Temporary navigation (normal) mode.
        # This happens when control-o has been pressed in insert or replace
        # mode. The user can now do one navigation action and we'll return back
        # to insert/replace.
        self.temporary_navigation_mode = False

    @property
    def input_mode(self) -> InputMode:
        "Get `InputMode`."
        return self.__input_mode

    @input_mode.setter
    def input_mode(self, value: InputMode) -> None:
        "Set `InputMode`."
        if value == InputMode.NAVIGATION:
            self.waiting_for_digraph = False
            self.operator_func = None
            self.operator_arg = None

        self.__input_mode = value

    def reset(self) -> None:
        """
        Reset state, go back to the given mode. INSERT by default.
        """
        # Go back to insert mode.
        self.input_mode = InputMode.INSERT

        self.waiting_for_digraph = False
        self.operator_func = None
        self.operator_arg = None

        # Reset recording state.
        self.recording_register = None
        self.current_recording = ""
