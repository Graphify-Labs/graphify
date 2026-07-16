"""
This module started out as largely a copy paste from the stdlib's
optparse module with the features removed that we do not need from
optparse because we implement them in Click on a higher level (for
instance type handling, help formatting and a lot more).

The plan is to remove more and more from here over time.

The reason this is a different module and not optparse from the stdlib
is that there are differences in 2.x and 3.x about the error messages
generated and optparse in the stdlib uses gettext for no good reason
and might cause us issues.

Click uses parts of optparse written by Gregory P. Ward and maintained
by the Python Software Foundation. This is limited to code in parser.py.

Copyright 2001-2006 Gregory P. Ward. All rights reserved.
Copyright 2002-2006 Python Software Foundation. All rights reserved.
"""

# This code uses parts of optparse written by Gregory P. Ward and
# maintained by the Python Software Foundation.
# Copyright 2001-2006 Gregory P. Ward
# Copyright 2002-2006 Python Software Foundation
from __future__ import annotations

import collections.abc as cabc
import typing as t
from collections import deque
from gettext import gettext as _
from gettext import ngettext

from ._utils import FLAG_NEEDS_VALUE
from ._utils import UNSET
from .exceptions import BadArgumentUsage
from .exceptions import BadOptionUsage
from .exceptions import NoSuchOption
from .exceptions import UsageError

if t.TYPE_CHECKING:
    from ._utils import T_FLAG_NEEDS_VALUE
    from ._utils import T_UNSET
    from .core import Argument as CoreArgument
    from .core import Context
    from .core import Option as CoreOption
    from .core import Parameter as CoreParameter

V = t.TypeVar("V")


def _unpack_args(
    args: cabc.Sequence[str], nargs_spec: cabc.Sequence[int]
) -> tuple[cabc.Sequence[str | cabc.Sequence[str | T_UNSET] | T_UNSET], list[str]]:
    """Given an iterable of arguments and an iterable of nargs specifications,
    it returns a tuple with all the unpacked arguments at the first index
    and all remaining arguments as the second.

    The nargs specification is the number of arguments that should be consumed
    or `-1` to indicate that this position should eat up all the remainders.

    Missing items are filled with ``UNSET``.
    """
    args = deque(args)
    nargs_spec = deque(nargs_spec)
    rv: list[str | tuple[str | T_UNSET, ...] | T_UNSET] = []
    spos: int | None = None

    def _fetch(c: deque[str]) -> str | T_UNSET:
        try:
            if spos is None:
                return c.popleft()
            else:
                return c.pop()
        except IndexError:
            return UNSET

    while nargs_spec:
        if spos is None:
            nargs = nargs_spec.popleft()
        else:
            nargs = nargs_spec.pop()

        if nargs == 1:
            rv.append(_fetch(args))
        elif nargs > 1:
            x: list[str | T_UNSET] = [_fetch(args) for _ in range(nargs)]

            # If we're reversed, we're pulling in the arguments in reverse,
            # so we need to turn them around.
            if spos is not None:
                x.reverse()

            rv.append(tuple(x))
        elif nargs < 0:
            if spos is not None:
                raise TypeError("Cannot have two nargs < 0")

            spos = len(rv)
            rv.append(UNSET)

    # spos is the position of the wildcard (star).  If it's not `None`,
    # we fill it with the remainder.
    if spos is not None:
        rv[spos] = tuple(args)
        args = []
        rv[spos + 1 :] = reversed(rv[spos + 1 :])

    return tuple(rv), list(args)


def _split_opt(opt: str) -> tuple[str, str]:
    first = opt[:1]
    if first.isalnum():
        return "", opt
    if opt[1:2] == first:
        return opt[:2], opt[2:]
    return first, opt[1:]


def _normalize_opt(opt: str, ctx: Context | None) -> str:
    if ctx is None or ctx.token_normalize_func is None:
        return opt
    prefix, opt = _split_opt(opt)
    return f"{prefix}{ctx.token_normalize_func(opt)}"


class _Option:
    def __init__(
        self,
        obj: CoreOption,
        opts: cabc.Sequence[str],
        dest: str | None,
        action: str | None = None,
        nargs: int = 1,
        const: t.Any | None = None,
    ):
        self._short_opts = []
        self._long_opts = []
        self.prefixes: set[str] = set()

        for opt in opts:
            prefix, value = _split_opt(opt)
            if not prefix:
                raise ValueError(
                    _("Invalid start character for option ({option})").format(
                        option=opt
                    )
                )
            self.prefixes.add(prefix[0])
            if len(prefix) == 1 and len(value) == 1:
                self._short_opts.append(opt)
            else:
                self._long_opts.append(opt)
                self.prefixes.add(prefix)

        if action is None:
            action = "store"

        self.dest = dest
        self.action = action
        self.nargs = nargs
        self.const = const
        self.obj = obj

    @property
    def takes_value(self) -> bool:
        return self.action in ("store", "append")

    def process(self, value: t.Any, state: _ParsingState) -> None:
        if self.action == "store":
            state.opts[self.dest] = value  # type: ignore
        elif self.action == "store_const":
            state.opts[self.dest] = self.const  # type: ignore
        elif self.action == "append":
            state.opts.setdefault(self.dest, []).append(value)  # type: ignore
        elif self.action == "append_const":
            state.opts.setdefault(self.dest, []).append(self.const)  # type: ignore
        elif self.action == "count":
            state.opts[self.dest] = state.opts.get(self.dest, 0) + 1  # type: ignore
        else:
            raise ValueError(f"unknown action '{self.action}'")
        state.order.append(self.obj)


class _Argument:
    def __init__(self, obj: CoreArgument, dest: str | None, nargs: int = 1):
        self.dest = dest
        self.nargs = nargs
        self.obj = obj

    def process(
        self,
        value: str | cabc.Sequence[str | T_UNSET] | T_UNSET,
        state: _ParsingState,
    ) -> None:
        if self.nargs > 1:
            assert isinstance(value, cabc.Sequence)
            holes = sum(x is UNSET for x in value)
            if holes == len(value):
                value = UNSET
            elif holes != 0:
                raise BadArgumentUsage(
                    _("Argument {name!r} takes {nargs} values.").format(
                        name=self.dest, nargs=self.nargs
                    )
                )

        # We failed to collect any argument value so we consider the argument as unset.
        if value == ():
            value = UNSET

        state.opts[self.dest] = value  # type: ignore
        state.order.append(self.obj)


class _ParsingState:
    def __init__(self, rargs: list[str]) -> None:
        self.opts: dict[str, t.Any] = {}
        self.largs: list[str] = []
        self.rargs = rargs
        self.order: list[CoreParameter] = []


class _OptionParser:
    """The option parser is an internal class that is ultimately used to
    parse options and arguments.  It's modelled after optparse and brings
    a similar but vastly simplified API.  It should generally not be used
    directly as the high level Click classes wrap it for you.

    It's not nearly as extensible as optparse or argparse as it does not
    implement features that are implemented on a higher level (such as
    types or defaults).

    :param ctx: optionally the :class:`~click.Context` where this parser
                should go with.

    .. deprecated:: 8.2
        Will be removed in Click 9.0.
    """

    def __init__(self, ctx: Context | None = None) -> None:
        #: The :class:`~click.Context` for this parser.  This might be
        #: `None` for some advanced use cases.
        self.ctx = ctx
        #: This controls how the parser deals with interspersed arguments.
        #: If this is set to `False`, the parser will stop on the first
        #: non-option.  Click uses this to implement nested subcommands
        #: safely.
        self.allow_interspersed_args: bool = True
        #: This tells the parser how to deal with unknown options.  By
        #: default it will error out (which is sensible), but there is a
        #: second mode where it will ignore it and continue processing
        #: after shifting all the unknown options into the resulting args.
        self.ignore_unknown_options: bool = False

        if ctx is not None:
            self.allow_interspersed_args = ctx.allow_interspersed_args
            self.ignore_unknown_options = ctx.ignore_unknown_options

        self._short_opt: dict[str, _Option] = {}
        self._long_opt: dict[str, _Option] = {}
        self._opt_prefixes = {"-", "--"}
        self._args: list[_Argument] = []

    def add_option(
        self,
        obj: CoreOption,
        opts: cabc.Sequence[str],
        dest: str | None,
        action: str | None = None,
        nargs: int = 1,
        const: t.Any | None = None,
    ) -> None:
        """Adds a new option named `dest` to the parser.  The destination
        is not inferred (unlike with optparse) and needs to be explicitly
        provided.  Action can be any of ``store``, ``store_const``,
        ``append``, ``append_const`` or ``count``.

        The `obj` can be used to identify the option in the order list
        that is returned from the parser.
        """
        opts = [_normalize_opt(opt, self.ctx) for opt in opts]
        option = _Option(obj, opts, dest, action=action, nargs=nargs, const=const)
        self._opt_prefixes.update(option.prefixes)
        for opt in option._short_opts:
            self._short_opt[opt] = option
        for opt in option._long_opts:
            self._long_opt[opt] = option

    def add_argument(self, obj: CoreArgument, dest: str | None, nargs: int = 1) -> None:
        """Adds a positional argument named `dest` to the parser.

        The `obj` can be used to identify the option in the order list
        that is returned from the parser.
        """
        self._args.append(_Argument(obj, dest=dest, nargs=nargs))

    def parse_args(
        self, args: list[str]
    ) -> tuple[dict[str, t.Any], list[str], list[CoreParameter]]:
        """Parses positional arguments and returns ``(values, args, order)``
        for the parsed options and arguments as well as the leftover
        arguments if there are any.  The order is a list of objects as they
        appear on the command line.  If arguments appear multiple times they
        will be memorized multiple times as well.
        """
        state = _ParsingState(args)
        try:
            self._process_args_for_options(state)
            self._process_args_for_args(state)
        except UsageError:
            if self.ctx is None or not self.ctx.resilient_parsing:
                raise
        return state.opts, state.largs, state.order

    def _process_args_for_args(self, state: _ParsingState) -> None:
        pargs, args = _unpack_args(
            state.largs + state.rargs, [x.nargs for x in self._args]
        )

        for idx, arg in enumerate(self._args):
            arg.process(pargs[idx], state)

        state.largs = args
        state.rargs = []

    def _process_args_for_options(self, state: _ParsingState) -> None:
        while state.rargs:
            arg = state.rargs.pop(0)
            arglen = len(arg)
            # Double dashes always handled explicitly regardless of what
            # prefixes are valid.
            if arg == "--":
                return
            elif arg[:1] in self._opt_prefixes and arglen > 1:
                self._process_opts(arg, state)
            elif self.allow_interspersed_args:
                state.largs.append(arg)
            else:
                state.rargs.insert(0, arg)
                return

        # Say this is the original argument list:
        # [arg0, arg1, ..., arg(i-1), arg(i), arg(i+1), ..., arg(N-1)]
        #                            ^
        # (we are about to process arg(i)).
        #
        # Then rargs is [arg(i), ..., arg(N-1)] and largs is a *subset* of
        # [arg0, ..., arg(i-1)] (any options and their arguments will have
        # been removed from largs).
        #
        # The while loop will usually consume 1 or more arguments per pass.
        # If it consumes 1 (eg. arg is an option that takes no arguments),
        # then after _process_arg() is done the situation is:
        #
        #   largs = subset of [arg0, ..., arg(i)]
        #   rargs = [arg(i+1), ..., arg(N-1)]
        #
        # If allow_interspersed_args is false, largs will always be
        # *empty* -- still a subset of [arg0, ..., arg(i-1)], but
        # not a very interesting subset!

    def _match_long_opt(
        self, opt: str, explicit_value: str | None, state: _ParsingState
    ) -> None:
        if opt not in self._long_opt:
            raise NoSuchOption(opt, possibilities=self._long_opt, ctx=self.ctx)

        option = self._long_opt[opt]
        if option.takes_value:
            # At this point it's safe to modify rargs by injecting the
            # explicit value, because no exception is raised in this
            # branch.  This means that the inserted value will be fully
            # consumed.
            if explicit_value is not None:
                state.rargs.insert(0, explicit_value)

            value = self._get_value_from_state(opt, option, state)

        elif explicit_value is not None:
            raise BadOptionUsage(
                opt, _("Option {name!r} does not take a value.").format(name=opt)
            )

        else:
            value = UNSET

        option.process(value, state)

    def _match_short_opt(self, arg: str, state: _ParsingState) -> None:
        stop = False
        i = 1
        prefix = arg[0]
        unknown_options = []

        for ch in arg[1:]:
            opt = _normalize_opt(f"{prefix}{ch}", self.ctx)
            option = self._short_opt.get(opt)
            i += 1

            if not option:
                if self.ignore_unknown_options:
                    unknown_options.append(ch)
                    continue
                raise NoSuchOption(opt, ctx=self.ctx)
            if option.takes_value:
                # Any characters left in arg?  Pretend they're the
                # next arg, and stop consuming characters of arg.
                if i < len(arg):
                    state.rargs.insert(0, arg[i:])
                    stop = True

                value = self._get_value_from_state(opt, option, state)

            else:
                value = UNSET

            option.process(value, state)

            if stop:
                break

        # If we got any unknown options we recombine the string of the
        # remaining options and re-attach the prefix, then report that
        # to the state as new large.  This way there is basic combinatorics
        # that can be achieved while still ignoring unknown arguments.
        if self.ignore_unknown_options and unknown_options:
            state.largs.append(f"{prefix}{''.join(unknown_options)}")

    def _get_value_from_state(
        self, option_name: str, option: _Option, state: _ParsingState
    ) -> str | cabc.Sequence[str] | T_UNSET | T_FLAG_NEEDS_VALUE:
        nargs = option.nargs

        value: str | cabc.Sequence[str] | T_UNSET | T_FLAG_NEEDS_VALUE

        if len(state.rargs) < nargs:
            if option.obj._flag_needs_value:
                # Option allows omitting the value.
                value = FLAG_NEEDS_VALUE
            else:
                raise BadOptionUsage(
                    option_name,
                    ngettext(
                        "Option {name!r} requires an argument.",
                        "Option {name!r} requires {nargs} arguments.",
                        nargs,
                    ).format(name=option_name, nargs=nargs),
                )
        elif nargs == 1:
            next_rarg = state.rargs[0]

            if (
                option.obj._flag_needs_value
                and isinstance(next_rarg, str)
                and next_rarg[:1] in self._opt_prefixes
                and len(next_rarg) > 1
            ):
                # The next arg looks like the start of an option, don't
                # use it as the value if omitting the value is allowed.
                value = FLAG_NEEDS_VALUE
            else:
                value = state.rargs.pop(0)
        else:
            value = tuple(state.rargs[:nargs])
            del state.rargs[:nargs]

        return value

    def _process_opts(self, arg: str, state: _ParsingState) -> None:
        explicit_value = None
        # Long option handling happens in two parts.  The first part is
        # supporting explicitly attached values.  In any case, we will try
        # to long match the option first.
        if "=" in arg:
            long_opt, explicit_value = arg.split("=", 1)
        else:
            long_opt = arg
        norm_long_opt = _normalize_opt(long_opt, self.ctx)

        # At this point we will match the (assumed) long option through
        # the long option matching code.  Note that this allows options
        # like "-foo" to be matched as long options.
        try:
            self._match_long_opt(norm_long_opt, explicit_value, state)
        except NoSuchOption:
            # At this point the long option matching failed, and we need
            # to try with short options.  However there is a special rule
            # which says, that if we have a two character options prefix
            # (applies to "--foo" for instance), we do not dispatch to the
            # short option code and will instead raise the no option
            # error.
            if arg[:2] not in self._opt_prefixes:
                self._match_short_opt(arg, state)
                return

            if not self.ignore_unknown_options:
                raise

            state.largs.append(arg)


def __getattr__(name: str) -> object:
    import warnings

    if name in {
        "OptionParser",
        "Argument",
        "Option",
        "split_opt",
        "normalize_opt",
        "ParsingState",
    }:
        warnings.warn(
            f"'parser.{name}' is deprecated and will be removed in Click 9.0."
            " The old parser is available in 'optparse'.",
            DeprecationWarning,
            stacklevel=2,
        )
        return globals()[f"_{name}"]

    if name == "split_arg_string":
        from .shell_completion import split_arg_string

        warnings.warn(
            "Importing 'parser.split_arg_string' is deprecated, it will only be"
            " available in 'shell_completion' in Click 9.0.",
            DeprecationWarning,
            stacklevel=2,
        )
        return split_arg_string

    raise AttributeError(name)
