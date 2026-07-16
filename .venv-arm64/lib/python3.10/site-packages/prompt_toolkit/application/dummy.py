from __future__ import annotations

from typing import Callable

from prompt_toolkit.eventloop import InputHook
from prompt_toolkit.formatted_text import AnyFormattedText
from prompt_toolkit.input import DummyInput
from prompt_toolkit.output import DummyOutput

from .application import Application

__all__ = [
    "DummyApplication",
]


class DummyApplication(Application[None]):
    """
    When no :class:`.Application` is running,
    :func:`.get_app` will run an instance of this :class:`.DummyApplication` instead.
    """

    def __init__(self) -> None:
        super().__init__(output=DummyOutput(), input=DummyInput())

    def run(
        self,
        pre_run: Callable[[], None] | None = None,
        set_exception_handler: bool = True,
        handle_sigint: bool = True,
        in_thread: bool = False,
        inputhook: InputHook | None = None,
    ) -> None:
        raise NotImplementedError("A DummyApplication is not supposed to run.")

    async def run_async(
        self,
        pre_run: Callable[[], None] | None = None,
        set_exception_handler: bool = True,
        handle_sigint: bool = True,
        slow_callback_duration: float = 0.5,
    ) -> None:
        raise NotImplementedError("A DummyApplication is not supposed to run.")

    async def run_system_command(
        self,
        command: str,
        wait_for_enter: bool = True,
        display_before_text: AnyFormattedText = "",
        wait_text: str = "",
    ) -> None:
        raise NotImplementedError

    def suspend_to_background(self, suspend_group: bool = True) -> None:
        raise NotImplementedError
