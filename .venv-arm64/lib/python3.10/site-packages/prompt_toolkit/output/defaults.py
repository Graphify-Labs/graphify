from __future__ import annotations

import sys
from typing import TYPE_CHECKING, TextIO, cast

from prompt_toolkit.utils import (
    get_bell_environment_variable,
    get_term_environment_variable,
    is_conemu_ansi,
)

from .base import DummyOutput, Output
from .color_depth import ColorDepth
from .plain_text import PlainTextOutput

if TYPE_CHECKING:
    from prompt_toolkit.patch_stdout import StdoutProxy


__all__ = [
    "create_output",
]


def create_output(
    stdout: TextIO | StdoutProxy | None = None, always_prefer_tty: bool = False
) -> Output:
    """
    Return an :class:`~prompt_toolkit.output.Output` instance for the command
    line.

    :param stdout: The stdout object
    :param always_prefer_tty: When set, look for `sys.stderr` if `sys.stdout`
        is not a TTY. Useful if `sys.stdout` is redirected to a file, but we
        still want user input and output on the terminal.

        By default, this is `False`. If `sys.stdout` is not a terminal (maybe
        it's redirected to a file), then a `PlainTextOutput` will be returned.
        That way, tools like `print_formatted_text` will write plain text into
        that file.
    """
    # Consider TERM, PROMPT_TOOLKIT_BELL, and PROMPT_TOOLKIT_COLOR_DEPTH
    # environment variables. Notice that PROMPT_TOOLKIT_COLOR_DEPTH value is
    # the default that's used if the Application doesn't override it.
    term_from_env = get_term_environment_variable()
    bell_from_env = get_bell_environment_variable()
    color_depth_from_env = ColorDepth.from_env()

    if stdout is None:
        # By default, render to stdout. If the output is piped somewhere else,
        # render to stderr.
        stdout = sys.stdout

        if always_prefer_tty:
            for io in [sys.stdout, sys.stderr]:
                if io is not None and io.isatty():
                    # (This is `None` when using `pythonw.exe` on Windows.)
                    stdout = io
                    break

    # If the patch_stdout context manager has been used, then sys.stdout is
    # replaced by this proxy. For prompt_toolkit applications, we want to use
    # the real stdout.
    from prompt_toolkit.patch_stdout import StdoutProxy

    while isinstance(stdout, StdoutProxy):
        stdout = stdout.original_stdout

    # If the output is still `None`, use a DummyOutput.
    # This happens for instance on Windows, when running the application under
    # `pythonw.exe`. In that case, there won't be a terminal Window, and
    # stdin/stdout/stderr are `None`.
    if stdout is None:
        return DummyOutput()

    if sys.platform == "win32":
        from .conemu import ConEmuOutput
        from .win32 import Win32Output
        from .windows10 import Windows10_Output, is_win_vt100_enabled

        if is_win_vt100_enabled():
            return cast(
                Output,
                Windows10_Output(stdout, default_color_depth=color_depth_from_env),
            )
        if is_conemu_ansi():
            return cast(
                Output, ConEmuOutput(stdout, default_color_depth=color_depth_from_env)
            )
        else:
            return Win32Output(stdout, default_color_depth=color_depth_from_env)
    else:
        from .vt100 import Vt100_Output

        # Stdout is not a TTY? Render as plain text.
        # This is mostly useful if stdout is redirected to a file, and
        # `print_formatted_text` is used.
        if not stdout.isatty():
            return PlainTextOutput(stdout)

        return Vt100_Output.from_pty(
            stdout,
            term=term_from_env,
            default_color_depth=color_depth_from_env,
            enable_bell=bell_from_env,
        )
