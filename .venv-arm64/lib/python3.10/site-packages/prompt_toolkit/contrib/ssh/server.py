"""
Utility for running a prompt_toolkit application in an asyncssh server.
"""

from __future__ import annotations

import asyncio
import traceback
from asyncio import get_running_loop
from typing import Any, Callable, Coroutine, TextIO, cast

import asyncssh

from prompt_toolkit.application.current import AppSession, create_app_session
from prompt_toolkit.data_structures import Size
from prompt_toolkit.input import PipeInput, create_pipe_input
from prompt_toolkit.output.vt100 import Vt100_Output

__all__ = ["PromptToolkitSSHSession", "PromptToolkitSSHServer"]


class PromptToolkitSSHSession(asyncssh.SSHServerSession):  # type: ignore
    def __init__(
        self,
        interact: Callable[[PromptToolkitSSHSession], Coroutine[Any, Any, None]],
        *,
        enable_cpr: bool,
    ) -> None:
        self.interact = interact
        self.enable_cpr = enable_cpr
        self.interact_task: asyncio.Task[None] | None = None
        self._chan: Any | None = None
        self.app_session: AppSession | None = None

        # PipInput object, for sending input in the CLI.
        # (This is something that we can use in the prompt_toolkit event loop,
        # but still write date in manually.)
        self._input: PipeInput | None = None
        self._output: Vt100_Output | None = None

        # Output object. Don't render to the real stdout, but write everything
        # in the SSH channel.
        class Stdout:
            def write(s, data: str) -> None:
                try:
                    if self._chan is not None:
                        self._chan.write(data.replace("\n", "\r\n"))
                except BrokenPipeError:
                    pass  # Channel not open for sending.

            def isatty(s) -> bool:
                return True

            def flush(s) -> None:
                pass

            @property
            def encoding(s) -> str:
                assert self._chan is not None
                return str(self._chan._orig_chan.get_encoding()[0])

        self.stdout = cast(TextIO, Stdout())

    def _get_size(self) -> Size:
        """
        Callable that returns the current `Size`, required by Vt100_Output.
        """
        if self._chan is None:
            return Size(rows=20, columns=79)
        else:
            width, height, pixwidth, pixheight = self._chan.get_terminal_size()
            return Size(rows=height, columns=width)

    def connection_made(self, chan: Any) -> None:
        self._chan = chan

    def shell_requested(self) -> bool:
        return True

    def session_started(self) -> None:
        self.interact_task = get_running_loop().create_task(self._interact())

    async def _interact(self) -> None:
        if self._chan is None:
            # Should not happen.
            raise Exception("`_interact` called before `connection_made`.")

        if hasattr(self._chan, "set_line_mode") and self._chan._editor is not None:
            # Disable the line editing provided by asyncssh. Prompt_toolkit
            # provides the line editing.
            self._chan.set_line_mode(False)

        term = self._chan.get_terminal_type()

        self._output = Vt100_Output(
            self.stdout, self._get_size, term=term, enable_cpr=self.enable_cpr
        )

        with create_pipe_input() as self._input:
            with create_app_session(input=self._input, output=self._output) as session:
                self.app_session = session
                try:
                    await self.interact(self)
                except BaseException:
                    traceback.print_exc()
                finally:
                    # Close the connection.
                    self._chan.close()
                    self._input.close()

    def terminal_size_changed(
        self, width: int, height: int, pixwidth: object, pixheight: object
    ) -> None:
        # Send resize event to the current application.
        if self.app_session and self.app_session.app:
            self.app_session.app._on_resize()

    def data_received(self, data: str, datatype: object) -> None:
        if self._input is None:
            # Should not happen.
            return

        self._input.send_text(data)


class PromptToolkitSSHServer(asyncssh.SSHServer):
    """
    Run a prompt_toolkit application over an asyncssh server.

    This takes one argument, an `interact` function, which is called for each
    connection. This should be an asynchronous function that runs the
    prompt_toolkit applications. This function runs in an `AppSession`, which
    means that we can have multiple UI interactions concurrently.

    Example usage:

    .. code:: python

        async def interact(ssh_session: PromptToolkitSSHSession) -> None:
            await yes_no_dialog("my title", "my text").run_async()

            prompt_session = PromptSession()
            text = await prompt_session.prompt_async("Type something: ")
            print_formatted_text('You said: ', text)

        server = PromptToolkitSSHServer(interact=interact)
        loop = get_running_loop()
        loop.run_until_complete(
            asyncssh.create_server(
                lambda: MySSHServer(interact),
                "",
                port,
                server_host_keys=["/etc/ssh/..."],
            )
        )
        loop.run_forever()

    :param enable_cpr: When `True`, the default, try to detect whether the SSH
        client runs in a terminal that responds to "cursor position requests".
        That way, we can properly determine how much space there is available
        for the UI (especially for drop down menus) to render.
    """

    def __init__(
        self,
        interact: Callable[[PromptToolkitSSHSession], Coroutine[Any, Any, None]],
        *,
        enable_cpr: bool = True,
    ) -> None:
        self.interact = interact
        self.enable_cpr = enable_cpr

    def begin_auth(self, username: str) -> bool:
        # No authentication.
        return False

    def session_requested(self) -> PromptToolkitSSHSession:
        return PromptToolkitSSHSession(self.interact, enable_cpr=self.enable_cpr)
