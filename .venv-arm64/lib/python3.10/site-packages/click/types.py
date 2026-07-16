from __future__ import annotations

import abc
import collections.abc as cabc
import enum
import os
import stat
import sys
import typing as t
import uuid
from datetime import datetime
from gettext import gettext as _
from gettext import ngettext

from ._compat import _get_argv_encoding
from ._compat import open_stream
from .exceptions import BadParameter
from .utils import format_filename
from .utils import LazyFile
from .utils import safecall

if t.TYPE_CHECKING:
    import typing_extensions as te

    from .core import Context
    from .core import Parameter
    from .shell_completion import CompletionItem

_ValueT = t.TypeVar("_ValueT")
_ValueT_contra = t.TypeVar("_ValueT_contra", contravariant=True)
_ValueT_co = t.TypeVar("_ValueT_co", covariant=True)

_FloatValueT = t.TypeVar("_FloatValueT", bound=float)
_FloatValueT_co = t.TypeVar("_FloatValueT_co", bound=float, covariant=True)


class ParamTypeInfoDict(t.TypedDict):
    param_type: str
    name: str


class ParamType(t.Generic[_ValueT_co], abc.ABC):
    """Represents the type of a parameter. Validates and converts values
    from the command line or Python into the correct type.

    To implement a custom type, subclass and implement at least the
    following:

    -   The :attr:`name` class attribute must be set.
    -   Calling an instance of the type with ``None`` must return
        ``None``. This is already implemented by default.
    -   :meth:`convert` must convert string values to the correct type.
    -   :meth:`convert` must accept values that are already the correct
        type.
    -   It must be able to convert a value if the ``ctx`` and ``param``
        arguments are ``None``. This can occur when converting prompt
        input.

    .. versionchanged:: 8.4.0
        Now a generic abstract base class. Parameterize with the
        converted value type (``ParamType[int]`` for an integer-returning
        type) so that :meth:`convert` and downstream consumers carry the
        narrowed return type.
    """

    is_composite: t.ClassVar[bool] = False
    arity: int = 1  # read-only

    #: the descriptive name of this type
    name: str

    #: if a list of this type is expected and the value is pulled from a
    #: string environment variable, this is what splits it up.  `None`
    #: means any whitespace.  For all parameters the general rule is that
    #: whitespace splits them up.  The exception are paths and files which
    #: are split by ``os.path.pathsep`` by default (":" on Unix and ";" on
    #: Windows).
    envvar_list_splitter: t.ClassVar[str | None] = None

    def to_info_dict(self) -> ParamTypeInfoDict:
        """Gather information that could be useful for a tool generating
        user-facing documentation.

        Use :meth:`click.Context.to_info_dict` to traverse the entire
        CLI structure.

        .. versionadded:: 8.0
        """
        # The class name without the "ParamType" suffix.
        param_type = type(self).__name__.partition("ParamType")[0]
        param_type = param_type.partition("ParameterType")[0]

        # Custom subclasses might not remember to set a name.
        if hasattr(self, "name"):
            name = self.name
        else:
            name = param_type

        return {"param_type": param_type, "name": name}

    def __call__(
        self,
        value: t.Any,
        param: Parameter | None = None,
        ctx: Context | None = None,
    ) -> _ValueT_co | None:
        if value is not None:
            return self.convert(value, param, ctx)
        return None

    def get_metavar(self, param: Parameter, ctx: Context) -> str | None:
        """Returns the metavar default for this param if it provides one."""

    def get_missing_message(self, param: Parameter, ctx: Context | None) -> str | None:
        """Optionally might return extra information about a missing
        parameter.

        .. versionadded:: 2.0
        """

    def convert(
        self, value: t.Any, param: Parameter | None, ctx: Context | None
    ) -> _ValueT_co:
        """Convert the value to the correct type. This is not called if
        the value is ``None`` (the missing value).

        This must accept string values from the command line, as well as
        values that are already the correct type. It may also convert
        other compatible types.

        The ``param`` and ``ctx`` arguments may be ``None`` in certain
        situations, such as when converting prompt input.

        If the value cannot be converted, call :meth:`fail` with a
        descriptive message.

        :param value: The value to convert.
        :param param: The parameter that is using this type to convert
            its value. May be ``None``.
        :param ctx: The current context that arrived at this value. May
            be ``None``.
        """
        # The default returns the value as-is so subclasses that only customize
        # metadata are not forced to redeclare ``convert``.
        return t.cast("_ValueT_co", value)

    def split_envvar_value(self, rv: str) -> cabc.Sequence[str]:
        """Given a value from an environment variable this splits it up
        into small chunks depending on the defined envvar list splitter.

        If the splitter is set to `None`, which means that whitespace splits,
        then leading and trailing whitespace is ignored.  Otherwise, leading
        and trailing splitters usually lead to empty items being included.
        """
        return (rv or "").split(self.envvar_list_splitter)

    def fail(
        self,
        message: str,
        param: Parameter | None = None,
        ctx: Context | None = None,
    ) -> t.NoReturn:
        """Helper method to fail with an invalid value message."""
        raise BadParameter(message, ctx=ctx, param=param)

    def shell_complete(
        self, ctx: Context, param: Parameter, incomplete: str
    ) -> list[CompletionItem]:
        """Return a list of
        :class:`~click.shell_completion.CompletionItem` objects for the
        incomplete value. Most types do not provide completions, but
        some do, and this allows custom types to provide custom
        completions as well.

        :param ctx: Invocation context for this command.
        :param param: The parameter that is requesting completion.
        :param incomplete: Value being completed. May be empty.

        .. versionadded:: 8.0
        """
        return []


class CompositeParamType(ParamType[_ValueT_co]):
    is_composite: t.ClassVar[bool] = True

    @property
    @abc.abstractmethod
    def arity(self) -> int: ...  # type: ignore[override]


if t.TYPE_CHECKING:
    # on Python 3.10 this will raise a TypeError

    class FuncParamTypeInfoDict(
        ParamTypeInfoDict,
        t.Generic[_ValueT_contra, _ValueT_co],
    ):
        func: t.Callable[[_ValueT_contra], _ValueT_co]
else:

    class FuncParamTypeInfoDict(ParamTypeInfoDict):
        func: t.Callable[[t.Any], t.Any]


class FuncParamType(ParamType[_ValueT_co], t.Generic[_ValueT_contra, _ValueT_co]):
    name: str
    func: t.Callable[[_ValueT_contra], _ValueT_co]

    def __init__(self, func: t.Callable[[_ValueT_contra], _ValueT_co]) -> None:
        self.name = func.__name__
        self.func = func

    def to_info_dict(self) -> FuncParamTypeInfoDict[_ValueT_contra, _ValueT_co]:
        return {"func": self.func, **super().to_info_dict()}

    def convert(
        self, value: _ValueT_contra, param: Parameter | None, ctx: Context | None
    ) -> _ValueT_co:
        try:
            return self.func(value)
        except ValueError as exc:
            message = str(exc)

            if not message:
                try:
                    message = str(value)
                except UnicodeError:
                    message = t.cast("bytes", value).decode("utf-8", "replace")

            self.fail(message, param, ctx)


class UnprocessedParamType(ParamType[t.Any]):
    name = "text"

    def convert(
        self, value: _ValueT, param: Parameter | None, ctx: Context | None
    ) -> _ValueT:
        return value

    def __repr__(self) -> str:
        return "UNPROCESSED"


class StringParamType(ParamType[str]):
    name = "text"

    def convert(
        self, value: t.Any, param: Parameter | None, ctx: Context | None
    ) -> str:
        if isinstance(value, bytes):
            enc = _get_argv_encoding()
            try:
                return value.decode(enc)
            except UnicodeError:
                fs_enc = sys.getfilesystemencoding()
                if fs_enc != enc:
                    try:
                        return value.decode(fs_enc)
                    except UnicodeError:
                        return value.decode("utf-8", "replace")
                else:
                    return value.decode("utf-8", "replace")
        return str(value)

    def __repr__(self) -> str:
        return "STRING"


if t.TYPE_CHECKING:
    # on Python 3.10 this will raise a TypeError

    class ChoiceInfoDict(ParamTypeInfoDict, t.Generic[_ValueT_co]):
        choices: tuple[_ValueT_co, ...]
        case_sensitive: bool
else:

    class ChoiceInfoDict(ParamTypeInfoDict):
        choices: tuple[t.Any, ...]
        case_sensitive: bool


class Choice(ParamType[_ValueT_co], t.Generic[_ValueT_co]):
    """The choice type allows a value to be checked against a fixed set
    of supported values.

    You may pass any iterable value which will be converted to a tuple
    and thus will only be iterated once.

    The resulting value will always be one of the originally passed choices.
    See :meth:`normalize_choice` for more info on the mapping of strings
    to choices. See :ref:`choice-opts` for an example.

    :param case_sensitive: Set to false to make choices case
        insensitive. Defaults to true.

    .. versionchanged:: 8.4.0
        Now generic in the choice value type. Parameterize with the type of
        the choice values (``Choice[HashType]`` for an enum, ``Choice[str]``
        for plain strings) to enable type-checked consumers.

    .. versionchanged:: 8.2.0
        Non-``str`` ``choices`` are now supported. It can additionally be any
        iterable. Before you were not recommended to pass anything but a list or
        tuple.

    .. versionadded:: 8.2.0
        Choice normalization can be overridden via :meth:`normalize_choice`.
    """

    name: str = "choice"

    choices: tuple[_ValueT_co, ...]
    case_sensitive: bool

    def __init__(
        self, choices: cabc.Iterable[_ValueT_co], case_sensitive: bool = True
    ) -> None:
        self.choices = tuple(choices)
        self.case_sensitive = case_sensitive

    def to_info_dict(self) -> ChoiceInfoDict[_ValueT_co]:
        return {
            "choices": self.choices,
            "case_sensitive": self.case_sensitive,
            **super().to_info_dict(),
        }

    def _normalized_mapping(
        self, ctx: Context | None = None
    ) -> cabc.Mapping[_ValueT_co, str]:
        """
        Returns mapping where keys are the original choices and the values are
        the normalized values that are accepted via the command line.

        This is a simple wrapper around :meth:`normalize_choice`, use that
        instead which is supported.
        """
        return {
            choice: self.normalize_choice(
                choice=choice,
                ctx=ctx,
            )
            for choice in self.choices
        }

    def normalize_choice(self, choice: object, ctx: Context | None) -> str:
        """
        Normalize a choice value, used to map a passed string to a choice.
        Each choice must have a unique normalized value.

        By default uses :meth:`Context.token_normalize_func` and if not case
        sensitive, convert it to a casefolded value.

        .. versionadded:: 8.2.0
        """
        normed_value = choice.name if isinstance(choice, enum.Enum) else str(choice)

        if ctx is not None and ctx.token_normalize_func is not None:
            normed_value = ctx.token_normalize_func(normed_value)

        if not self.case_sensitive:
            normed_value = normed_value.casefold()

        return normed_value

    def get_metavar(self, param: Parameter, ctx: Context) -> str | None:
        if param.param_type_name == "option" and not param.show_choices:  # type: ignore[attr-defined]
            choice_metavars = [
                convert_type(type(choice)).name.upper() for choice in self.choices
            ]
            choices_str = "|".join([*dict.fromkeys(choice_metavars)])
        else:
            choices_str = "|".join(
                [str(i) for i in self._normalized_mapping(ctx=ctx).values()]
            )

        # Use curly braces to indicate a required argument.
        if param.required and param.param_type_name == "argument":
            return f"{{{choices_str}}}"

        # Use square braces to indicate an option or optional argument.
        return f"[{choices_str}]"

    def get_missing_message(self, param: Parameter, ctx: Context | None) -> str:
        """
        Message shown when no choice is passed.

        .. versionchanged:: 8.2.0 Added ``ctx`` argument.
        """
        return _("Choose from:\n\t{choices}").format(
            choices=",\n\t".join(self._normalized_mapping(ctx=ctx).values())
        )

    def convert(
        self, value: t.Any, param: Parameter | None, ctx: Context | None
    ) -> _ValueT_co:
        """
        For a given value from the parser, normalize it and find its
        matching normalized value in the list of choices. Then return the
        matched "original" choice.
        """
        normed_value = self.normalize_choice(choice=value, ctx=ctx)
        normalized_mapping = self._normalized_mapping(ctx=ctx)

        try:
            return next(
                original
                for original, normalized in normalized_mapping.items()
                if normalized == normed_value
            )
        except StopIteration:
            self.fail(
                self.get_invalid_choice_message(value=value, ctx=ctx),
                param=param,
                ctx=ctx,
            )

    def get_invalid_choice_message(self, value: t.Any, ctx: Context | None) -> str:
        """Get the error message when the given choice is invalid.

        :param value: The invalid value.

        .. versionadded:: 8.2
        """
        choices_str = ", ".join(map(repr, self._normalized_mapping(ctx=ctx).values()))
        return ngettext(
            "{value!r} is not {choice}.",
            "{value!r} is not one of {choices}.",
            len(self.choices),
        ).format(value=value, choice=choices_str, choices=choices_str)

    def __repr__(self) -> str:
        return _("Choice({choices})").format(choices=list(self.choices))

    def shell_complete(
        self, ctx: Context, param: Parameter, incomplete: str
    ) -> list[CompletionItem]:
        """Complete choices that start with the incomplete value.

        :param ctx: Invocation context for this command.
        :param param: The parameter that is requesting completion.
        :param incomplete: Value being completed. May be empty.

        .. versionadded:: 8.0
        """
        from click.shell_completion import CompletionItem

        str_choices = [self.normalize_choice(choice, ctx) for choice in self.choices]
        if self.case_sensitive:
            matched = (c for c in str_choices if c.startswith(incomplete))
        else:
            incomplete = incomplete.lower()
            matched = (c for c in str_choices if c.lower().startswith(incomplete))

        return [CompletionItem(c) for c in matched]


class DateTimeInfoDict(ParamTypeInfoDict):
    formats: cabc.Sequence[str]


class DateTime(ParamType[datetime]):
    """The DateTime type converts date strings into `datetime` objects.

    The format strings which are checked are configurable, but default to some
    common (non-timezone aware) ISO 8601 formats.

    When specifying *DateTime* formats, you should only pass a list or a tuple.
    Other iterables, like generators, may lead to surprising results.

    The format strings are processed using ``datetime.strptime``, and this
    consequently defines the format strings which are allowed.

    Parsing is tried using each format, in order, and the first format which
    parses successfully is used.

    :param formats: A list or tuple of date format strings, in the order in
                    which they should be tried. Defaults to
                    ``'%Y-%m-%d'``, ``'%Y-%m-%dT%H:%M:%S'``,
                    ``'%Y-%m-%d %H:%M:%S'``.
    """

    name = "datetime"

    formats: cabc.Sequence[str]

    def __init__(self, formats: cabc.Sequence[str] | None = None):
        self.formats = formats or [
            "%Y-%m-%d",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
        ]

    def to_info_dict(self) -> DateTimeInfoDict:
        return {"formats": self.formats, **super().to_info_dict()}

    def get_metavar(self, param: Parameter, ctx: Context) -> str:
        return f"[{'|'.join(self.formats)}]"

    def _try_to_convert_date(self, value: t.Any, format: str) -> datetime | None:
        try:
            return datetime.strptime(value, format)
        except ValueError:
            return None

    def convert(
        self, value: t.Any, param: Parameter | None, ctx: Context | None
    ) -> datetime:
        if isinstance(value, datetime):
            return value

        for format in self.formats:
            converted = self._try_to_convert_date(value, format)

            if converted is not None:
                return converted

        formats_str = ", ".join(map(repr, self.formats))
        self.fail(
            ngettext(
                "{value!r} does not match the format {format}.",
                "{value!r} does not match the formats {formats}.",
                len(self.formats),
            ).format(value=value, format=formats_str, formats=formats_str),
            param,
            ctx,
        )

    def __repr__(self) -> str:
        return "DateTime"


class _NumberParamTypeBase(
    ParamType[_ValueT_co], t.Generic[_ValueT_contra, _ValueT_co]
):
    _number_class: t.Callable[[_ValueT_contra], _ValueT_co]

    def convert(
        self, value: _ValueT_contra, param: Parameter | None, ctx: Context | None
    ) -> _ValueT_co:
        try:
            return self._number_class(value)
        except ValueError:
            self.fail(
                _("{value!r} is not a valid {number_type}.").format(
                    value=value, number_type=self.name
                ),
                param,
                ctx,
            )


if t.TYPE_CHECKING:
    # on Python 3.10 this will raise a TypeError

    class NumberRangeInfoDict(ParamTypeInfoDict, t.Generic[_FloatValueT_co]):
        min: _FloatValueT_co | None
        max: _FloatValueT_co | None
        min_open: bool
        max_open: bool
        clamp: bool
else:

    class NumberRangeInfoDict(ParamTypeInfoDict):
        min: t.Any | None
        max: t.Any | None
        min_open: bool
        max_open: bool
        clamp: bool


class _NumberRangeBase(
    _NumberParamTypeBase[_ValueT_contra, _FloatValueT_co],
    t.Generic[_ValueT_contra, _FloatValueT_co],
):
    min: _FloatValueT_co | None
    max: _FloatValueT_co | None
    min_open: bool
    max_open: bool
    clamp: bool

    def __init__(
        self,
        min: _FloatValueT_co | None = None,
        max: _FloatValueT_co | None = None,
        min_open: bool = False,
        max_open: bool = False,
        clamp: bool = False,
    ) -> None:
        self.min = min
        self.max = max
        self.min_open = min_open
        self.max_open = max_open
        self.clamp = clamp

    def to_info_dict(self) -> NumberRangeInfoDict[_FloatValueT_co]:
        return {
            "min": self.min,
            "max": self.max,
            "min_open": self.min_open,
            "max_open": self.max_open,
            "clamp": self.clamp,
            **super().to_info_dict(),
        }

    def convert(
        self, value: _ValueT_contra, param: Parameter | None, ctx: Context | None
    ) -> _FloatValueT_co:
        import operator

        rv = super().convert(value, param, ctx)
        min = self.min
        max = self.max
        lt_min: bool = min is not None and (
            operator.le if self.min_open else operator.lt
        )(rv, min)
        gt_max: bool = max is not None and (
            operator.ge if self.max_open else operator.gt
        )(rv, max)

        if self.clamp:
            if min is not None and lt_min:
                return self._clamp(min, 1, self.min_open)

            if max is not None and gt_max:
                return self._clamp(max, -1, self.max_open)

        if lt_min or gt_max:
            self.fail(
                _("{value} is not in the range {range}.").format(
                    value=rv, range=self._describe_range()
                ),
                param,
                ctx,
            )

        return rv

    @abc.abstractmethod
    def _clamp(
        # Covariant type variables cannot be used in input positions, so we use a
        # separate method-scoped type variable instead.
        self: _NumberRangeBase[t.Any, _FloatValueT],
        bound: _FloatValueT,
        dir: t.Literal[1, -1],
        open: bool,
    ) -> _FloatValueT:
        """Find the valid value to clamp to bound in the given
        direction.

        :param bound: The boundary value.
        :param dir: 1 or -1 indicating the direction to move.
        :param open: If true, the range does not include the bound.
        """
        ...

    def _describe_range(self) -> str:
        """Describe the range for use in help text."""
        if self.min is None:
            op = "<" if self.max_open else "<="
            return f"x{op}{self.max}"

        if self.max is None:
            op = ">" if self.min_open else ">="
            return f"x{op}{self.min}"

        lop = "<" if self.min_open else "<="
        rop = "<" if self.max_open else "<="
        return f"{self.min}{lop}x{rop}{self.max}"

    def __repr__(self) -> str:
        clamp = " clamped" if self.clamp else ""
        return f"<{type(self).__name__} {self._describe_range()}{clamp}>"


class IntParamType(_NumberParamTypeBase[t.SupportsInt | t.SupportsIndex, int]):
    name = "integer"
    _number_class = int

    def __repr__(self) -> str:
        return "INT"


class IntRange(_NumberRangeBase[int, int], IntParamType):
    """Restrict an :data:`click.INT` value to a range of accepted
    values. See :ref:`ranges`.

    If ``min`` or ``max`` are not passed, any value is accepted in that
    direction. If ``min_open`` or ``max_open`` are enabled, the
    corresponding boundary is not included in the range.

    If ``clamp`` is enabled, a value outside the range is clamped to the
    boundary instead of failing.

    .. versionchanged:: 8.0
        Added the ``min_open`` and ``max_open`` parameters.
    """

    name = "integer range"

    def _clamp(self, bound: int, dir: t.Literal[1, -1], open: bool) -> int:
        if not open:
            return bound

        return bound + dir


class FloatParamType(_NumberParamTypeBase[t.SupportsFloat | t.SupportsIndex, float]):
    name = "float"
    _number_class = float

    def __repr__(self) -> str:
        return "FLOAT"


class FloatRange(_NumberRangeBase[float, float], FloatParamType):
    """Restrict a :data:`click.FLOAT` value to a range of accepted
    values. See :ref:`ranges`.

    If ``min`` or ``max`` are not passed, any value is accepted in that
    direction. If ``min_open`` or ``max_open`` are enabled, the
    corresponding boundary is not included in the range.

    If ``clamp`` is enabled, a value outside the range is clamped to the
    boundary instead of failing. This is not supported if either
    boundary is marked ``open``.

    .. versionchanged:: 8.0
        Added the ``min_open`` and ``max_open`` parameters.
    """

    name = "float range"

    def __init__(
        self,
        min: float | None = None,
        max: float | None = None,
        min_open: bool = False,
        max_open: bool = False,
        clamp: bool = False,
    ) -> None:
        super().__init__(
            min=min, max=max, min_open=min_open, max_open=max_open, clamp=clamp
        )

        if (min_open or max_open) and clamp:
            raise TypeError("Clamping is not supported for open bounds.")

    def _clamp(self, bound: float, dir: t.Literal[1, -1], open: bool) -> float:
        if not open:
            return bound

        # Could use math.nextafter here, but clamping an
        # open float range doesn't seem to be particularly useful. It's
        # left up to the user to write a callback to do it if needed.
        raise RuntimeError("Clamping is not supported for open bounds.")


class BoolParamType(ParamType[bool]):
    name = "boolean"

    bool_states: dict[str, bool] = {
        "1": True,
        "0": False,
        "yes": True,
        "no": False,
        "true": True,
        "false": False,
        "on": True,
        "off": False,
        "t": True,
        "f": False,
        "y": True,
        "n": False,
        # Absence of value is considered False.
        "": False,
    }
    """A mapping of string values to boolean states.

    Mapping is inspired by :py:attr:`configparser.ConfigParser.BOOLEAN_STATES`
    and extends it.

    .. caution::
        String values are lower-cased, as the ``str_to_bool`` comparison function
        below is case-insensitive.

    .. warning::
        The mapping is not exhaustive, and does not cover all possible boolean strings
        representations. It will remains as it is to avoid endless bikeshedding.

        Future work my be considered to make this mapping user-configurable from public
        API.
    """

    @staticmethod
    def str_to_bool(value: str | bool) -> bool | None:
        """Convert a string to a boolean value.

        If the value is already a boolean, it is returned as-is. If the value is a
        string, it is stripped of whitespaces and lower-cased, then checked against
        the known boolean states pre-defined in the `BoolParamType.bool_states` mapping
        above.

        Returns `None` if the value does not match any known boolean state.
        """
        if isinstance(value, bool):
            return value
        return BoolParamType.bool_states.get(value.strip().lower())

    def convert(
        self, value: t.Any, param: Parameter | None, ctx: Context | None
    ) -> bool:
        normalized = self.str_to_bool(value)
        if normalized is None:
            self.fail(
                _(
                    "{value!r} is not a valid boolean. Recognized values: {states}"
                ).format(value=value, states=", ".join(sorted(self.bool_states))),
                param,
                ctx,
            )
        return normalized

    def __repr__(self) -> str:
        return "BOOL"


class UUIDParameterType(ParamType[uuid.UUID]):
    name = "uuid"

    def convert(
        self, value: uuid.UUID | str, param: Parameter | None, ctx: Context | None
    ) -> uuid.UUID:
        if isinstance(value, uuid.UUID):
            return value

        value = value.strip()

        try:
            return uuid.UUID(value)
        except ValueError:
            self.fail(
                _("{value!r} is not a valid UUID.").format(value=value), param, ctx
            )

    def __repr__(self) -> str:
        return "UUID"


class FileInfoDict(ParamTypeInfoDict):
    mode: str
    encoding: str | None


class File(ParamType[t.IO[t.Any]]):
    """Declares a parameter to be a file for reading or writing.  The file
    is automatically closed once the context tears down (after the command
    finished working).

    Files can be opened for reading or writing.  The special value ``-``
    indicates stdin or stdout depending on the mode.

    By default, the file is opened for reading text data, but it can also be
    opened in binary mode or for writing.  The encoding parameter can be used
    to force a specific encoding.

    The `lazy` flag controls if the file should be opened immediately or upon
    first IO. The default is to be non-lazy for standard input and output
    streams as well as files opened for reading, `lazy` otherwise. When opening a
    file lazily for reading, it is still opened temporarily for validation, but
    will not be held open until first IO. lazy is mainly useful when opening
    for writing to avoid creating the file until it is needed.

    Files can also be opened atomically in which case all writes go into a
    separate file in the same folder and upon completion the file will
    be moved over to the original location.  This is useful if a file
    regularly read by other users is modified.

    See :ref:`file-args` for more information.

    .. versionchanged:: 2.0
        Added the ``atomic`` parameter.
    """

    name = "filename"
    envvar_list_splitter: t.ClassVar[str] = os.path.pathsep

    mode: str
    encoding: str | None
    errors: str | None
    lazy: bool | None
    atomic: bool

    def __init__(
        self,
        mode: str = "r",
        encoding: str | None = None,
        errors: str | None = "strict",
        lazy: bool | None = None,
        atomic: bool = False,
    ) -> None:
        self.mode = mode
        self.encoding = encoding
        self.errors = errors
        self.lazy = lazy
        self.atomic = atomic

    def to_info_dict(self) -> FileInfoDict:
        return {
            "mode": self.mode,
            "encoding": self.encoding,
            **super().to_info_dict(),
        }

    def resolve_lazy_flag(self, value: str | os.PathLike[str]) -> bool:
        if self.lazy is not None:
            return self.lazy
        if os.fspath(value) == "-":
            return False
        elif "w" in self.mode:
            return True
        return False

    def convert(
        self,
        value: str | os.PathLike[str] | t.IO[t.Any],
        param: Parameter | None,
        ctx: Context | None,
    ) -> t.IO[t.Any]:
        if _is_file_like(value):
            return value

        try:
            lazy = self.resolve_lazy_flag(value)

            if lazy:
                lf = LazyFile(
                    value, self.mode, self.encoding, self.errors, atomic=self.atomic
                )

                if ctx is not None:
                    ctx.call_on_close(lf.close_intelligently)

                return t.cast("t.IO[t.Any]", lf)

            f, should_close = open_stream(
                value, self.mode, self.encoding, self.errors, atomic=self.atomic
            )

            # If a context is provided, we automatically close the file
            # at the end of the context execution (or flush out).  If a
            # context does not exist, it's the caller's responsibility to
            # properly close the file.  This for instance happens when the
            # type is used with prompts.
            if ctx is not None:
                if should_close:
                    ctx.call_on_close(safecall(f.close))
                else:
                    ctx.call_on_close(safecall(f.flush))

            return f
        except OSError as e:
            self.fail(
                f"'{format_filename(value)}': {e.strerror}",
                param,
                ctx,
            )

    def shell_complete(
        self, ctx: Context, param: Parameter, incomplete: str
    ) -> list[CompletionItem]:
        """Return a special completion marker that tells the completion
        system to use the shell to provide file path completions.

        :param ctx: Invocation context for this command.
        :param param: The parameter that is requesting completion.
        :param incomplete: Value being completed. May be empty.

        .. versionadded:: 8.0
        """
        from click.shell_completion import CompletionItem

        return [CompletionItem(incomplete, type="file")]


def _is_file_like(value: t.Any) -> te.TypeIs[t.IO[t.Any]]:
    return hasattr(value, "read") or hasattr(value, "write")


class PathInfoDict(ParamTypeInfoDict):
    exists: bool
    file_okay: bool
    dir_okay: bool
    writable: bool
    readable: bool
    allow_dash: bool


class Path(ParamType[str | bytes | os.PathLike[str]]):
    """The ``Path`` type is similar to the :class:`File` type, but
    returns the filename instead of an open file. Various checks can be
    enabled to validate the type of file and permissions.

    :param exists: The file or directory needs to exist for the value to
        be valid. If this is not set to ``True``, and the file does not
        exist, then all further checks are silently skipped.
    :param file_okay: Allow a file as a value.
    :param dir_okay: Allow a directory as a value.
    :param readable: if true, a readable check is performed.
    :param writable: if true, a writable check is performed.
    :param executable: if true, an executable check is performed.
    :param resolve_path: Make the value absolute and resolve any
        symlinks. A ``~`` is not expanded, as this is supposed to be
        done by the shell only.
    :param allow_dash: Allow a single dash as a value, which indicates
        a standard stream (but does not open it). Use
        :func:`~click.open_file` to handle opening this value.
    :param path_type: Convert the incoming path value to this type. If
        ``None``, keep Python's default, which is ``str``. Useful to
        convert to :class:`pathlib.Path`.

    .. versionchanged:: 8.1
        Added the ``executable`` parameter.

    .. versionchanged:: 8.0
        Allow passing ``path_type=pathlib.Path``.

    .. versionchanged:: 6.0
        Added the ``allow_dash`` parameter.
    """

    envvar_list_splitter: t.ClassVar[str] = os.path.pathsep

    exists: bool
    file_okay: bool
    dir_okay: bool
    readable: bool
    writable: bool
    executable: bool
    resolve_path: bool
    allow_dash: bool
    name: str

    def __init__(
        self,
        exists: bool = False,
        file_okay: bool = True,
        dir_okay: bool = True,
        writable: bool = False,
        readable: bool = True,
        resolve_path: bool = False,
        allow_dash: bool = False,
        path_type: type | None = None,
        executable: bool = False,
    ) -> None:
        self.exists = exists
        self.file_okay = file_okay
        self.dir_okay = dir_okay
        self.readable = readable
        self.writable = writable
        self.executable = executable
        self.resolve_path = resolve_path
        self.allow_dash = allow_dash
        self.type: type | None = path_type

        if self.file_okay and not self.dir_okay:
            self.name = _("file")
        elif self.dir_okay and not self.file_okay:
            self.name = _("directory")
        else:
            self.name = _("path")

    def to_info_dict(self) -> PathInfoDict:
        return {
            "exists": self.exists,
            "file_okay": self.file_okay,
            "dir_okay": self.dir_okay,
            "writable": self.writable,
            "readable": self.readable,
            "allow_dash": self.allow_dash,
            **super().to_info_dict(),
        }

    def coerce_path_result(
        self, value: str | os.PathLike[str]
    ) -> str | bytes | os.PathLike[str]:
        if self.type is not None and not isinstance(value, self.type):
            if self.type is str:
                return os.fsdecode(value)
            elif self.type is bytes:
                return os.fsencode(value)
            else:
                return t.cast("os.PathLike[str]", self.type(value))

        return value

    def convert(
        self,
        value: str | os.PathLike[str],
        param: Parameter | None,
        ctx: Context | None,
    ) -> str | bytes | os.PathLike[str]:
        rv = value

        is_dash = self.file_okay and self.allow_dash and rv in (b"-", "-")

        if not is_dash:
            if self.resolve_path:
                rv = os.path.realpath(rv)

            try:
                st = os.stat(rv)
            except OSError:
                if not self.exists:
                    return self.coerce_path_result(rv)
                self.fail(
                    _("{name} {filename!r} does not exist.").format(
                        name=self.name.title(), filename=format_filename(value)
                    ),
                    param,
                    ctx,
                )

            if not self.file_okay and stat.S_ISREG(st.st_mode):
                self.fail(
                    _("{name} {filename!r} is a file.").format(
                        name=self.name.title(), filename=format_filename(value)
                    ),
                    param,
                    ctx,
                )
            if not self.dir_okay and stat.S_ISDIR(st.st_mode):
                self.fail(
                    _("{name} {filename!r} is a directory.").format(
                        name=self.name.title(), filename=format_filename(value)
                    ),
                    param,
                    ctx,
                )

            if self.readable and not os.access(rv, os.R_OK):
                self.fail(
                    _("{name} {filename!r} is not readable.").format(
                        name=self.name.title(), filename=format_filename(value)
                    ),
                    param,
                    ctx,
                )

            if self.writable and not os.access(rv, os.W_OK):
                self.fail(
                    _("{name} {filename!r} is not writable.").format(
                        name=self.name.title(), filename=format_filename(value)
                    ),
                    param,
                    ctx,
                )

            if self.executable and not os.access(value, os.X_OK):
                self.fail(
                    _("{name} {filename!r} is not executable.").format(
                        name=self.name.title(), filename=format_filename(value)
                    ),
                    param,
                    ctx,
                )

        return self.coerce_path_result(rv)

    def shell_complete(
        self, ctx: Context, param: Parameter, incomplete: str
    ) -> list[CompletionItem]:
        """Return a special completion marker that tells the completion
        system to use the shell to provide path completions for only
        directories or any paths.

        :param ctx: Invocation context for this command.
        :param param: The parameter that is requesting completion.
        :param incomplete: Value being completed. May be empty.

        .. versionadded:: 8.0
        """
        from click.shell_completion import CompletionItem

        type = "dir" if self.dir_okay and not self.file_okay else "file"
        return [CompletionItem(incomplete, type=type)]


class TupleInfoDict(ParamTypeInfoDict):
    types: cabc.Sequence[ParamTypeInfoDict]


class Tuple(CompositeParamType[tuple[t.Any, ...]]):
    """The default behavior of Click is to apply a type on a value directly.
    This works well in most cases, except for when `nargs` is set to a fixed
    count and different types should be used for different items.  In this
    case the :class:`Tuple` type can be used.  This type can only be used
    if `nargs` is set to a fixed number.

    For more information see :ref:`tuple-type`.

    This can be selected by using a Python tuple literal as a type.

    :param types: a list of types that should be used for the tuple items.
    """

    def __init__(self, types: cabc.Sequence[type[t.Any] | ParamType[t.Any]]) -> None:
        self.types: cabc.Sequence[ParamType[t.Any]] = [convert_type(ty) for ty in types]

    def to_info_dict(self) -> TupleInfoDict:
        return {
            "types": [ty.to_info_dict() for ty in self.types],
            **super().to_info_dict(),
        }

    @property
    def name(self) -> str:  # type: ignore[override]
        return f"<{' '.join(ty.name for ty in self.types)}>"

    @property
    def arity(self) -> int:  # type: ignore[override]
        return len(self.types)

    def convert(
        self, value: t.Any, param: Parameter | None, ctx: Context | None
    ) -> tuple[t.Any, ...]:
        len_type = len(self.types)
        len_value = len(value)

        if len_value != len_type:
            self.fail(
                ngettext(
                    "{len_type} values are required, but {len_value} was given.",
                    "{len_type} values are required, but {len_value} were given.",
                    len_value,
                ).format(len_type=len_type, len_value=len_value),
                param=param,
                ctx=ctx,
            )

        return tuple(
            ty(x, param, ctx) for ty, x in zip(self.types, value, strict=False)
        )


def _guess_type(
    ty: type[t.Any] | ParamType[t.Any] | None,
    default: t.Any | None,
) -> type[t.Any] | tuple[type[t.Any], ...] | ParamType[t.Any] | None:
    """Infer a type from *ty* or *default*.

    Returns *ty* unchanged when it is not ``None``.  Otherwise inspects
    *default* to produce a ``type``, a ``tuple`` of types (for tuple
    defaults), or ``None``.
    """
    if ty is not None:
        return ty

    if default is None:
        return None

    if not isinstance(default, (tuple, list)):
        return type(default)

    # If the default is empty, return None so convert_type falls
    # through to STRING.
    if not default:
        return None

    item = default[0]

    # A sequence of iterables needs to detect the inner types.
    # Can't call convert_type recursively because that would
    # incorrectly unwind the tuple to a single type.
    if isinstance(item, (tuple, list)):
        return tuple(map(type, item))

    return type(item)


@t.overload
def convert_type(ty: None, default: None = None) -> StringParamType: ...
@t.overload
def convert_type(
    ty: type | ParamType[t.Any], default: t.Any | None = None
) -> ParamType[t.Any]: ...
@t.overload
def convert_type(
    ty: t.Any | None, default: t.Any | None = None
) -> ParamType[t.Any]: ...
def convert_type(
    ty: t.Any | None = None, default: t.Any | None = None
) -> ParamType[t.Any]:
    """Find the most appropriate :class:`ParamType` for the given Python
    type. If the type isn't provided, it can be inferred from a default
    value.
    """
    guessed = _guess_type(ty, default)
    is_guessed = guessed is not ty

    if isinstance(guessed, tuple):
        return Tuple(guessed)

    if isinstance(guessed, ParamType):
        return guessed

    if guessed is str or guessed is None:
        return STRING

    if guessed is int:
        return INT

    if guessed is float:
        return FLOAT

    if guessed is bool:
        return BOOL

    if is_guessed:
        return STRING

    if __debug__:
        try:
            if issubclass(guessed, ParamType):
                raise AssertionError(
                    f"Attempted to use an uninstantiated parameter type ({guessed})."
                )
        except TypeError:
            # guessed is an instance (correct), so issubclass fails.
            pass

    return FuncParamType(guessed)


#: A dummy parameter type that just does nothing.  From a user's
#: perspective this appears to just be the same as `STRING` but
#: internally no string conversion takes place if the input was bytes.
#: This is usually useful when working with file paths as they can
#: appear in bytes and unicode.
#:
#: For path related uses the :class:`Path` type is a better choice but
#: there are situations where an unprocessed type is useful which is why
#: it is provided.
#:
#: .. versionadded:: 4.0
UNPROCESSED: t.Final[UnprocessedParamType] = UnprocessedParamType()

#: A unicode string parameter type which is the implicit default.  This
#: can also be selected by using ``str`` as type.
STRING: t.Final[StringParamType] = StringParamType()

#: An integer parameter.  This can also be selected by using ``int`` as
#: type.
INT: t.Final[IntParamType] = IntParamType()

#: A floating point value parameter.  This can also be selected by using
#: ``float`` as type.
FLOAT: t.Final[FloatParamType] = FloatParamType()

#: A boolean parameter.  This is the default for boolean flags.  This can
#: also be selected by using ``bool`` as a type.
BOOL: t.Final[BoolParamType] = BoolParamType()

#: A UUID parameter.
UUID: t.Final[UUIDParameterType] = UUIDParameterType()


class OptionHelpExtra(t.TypedDict, total=False):
    envvars: tuple[str, ...]
    default: str
    range: str
    required: str
