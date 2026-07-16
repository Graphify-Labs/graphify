# mypy: allow-untyped-defs
from __future__ import annotations

import argparse
from collections.abc import Callable
from collections.abc import Sequence
import os
import sys
import textwrap
from typing import Any
from typing import final
from typing import Literal
from typing import NoReturn

from .exceptions import UsageError
import _pytest._io
from _pytest.compat import NOTSET
from _pytest.deprecated import check_ispytest


FILE_OR_DIR = "file_or_dir"


@final
class Parser:
    """Parser for command line arguments and config-file values.

    :ivar extra_info: Dict of generic param -> value to display in case
        there's an error processing the command line arguments.
    """

    def __init__(
        self,
        usage: str | None = None,
        processopt: Callable[[Argument], None] | None = None,
        *,
        prog: str | None = None,
        _ispytest: bool = False,
    ) -> None:
        check_ispytest(_ispytest)

        from _pytest._argcomplete import filescompleter

        self._processopt = processopt
        self.extra_info: dict[str, Any] = {}
        self.optparser = PytestArgumentParser(usage, self.extra_info, prog=prog)
        anonymous_arggroup = self.optparser.add_argument_group("Custom options")
        self._anonymous = OptionGroup(
            anonymous_arggroup, "_anonymous", self, _ispytest=True
        )
        self._groups = [self._anonymous]
        # Maps option strings -> dest, e.g. "-V" and "--version" to "version".
        self._opt2dest: dict[str, str] = {}
        file_or_dir_arg = self.optparser.add_argument(FILE_OR_DIR, nargs="*")
        file_or_dir_arg.completer = filescompleter  # type: ignore

        self._inidict: dict[str, tuple[str, str, Any]] = {}
        # Maps alias -> canonical name.
        self._ini_aliases: dict[str, str] = {}

    @property
    def prog(self) -> str:
        return self.optparser.prog

    @prog.setter
    def prog(self, value: str) -> None:
        self.optparser.prog = value

    def processoption(self, option: Argument) -> None:
        if self._processopt:
            if option.dest:
                self._processopt(option)

    def getgroup(
        self, name: str, description: str = "", after: str | None = None
    ) -> OptionGroup:
        """Get (or create) a named option Group.

        :param name: Name of the option group.
        :param description: Long description for --help output.
        :param after: Name of another group, used for ordering --help output.
        :returns: The option group.

        The returned group object has an ``addoption`` method with the same
        signature as :func:`parser.addoption <pytest.Parser.addoption>` but
        will be shown in the respective group in the output of
        ``pytest --help``.
        """
        for group in self._groups:
            if group.name == name:
                return group

        arggroup = self.optparser.add_argument_group(description or name)
        group = OptionGroup(arggroup, name, self, _ispytest=True)
        i = 0
        for i, grp in enumerate(self._groups):
            if grp.name == after:
                break
        self._groups.insert(i + 1, group)
        # argparse doesn't provide a way to control `--help` order, so must
        # access its internals ☹.
        self.optparser._action_groups.insert(i + 1, self.optparser._action_groups.pop())
        return group

    def addoption(self, *opts: str, **attrs: Any) -> None:
        """Register a command line option.

        :param opts:
            Option names, can be short or long options.
        :param attrs:
            Same attributes as the argparse library's :meth:`add_argument()
            <argparse.ArgumentParser.add_argument>` function accepts.

        After command line parsing, options are available on the pytest config
        object via ``config.option.NAME`` where ``NAME`` is usually set
        by passing a ``dest`` attribute, for example
        ``addoption("--long", dest="NAME", ...)``.
        """
        self._anonymous.addoption(*opts, **attrs)

    def parse(
        self,
        args: Sequence[str | os.PathLike[str]],
        namespace: argparse.Namespace | None = None,
    ) -> argparse.Namespace:
        """Parse the arguments.

        Unlike ``parse_known_args`` and ``parse_known_and_unknown_args``,
        raises PrintHelp on `--help` and UsageError on unknown flags

        :meta private:
        """
        from _pytest._argcomplete import try_argcomplete

        try_argcomplete(self.optparser)
        strargs = [os.fspath(x) for x in args]
        if namespace is None:
            namespace = argparse.Namespace()
        try:
            namespace._raise_print_help = True
            return self.optparser.parse_intermixed_args(strargs, namespace=namespace)
        finally:
            del namespace._raise_print_help

    def parse_known_args(
        self,
        args: Sequence[str | os.PathLike[str]],
        namespace: argparse.Namespace | None = None,
    ) -> argparse.Namespace:
        """Parse the known arguments at this point.

        :returns: An argparse namespace object.
        """
        return self.parse_known_and_unknown_args(args, namespace=namespace)[0]

    def parse_known_and_unknown_args(
        self,
        args: Sequence[str | os.PathLike[str]],
        namespace: argparse.Namespace | None = None,
    ) -> tuple[argparse.Namespace, list[str]]:
        """Parse the known arguments at this point, and also return the
        remaining unknown flag arguments.

        :returns:
            A tuple containing an argparse namespace object for the known
            arguments, and a list of unknown flag arguments.
        """
        strargs = [os.fspath(x) for x in args]
        if sys.version_info < (3, 12, 8) or (3, 13) <= sys.version_info < (3, 13, 1):
            # Older argparse have a bugged parse_known_intermixed_args.
            namespace, unknown = self.optparser.parse_known_args(strargs, namespace)
            assert namespace is not None
            file_or_dir = getattr(namespace, FILE_OR_DIR)
            unknown_flags: list[str] = []
            for arg in unknown:
                (unknown_flags if arg.startswith("-") else file_or_dir).append(arg)
            return namespace, unknown_flags
        else:
            return self.optparser.parse_known_intermixed_args(strargs, namespace)

    def addini(
        self,
        name: str,
        help: str,
        type: Literal[
            "string", "paths", "pathlist", "args", "linelist", "bool", "int", "float"
        ]
        | None = None,
        default: Any = NOTSET,
        *,
        aliases: Sequence[str] = (),
    ) -> None:
        """Register a configuration file option.

        :param name:
            Name of the configuration.
        :param type:
            Type of the configuration. Can be:

                * ``string``: a string
                * ``bool``: a boolean
                * ``args``: a list of strings, separated as in a shell
                * ``linelist``: a list of strings, separated by line breaks
                * ``paths``: a list of :class:`pathlib.Path`, separated as in a shell
                * ``pathlist``: a list of ``py.path``, separated as in a shell
                * ``int``: an integer
                * ``float``: a floating-point number

                .. versionadded:: 8.4

                    The ``float`` and ``int`` types.

            For ``paths`` and ``pathlist`` types, they are considered relative to the config-file.
            In case the execution is happening without a config-file defined,
            they will be considered relative to the current working directory (for example with ``--override-ini``).

            .. versionadded:: 7.0
                The ``paths`` variable type.

            .. versionadded:: 8.1
                Use the current working directory to resolve ``paths`` and ``pathlist`` in the absence of a config-file.

            Defaults to ``string`` if ``None`` or not passed.
        :param default:
            Default value if no config-file option exists but is queried.
        :param aliases:
            Additional names by which this option can be referenced.
            Aliases resolve to the canonical name.

            .. versionadded:: 9.0
                The ``aliases`` parameter.

        The value of configuration keys can be retrieved via a call to
        :py:func:`config.getini(name) <pytest.Config.getini>`.
        """
        assert type in (
            None,
            "string",
            "paths",
            "pathlist",
            "args",
            "linelist",
            "bool",
            "int",
            "float",
        )
        if type is None:
            type = "string"
        if default is NOTSET:
            default = get_ini_default_for_type(type)

        self._inidict[name] = (help, type, default)

        for alias in aliases:
            if alias in self._inidict:
                raise ValueError(
                    f"alias {alias!r} conflicts with existing configuration option"
                )
            if (already := self._ini_aliases.get(alias)) is not None:
                raise ValueError(f"{alias!r} is already an alias of {already!r}")
            self._ini_aliases[alias] = name


def get_ini_default_for_type(
    type: Literal[
        "string", "paths", "pathlist", "args", "linelist", "bool", "int", "float"
    ],
) -> Any:
    """
    Used by addini to get the default value for a given config option type, when
    default is not supplied.
    """
    if type in ("paths", "pathlist", "args", "linelist"):
        return []
    elif type == "bool":
        return False
    elif type == "int":
        return 0
    elif type == "float":
        return 0.0
    else:
        return ""


class Argument:
    """An option defined in an OptionGroup."""

    def __init__(self, action: argparse.Action) -> None:
        self._action = action

    def attrs(self) -> dict[str, Any]:
        return self._action.__dict__

    def names(self) -> Sequence[str]:
        return self._action.option_strings

    @property
    def dest(self) -> str:
        return self._action.dest

    @property
    def default(self) -> Any:
        return self._action.default

    @property
    def type(self) -> Any | None:
        return self._action.type

    def __repr__(self) -> str:
        action = getattr(self, "_action", None)
        if action is None:
            return "Argument(<uninitialized>)"
        args: list[str] = []
        args += ["opts: " + repr(self.names())]
        args += ["dest: " + repr(self.dest)]
        if action.type:
            args += ["type: " + repr(self.type)]
        args += ["default: " + repr(self.default)]
        return "Argument({})".format(", ".join(args))


class OptionGroup:
    """A group of options shown in its own section."""

    def __init__(
        self,
        arggroup: argparse._ArgumentGroup,
        name: str,
        parser: Parser | None,
        _ispytest: bool = False,
    ) -> None:
        check_ispytest(_ispytest)
        self._arggroup = arggroup
        self.name = name
        self.options: list[Argument] = []
        self.parser = parser

    def addoption(self, *opts: str, **attrs: Any) -> None:
        """Add an option to this group.

        If a shortened version of a long option is specified, it will
        be suppressed in the help. ``addoption('--twowords', '--two-words')``
        results in help showing ``--two-words`` only, but ``--twowords`` gets
        accepted **and** the automatic destination is in ``args.twowords``.

        :param opts:
            Option names, can be short or long options.
            Note that lower-case short options (e.g. `-x`) are reserved.
        :param attrs:
            Same attributes as the argparse library's :meth:`add_argument()
            <argparse.ArgumentParser.add_argument>` function accepts.
        """
        conflict = set(opts).intersection(
            name for opt in self.options for name in opt.names()
        )
        if conflict:
            raise ValueError(f"option names {conflict} already added")
        self._addoption_inner(opts, attrs, allow_reserved=False)

    def _addoption(self, *opts: str, **attrs: Any) -> None:
        """Like addoption(), but also allows registering short lower case options (e.g. -x),
        which are reserved for pytest core."""
        self._addoption_inner(opts, attrs, allow_reserved=True)

    def _addoption_inner(
        self, opts: tuple[str, ...], attrs: dict[str, Any], allow_reserved: bool
    ) -> None:
        if not allow_reserved:
            for opt in opts:
                if len(opt) >= 2 and opt[0] == "-" and opt[1].islower():
                    raise ValueError("lowercase short options are reserved")

        action = self._arggroup.add_argument(*opts, **attrs)
        option = Argument(action)
        self.options.append(option)
        if self.parser:
            for name in option.names():
                self.parser._opt2dest[name] = option.dest
            self.parser.processoption(option)


class PytestArgumentParser(argparse.ArgumentParser):
    def __init__(
        self,
        usage: str | None,
        extra_info: dict[str, str],
        *,
        prog: str | None = None,
    ) -> None:
        super().__init__(
            usage=usage,
            prog=prog,
            add_help=False,
            formatter_class=DropShorterLongHelpFormatter,
            allow_abbrev=False,
            fromfile_prefix_chars="@",
        )
        # extra_info is a dict of (param -> value) to display if there's
        # an usage error to provide more contextual information to the user.
        self.extra_info = extra_info

    def error(self, message: str) -> NoReturn:
        """Transform argparse error message into UsageError."""
        # TODO(py313): Replace with `exit_on_error=False`. Note that while it
        # was added in Python 3.9, it was broken until 3.13 (cpython#121018).
        msg = f"{self.prog}: error: {message}"
        if self.extra_info:
            msg += "\n" + "\n".join(
                f"  {k}: {v}" for k, v in sorted(self.extra_info.items())
            )
        raise UsageError(self.format_usage() + msg)


class DropShorterLongHelpFormatter(argparse.HelpFormatter):
    """Shorten help for long options that differ only in extra hyphens.

    - Collapse **long** options that are the same except for extra hyphens.
    - Shortcut if there are only two options and one of them is a short one.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # Use more accurate terminal width.
        if "width" not in kwargs:
            kwargs["width"] = _pytest._io.get_terminal_width()
        super().__init__(*args, **kwargs)

    def _format_action_invocation(self, action: argparse.Action) -> str:
        orgstr = super()._format_action_invocation(action)
        if orgstr and orgstr[0] != "-":  # only optional arguments
            return orgstr
        options = orgstr.split(", ")
        if len(options) == 2 and (len(options[0]) == 2 or len(options[1]) == 2):
            # a shortcut for '-h, --help' or '--abc', '-a'
            return orgstr
        return_list = []
        short_long: dict[str, str] = {}
        for option in options:
            if len(option) == 2 or option[2] == " ":
                continue
            assert option.startswith("--"), (
                f'long optional argument without "--": [{option}]'
            )
            xxoption = option[2:]
            shortened = xxoption.replace("-", "")
            if shortened not in short_long or len(short_long[shortened]) < len(
                xxoption
            ):
                short_long[shortened] = xxoption
        # now short_long has been filled out to the longest with dashes
        # **and** we keep the right option ordering from add_argument
        for option in options:
            if len(option) == 2 or option[2] == " ":
                return_list.append(option)
            if option[2:] == short_long.get(option.replace("-", "")):
                return_list.append(option.replace(" ", "=", 1))
        return ", ".join(return_list)

    def _split_lines(self, text: str, width: int) -> list[str]:
        """Wrap lines after splitting on original newlines.

        This allows to have explicit line breaks in the help text.
        """
        lines = []
        for line in text.splitlines():
            lines.extend(textwrap.wrap(line.strip(), width))
        return lines


class OverrideIniAction(argparse.Action):
    """Custom argparse action that makes a CLI flag equivalent to overriding an
    option, in addition to behaving like `store_true`.

    This can simplify things since code only needs to inspect the config option
    and not consider the CLI flag.
    """

    def __init__(
        self,
        option_strings: Sequence[str],
        dest: str,
        nargs: int | str | None = None,
        *args,
        ini_option: str,
        ini_value: str,
        **kwargs,
    ) -> None:
        super().__init__(option_strings, dest, 0, *args, **kwargs)
        self.ini_option = ini_option
        self.ini_value = ini_value

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        *args,
        **kwargs,
    ) -> None:
        setattr(namespace, self.dest, True)
        current_overrides = getattr(namespace, "override_ini", None)
        if current_overrides is None:
            current_overrides = []
        current_overrides.append(f"{self.ini_option}={self.ini_value}")
        setattr(namespace, "override_ini", current_overrides)
