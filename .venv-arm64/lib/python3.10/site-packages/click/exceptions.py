from __future__ import annotations

import collections.abc as cabc
import typing as t
from gettext import gettext as _
from gettext import ngettext

from ._compat import get_text_stderr
from .globals import resolve_color_default
from .utils import echo
from .utils import format_filename

if t.TYPE_CHECKING:
    from .core import Command
    from .core import Context
    from .core import Parameter


def _join_param_hints(param_hint: cabc.Sequence[str] | str | None) -> str | None:
    if param_hint is not None and not isinstance(param_hint, str):
        return " / ".join(repr(x) for x in param_hint)

    return param_hint


def _format_possibilities(possibilities: list[str]) -> str:
    possibility_str = ", ".join(repr(p) for p in sorted(possibilities))
    return ngettext(
        "Did you mean {possibility}?",
        "(Did you mean one of: {possibilities}?)",
        len(possibilities),
    ).format(possibility=possibility_str, possibilities=possibility_str)


class ClickException(Exception):
    """An exception that Click can handle and show to the user."""

    #: The exit code for this exception.
    exit_code: t.ClassVar[int] = 1

    show_color: t.Final[bool | None]
    message: t.Final[str]

    def __init__(self, message: str) -> None:
        super().__init__(message)
        # The context will be removed by the time we print the message, so cache
        # the color settings here to be used later on (in `show`)
        self.show_color = resolve_color_default()
        self.message = message

    def format_message(self) -> str:
        return self.message

    def __str__(self) -> str:
        return self.message

    def show(self, file: t.IO[t.Any] | None = None) -> None:
        if file is None:
            file = get_text_stderr()

        echo(
            _("Error: {message}").format(message=self.format_message()),
            file=file,
            color=self.show_color,
        )


class UsageError(ClickException):
    """An internal exception that signals a usage error.  This typically
    aborts any further handling.

    :param message: the error message to display.
    :param ctx: optionally the context that caused this error.  Click will
                fill in the context automatically in some situations.
    """

    exit_code: t.ClassVar[int] = 2

    ctx: Context | None
    cmd: t.Final[Command | None]

    def __init__(self, message: str, ctx: Context | None = None) -> None:
        super().__init__(message)
        self.ctx = ctx
        self.cmd = self.ctx.command if self.ctx else None

    def show(self, file: t.IO[t.Any] | None = None) -> None:
        if file is None:
            file = get_text_stderr()
        color = None
        hint = ""
        if (
            self.ctx is not None
            and self.ctx.command.get_help_option(self.ctx) is not None
        ):
            help_names = self.ctx.command.get_help_option_names(self.ctx)
            # Pick the longest name (like ``--help`` over ``-h``) for
            # readability in error messages.
            hint = _("Try '{command} {option}' for help.").format(
                command=self.ctx.command_path,
                option=max(help_names, key=len),
            )
            hint = f"{hint}\n"
        if self.ctx is not None:
            color = self.ctx.color
            echo(f"{self.ctx.get_usage()}\n{hint}", file=file, color=color)
        echo(
            _("Error: {message}").format(message=self.format_message()),
            file=file,
            color=color,
        )


class BadParameter(UsageError):
    """An exception that formats out a standardized error message for a
    bad parameter.  This is useful when thrown from a callback or type as
    Click will attach contextual information to it (for instance, which
    parameter it is).

    .. versionadded:: 2.0

    :param param: the parameter object that caused this error.  This can
                  be left out, and Click will attach this info itself
                  if possible.
    :param param_hint: a string that shows up as parameter name.  This
                       can be used as alternative to `param` in cases
                       where custom validation should happen.  If it is
                       a string it's used as such, if it's a list then
                       each item is quoted and separated.
    """

    param: Parameter | None
    param_hint: cabc.Sequence[str] | str | None

    def __init__(
        self,
        message: str,
        ctx: Context | None = None,
        param: Parameter | None = None,
        param_hint: cabc.Sequence[str] | str | None = None,
    ) -> None:
        super().__init__(message, ctx)
        self.param = param
        self.param_hint = param_hint

    def format_message(self) -> str:
        if self.param_hint is not None:
            param_hint = self.param_hint
        elif self.param is not None:
            param_hint = self.param.get_error_hint(self.ctx)
        else:
            return _("Invalid value: {message}").format(message=self.message)

        return _("Invalid value for {param_hint}: {message}").format(
            param_hint=_join_param_hints(param_hint), message=self.message
        )


class MissingParameter(BadParameter):
    """Raised if click required an option or argument but it was not
    provided when invoking the script.

    .. versionadded:: 4.0

    :param param_type: a string that indicates the type of the parameter.
                       The default is to inherit the parameter type from
                       the given `param`.  Valid values are ``'parameter'``,
                       ``'option'`` or ``'argument'``.
    """

    param_type: t.Final[str | None]

    def __init__(
        self,
        message: str | None = None,
        ctx: Context | None = None,
        param: Parameter | None = None,
        param_hint: cabc.Sequence[str] | str | None = None,
        param_type: str | None = None,
    ) -> None:
        super().__init__(message or "", ctx, param, param_hint)
        self.param_type = param_type

    def format_message(self) -> str:
        if self.param_hint is not None:
            param_hint: cabc.Sequence[str] | str | None = self.param_hint
        elif self.param is not None:
            param_hint = self.param.get_error_hint(self.ctx)
        else:
            param_hint = None

        param_hint = _join_param_hints(param_hint)
        param_hint = f" {param_hint}" if param_hint else ""

        param_type = self.param_type
        if param_type is None and self.param is not None:
            param_type = self.param.param_type_name

        msg = self.message
        if self.param is not None:
            msg_extra = self.param.type.get_missing_message(
                param=self.param, ctx=self.ctx
            )
            if msg_extra:
                if msg:
                    msg += f". {msg_extra}"
                else:
                    msg = msg_extra

        msg = f" {msg}" if msg else ""

        # Translate param_type for known types.
        if param_type == "argument":
            missing = _("Missing argument")
        elif param_type == "option":
            missing = _("Missing option")
        elif param_type == "parameter":
            missing = _("Missing parameter")
        else:
            missing = _("Missing {param_type}").format(param_type=param_type)

        return f"{missing}{param_hint}.{msg}"

    def __str__(self) -> str:
        if not self.message:
            param_name = self.param.name if self.param else None
            return _("Missing parameter: {param_name}").format(param_name=param_name)
        else:
            return self.message


class NoSuchOption(UsageError):
    """Raised if Click attempted to handle an option that does not exist.

    .. versionadded:: 4.0
    """

    option_name: t.Final[str]
    possibilities: t.Final[list[str] | None]

    def __init__(
        self,
        option_name: str,
        message: str | None = None,
        possibilities: cabc.Iterable[str] | None = None,
        ctx: Context | None = None,
    ) -> None:
        if message is None:
            message = _("No such option {name!r}.").format(name=option_name)

        super().__init__(message, ctx)
        self.option_name = option_name

        if possibilities:
            from difflib import get_close_matches

            possibilities_ = get_close_matches(option_name, possibilities)
        else:
            possibilities_ = None
        self.possibilities = possibilities_

    def format_message(self) -> str:
        if not self.possibilities:
            return self.message
        return f"{self.message} {_format_possibilities(self.possibilities)}"


class NoSuchCommand(UsageError):
    """Raised if Click attempted to handle a command that does not exist.

    .. versionadded:: 8.4.0
    """

    command_name: t.Final[str]
    possibilities: t.Final[list[str] | None]

    def __init__(
        self,
        command_name: str,
        message: str | None = None,
        possibilities: cabc.Iterable[str] | None = None,
        ctx: Context | None = None,
    ) -> None:
        if message is None:
            message = _("No such command {name!r}.").format(name=command_name)

        super().__init__(message, ctx)
        self.command_name = command_name

        if possibilities:
            from difflib import get_close_matches

            possibilities_ = get_close_matches(command_name, possibilities)
        else:
            possibilities_ = None
        self.possibilities = possibilities_

    def format_message(self) -> str:
        if not self.possibilities:
            return self.message
        return f"{self.message} {_format_possibilities(self.possibilities)}"


class BadOptionUsage(UsageError):
    """Raised if an option is generally supplied but the use of the option
    was incorrect.  This is for instance raised if the number of arguments
    for an option is not correct.

    .. versionadded:: 4.0

    :param option_name: the name of the option being used incorrectly.
    """

    option_name: t.Final[str]

    def __init__(
        self, option_name: str, message: str, ctx: Context | None = None
    ) -> None:
        super().__init__(message, ctx)
        self.option_name = option_name


class BadArgumentUsage(UsageError):
    """Raised if an argument is generally supplied but the use of the argument
    was incorrect.  This is for instance raised if the number of values
    for an argument is not correct.

    .. versionadded:: 6.0
    """


class NoArgsIsHelpError(UsageError):
    ctx: Context

    def __init__(self, ctx: Context) -> None:
        super().__init__(ctx.get_help(), ctx=ctx)

    def show(self, file: t.IO[t.Any] | None = None) -> None:
        echo(self.format_message(), file=file, err=True, color=self.ctx.color)


class FileError(ClickException):
    """Raised if a file cannot be opened."""

    ui_filename: t.Final[str]
    filename: t.Final[str]

    def __init__(self, filename: str, hint: str | None = None) -> None:
        if hint is None:
            hint = _("unknown error")

        super().__init__(hint)
        self.ui_filename = format_filename(filename)
        self.filename = filename

    def format_message(self) -> str:
        return _("Could not open file {filename!r}: {message}").format(
            filename=self.ui_filename, message=self.message
        )


class Abort(RuntimeError):
    """An internal signalling exception that signals Click to abort."""


class Exit(RuntimeError):
    """An exception that indicates that the application should exit with some
    status code.

    :param code: the status code to exit with.
    """

    __slots__ = ("exit_code",)

    exit_code: t.Final[int]

    def __init__(self, code: int = 0) -> None:
        self.exit_code = code
