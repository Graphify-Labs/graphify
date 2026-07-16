from __future__ import annotations

from abc import ABC
from abc import abstractmethod
import re
from re import Pattern
import sys
from textwrap import indent
from typing import Any
from typing import cast
from typing import final
from typing import Generic
from typing import get_args
from typing import get_origin
from typing import Literal
from typing import overload
from typing import TYPE_CHECKING
import warnings

from _pytest._code import ExceptionInfo
from _pytest._code.code import stringify_exception
from _pytest.outcomes import fail
from _pytest.warning_types import PytestWarning


if TYPE_CHECKING:
    from collections.abc import Callable
    from collections.abc import Sequence

    # for some reason Sphinx does not play well with 'from types import TracebackType'
    import types
    from typing import TypeGuard

    from typing_extensions import ParamSpec
    from typing_extensions import TypeVar

    P = ParamSpec("P")

    # this conditional definition is because we want to allow a TypeVar default
    BaseExcT_co_default = TypeVar(
        "BaseExcT_co_default",
        bound=BaseException,
        default=BaseException,
        covariant=True,
    )

    # Use short name because it shows up in docs.
    E = TypeVar("E", bound=BaseException, default=BaseException)
else:
    from typing import TypeVar

    BaseExcT_co_default = TypeVar(
        "BaseExcT_co_default", bound=BaseException, covariant=True
    )

# RaisesGroup doesn't work with a default.
BaseExcT_co = TypeVar("BaseExcT_co", bound=BaseException, covariant=True)
BaseExcT_1 = TypeVar("BaseExcT_1", bound=BaseException)
BaseExcT_2 = TypeVar("BaseExcT_2", bound=BaseException)
ExcT_1 = TypeVar("ExcT_1", bound=Exception)
ExcT_2 = TypeVar("ExcT_2", bound=Exception)

if sys.version_info < (3, 11):
    from exceptiongroup import BaseExceptionGroup
    from exceptiongroup import ExceptionGroup


# String patterns default to including the unicode flag.
_REGEX_NO_FLAGS = re.compile(r"").flags


# pytest.raises helper
@overload
def raises(
    expected_exception: type[E] | tuple[type[E], ...],
    *,
    match: str | re.Pattern[str] | None = ...,
    check: Callable[[E], bool] = ...,
) -> RaisesExc[E]: ...


@overload
def raises(
    *,
    match: str | re.Pattern[str],
    # If exception_type is not provided, check() must do any typechecks itself.
    check: Callable[[BaseException], bool] = ...,
) -> RaisesExc[BaseException]: ...


@overload
def raises(*, check: Callable[[BaseException], bool]) -> RaisesExc[BaseException]: ...


@overload
def raises(
    expected_exception: type[E] | tuple[type[E], ...],
    func: Callable[P, object],
    *args: P.args,
    **kwargs: P.kwargs,
) -> ExceptionInfo[E]: ...


def raises(
    expected_exception: type[E] | tuple[type[E], ...] | None = None,
    func: Callable[P, object] | None = None,
    *args: Any,
    **kwargs: Any,
) -> RaisesExc[BaseException] | ExceptionInfo[E]:
    r"""Assert that a code block/function call raises an exception type, or one of its subclasses.

    :param expected_exception:
        The expected exception type, or a tuple if one of multiple possible
        exception types are expected. Note that subclasses of the passed exceptions
        will also match.

        This is not a required parameter, you may opt to only use ``match`` and/or
        ``check`` for verifying the raised exception.

    :kwparam str | re.Pattern[str] | None match:
        If specified, a string containing a regular expression,
        or a regular expression object, that is tested against the string
        representation of the exception and its :pep:`678` `__notes__`
        using :func:`re.search`.

        To match a literal string that may contain :ref:`special characters
        <re-syntax>`, the pattern can first be escaped with :func:`re.escape`.

        (This is only used when ``pytest.raises`` is used as a context manager,
        and passed through to the function otherwise.
        When using ``pytest.raises`` as a function, you can use:
        ``pytest.raises(Exc, func, match="passed on").match("my pattern")``.)

    :kwparam Callable[[BaseException], bool] check:

        .. versionadded:: 8.4

        If specified, a callable that will be called with the exception as a parameter
        after checking the type and the match regex if specified.
        If it returns ``True`` it will be considered a match, if not it will
        be considered a failed match.


    Use ``pytest.raises`` as a context manager, which will capture the exception of the given
    type, or any of its subclasses::

        >>> import pytest
        >>> with pytest.raises(ZeroDivisionError):
        ...    1/0

    If the code block does not raise the expected exception (:class:`ZeroDivisionError` in the example
    above), or no exception at all, the check will fail instead.

    You can also use the keyword argument ``match`` to assert that the
    exception matches a text or regex::

        >>> with pytest.raises(ValueError, match='must be 0 or None'):
        ...     raise ValueError("value must be 0 or None")

        >>> with pytest.raises(ValueError, match=r'must be \d+$'):
        ...     raise ValueError("value must be 42")

    The ``match`` argument searches the formatted exception string, which includes any
    `PEP-678 <https://peps.python.org/pep-0678/>`__ ``__notes__``:

        >>> with pytest.raises(ValueError, match=r"had a note added"):  # doctest: +SKIP
        ...     e = ValueError("value must be 42")
        ...     e.add_note("had a note added")
        ...     raise e

    The ``check`` argument, if provided, must return True when passed the raised exception
    for the match to be successful, otherwise an :exc:`AssertionError` is raised.

        >>> import errno
        >>> with pytest.raises(OSError, check=lambda e: e.errno == errno.EACCES):
        ...     raise OSError(errno.EACCES, "no permission to view")

    The context manager produces an :class:`ExceptionInfo` object which can be used to inspect the
    details of the captured exception::

        >>> with pytest.raises(ValueError) as exc_info:
        ...     raise ValueError("value must be 42")
        >>> assert exc_info.type is ValueError
        >>> assert exc_info.value.args[0] == "value must be 42"

    .. warning::

       Given that ``pytest.raises`` matches subclasses, be wary of using it to match :class:`Exception` like this::

           # Careful, this will catch ANY exception raised.
           with pytest.raises(Exception):
               some_function()

       Because :class:`Exception` is the base class of almost all exceptions, it is easy for this to hide
       real bugs, where the user wrote this expecting a specific exception, but some other exception is being
       raised due to a bug introduced during a refactoring.

       Avoid using ``pytest.raises`` to catch :class:`Exception` unless certain that you really want to catch
       **any** exception raised.

    .. note::

       When using ``pytest.raises`` as a context manager, it's worthwhile to
       note that normal context manager rules apply and that the exception
       raised *must* be the final line in the scope of the context manager.
       Lines of code after that, within the scope of the context manager will
       not be executed. For example::

           >>> value = 15
           >>> with pytest.raises(ValueError) as exc_info:
           ...     if value > 10:
           ...         raise ValueError("value must be <= 10")
           ...     assert exc_info.type is ValueError  # This will not execute.

       Instead, the following approach must be taken (note the difference in
       scope)::

           >>> with pytest.raises(ValueError) as exc_info:
           ...     if value > 10:
           ...         raise ValueError("value must be <= 10")
           ...
           >>> assert exc_info.type is ValueError

    **Expecting exception groups**

    When expecting exceptions wrapped in :exc:`BaseExceptionGroup` or
    :exc:`ExceptionGroup`, you should instead use :class:`pytest.RaisesGroup`.

    **Using with** ``pytest.mark.parametrize``

    When using :ref:`pytest.mark.parametrize ref`
    it is possible to parametrize tests such that
    some runs raise an exception and others do not.

    See :ref:`parametrizing_conditional_raising` for an example.

    .. seealso::

        :ref:`assertraises` for more examples and detailed discussion.

    .. note::
        Similar to caught exception objects in Python, explicitly clearing
        local references to returned ``ExceptionInfo`` objects can
        help the Python interpreter speed up its garbage collection.

        Clearing those references breaks a reference cycle
        (``ExceptionInfo`` --> caught exception --> frame stack raising
        the exception --> current frame stack --> local variables -->
        ``ExceptionInfo``) which makes Python keep all objects referenced
        from that cycle (including all local variables in the current
        frame) alive until the next cyclic garbage collection run.
        More detailed information can be found in the official Python
        documentation for :ref:`the try statement <python:try>`.
    """
    __tracebackhide__ = True

    if func is None and not args:
        if set(kwargs) - {"match", "check", "expected_exception"}:
            msg = "Unexpected keyword arguments passed to pytest.raises: "
            msg += ", ".join(sorted(kwargs))
            msg += "\nUse context-manager form instead?"
            raise TypeError(msg)

        if expected_exception is None:
            return RaisesExc(**kwargs)
        return RaisesExc(expected_exception, **kwargs)

    if not expected_exception:
        raise ValueError(
            f"Expected an exception type or a tuple of exception types, but got `{expected_exception!r}`. "
            f"Raising exceptions is already understood as failing the test, so you don't need "
            f"any special code to say 'this should never raise an exception'."
        )
    if not callable(func):
        raise TypeError(f"{func!r} object (type: {type(func)}) must be callable")
    with RaisesExc(expected_exception) as excinfo:
        func(*args, **kwargs)
    try:
        return excinfo
    finally:
        del excinfo


# note: RaisesExc/RaisesGroup uses fail() internally, so this alias
#  indicates (to [internal] plugins?) that `pytest.raises` will
#  raise `_pytest.outcomes.Failed`, where
#  `outcomes.Failed is outcomes.fail.Exception is raises.Exception`
# note: this is *not* the same as `_pytest.main.Failed`
# note: mypy does not recognize this attribute, and it's not possible
#  to use a protocol/decorator like the others in outcomes due to
#  https://github.com/python/mypy/issues/18715
raises.Exception = fail.Exception  # type: ignore[attr-defined]


def _match_pattern(match: Pattern[str]) -> str | Pattern[str]:
    """Helper function to remove redundant `re.compile` calls when printing regex"""
    return match.pattern if match.flags == _REGEX_NO_FLAGS else match


def repr_callable(fun: Callable[[BaseExcT_1], bool]) -> str:
    """Get the repr of a ``check`` parameter.

    Split out so it can be monkeypatched (e.g. by hypothesis)
    """
    return repr(fun)


def backquote(s: str) -> str:
    return "`" + s + "`"


def _exception_type_name(
    e: type[BaseException] | tuple[type[BaseException], ...],
) -> str:
    if isinstance(e, type):
        return e.__name__
    if len(e) == 1:
        return e[0].__name__
    return "(" + ", ".join(ee.__name__ for ee in e) + ")"


def _check_raw_type(
    expected_type: type[BaseException] | tuple[type[BaseException], ...] | None,
    exception: BaseException,
) -> str | None:
    if expected_type is None or expected_type == ():
        return None

    if not isinstance(
        exception,
        expected_type,
    ):
        actual_type_str = backquote(_exception_type_name(type(exception)) + "()")
        expected_type_str = backquote(_exception_type_name(expected_type))
        if (
            isinstance(exception, BaseExceptionGroup)
            and isinstance(expected_type, type)
            and not issubclass(expected_type, BaseExceptionGroup)
        ):
            return f"Unexpected nested {actual_type_str}, expected {expected_type_str}"
        return f"{actual_type_str} is not an instance of {expected_type_str}"
    return None


def is_fully_escaped(s: str) -> bool:
    # we know we won't compile with re.VERBOSE, so whitespace doesn't need to be escaped
    metacharacters = "{}()+.*?^$[]|"
    # Strip all escape sequences (backslash + any char), then check if any
    # metacharacter remains unescaped in the resulting string.
    stripped = re.sub(r"\\.", "", s)
    return not any(c in metacharacters for c in stripped)


def unescape(s: str) -> str:
    return re.sub(r"\\([{}()+-.*?^$\[\]\s\\|])", r"\1", s)


# These classes conceptually differ from ExceptionInfo in that ExceptionInfo is tied, and
# constructed from, a particular exception - whereas these are constructed with expected
# exceptions, and later allow matching towards particular exceptions.
# But there's overlap in `ExceptionInfo.match` and `AbstractRaises._check_match`, as with
# `AbstractRaises.matches` and `ExceptionInfo.errisinstance`+`ExceptionInfo.group_contains`.
# The interaction between these classes should perhaps be improved.
class AbstractRaises(ABC, Generic[BaseExcT_co]):
    """ABC with common functionality shared between RaisesExc and RaisesGroup"""

    def __init__(
        self,
        *,
        match: str | Pattern[str] | None,
        check: Callable[[BaseExcT_co], bool] | None,
    ) -> None:
        if isinstance(match, str):
            # juggle error in order to avoid context to fail (necessary?)
            re_error = None
            try:
                self.match: Pattern[str] | None = re.compile(match)
            except re.error as e:
                re_error = e
            if re_error is not None:
                fail(f"Invalid regex pattern provided to 'match': {re_error}")
            if match == "":
                warnings.warn(
                    PytestWarning(
                        "matching against an empty string will *always* pass. If you want "
                        "to check for an empty message you need to pass '^$'. If you don't "
                        "want to match you should pass `None` or leave out the parameter."
                    ),
                    stacklevel=2,
                )
        else:
            self.match = match

        # check if this is a fully escaped regex and has ^$ to match fully
        # in which case we can do a proper diff on error
        self.rawmatch: str | None = None
        if isinstance(match, str) or (
            isinstance(match, Pattern) and match.flags == _REGEX_NO_FLAGS
        ):
            if isinstance(match, Pattern):
                match = match.pattern
            if (
                match
                and match[0] == "^"
                and match[-1] == "$"
                and is_fully_escaped(match[1:-1])
            ):
                self.rawmatch = unescape(match[1:-1])

        self.check = check
        self._fail_reason: str | None = None

        # used to suppress repeated printing of `repr(self.check)`
        self._nested: bool = False

        # set in self._parse_exc
        self.is_baseexception = False

    def _parse_exc(
        self, exc: type[BaseExcT_1] | types.GenericAlias, expected: str
    ) -> type[BaseExcT_1]:
        if isinstance(exc, type) and issubclass(exc, BaseException):
            if not issubclass(exc, Exception):
                self.is_baseexception = True
            return exc
        # because RaisesGroup does not support variable number of exceptions there's
        # still a use for RaisesExc(ExceptionGroup[Exception]).
        origin_exc: type[BaseException] | None = get_origin(exc)
        if origin_exc and issubclass(origin_exc, BaseExceptionGroup):
            exc_type = get_args(exc)[0]
            if (
                issubclass(origin_exc, ExceptionGroup) and exc_type in (Exception, Any)
            ) or (
                issubclass(origin_exc, BaseExceptionGroup)
                and exc_type in (BaseException, Any)
            ):
                if not issubclass(origin_exc, ExceptionGroup):
                    self.is_baseexception = True
                return cast(type[BaseExcT_1], origin_exc)
            else:
                raise ValueError(
                    f"Only `ExceptionGroup[Exception]` or `BaseExceptionGroup[BaseException]` "
                    f"are accepted as generic types but got `{exc}`. "
                    f"As `raises` will catch all instances of the specified group regardless of the "
                    f"generic argument specific nested exceptions has to be checked "
                    f"with `RaisesGroup`."
                )
        # unclear if the Type/ValueError distinction is even helpful here
        msg = f"Expected {expected}, but got "
        if isinstance(exc, type):  # type: ignore[unreachable]
            raise ValueError(msg + f"{exc.__name__!r}")
        if isinstance(exc, BaseException):  # type: ignore[unreachable]
            raise TypeError(msg + f"an exception instance: {type(exc).__name__}")
        raise TypeError(msg + repr(type(exc).__name__))

    @property
    def fail_reason(self) -> str | None:
        """Set after a call to :meth:`matches` to give a human-readable reason for why the match failed.
        When used as a context manager the string will be printed as the reason for the
        test failing."""
        return self._fail_reason

    def _check_check(
        self: AbstractRaises[BaseExcT_1],
        exception: BaseExcT_1,
    ) -> bool:
        if self.check is None:
            return True

        if self.check(exception):
            return True

        check_repr = "" if self._nested else " " + repr_callable(self.check)
        self._fail_reason = f"check{check_repr} did not return True"
        return False

    # TODO: harmonize with ExceptionInfo.match
    def _check_match(self, e: BaseException) -> bool:
        if self.match is None or re.search(
            self.match,
            stringified_exception := stringify_exception(
                e, include_subexception_msg=False
            ),
        ):
            return True

        # if we're matching a group, make sure we're explicit to reduce confusion
        # if they're trying to match an exception contained within the group
        maybe_specify_type = (
            f" the `{_exception_type_name(type(e))}()`"
            if isinstance(e, BaseExceptionGroup)
            else ""
        )
        if isinstance(self.rawmatch, str):
            from _pytest.assertion.compare_text import _diff_text
            from _pytest.assertion.highlight import dummy_highlighter
            from _pytest.assertion.util import _config
            from _pytest.config import Config

            verbose = (
                _config.get_verbosity(Config.VERBOSITY_ASSERTIONS)
                if _config is not None
                else 0
            )
            diff = list(
                _diff_text(
                    self.rawmatch, stringified_exception, dummy_highlighter, verbose
                )
            )
            self._fail_reason = ("\n" if diff[0][0] == "-" else "") + "\n".join(diff)
            return False

        self._fail_reason = (
            f"Regex pattern did not match{maybe_specify_type}.\n"
            f"  Expected regex: {_match_pattern(self.match)!r}\n"
            f"  Actual message: {stringified_exception!r}"
        )
        if _match_pattern(self.match) == stringified_exception:
            self._fail_reason += "\n Did you mean to `re.escape()` the regex?"
        return False

    @abstractmethod
    def matches(
        self: AbstractRaises[BaseExcT_1], exception: BaseException
    ) -> TypeGuard[BaseExcT_1]:
        """Check if an exception matches the requirements of this AbstractRaises.
        If it fails, :meth:`AbstractRaises.fail_reason` should be set.
        """


@final
class RaisesExc(AbstractRaises[BaseExcT_co_default]):
    """
    .. versionadded:: 8.4


    This is the class constructed when calling :func:`pytest.raises`, but may be used
    directly as a helper class with :class:`RaisesGroup` when you want to specify
    requirements on sub-exceptions.

    You don't need this if you only want to specify the type, since :class:`RaisesGroup`
    accepts ``type[BaseException]``.

    :param type[BaseException] | tuple[type[BaseException]] | None expected_exception:
        The expected type, or one of several possible types.
        May be ``None`` in order to only make use of ``match`` and/or ``check``

        The type is checked with :func:`isinstance`, and does not need to be an exact match.
        If that is wanted you can use the ``check`` parameter.

    :kwparam str | Pattern[str] match:
        A regex to match.

    :kwparam Callable[[BaseException], bool] check:
        If specified, a callable that will be called with the exception as a parameter
        after checking the type and the match regex if specified.
        If it returns ``True`` it will be considered a match, if not it will
        be considered a failed match.

    :meth:`RaisesExc.matches` can also be used standalone to check individual exceptions.

    Examples::

        with RaisesGroup(RaisesExc(ValueError, match="string"))
            ...
        with RaisesGroup(RaisesExc(check=lambda x: x.args == (3, "hello"))):
            ...
        with RaisesGroup(RaisesExc(check=lambda x: type(x) is ValueError)):
            ...
    """

    # Trio bundled hypothesis monkeypatching, we will probably instead assume that
    # hypothesis will handle that in their pytest plugin by the time this is released.
    # Alternatively we could add a version of get_pretty_function_description ourselves
    # https://github.com/HypothesisWorks/hypothesis/blob/8ced2f59f5c7bea3344e35d2d53e1f8f8eb9fcd8/hypothesis-python/src/hypothesis/internal/reflection.py#L439

    # At least one of the three parameters must be passed.
    @overload
    def __init__(
        self,
        expected_exception: (
            type[BaseExcT_co_default] | tuple[type[BaseExcT_co_default], ...]
        ),
        /,
        *,
        match: str | Pattern[str] | None = ...,
        check: Callable[[BaseExcT_co_default], bool] | None = ...,
    ) -> None: ...

    @overload
    def __init__(
        self: RaisesExc[BaseException],  # Give E a value.
        /,
        *,
        match: str | Pattern[str] | None,
        # If exception_type is not provided, check() must do any typechecks itself.
        check: Callable[[BaseException], bool] | None = ...,
    ) -> None: ...

    @overload
    def __init__(self, /, *, check: Callable[[BaseException], bool]) -> None: ...

    def __init__(
        self,
        expected_exception: (
            type[BaseExcT_co_default] | tuple[type[BaseExcT_co_default], ...] | None
        ) = None,
        /,
        *,
        match: str | Pattern[str] | None = None,
        check: Callable[[BaseExcT_co_default], bool] | None = None,
    ):
        super().__init__(match=match, check=check)
        if isinstance(expected_exception, tuple):
            expected_exceptions = expected_exception
        elif expected_exception is None:
            expected_exceptions = ()
        else:
            expected_exceptions = (expected_exception,)

        if (expected_exceptions == ()) and match is None and check is None:
            raise ValueError("You must specify at least one parameter to match on.")

        self.expected_exceptions = tuple(
            self._parse_exc(e, expected="a BaseException type")
            for e in expected_exceptions
        )

        self._just_propagate = False

    def matches(
        self,
        exception: BaseException | None,
    ) -> TypeGuard[BaseExcT_co_default]:
        """Check if an exception matches the requirements of this :class:`RaisesExc`.
        If it fails, :attr:`RaisesExc.fail_reason` will be set.

        Examples::

            assert RaisesExc(ValueError).matches(my_exception):
            # is equivalent to
            assert isinstance(my_exception, ValueError)

            # this can be useful when checking e.g. the ``__cause__`` of an exception.
            with pytest.raises(ValueError) as excinfo:
                ...
            assert RaisesExc(SyntaxError, match="foo").matches(excinfo.value.__cause__)
            # above line is equivalent to
            assert isinstance(excinfo.value.__cause__, SyntaxError)
            assert re.search("foo", str(excinfo.value.__cause__)

        """
        self._just_propagate = False
        if exception is None:
            self._fail_reason = "exception is None"
            return False
        if not self._check_type(exception):
            self._just_propagate = True
            return False

        if not self._check_match(exception):
            return False

        return self._check_check(exception)

    def __repr__(self) -> str:
        parameters = []
        if self.expected_exceptions:
            parameters.append(_exception_type_name(self.expected_exceptions))
        if self.match is not None:
            # If no flags were specified, discard the redundant re.compile() here.
            parameters.append(
                f"match={_match_pattern(self.match)!r}",
            )
        if self.check is not None:
            parameters.append(f"check={repr_callable(self.check)}")
        return f"RaisesExc({', '.join(parameters)})"

    def _check_type(self, exception: BaseException) -> TypeGuard[BaseExcT_co_default]:
        self._fail_reason = _check_raw_type(self.expected_exceptions, exception)
        return self._fail_reason is None

    def __enter__(self) -> ExceptionInfo[BaseExcT_co_default]:
        self.excinfo: ExceptionInfo[BaseExcT_co_default] = ExceptionInfo.for_later()
        return self.excinfo

    # TODO: move common code into superclass
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> bool:
        __tracebackhide__ = True
        if exc_type is None:
            if not self.expected_exceptions:
                fail("DID NOT RAISE any exception")
            if len(self.expected_exceptions) == 1:
                fail(f"DID NOT RAISE {self.expected_exceptions[0].__name__}")
            else:
                names = ", ".join(x.__name__ for x in self.expected_exceptions)
                fail(f"DID NOT RAISE any of ({names})")

        assert self.excinfo is not None, (
            "Internal error - should have been constructed in __enter__"
        )

        if not self.matches(exc_val):
            if self._just_propagate:
                return False
            raise AssertionError(self._fail_reason) from None

        # Cast to narrow the exception type now that it's verified....
        # even though the TypeGuard in self.matches should be narrowing
        exc_info = cast(
            "tuple[type[BaseExcT_co_default], BaseExcT_co_default, types.TracebackType]",
            (exc_type, exc_val, exc_tb),
        )
        self.excinfo.fill_unfilled(exc_info)
        return True


@final
class RaisesGroup(AbstractRaises[BaseExceptionGroup[BaseExcT_co]]):
    """
    .. versionadded:: 8.4

    Contextmanager for checking for an expected :exc:`ExceptionGroup`.
    This works similar to :func:`pytest.raises`, but allows for specifying the structure of an :exc:`ExceptionGroup`.
    :meth:`ExceptionInfo.group_contains` also tries to handle exception groups,
    but it is very bad at checking that you *didn't* get unexpected exceptions.

    The catching behaviour differs from :ref:`except* <except_star>`, being much
    stricter about the structure by default.
    By using ``allow_unwrapped=True`` and ``flatten_subgroups=True`` you can match
    :ref:`except* <except_star>` fully when expecting a single exception.

    :param args:
        Any number of exception types, :class:`RaisesGroup` or :class:`RaisesExc`
        to specify the exceptions contained in this exception.
        All specified exceptions must be present in the raised group, *and no others*.

        If you expect a variable number of exceptions you need to use
        :func:`pytest.raises(ExceptionGroup) <pytest.raises>` and manually check
        the contained exceptions. Consider making use of :meth:`RaisesExc.matches`.

        It does not care about the order of the exceptions, so
        ``RaisesGroup(ValueError, TypeError)``
        is equivalent to
        ``RaisesGroup(TypeError, ValueError)``.
    :kwparam str | re.Pattern[str] | None match:
        If specified, a string containing a regular expression,
        or a regular expression object, that is tested against the string
        representation of the exception group and its :pep:`678` `__notes__`
        using :func:`re.search`.

        To match a literal string that may contain :ref:`special characters
        <re-syntax>`, the pattern can first be escaped with :func:`re.escape`.

        Note that " (5 subgroups)" will be stripped from the ``repr`` before matching.
    :kwparam Callable[[E], bool] check:
        If specified, a callable that will be called with the group as a parameter
        after successfully matching the expected exceptions. If it returns ``True``
        it will be considered a match, if not it will be considered a failed match.
    :kwparam bool allow_unwrapped:
        If expecting a single exception or :class:`RaisesExc` it will match even
        if the exception is not inside an exceptiongroup.

        Using this together with ``match``, ``check`` or expecting multiple exceptions
        will raise an error.
    :kwparam bool flatten_subgroups:
        "flatten" any groups inside the raised exception group, extracting all exceptions
        inside any nested groups, before matching. Without this it expects you to
        fully specify the nesting structure by passing :class:`RaisesGroup` as expected
        parameter.

    Examples::

        with RaisesGroup(ValueError):
            raise ExceptionGroup("", (ValueError(),))
        # match
        with RaisesGroup(
            ValueError,
            ValueError,
            RaisesExc(TypeError, match="^expected int$"),
            match="^my group$",
        ):
            raise ExceptionGroup(
                "my group",
                [
                    ValueError(),
                    TypeError("expected int"),
                    ValueError(),
                ],
            )
        # check
        with RaisesGroup(
            KeyboardInterrupt,
            match="^hello$",
            check=lambda x: isinstance(x.__cause__, ValueError),
        ):
            raise BaseExceptionGroup("hello", [KeyboardInterrupt()]) from ValueError
        # nested groups
        with RaisesGroup(RaisesGroup(ValueError)):
            raise ExceptionGroup("", (ExceptionGroup("", (ValueError(),)),))

        # flatten_subgroups
        with RaisesGroup(ValueError, flatten_subgroups=True):
            raise ExceptionGroup("", (ExceptionGroup("", (ValueError(),)),))

        # allow_unwrapped
        with RaisesGroup(ValueError, allow_unwrapped=True):
            raise ValueError


    :meth:`RaisesGroup.matches` can also be used directly to check a standalone exception group.


    The matching algorithm is greedy, which means cases such as this may fail::

        with RaisesGroup(ValueError, RaisesExc(ValueError, match="hello")):
            raise ExceptionGroup("", (ValueError("hello"), ValueError("goodbye")))

    even though it generally does not care about the order of the exceptions in the group.
    To avoid the above you should specify the first :exc:`ValueError` with a :class:`RaisesExc` as well.

    .. note::
        When raised exceptions don't match the expected ones, you'll get a detailed error
        message explaining why. This includes ``repr(check)`` if set, which in Python can be
        overly verbose, showing memory locations etc etc.

        If installed and imported (in e.g. ``conftest.py``), the ``hypothesis`` library will
        monkeypatch this output to provide shorter & more readable repr's.
    """

    # allow_unwrapped=True requires: singular exception, exception not being
    # RaisesGroup instance, match is None, check is None
    @overload
    def __init__(
        self,
        expected_exception: type[BaseExcT_co] | RaisesExc[BaseExcT_co],
        /,
        *,
        allow_unwrapped: Literal[True],
        flatten_subgroups: bool = False,
    ) -> None: ...

    # flatten_subgroups = True also requires no nested RaisesGroup
    @overload
    def __init__(
        self,
        expected_exception: type[BaseExcT_co] | RaisesExc[BaseExcT_co],
        /,
        *other_exceptions: type[BaseExcT_co] | RaisesExc[BaseExcT_co],
        flatten_subgroups: Literal[True],
        match: str | Pattern[str] | None = None,
        check: Callable[[BaseExceptionGroup[BaseExcT_co]], bool] | None = None,
    ) -> None: ...

    # simplify the typevars if possible (the following 3 are equivalent but go simpler->complicated)
    # ... the first handles RaisesGroup[ValueError], the second RaisesGroup[ExceptionGroup[ValueError]],
    #     the third RaisesGroup[ValueError | ExceptionGroup[ValueError]].
    # ... otherwise, we will get results like RaisesGroup[ValueError | ExceptionGroup[Never]] (I think)
    #     (technically correct but misleading)
    @overload
    def __init__(
        self: RaisesGroup[ExcT_1],
        expected_exception: type[ExcT_1] | RaisesExc[ExcT_1],
        /,
        *other_exceptions: type[ExcT_1] | RaisesExc[ExcT_1],
        match: str | Pattern[str] | None = None,
        check: Callable[[ExceptionGroup[ExcT_1]], bool] | None = None,
    ) -> None: ...

    @overload
    def __init__(
        self: RaisesGroup[ExceptionGroup[ExcT_2]],
        expected_exception: RaisesGroup[ExcT_2],
        /,
        *other_exceptions: RaisesGroup[ExcT_2],
        match: str | Pattern[str] | None = None,
        check: Callable[[ExceptionGroup[ExceptionGroup[ExcT_2]]], bool] | None = None,
    ) -> None: ...

    @overload
    def __init__(
        self: RaisesGroup[ExcT_1 | ExceptionGroup[ExcT_2]],
        expected_exception: type[ExcT_1] | RaisesExc[ExcT_1] | RaisesGroup[ExcT_2],
        /,
        *other_exceptions: type[ExcT_1] | RaisesExc[ExcT_1] | RaisesGroup[ExcT_2],
        match: str | Pattern[str] | None = None,
        check: (
            Callable[[ExceptionGroup[ExcT_1 | ExceptionGroup[ExcT_2]]], bool] | None
        ) = None,
    ) -> None: ...

    # same as the above 3 but handling BaseException
    @overload
    def __init__(
        self: RaisesGroup[BaseExcT_1],
        expected_exception: type[BaseExcT_1] | RaisesExc[BaseExcT_1],
        /,
        *other_exceptions: type[BaseExcT_1] | RaisesExc[BaseExcT_1],
        match: str | Pattern[str] | None = None,
        check: Callable[[BaseExceptionGroup[BaseExcT_1]], bool] | None = None,
    ) -> None: ...

    @overload
    def __init__(
        self: RaisesGroup[BaseExceptionGroup[BaseExcT_2]],
        expected_exception: RaisesGroup[BaseExcT_2],
        /,
        *other_exceptions: RaisesGroup[BaseExcT_2],
        match: str | Pattern[str] | None = None,
        check: (
            Callable[[BaseExceptionGroup[BaseExceptionGroup[BaseExcT_2]]], bool] | None
        ) = None,
    ) -> None: ...

    @overload
    def __init__(
        self: RaisesGroup[BaseExcT_1 | BaseExceptionGroup[BaseExcT_2]],
        expected_exception: type[BaseExcT_1]
        | RaisesExc[BaseExcT_1]
        | RaisesGroup[BaseExcT_2],
        /,
        *other_exceptions: type[BaseExcT_1]
        | RaisesExc[BaseExcT_1]
        | RaisesGroup[BaseExcT_2],
        match: str | Pattern[str] | None = None,
        check: (
            Callable[
                [BaseExceptionGroup[BaseExcT_1 | BaseExceptionGroup[BaseExcT_2]]],
                bool,
            ]
            | None
        ) = None,
    ) -> None: ...

    def __init__(
        self: RaisesGroup[ExcT_1 | BaseExcT_1 | BaseExceptionGroup[BaseExcT_2]],
        expected_exception: type[BaseExcT_1]
        | RaisesExc[BaseExcT_1]
        | RaisesGroup[BaseExcT_2],
        /,
        *other_exceptions: type[BaseExcT_1]
        | RaisesExc[BaseExcT_1]
        | RaisesGroup[BaseExcT_2],
        allow_unwrapped: bool = False,
        flatten_subgroups: bool = False,
        match: str | Pattern[str] | None = None,
        check: (
            Callable[[BaseExceptionGroup[BaseExcT_1]], bool]
            | Callable[[ExceptionGroup[ExcT_1]], bool]
            | None
        ) = None,
    ):
        # The type hint on the `self` and `check` parameters uses different formats
        # that are *very* hard to reconcile while adhering to the overloads, so we cast
        # it to avoid an error when passing it to super().__init__
        check = cast(
            "Callable[[BaseExceptionGroup[ExcT_1|BaseExcT_1|BaseExceptionGroup[BaseExcT_2]]], bool]",
            check,
        )
        super().__init__(match=match, check=check)
        self.allow_unwrapped = allow_unwrapped
        self.flatten_subgroups: bool = flatten_subgroups
        self.is_baseexception = False

        if allow_unwrapped and other_exceptions:
            raise ValueError(
                "You cannot specify multiple exceptions with `allow_unwrapped=True.`"
                " If you want to match one of multiple possible exceptions you should"
                " use a `RaisesExc`."
                " E.g. `RaisesExc(check=lambda e: isinstance(e, (...)))`",
            )
        if allow_unwrapped and isinstance(expected_exception, RaisesGroup):
            raise ValueError(
                "`allow_unwrapped=True` has no effect when expecting a `RaisesGroup`."
                " You might want it in the expected `RaisesGroup`, or"
                " `flatten_subgroups=True` if you don't care about the structure.",
            )
        if allow_unwrapped and (match is not None or check is not None):
            raise ValueError(
                "`allow_unwrapped=True` bypasses the `match` and `check` parameters"
                " if the exception is unwrapped. If you intended to match/check the"
                " exception you should use a `RaisesExc` object. If you want to match/check"
                " the exceptiongroup when the exception *is* wrapped you need to"
                " do e.g. `if isinstance(exc.value, ExceptionGroup):"
                " assert RaisesGroup(...).matches(exc.value)` afterwards.",
            )

        self.expected_exceptions: tuple[
            type[BaseExcT_co] | RaisesExc[BaseExcT_co] | RaisesGroup[BaseException], ...
        ] = tuple(
            self._parse_excgroup(e, "a BaseException type, RaisesExc, or RaisesGroup")
            for e in (
                expected_exception,
                *other_exceptions,
            )
        )

    def _parse_excgroup(
        self,
        exc: (
            type[BaseExcT_co]
            | types.GenericAlias
            | RaisesExc[BaseExcT_1]
            | RaisesGroup[BaseExcT_2]
        ),
        expected: str,
    ) -> type[BaseExcT_co] | RaisesExc[BaseExcT_1] | RaisesGroup[BaseExcT_2]:
        # verify exception type and set `self.is_baseexception`
        match exc:
            case RaisesGroup() if self.flatten_subgroups:
                raise ValueError(
                    "You cannot specify a nested structure inside a RaisesGroup with"
                    " `flatten_subgroups=True`. The parameter will flatten subgroups"
                    " in the raised exceptiongroup before matching, which would never"
                    " match a nested structure.",
                )
            case RaisesGroup() | RaisesExc():
                self.is_baseexception |= exc.is_baseexception
                exc._nested = True
                return exc
            case tuple():
                raise TypeError(
                    f"Expected {expected}, but got {type(exc).__name__!r}.\n"
                    "RaisesGroup does not support tuples of exception types when expecting one of "
                    "several possible exception types like RaisesExc.\n"
                    "If you meant to expect a group with multiple exceptions, list them as separate arguments."
                )
            case _:
                return super()._parse_exc(exc, expected)

    @overload
    def __enter__(
        self: RaisesGroup[ExcT_1],
    ) -> ExceptionInfo[ExceptionGroup[ExcT_1]]: ...
    @overload
    def __enter__(
        self: RaisesGroup[BaseExcT_1],
    ) -> ExceptionInfo[BaseExceptionGroup[BaseExcT_1]]: ...

    def __enter__(self) -> ExceptionInfo[BaseExceptionGroup[BaseException]]:
        self.excinfo: ExceptionInfo[BaseExceptionGroup[BaseExcT_co]] = (
            ExceptionInfo.for_later()
        )
        return self.excinfo

    def __repr__(self) -> str:
        reqs = [
            e.__name__ if isinstance(e, type) else repr(e)
            for e in self.expected_exceptions
        ]
        if self.allow_unwrapped:
            reqs.append(f"allow_unwrapped={self.allow_unwrapped}")
        if self.flatten_subgroups:
            reqs.append(f"flatten_subgroups={self.flatten_subgroups}")
        if self.match is not None:
            # If no flags were specified, discard the redundant re.compile() here.
            reqs.append(f"match={_match_pattern(self.match)!r}")
        if self.check is not None:
            reqs.append(f"check={repr_callable(self.check)}")
        return f"RaisesGroup({', '.join(reqs)})"

    def _unroll_exceptions(
        self,
        exceptions: Sequence[BaseException],
    ) -> Sequence[BaseException]:
        """Used if `flatten_subgroups=True`."""
        res: list[BaseException] = []
        for exc in exceptions:
            if isinstance(exc, BaseExceptionGroup):
                res.extend(self._unroll_exceptions(exc.exceptions))

            else:
                res.append(exc)
        return res

    @overload
    def matches(
        self: RaisesGroup[ExcT_1],
        exception: BaseException | None,
    ) -> TypeGuard[ExceptionGroup[ExcT_1]]: ...
    @overload
    def matches(
        self: RaisesGroup[BaseExcT_1],
        exception: BaseException | None,
    ) -> TypeGuard[BaseExceptionGroup[BaseExcT_1]]: ...

    def matches(
        self,
        exception: BaseException | None,
    ) -> bool:
        """Check if an exception matches the requirements of this RaisesGroup.
        If it fails, `RaisesGroup.fail_reason` will be set.

        Example::

            with pytest.raises(TypeError) as excinfo:
                ...
            assert RaisesGroup(ValueError).matches(excinfo.value.__cause__)
            # the above line is equivalent to
            myexc = excinfo.value.__cause
            assert isinstance(myexc, BaseExceptionGroup)
            assert len(myexc.exceptions) == 1
            assert isinstance(myexc.exceptions[0], ValueError)
        """
        self._fail_reason = None
        if exception is None:
            self._fail_reason = "exception is None"
            return False
        if not isinstance(exception, BaseExceptionGroup):
            # we opt to only print type of the exception here, as the repr would
            # likely be quite long
            not_group_msg = f"`{type(exception).__name__}()` is not an exception group"
            if len(self.expected_exceptions) > 1:
                self._fail_reason = not_group_msg
                return False
            # if we have 1 expected exception, check if it would work even if
            # allow_unwrapped is not set
            res = self._check_expected(self.expected_exceptions[0], exception)
            if res is None and self.allow_unwrapped:
                return True

            if res is None:
                self._fail_reason = (
                    f"{not_group_msg}, but would match with `allow_unwrapped=True`"
                )
            elif self.allow_unwrapped:
                self._fail_reason = res
            else:
                self._fail_reason = not_group_msg
            return False

        actual_exceptions: Sequence[BaseException] = exception.exceptions
        if self.flatten_subgroups:
            actual_exceptions = self._unroll_exceptions(actual_exceptions)

        if not self._check_match(exception):
            self._fail_reason = cast(str, self._fail_reason)
            old_reason = self._fail_reason
            if (
                len(actual_exceptions) == len(self.expected_exceptions) == 1
                and isinstance(expected := self.expected_exceptions[0], type)
                and isinstance(actual := actual_exceptions[0], expected)
                and self._check_match(actual)
            ):
                assert self.match is not None, "can't be None if _check_match failed"
                assert self._fail_reason is old_reason is not None
                self._fail_reason += (
                    f"\n"
                    f" but matched the expected `{self._repr_expected(expected)}`.\n"
                    f" You might want "
                    f"`RaisesGroup(RaisesExc({expected.__name__}, match={_match_pattern(self.match)!r}))`"
                )
            else:
                self._fail_reason = old_reason
            return False

        # do the full check on expected exceptions
        if not self._check_exceptions(
            exception,
            actual_exceptions,
        ):
            self._fail_reason = cast(str, self._fail_reason)
            assert self._fail_reason is not None
            old_reason = self._fail_reason
            # if we're not expecting a nested structure, and there is one, do a second
            # pass where we try flattening it
            if (
                not self.flatten_subgroups
                and not any(
                    isinstance(e, RaisesGroup) for e in self.expected_exceptions
                )
                and any(isinstance(e, BaseExceptionGroup) for e in actual_exceptions)
                and self._check_exceptions(
                    exception,
                    self._unroll_exceptions(exception.exceptions),
                )
            ):
                # only indent if it's a single-line reason. In a multi-line there's already
                # indented lines that this does not belong to.
                indent = "  " if "\n" not in self._fail_reason else ""
                self._fail_reason = (
                    old_reason
                    + f"\n{indent}Did you mean to use `flatten_subgroups=True`?"
                )
            else:
                self._fail_reason = old_reason
            return False

        # Only run `self.check` once we know `exception` is of the correct type.
        if not self._check_check(exception):
            reason = (
                cast(str, self._fail_reason) + f" on the {type(exception).__name__}"
            )
            if (
                len(actual_exceptions) == len(self.expected_exceptions) == 1
                and isinstance(expected := self.expected_exceptions[0], type)
                # we explicitly break typing here :)
                and self._check_check(actual_exceptions[0])  # type: ignore[arg-type]
            ):
                self._fail_reason = reason + (
                    f", but did return True for the expected {self._repr_expected(expected)}."
                    f" You might want RaisesGroup(RaisesExc({expected.__name__}, check=<...>))"
                )
            else:
                self._fail_reason = reason
            return False

        return True

    @staticmethod
    def _check_expected(
        expected_type: (
            type[BaseException] | RaisesExc[BaseException] | RaisesGroup[BaseException]
        ),
        exception: BaseException,
    ) -> str | None:
        """Helper method for `RaisesGroup.matches` and `RaisesGroup._check_exceptions`
        to check one of potentially several expected exceptions."""
        if isinstance(expected_type, type):
            return _check_raw_type(expected_type, exception)
        res = expected_type.matches(exception)
        if res:
            return None
        assert expected_type.fail_reason is not None
        if expected_type.fail_reason.startswith("\n"):
            return f"\n{expected_type!r}: {indent(expected_type.fail_reason, '  ')}"
        return f"{expected_type!r}: {expected_type.fail_reason}"

    @staticmethod
    def _repr_expected(e: type[BaseException] | AbstractRaises[BaseException]) -> str:
        """Get the repr of an expected type/RaisesExc/RaisesGroup, but we only want
        the name if it's a type"""
        if isinstance(e, type):
            return _exception_type_name(e)
        return repr(e)

    @overload
    def _check_exceptions(
        self: RaisesGroup[ExcT_1],
        _exception: Exception,
        actual_exceptions: Sequence[Exception],
    ) -> TypeGuard[ExceptionGroup[ExcT_1]]: ...
    @overload
    def _check_exceptions(
        self: RaisesGroup[BaseExcT_1],
        _exception: BaseException,
        actual_exceptions: Sequence[BaseException],
    ) -> TypeGuard[BaseExceptionGroup[BaseExcT_1]]: ...

    def _check_exceptions(
        self,
        _exception: BaseException,
        actual_exceptions: Sequence[BaseException],
    ) -> bool:
        """Helper method for RaisesGroup.matches that attempts to pair up expected and actual exceptions"""
        # The _exception parameter is not used, but necessary for the TypeGuard

        # full table with all results
        results = ResultHolder(self.expected_exceptions, actual_exceptions)

        # (indexes of) raised exceptions that haven't (yet) found an expected
        remaining_actual = list(range(len(actual_exceptions)))
        # (indexes of) expected exceptions that haven't found a matching raised
        failed_expected: list[int] = []
        # successful greedy matches
        matches: dict[int, int] = {}

        # loop over expected exceptions first to get a more predictable result
        for i_exp, expected in enumerate(self.expected_exceptions):
            for i_rem in remaining_actual:
                res = self._check_expected(expected, actual_exceptions[i_rem])
                results.set_result(i_exp, i_rem, res)
                if res is None:
                    remaining_actual.remove(i_rem)
                    matches[i_exp] = i_rem
                    break
            else:
                failed_expected.append(i_exp)

        # All exceptions matched up successfully
        if not remaining_actual and not failed_expected:
            return True

        # in case of a single expected and single raised we simplify the output
        if 1 == len(actual_exceptions) == len(self.expected_exceptions):
            assert not matches
            self._fail_reason = res
            return False

        # The test case is failing, so we can do a slow and exhaustive check to find
        # duplicate matches etc that will be helpful in debugging
        for i_exp, expected in enumerate(self.expected_exceptions):
            for i_actual, actual in enumerate(actual_exceptions):
                if results.has_result(i_exp, i_actual):
                    continue
                results.set_result(
                    i_exp, i_actual, self._check_expected(expected, actual)
                )

        successful_str = (
            f"{len(matches)} matched exception{'s' if len(matches) > 1 else ''}. "
            if matches
            else ""
        )

        # all expected were found
        if not failed_expected and results.no_match_for_actual(remaining_actual):
            self._fail_reason = (
                f"{successful_str}Unexpected exception(s):"
                f" {[actual_exceptions[i] for i in remaining_actual]!r}"
            )
            return False
        # all raised exceptions were expected
        if not remaining_actual and results.no_match_for_expected(failed_expected):
            no_match_for_str = ", ".join(
                self._repr_expected(self.expected_exceptions[i])
                for i in failed_expected
            )
            self._fail_reason = f"{successful_str}Too few exceptions raised, found no match for: [{no_match_for_str}]"
            return False

        # if there's only one remaining and one failed, and the unmatched didn't match anything else,
        # we elect to only print why the remaining and the failed didn't match.
        if (
            1 == len(remaining_actual) == len(failed_expected)
            and results.no_match_for_actual(remaining_actual)
            and results.no_match_for_expected(failed_expected)
        ):
            self._fail_reason = f"{successful_str}{results.get_result(failed_expected[0], remaining_actual[0])}"
            return False

        # there's both expected and raised exceptions without matches
        s = ""
        if matches:
            s += f"\n{successful_str}"
        indent_1 = " " * 2
        indent_2 = " " * 4

        if not remaining_actual:
            s += "\nToo few exceptions raised!"
        elif not failed_expected:
            s += "\nUnexpected exception(s)!"

        if failed_expected:
            s += "\nThe following expected exceptions did not find a match:"
            rev_matches = {v: k for k, v in matches.items()}
        for i_failed in failed_expected:
            s += (
                f"\n{indent_1}{self._repr_expected(self.expected_exceptions[i_failed])}"
            )
            for i_actual, actual in enumerate(actual_exceptions):
                if results.get_result(i_failed, i_actual) is None:
                    # we print full repr of match target
                    s += (
                        f"\n{indent_2}It matches {backquote(repr(actual))} which was paired with "
                        + backquote(
                            self._repr_expected(
                                self.expected_exceptions[rev_matches[i_actual]]
                            )
                        )
                    )

        if remaining_actual:
            s += "\nThe following raised exceptions did not find a match"
        for i_actual in remaining_actual:
            s += f"\n{indent_1}{actual_exceptions[i_actual]!r}:"
            for i_exp, expected in enumerate(self.expected_exceptions):
                res = results.get_result(i_exp, i_actual)
                if i_exp in failed_expected:
                    assert res is not None
                    if res[0] != "\n":
                        s += "\n"
                    s += indent(res, indent_2)
                if res is None:
                    # we print full repr of match target
                    s += (
                        f"\n{indent_2}It matches {backquote(self._repr_expected(expected))} "
                        f"which was paired with {backquote(repr(actual_exceptions[matches[i_exp]]))}"
                    )

        if len(self.expected_exceptions) == len(actual_exceptions) and possible_match(
            results
        ):
            s += (
                "\nThere exist a possible match when attempting an exhaustive check,"
                " but RaisesGroup uses a greedy algorithm. "
                "Please make your expected exceptions more stringent with `RaisesExc` etc"
                " so the greedy algorithm can function."
            )
        self._fail_reason = s
        return False

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> bool:
        __tracebackhide__ = True
        if exc_type is None:
            fail(f"DID NOT RAISE any exception, expected `{self.expected_type()}`")

        assert self.excinfo is not None, (
            "Internal error - should have been constructed in __enter__"
        )

        # group_str is the only thing that differs between RaisesExc and RaisesGroup...
        # I might just scrap it? Or make it part of fail_reason
        group_str = (
            "(group)"
            if self.allow_unwrapped and not issubclass(exc_type, BaseExceptionGroup)
            else "group"
        )

        if not self.matches(exc_val):
            fail(f"Raised exception {group_str} did not match: {self._fail_reason}")

        # Cast to narrow the exception type now that it's verified....
        # even though the TypeGuard in self.matches should be narrowing
        exc_info = cast(
            "tuple[type[BaseExceptionGroup[BaseExcT_co]], BaseExceptionGroup[BaseExcT_co], types.TracebackType]",
            (exc_type, exc_val, exc_tb),
        )
        self.excinfo.fill_unfilled(exc_info)
        return True

    def expected_type(self) -> str:
        subexcs = []
        for e in self.expected_exceptions:
            if isinstance(e, RaisesExc):
                subexcs.append(repr(e))
            elif isinstance(e, RaisesGroup):
                subexcs.append(e.expected_type())
            elif isinstance(e, type):
                subexcs.append(e.__name__)
            else:  # pragma: no cover
                raise AssertionError("unknown type")
        group_type = "Base" if self.is_baseexception else ""
        return f"{group_type}ExceptionGroup({', '.join(subexcs)})"


@final
class NotChecked:
    """Singleton for unchecked values in ResultHolder"""


class ResultHolder:
    """Container for results of checking exceptions.
    Used in RaisesGroup._check_exceptions and possible_match.
    """

    def __init__(
        self,
        expected_exceptions: tuple[
            type[BaseException] | AbstractRaises[BaseException], ...
        ],
        actual_exceptions: Sequence[BaseException],
    ) -> None:
        self.results: list[list[str | type[NotChecked] | None]] = [
            [NotChecked for _ in expected_exceptions] for _ in actual_exceptions
        ]

    def set_result(self, expected: int, actual: int, result: str | None) -> None:
        self.results[actual][expected] = result

    def get_result(self, expected: int, actual: int) -> str | None:
        res = self.results[actual][expected]
        assert res is not NotChecked
        return res

    def has_result(self, expected: int, actual: int) -> bool:
        return self.results[actual][expected] is not NotChecked

    def no_match_for_expected(self, expected: list[int]) -> bool:
        for i in expected:
            for actual_results in self.results:
                assert actual_results[i] is not NotChecked
                if actual_results[i] is None:
                    return False
        return True

    def no_match_for_actual(self, actual: list[int]) -> bool:
        for i in actual:
            for res in self.results[i]:
                assert res is not NotChecked
                if res is None:
                    return False
        return True


def possible_match(results: ResultHolder, used: set[int] | None = None) -> bool:
    if used is None:
        used = set()
    curr_row = len(used)
    if curr_row == len(results.results):
        return True
    return any(
        val is None and i not in used and possible_match(results, used | {i})
        for (i, val) in enumerate(results.results[curr_row])
    )
