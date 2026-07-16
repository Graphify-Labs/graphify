# mypy: allow-untyped-defs
from __future__ import annotations

import ast
from collections.abc import Callable
from collections.abc import Iterable
from collections.abc import Mapping
from collections.abc import Sequence
import dataclasses
import inspect
from io import StringIO
import os
from pathlib import Path
import re
import sys
from traceback import extract_tb
from traceback import format_exception
from traceback import format_exception_only
from traceback import FrameSummary
from types import CodeType
from types import FrameType
from types import TracebackType
from typing import Any
from typing import ClassVar
from typing import Final
from typing import final
from typing import Generic
from typing import Literal
from typing import overload
from typing import SupportsIndex
from typing import TypeAlias
from typing import TypeVar

import pluggy

import _pytest
from _pytest._code.source import findsource
from _pytest._code.source import getrawcode
from _pytest._code.source import getstatementrange_ast
from _pytest._code.source import Source
from _pytest._io import TerminalWriter
from _pytest._io.saferepr import safeformat
from _pytest._io.saferepr import saferepr
from _pytest.compat import get_real_func
from _pytest.deprecated import check_ispytest
from _pytest.pathlib import absolutepath
from _pytest.pathlib import bestrelpath


if sys.version_info < (3, 11):
    from exceptiongroup import BaseExceptionGroup

TracebackStyle = Literal["long", "short", "line", "no", "native", "value", "auto"]

EXCEPTION_OR_MORE = type[BaseException] | tuple[type[BaseException], ...]


class Code:
    """Wrapper around Python code objects."""

    __slots__ = ("raw",)

    def __init__(self, obj: CodeType) -> None:
        self.raw = obj

    @classmethod
    def from_function(cls, obj: object) -> Code:
        return cls(getrawcode(obj))

    def __eq__(self, other):
        return self.raw == other.raw

    # Ignore type because of https://github.com/python/mypy/issues/4266.
    __hash__ = None  # type: ignore

    @property
    def firstlineno(self) -> int:
        return self.raw.co_firstlineno - 1

    @property
    def name(self) -> str:
        return self.raw.co_name

    @property
    def path(self) -> Path | str:
        """Return a path object pointing to source code, or an ``str`` in
        case of ``OSError`` / non-existing file."""
        filename = inspect.getfile(self.raw)
        if not filename:
            return ""
        try:
            p = absolutepath(filename)
            # maybe don't try this checking
            if not p.exists():
                raise OSError("path check failed.")
            return p
        except OSError:
            # XXX maybe try harder like the weird logic
            # in the standard lib [linecache.updatecache] does?
            return filename

    @property
    def fullsource(self) -> Source | None:
        """Return a _pytest._code.Source object for the full source file of the code."""
        full, _ = findsource(self.raw)
        return full

    def source(self) -> Source:
        """Return a _pytest._code.Source object for the code object's source only."""
        # return source only for that part of code
        return Source(self.raw)

    def getargs(self, var: bool = False) -> tuple[str, ...]:
        """Return a tuple with the argument names for the code object.

        If 'var' is set True also return the names of the variable and
        keyword arguments when present.
        """
        # inspect.getargs merges positional and kwonly into a single list;
        # co_argcount is needed to exclude kwonly when var=False.
        args, varargs, varkw = inspect.getargs(self.raw)
        if not var:
            return tuple(args[: self.raw.co_argcount])
        result = list(args)
        if varargs is not None:
            result.append(varargs)
        if varkw is not None:
            result.append(varkw)
        return tuple(result)


class Frame:
    """Wrapper around a Python frame holding f_locals and f_globals
    in which expressions can be evaluated."""

    __slots__ = ("raw",)

    def __init__(self, frame: FrameType) -> None:
        self.raw = frame

    @property
    def lineno(self) -> int:
        return self.raw.f_lineno - 1

    @property
    def f_globals(self) -> dict[str, Any]:
        return self.raw.f_globals

    @property
    def f_locals(self) -> dict[str, Any]:
        return self.raw.f_locals

    @property
    def code(self) -> Code:
        return Code(self.raw.f_code)

    @property
    def statement(self) -> Source:
        """Statement this frame is at."""
        if self.code.fullsource is None:
            return Source("")
        return self.code.fullsource.getstatement(self.lineno)

    def eval(self, code, **vars):
        """Evaluate 'code' in the frame.

        'vars' are optional additional local variables.

        Returns the result of the evaluation.
        """
        f_locals = self.f_locals.copy()
        f_locals.update(vars)
        return eval(code, self.f_globals, f_locals)

    def repr(self, object: object) -> str:
        """Return a 'safe' (non-recursive, one-line) string repr for 'object'."""
        return saferepr(object)

    def getargs(self, var: bool = False):
        """Return a list of tuples (name, value) for all arguments.

        If 'var' is set True, also include the variable and keyword arguments
        when present.
        """
        retval = []
        for arg in self.code.getargs(var):
            try:
                retval.append((arg, self.f_locals[arg]))
            except KeyError:
                pass  # this can occur when using Psyco
        return retval


class TracebackEntry:
    """A single entry in a Traceback."""

    __slots__ = ("_rawentry", "_repr_style")

    def __init__(
        self,
        rawentry: TracebackType,
        repr_style: Literal["short", "long"] | None = None,
    ) -> None:
        self._rawentry: Final = rawentry
        self._repr_style: Final = repr_style

    def with_repr_style(
        self, repr_style: Literal["short", "long"] | None
    ) -> TracebackEntry:
        return TracebackEntry(self._rawentry, repr_style)

    @property
    def lineno(self) -> int:
        return self._rawentry.tb_lineno - 1

    def get_python_framesummary(self) -> FrameSummary:
        # Python's built-in traceback module implements all the nitty gritty
        # details to get column numbers of out frames.
        stack_summary = extract_tb(self._rawentry, limit=1)
        return stack_summary[0]

    # Column and end line numbers introduced in python 3.11
    if sys.version_info < (3, 11):

        @property
        def end_lineno_relative(self) -> int | None:
            return None

        @property
        def colno(self) -> int | None:
            return None

        @property
        def end_colno(self) -> int | None:
            return None
    else:

        @property
        def end_lineno_relative(self) -> int | None:
            frame_summary = self.get_python_framesummary()
            if frame_summary.end_lineno is None:  # pragma: no cover
                return None
            return frame_summary.end_lineno - 1 - self.frame.code.firstlineno

        @property
        def colno(self) -> int | None:
            """Starting byte offset of the expression in the traceback entry."""
            return self.get_python_framesummary().colno

        @property
        def end_colno(self) -> int | None:
            """Ending byte offset of the expression in the traceback entry."""
            return self.get_python_framesummary().end_colno

    @property
    def frame(self) -> Frame:
        return Frame(self._rawentry.tb_frame)

    @property
    def relline(self) -> int:
        return self.lineno - self.frame.code.firstlineno

    def __repr__(self) -> str:
        return f"<TracebackEntry {self.frame.code.path}:{self.lineno + 1}>"

    @property
    def statement(self) -> Source:
        """_pytest._code.Source object for the current statement."""
        source = self.frame.code.fullsource
        assert source is not None
        return source.getstatement(self.lineno)

    @property
    def path(self) -> Path | str:
        """Path to the source code."""
        return self.frame.code.path

    @property
    def locals(self) -> dict[str, Any]:
        """Locals of underlying frame."""
        return self.frame.f_locals

    def getfirstlinesource(self) -> int:
        return self.frame.code.firstlineno

    def getsource(
        self, astcache: dict[str | Path, ast.AST] | None = None
    ) -> Source | None:
        """Return failing source code."""
        # we use the passed in astcache to not reparse asttrees
        # within exception info printing
        source = self.frame.code.fullsource
        if source is None:
            return None
        key = astnode = None
        if astcache is not None:
            key = self.frame.code.path
            if key is not None:
                astnode = astcache.get(key, None)
        start = self.getfirstlinesource()
        try:
            astnode, _, end = getstatementrange_ast(
                self.lineno, source, astnode=astnode
            )
        except SyntaxError:
            end = self.lineno + 1
        else:
            if key is not None and astcache is not None:
                astcache[key] = astnode
        return source[start:end]

    source = property(getsource)

    def ishidden(self, excinfo: ExceptionInfo[BaseException] | None) -> bool:
        """Return True if the current frame has a var __tracebackhide__
        resolving to True.

        If __tracebackhide__ is a callable, it gets called with the
        ExceptionInfo instance and can decide whether to hide the traceback.

        Mostly for internal use.
        """
        tbh: bool | Callable[[ExceptionInfo[BaseException] | None], bool] = False
        for maybe_ns_dct in (self.frame.f_locals, self.frame.f_globals):
            # in normal cases, f_locals and f_globals are dictionaries
            # however via `exec(...)` / `eval(...)` they can be other types
            # (even incorrect types!).
            # as such, we suppress all exceptions while accessing __tracebackhide__
            try:
                tbh = maybe_ns_dct["__tracebackhide__"]
            except Exception:
                pass
            else:
                break
        if tbh and callable(tbh):
            return tbh(excinfo)
        return tbh

    def __str__(self) -> str:
        name = self.frame.code.name
        try:
            line = str(self.statement).lstrip()
        except KeyboardInterrupt:
            raise
        except BaseException:
            line = "???"
        # This output does not quite match Python's repr for traceback entries,
        # but changing it to do so would break certain plugins.  See
        # https://github.com/pytest-dev/pytest/pull/7535/ for details.
        return f"  File '{self.path}':{self.lineno + 1} in {name}\n  {line}\n"

    @property
    def name(self) -> str:
        """co_name of underlying code."""
        return self.frame.code.raw.co_name


class Traceback(list[TracebackEntry]):
    """Traceback objects encapsulate and offer higher level access to Traceback entries."""

    def __init__(
        self,
        tb: TracebackType | Iterable[TracebackEntry],
    ) -> None:
        """Initialize from given python traceback object and ExceptionInfo."""
        if isinstance(tb, TracebackType):

            def f(cur: TracebackType) -> Iterable[TracebackEntry]:
                cur_: TracebackType | None = cur
                while cur_ is not None:
                    yield TracebackEntry(cur_)
                    cur_ = cur_.tb_next

            super().__init__(f(tb))
        else:
            super().__init__(tb)

    def cut(
        self,
        path: os.PathLike[str] | str | None = None,
        lineno: int | None = None,
        firstlineno: int | None = None,
        excludepath: os.PathLike[str] | None = None,
    ) -> Traceback:
        """Return a Traceback instance wrapping part of this Traceback.

        By providing any combination of path, lineno and firstlineno, the
        first frame to start the to-be-returned traceback is determined.

        This allows cutting the first part of a Traceback instance e.g.
        for formatting reasons (removing some uninteresting bits that deal
        with handling of the exception/traceback).
        """
        path_ = None if path is None else os.fspath(path)
        excludepath_ = None if excludepath is None else os.fspath(excludepath)
        for x in self:
            code = x.frame.code
            codepath = code.path
            if path is not None and str(codepath) != path_:
                continue
            if (
                excludepath is not None
                and isinstance(codepath, Path)
                and excludepath_ in (str(p) for p in codepath.parents)  # type: ignore[operator]
            ):
                continue
            if lineno is not None and x.lineno != lineno:
                continue
            if firstlineno is not None and x.frame.code.firstlineno != firstlineno:
                continue
            return Traceback(x._rawentry)
        return self

    @overload
    def __getitem__(self, key: SupportsIndex) -> TracebackEntry: ...

    @overload
    def __getitem__(self, key: slice) -> Traceback: ...

    def __getitem__(self, key: SupportsIndex | slice) -> TracebackEntry | Traceback:
        if isinstance(key, slice):
            return self.__class__(super().__getitem__(key))
        else:
            return super().__getitem__(key)

    def filter(
        self,
        excinfo_or_fn: ExceptionInfo[BaseException] | Callable[[TracebackEntry], bool],
        /,
    ) -> Traceback:
        """Return a Traceback instance with certain items removed.

        If the filter is an `ExceptionInfo`, removes all the ``TracebackEntry``s
        which are hidden (see ishidden() above).

        Otherwise, the filter is a function that gets a single argument, a
        ``TracebackEntry`` instance, and should return True when the item should
        be added to the ``Traceback``, False when not.
        """
        if isinstance(excinfo_or_fn, ExceptionInfo):
            fn = lambda x: not x.ishidden(excinfo_or_fn)  # noqa: E731
        else:
            fn = excinfo_or_fn
        return Traceback(filter(fn, self))

    def recursionindex(self) -> int | None:
        """Return the index of the frame/TracebackEntry where recursion originates if
        appropriate, None if no recursion occurred."""
        cache: dict[tuple[Any, int, int], list[dict[str, Any]]] = {}
        for i, entry in enumerate(self):
            # id for the code.raw is needed to work around
            # the strange metaprogramming in the decorator lib from pypi
            # which generates code objects that have hash/value equality
            # XXX needs a test
            key = entry.frame.code.path, id(entry.frame.code.raw), entry.lineno
            values = cache.setdefault(key, [])
            # Since Python 3.13 f_locals is a proxy, freeze it.
            loc = dict(entry.frame.f_locals)
            if values:
                for otherloc in values:
                    if otherloc == loc:
                        return i
            values.append(loc)
        return None


def stringify_exception(
    exc: BaseException, include_subexception_msg: bool = True
) -> str:
    try:
        notes = getattr(exc, "__notes__", [])
    except KeyError:
        # Workaround for https://github.com/python/cpython/issues/98778 on
        # some 3.10 and 3.11 patch versions.
        HTTPError = getattr(sys.modules.get("urllib.error", None), "HTTPError", ())
        if sys.version_info < (3, 12) and isinstance(exc, HTTPError):
            notes = []
        else:  # pragma: no cover
            # exception not related to above bug, reraise
            raise
    if not include_subexception_msg and isinstance(exc, BaseExceptionGroup):
        message = exc.message
    else:
        message = str(exc)

    return "\n".join(
        [
            message,
            *notes,
        ]
    )


E = TypeVar("E", bound=BaseException, covariant=True)


@final
@dataclasses.dataclass
class ExceptionInfo(Generic[E]):
    """Wraps sys.exc_info() objects and offers help for navigating the traceback."""

    _assert_start_repr: ClassVar = "AssertionError('assert "

    _excinfo: tuple[type[E], E, TracebackType] | None
    _striptext: str
    _traceback: Traceback | None

    def __init__(
        self,
        excinfo: tuple[type[E], E, TracebackType] | None,
        striptext: str = "",
        traceback: Traceback | None = None,
        *,
        _ispytest: bool = False,
    ) -> None:
        check_ispytest(_ispytest)
        self._excinfo = excinfo
        self._striptext = striptext
        self._traceback = traceback

    @classmethod
    def from_exception(
        cls,
        # Ignoring error: "Cannot use a covariant type variable as a parameter".
        # This is OK to ignore because this class is (conceptually) readonly.
        # See https://github.com/python/mypy/issues/7049.
        exception: E,  # type: ignore[misc]
        exprinfo: str | None = None,
    ) -> ExceptionInfo[E]:
        """Return an ExceptionInfo for an existing exception.

        The exception must have a non-``None`` ``__traceback__`` attribute,
        otherwise this function fails with an assertion error. This means that
        the exception must have been raised, or added a traceback with the
        :py:meth:`~BaseException.with_traceback()` method.

        :param exprinfo:
            A text string helping to determine if we should strip
            ``AssertionError`` from the output. Defaults to the exception
            message/``__str__()``.

        .. versionadded:: 7.4
        """
        assert exception.__traceback__, (
            "Exceptions passed to ExcInfo.from_exception(...)"
            " must have a non-None __traceback__."
        )
        exc_info = (type(exception), exception, exception.__traceback__)
        return cls.from_exc_info(exc_info, exprinfo)

    @classmethod
    def from_exc_info(
        cls,
        exc_info: tuple[type[E], E, TracebackType],
        exprinfo: str | None = None,
    ) -> ExceptionInfo[E]:
        """Like :func:`from_exception`, but using old-style exc_info tuple."""
        _striptext = ""
        if exprinfo is None and isinstance(exc_info[1], AssertionError):
            exprinfo = getattr(exc_info[1], "msg", None)
            if exprinfo is None:
                exprinfo = saferepr(exc_info[1])
            if exprinfo and exprinfo.startswith(cls._assert_start_repr):
                _striptext = "AssertionError: "

        return cls(exc_info, _striptext, _ispytest=True)

    @classmethod
    def from_current(cls, exprinfo: str | None = None) -> ExceptionInfo[BaseException]:
        """Return an ExceptionInfo matching the current traceback.

        .. warning::

            Experimental API

        :param exprinfo:
            A text string helping to determine if we should strip
            ``AssertionError`` from the output. Defaults to the exception
            message/``__str__()``.
        """
        tup = sys.exc_info()
        assert tup[0] is not None, "no current exception"
        assert tup[1] is not None, "no current exception"
        assert tup[2] is not None, "no current exception"
        exc_info = (tup[0], tup[1], tup[2])
        return ExceptionInfo.from_exc_info(exc_info, exprinfo)

    @classmethod
    def for_later(cls) -> ExceptionInfo[E]:
        """Return an unfilled ExceptionInfo."""
        return cls(None, _ispytest=True)

    def fill_unfilled(self, exc_info: tuple[type[E], E, TracebackType]) -> None:
        """Fill an unfilled ExceptionInfo created with ``for_later()``."""
        assert self._excinfo is None, "ExceptionInfo was already filled"
        self._excinfo = exc_info

    @property
    def type(self) -> type[E]:
        """The exception class."""
        assert self._excinfo is not None, (
            ".type can only be used after the context manager exits"
        )
        return self._excinfo[0]

    @property
    def value(self) -> E:
        """The exception value."""
        assert self._excinfo is not None, (
            ".value can only be used after the context manager exits"
        )
        return self._excinfo[1]

    @property
    def tb(self) -> TracebackType:
        """The exception raw traceback."""
        assert self._excinfo is not None, (
            ".tb can only be used after the context manager exits"
        )
        return self._excinfo[2]

    @property
    def typename(self) -> str:
        """The type name of the exception."""
        assert self._excinfo is not None, (
            ".typename can only be used after the context manager exits"
        )
        return self.type.__name__

    @property
    def traceback(self) -> Traceback:
        """The traceback."""
        if self._traceback is None:
            self._traceback = Traceback(self.tb)
        return self._traceback

    @traceback.setter
    def traceback(self, value: Traceback) -> None:
        self._traceback = value

    def __repr__(self) -> str:
        if self._excinfo is None:
            return "<ExceptionInfo for raises contextmanager>"
        return f"<{self.__class__.__name__} {saferepr(self._excinfo[1])} tblen={len(self.traceback)}>"

    def exconly(self, tryshort: bool = False) -> str:
        """Return the exception as a string.

        This is usually a single line "<exception type>: <exception str>", but
        may also include additional lines for the exception notes, and detailed
        information for SyntaxError's.

        :param tryshort:
            If true, and the exception is an AssertionError, strip
            'AssertionError: ' from the beginning.
        """

        def _get_single_subexc(
            eg: BaseExceptionGroup[BaseException],
        ) -> BaseException | None:
            if len(eg.exceptions) != 1:
                return None
            if isinstance(e := eg.exceptions[0], BaseExceptionGroup):
                return _get_single_subexc(e)
            return e

        if (
            tryshort
            and isinstance(self.value, BaseExceptionGroup)
            and (subexc := _get_single_subexc(self.value)) is not None
        ):
            return f"{subexc!r} [single exception in {type(self.value).__name__}]"

        lines = format_exception_only(self.value)
        # The lines already include line separators.
        text = "".join(lines)
        text = text.rstrip()
        if tryshort:
            if text.startswith(self._striptext):
                text = text[len(self._striptext) :]
        return text

    def errisinstance(self, exc: EXCEPTION_OR_MORE) -> bool:
        """Return True if the exception is an instance of exc.

        Consider using ``isinstance(excinfo.value, exc)`` instead.
        """
        return isinstance(self.value, exc)

    def _getreprcrash(self) -> ReprFileLocation | None:
        # Find last non-hidden traceback entry that led to the exception of the
        # traceback, or None if all hidden.
        for i in range(-1, -len(self.traceback) - 1, -1):
            entry = self.traceback[i]
            if not entry.ishidden(self):
                path, lineno = entry.frame.code.raw.co_filename, entry.lineno
                exconly = self.exconly(tryshort=True)
                return ReprFileLocation(path, lineno + 1, exconly)
        return None

    def getrepr(
        self,
        showlocals: bool = False,
        style: TracebackStyle = "long",
        abspath: bool = False,
        tbfilter: bool | Callable[[ExceptionInfo[BaseException]], Traceback] = True,
        funcargs: bool = False,
        truncate_locals: bool = True,
        truncate_args: bool = True,
        chain: bool = True,
    ) -> ReprExceptionInfo | ExceptionChainRepr:
        """Return str()able representation of this exception info.

        The formatting parameters are ineffective if ``style="native"``,
        since in this case the native formatting is used.

        :param bool showlocals:
            Show locals per traceback entry.

        :param str style:
            long|short|line|no|native|value traceback style.

        :param bool abspath:
            If paths should be changed to absolute or left unchanged.

        :param tbfilter:
            A filter for traceback entries.

            * If false, don't hide any entries.
            * If true, hide internal entries and entries that contain a local
              variable ``__tracebackhide__ = True``.
            * If a callable, delegates the filtering to the callable.

        :param bool funcargs:
            Show function arguments per traceback entry.

        :param bool truncate_locals:
            Whether to show a size-limited `repr()` of locals, or a full
            pretty-printing.

        :param bool truncate_args:
            Whether to show a size-limited truncated `repr()` of function
            arguments, or a full pretty-printing.

        :param bool chain:
            If chained exceptions should be shown.

        .. versionchanged:: 3.9

            Added the ``chain`` parameter.
        """
        if style == "native":
            return ReprExceptionInfo(
                reprtraceback=ReprTracebackNative(
                    format_exception(
                        self.type,
                        self.value,
                        self.traceback[0]._rawentry if self.traceback else None,
                    )
                ),
                reprcrash=self._getreprcrash(),
            )

        fmt = ExceptionInfoFormatter(
            showlocals=showlocals,
            style=style,
            abspath=abspath,
            tbfilter=tbfilter,
            funcargs=funcargs,
            truncate_locals=truncate_locals,
            truncate_args=truncate_args,
            chain=chain,
        )
        return fmt.repr_excinfo(self)

    def match(self, regexp: str | re.Pattern[str]) -> Literal[True]:
        """Check whether the regular expression `regexp` matches the string
        representation of the exception using :func:`python:re.search`.

        If it matches `True` is returned, otherwise an `AssertionError` is raised.
        """
        __tracebackhide__ = True
        value = stringify_exception(self.value)
        msg = (
            f"Regex pattern did not match.\n"
            f"  Expected regex: {regexp!r}\n"
            f"  Actual message: {value!r}"
        )
        if regexp == value:
            msg += "\n Did you mean to `re.escape()` the regex?"
        assert re.search(regexp, value), msg
        # Return True to allow for "assert excinfo.match()".
        return True

    def _group_contains(
        self,
        exc_group: BaseExceptionGroup[BaseException],
        expected_exception: EXCEPTION_OR_MORE,
        match: str | re.Pattern[str] | None,
        target_depth: int | None = None,
        current_depth: int = 1,
    ) -> bool:
        """Return `True` if a `BaseExceptionGroup` contains a matching exception."""
        if (target_depth is not None) and (current_depth > target_depth):
            # already descended past the target depth
            return False
        for exc in exc_group.exceptions:
            if isinstance(exc, BaseExceptionGroup):
                if self._group_contains(
                    exc, expected_exception, match, target_depth, current_depth + 1
                ):
                    return True
            if (target_depth is not None) and (current_depth != target_depth):
                # not at the target depth, no match
                continue
            if not isinstance(exc, expected_exception):
                continue
            if match is not None:
                value = stringify_exception(exc)
                if not re.search(match, value):
                    continue
            return True
        return False

    def group_contains(
        self,
        expected_exception: EXCEPTION_OR_MORE,
        *,
        match: str | re.Pattern[str] | None = None,
        depth: int | None = None,
    ) -> bool:
        """Check whether a captured exception group contains a matching exception.

        :param Type[BaseException] | Tuple[Type[BaseException]] expected_exception:
            The expected exception type, or a tuple if one of multiple possible
            exception types are expected.

        :param str | re.Pattern[str] | None match:
            If specified, a string containing a regular expression,
            or a regular expression object, that is tested against the string
            representation of the exception and its `PEP-678 <https://peps.python.org/pep-0678/>` `__notes__`
            using :func:`re.search`.

            To match a literal string that may contain :ref:`special characters
            <re-syntax>`, the pattern can first be escaped with :func:`re.escape`.

        :param Optional[int] depth:
            If `None`, will search for a matching exception at any nesting depth.
            If >= 1, will only match an exception if it's at the specified depth (depth = 1 being
            the exceptions contained within the topmost exception group).

        .. versionadded:: 8.0

        .. warning::
           This helper makes it easy to check for the presence of specific exceptions,
           but it is very bad for checking that the group does *not* contain
           *any other exceptions*.
           You should instead consider using :class:`pytest.RaisesGroup`

        """
        msg = "Captured exception is not an instance of `BaseExceptionGroup`"
        assert isinstance(self.value, BaseExceptionGroup), msg
        msg = "`depth` must be >= 1 if specified"
        assert (depth is None) or (depth >= 1), msg
        return self._group_contains(self.value, expected_exception, match, depth)


# Type alias for the `tbfilter` setting:
# bool: If True, it should be filtered using Traceback.filter()
# callable: A callable that takes an ExceptionInfo and returns the filtered traceback.
TracebackFilter: TypeAlias = bool | Callable[[ExceptionInfo[BaseException]], Traceback]


@dataclasses.dataclass
class ExceptionInfoFormatter:
    """Helper object to format ExceptionInfo's and individual exception parts
    into TerminalRepr's.

    See :func:`ExceptionInfo.getrepr` for parameters.
    """

    # for traceback entries
    flow_marker: ClassVar = ">"
    fail_marker: ClassVar = "E"

    showlocals: bool = False
    # Note: "native" is handled outside of ExceptionInfoFormatter.
    style: TracebackStyle = "long"
    abspath: bool = True
    tbfilter: TracebackFilter = True
    funcargs: bool = False
    truncate_locals: bool = True
    truncate_args: bool = True
    chain: bool = True

    astcache: dict[str | Path, ast.AST] = dataclasses.field(
        default_factory=dict, init=False, repr=False
    )

    def _getindent(self, source: Source) -> int:
        # Figure out indent for the given source.
        try:
            s = str(source.getstatement(len(source) - 1))
        except KeyboardInterrupt:
            raise
        except BaseException:
            try:
                s = str(source[-1])
            except KeyboardInterrupt:
                raise
            except BaseException:
                return 0
        return 4 + (len(s) - len(s.lstrip()))

    def _getentrysource(self, entry: TracebackEntry) -> Source | None:
        source = entry.getsource(self.astcache)
        if source is not None:
            source = source.deindent()
        return source

    def repr_args(self, entry: TracebackEntry) -> ReprFuncArgs | None:
        if self.funcargs:
            args = []
            for argname, argvalue in entry.frame.getargs(var=True):
                if self.truncate_args:
                    str_repr = saferepr(argvalue)
                else:
                    str_repr = saferepr(argvalue, maxsize=None)
                args.append((argname, str_repr))
            return ReprFuncArgs(args)
        return None

    def get_source(
        self,
        source: Source | None,
        line_index: int = -1,
        excinfo: ExceptionInfo[BaseException] | None = None,
        short: bool = False,
        end_line_index: int | None = None,
        colno: int | None = None,
        end_colno: int | None = None,
    ) -> list[str]:
        """Return formatted and marked up source lines."""
        lines = []
        if source is not None and line_index < 0:
            line_index += len(source)
        if source is None or line_index >= len(source.lines) or line_index < 0:
            # `line_index` could still be outside `range(len(source.lines))` if
            # we're processing AST with pathological position attributes.
            source = Source("???")
            line_index = 0
        space_prefix = "    "
        if short:
            lines.append(space_prefix + source.lines[line_index].strip())
            lines.extend(
                self.get_highlight_arrows_for_line(
                    raw_line=source.raw_lines[line_index],
                    line=source.lines[line_index].strip(),
                    lineno=line_index,
                    end_lineno=end_line_index,
                    colno=colno,
                    end_colno=end_colno,
                )
            )
        else:
            for line in source.lines[:line_index]:
                lines.append(space_prefix + line)
            lines.append(self.flow_marker + "   " + source.lines[line_index])
            lines.extend(
                self.get_highlight_arrows_for_line(
                    raw_line=source.raw_lines[line_index],
                    line=source.lines[line_index],
                    lineno=line_index,
                    end_lineno=end_line_index,
                    colno=colno,
                    end_colno=end_colno,
                )
            )
            for line in source.lines[line_index + 1 :]:
                lines.append(space_prefix + line)
        if excinfo is not None:
            indent = 4 if short else self._getindent(source)
            lines.extend(self.get_exconly(excinfo, indent=indent, markall=True))
        return lines

    def get_highlight_arrows_for_line(
        self,
        line: str,
        raw_line: str,
        lineno: int | None,
        end_lineno: int | None,
        colno: int | None,
        end_colno: int | None,
    ) -> list[str]:
        """Return characters highlighting a source line.

        Example with colno and end_colno pointing to the bar expression:
                   "foo() + bar()"
        returns    "        ^^^^^"
        """
        if lineno != end_lineno:
            # Don't handle expressions that span multiple lines.
            return []
        if colno is None or end_colno is None:
            # Can't do anything without column information.
            return []

        num_stripped_chars = len(raw_line) - len(line)

        start_char_offset = _byte_offset_to_character_offset(raw_line, colno)
        end_char_offset = _byte_offset_to_character_offset(raw_line, end_colno)
        num_carets = end_char_offset - start_char_offset
        # If the highlight would span the whole line, it is redundant, don't
        # show it.
        if num_carets >= len(line.strip()):
            return []

        highlights = "    "
        highlights += " " * (start_char_offset - num_stripped_chars + 1)
        highlights += "^" * num_carets
        return [highlights]

    def get_exconly(
        self,
        excinfo: ExceptionInfo[BaseException],
        indent: int = 4,
        markall: bool = False,
    ) -> list[str]:
        lines = []
        indentstr = " " * indent
        # Get the real exception information out.
        exlines = excinfo.exconly(tryshort=True).split("\n")
        failindent = self.fail_marker + indentstr[1:]
        for line in exlines:
            lines.append(failindent + line)
            if not markall:
                failindent = indentstr
        return lines

    def repr_locals(self, locals: Mapping[str, object]) -> ReprLocals | None:
        if self.showlocals:
            lines = []
            # Variables starting with `@` are helpers injected by assertion
            # rewriting, not user variables, so hide them.
            keys = [loc for loc in locals if loc[0] != "@"]
            keys.sort()
            for name in keys:
                value = locals[name]
                if name == "__builtins__":
                    lines.append("__builtins__ = <builtins>")
                else:
                    # This formatting could all be handled by the
                    # _repr() function, which is only reprlib.Repr in
                    # disguise, so is very configurable.
                    if self.truncate_locals:
                        str_repr = saferepr(value)
                    else:
                        str_repr = safeformat(value)
                    # if len(str_repr) < 70 or not isinstance(value, (list, tuple, dict)):
                    lines.append(f"{name:<10} = {str_repr}")
                    # else:
                    #    self._line("%-10s =\\" % (name,))
                    #    # XXX
                    #    pprint.pprint(value, stream=self.excinfowriter)
            return ReprLocals(lines)
        return None

    def repr_traceback_entry(
        self,
        entry: TracebackEntry | None,
        excinfo: ExceptionInfo[BaseException] | None = None,
    ) -> ReprEntry:
        lines: list[str] = []
        style = (
            entry._repr_style
            if entry is not None and entry._repr_style is not None
            else self.style
        )
        if style in ("short", "long") and entry is not None:
            source = self._getentrysource(entry)
            if source is None:
                source = Source("???")
                line_index = 0
                end_line_index, colno, end_colno = None, None, None
            else:
                line_index = entry.relline
                end_line_index = entry.end_lineno_relative
                colno = entry.colno
                end_colno = entry.end_colno
            short = style == "short"
            reprargs = self.repr_args(entry) if not short else None
            s = self.get_source(
                source=source,
                line_index=line_index,
                excinfo=excinfo,
                short=short,
                end_line_index=end_line_index,
                colno=colno,
                end_colno=end_colno,
            )
            lines.extend(s)
            if short:
                message = f"in {entry.name}"
            else:
                message = (excinfo and excinfo.typename) or ""
            entry_path = entry.path
            path = self._makepath(entry_path)
            reprfileloc = ReprFileLocation(path, entry.lineno + 1, message)
            localsrepr = self.repr_locals(entry.locals)
            return ReprEntry(lines, reprargs, localsrepr, reprfileloc, style)
        elif style == "value":
            if excinfo:
                lines.extend(str(excinfo.value).split("\n"))
            return ReprEntry(lines, None, None, None, style)
        else:
            if excinfo:
                lines.extend(self.get_exconly(excinfo, indent=4))
            return ReprEntry(lines, None, None, None, style)

    def _makepath(self, path: Path | str) -> str:
        if not self.abspath and isinstance(path, Path):
            try:
                np = bestrelpath(Path.cwd(), path)
            except OSError:
                return str(path)
            if len(np) < len(str(path)):
                return np
        return str(path)

    def repr_traceback(self, excinfo: ExceptionInfo[BaseException]) -> ReprTraceback:
        traceback = filter_excinfo_traceback(self.tbfilter, excinfo)

        if isinstance(excinfo.value, RecursionError):
            traceback, extraline = self._truncate_recursive_traceback(traceback)
        else:
            extraline = None

        if not traceback:
            if extraline is None:
                extraline = "All traceback entries are hidden. Pass `--full-trace` to see hidden and internal frames."
            entries = [self.repr_traceback_entry(None, excinfo)]
            return ReprTraceback(entries, extraline, style=self.style)

        last = traceback[-1]
        if self.style == "value":
            entries = [self.repr_traceback_entry(last, excinfo)]
            return ReprTraceback(entries, None, style=self.style)

        entries = [
            self.repr_traceback_entry(entry, excinfo if last == entry else None)
            for entry in traceback
        ]
        return ReprTraceback(entries, extraline, style=self.style)

    def _truncate_recursive_traceback(
        self, traceback: Traceback
    ) -> tuple[Traceback, str | None]:
        """Truncate the given recursive traceback trying to find the starting
        point of the recursion.

        The detection is done by going through each traceback entry and
        finding the point in which the locals of the frame are equal to the
        locals of a previous frame (see ``recursionindex()``).

        Handle the situation where the recursion process might raise an
        exception (for example comparing numpy arrays using equality raises a
        TypeError), in which case we do our best to warn the user of the
        error and show a limited traceback.
        """
        try:
            recursionindex = traceback.recursionindex()
        except Exception as e:
            max_frames = 10
            extraline: str | None = (
                "!!! Recursion error detected, but an error occurred locating the origin of recursion.\n"
                "  The following exception happened when comparing locals in the stack frame:\n"
                f"    {type(e).__name__}: {e!s}\n"
                f"  Displaying first and last {max_frames} stack frames out of {len(traceback)}."
            )
            # Type ignored because adding two instances of a List subtype
            # currently incorrectly has type List instead of the subtype.
            traceback = traceback[:max_frames] + traceback[-max_frames:]  # type: ignore
        else:
            if recursionindex is not None:
                extraline = "!!! Recursion detected (same locals & position)"
                traceback = traceback[: recursionindex + 1]
            else:
                extraline = None

        return traceback, extraline

    def repr_excinfo(self, excinfo: ExceptionInfo[BaseException]) -> ExceptionChainRepr:
        repr_chain: list[tuple[ReprTraceback, ReprFileLocation | None, str | None]] = []
        e: BaseException | None = excinfo.value
        excinfo_: ExceptionInfo[BaseException] | None = excinfo
        description = None
        seen: set[int] = set()
        while e is not None and id(e) not in seen:
            seen.add(id(e))

            if excinfo_:
                # Fall back to native traceback as a temporary workaround until
                # full support for exception groups added to ExceptionInfo.
                # See https://github.com/pytest-dev/pytest/issues/9159
                reprtraceback: ReprTraceback | ReprTracebackNative
                if isinstance(e, BaseExceptionGroup):
                    # don't filter any sub-exceptions since they shouldn't have any internal frames
                    traceback = filter_excinfo_traceback(self.tbfilter, excinfo)
                    extraline = (
                        "All traceback entries are hidden. Pass `--full-trace` to see hidden and internal frames."
                        if not traceback
                        else None
                    )
                    reprtraceback = ReprTracebackNative(
                        format_exception(
                            type(excinfo.value),
                            excinfo.value,
                            traceback[0]._rawentry if traceback else None,
                        ),
                        extraline=extraline,
                    )

                else:
                    reprtraceback = self.repr_traceback(excinfo_)
                reprcrash = excinfo_._getreprcrash()
            else:
                # Fallback to native repr if the exception doesn't have a traceback:
                # ExceptionInfo objects require a full traceback to work.
                reprtraceback = ReprTracebackNative(format_exception(type(e), e, None))
                reprcrash = None
            repr_chain.append((reprtraceback, reprcrash, description))

            if e.__cause__ is not None and self.chain:
                e = e.__cause__
                excinfo_ = ExceptionInfo.from_exception(e) if e.__traceback__ else None
                description = "The above exception was the direct cause of the following exception:"
            elif (
                e.__context__ is not None and not e.__suppress_context__ and self.chain
            ):
                e = e.__context__
                excinfo_ = ExceptionInfo.from_exception(e) if e.__traceback__ else None
                description = "During handling of the above exception, another exception occurred:"
            else:
                e = None
        repr_chain.reverse()
        return ExceptionChainRepr(repr_chain)


@dataclasses.dataclass(eq=False)
class TerminalRepr:
    """Base class for terminal representations -- pieces of data that display
    themselves to a terminal."""

    def __str__(self) -> str:
        # FYI this is called from pytest-xdist's serialization of exception
        # information.
        io = StringIO()
        tw = TerminalWriter(file=io)
        self.toterminal(tw)
        return io.getvalue().strip()

    def __repr__(self) -> str:
        return f"<{self.__class__} instance at {id(self):0x}>"

    def toterminal(self, tw: TerminalWriter) -> None:
        raise NotImplementedError()


@dataclasses.dataclass(eq=False)
class ExceptionRepr(TerminalRepr):
    """Base class for exception terminal representations.

    The representation generally contains:
    - The exception traceback (`reprtraceback`)
    - The exception message and location (`reprcrash`)
    - Separated, titled sections with additional data (pytest core doesn't use
      this currently).
    """

    reprtraceback: ReprTraceback
    reprcrash: ReprFileLocation | None
    sections: list[tuple[str, str, str]] = dataclasses.field(
        init=False, default_factory=list
    )

    def addsection(self, name: str, content: str, sep: str = "-") -> None:
        self.sections.append((name, content, sep))

    def toterminal(self, tw: TerminalWriter) -> None:
        for name, content, sep in self.sections:
            tw.sep(sep, name)
            tw.line(content)


@dataclasses.dataclass(eq=False)
class ExceptionChainRepr(ExceptionRepr):
    """A chain of exceptions, separated by descriptions (e.g. "The above
    exception was the direct cause of the following exception")."""

    chain: Sequence[tuple[ReprTraceback, ReprFileLocation | None, str | None]]

    def __init__(
        self,
        chain: Sequence[tuple[ReprTraceback, ReprFileLocation | None, str | None]],
    ) -> None:
        # reprcrash and reprtraceback of the outermost (the newest) exception
        # in the chain.
        super().__init__(
            reprtraceback=chain[-1][0],
            reprcrash=chain[-1][1],
        )
        self.chain = chain

    def toterminal(self, tw: TerminalWriter) -> None:
        for reprtraceback, reprcrash, description in self.chain:
            reprtraceback.toterminal(tw)
            if description is not None:
                tw.line("")
                tw.line(description, yellow=True)
        super().toterminal(tw)


@dataclasses.dataclass(eq=False)
class ReprExceptionInfo(ExceptionRepr):
    """A single exception with optional extra details (function arguments,
    function locals, file location) and possible extra line and sections emitted
    at the end."""

    def toterminal(self, tw: TerminalWriter) -> None:
        self.reprtraceback.toterminal(tw)
        super().toterminal(tw)


@dataclasses.dataclass(eq=False)
class ReprTraceback(TerminalRepr):
    """A traceback with optional extra details (function arguments, function
    locals, file location) and possible extra line emitted at the end."""

    reprentries: Sequence[ReprEntry | ReprEntryNative]
    extraline: str | None
    style: TracebackStyle

    entrysep: ClassVar = "_ "

    def toterminal(self, tw: TerminalWriter) -> None:
        # The entries might have different styles.
        for i, entry in enumerate(self.reprentries):
            if entry.style == "long":
                tw.line("")
            entry.toterminal(tw)
            if i < len(self.reprentries) - 1:
                next_entry = self.reprentries[i + 1]
                if entry.style == "long" or (
                    entry.style == "short" and next_entry.style == "long"
                ):
                    tw.sep(self.entrysep)

        if self.extraline:
            tw.line(self.extraline)


class ReprTracebackNative(ReprTraceback):
    """A traceback in native style.

    The lines are emitted as is; uses a single entry for the entire native
    traceback.
    """

    def __init__(self, tblines: Sequence[str], *, extraline: str | None = None) -> None:
        self.reprentries = [ReprEntryNative(tblines)]
        self.extraline = extraline
        self.style = "native"


@dataclasses.dataclass(eq=False)
class ReprEntryNative(TerminalRepr):
    """An entry in a traceback in native style.

    Emits the lines as is. The lines are assumed to include the line separators.

    [Note that we currently use a single "entry" for the entire native
    traceback, so this is a bit misleading, but there's no point trying to parse
    or split a native traceback.]
    """

    lines: Sequence[str]

    style: ClassVar[TracebackStyle] = "native"

    def toterminal(self, tw: TerminalWriter) -> None:
        tw.write("".join(self.lines))


@dataclasses.dataclass(eq=False)
class ReprEntry(TerminalRepr):
    """An entry in a traceback with possible extra details (function arguments,
    function locals, source snippet, function's file and line)."""

    lines: Sequence[str]
    reprfuncargs: ReprFuncArgs | None
    reprlocals: ReprLocals | None
    reprfileloc: ReprFileLocation | None
    style: TracebackStyle

    def _write_entry_lines(self, tw: TerminalWriter) -> None:
        """Write the source code portions of a list of traceback entries with syntax highlighting.

        Usually entries are lines like these:

            "     x = 1"
            ">    assert x == 2"
            "E    assert 1 == 2"

        This function takes care of rendering the "source" portions of it (the lines without
        the "E" prefix) using syntax highlighting, taking care to not highlighting the ">"
        character, as doing so might break line continuations.
        """
        if not self.lines:
            return

        if self.style == "value":
            # Using tw.write instead of tw.line for testing purposes due to TWMock implementation;
            # lines written with TWMock.line and TWMock._write_source cannot be distinguished
            # from each other, whereas lines written with TWMock.write are marked with TWMock.WRITE
            for line in self.lines:
                tw.write(line)
                tw.write("\n")
            return

        # separate indents and source lines that are not failures: we want to
        # highlight the code but not the indentation, which may contain markers
        # such as ">   assert 0"
        fail_marker = f"{ExceptionInfoFormatter.fail_marker}   "
        indent_size = len(fail_marker)
        indents: list[str] = []
        source_lines: list[str] = []
        failure_lines: list[str] = []
        for index, line in enumerate(self.lines):
            is_failure_line = line.startswith(fail_marker)
            if is_failure_line:
                # from this point on all lines are considered part of the failure
                failure_lines.extend(self.lines[index:])
                break
            else:
                indents.append(line[:indent_size])
                source_lines.append(line[indent_size:])

        tw._write_source(source_lines, indents)

        # failure lines are always completely red and bold
        for line in failure_lines:
            tw.line(line, bold=True, red=True)

    def toterminal(self, tw: TerminalWriter) -> None:
        if self.style == "short":
            if self.reprfileloc:
                self.reprfileloc.toterminal(tw)
            self._write_entry_lines(tw)
            if self.reprlocals:
                self.reprlocals.toterminal(tw, indent=" " * 8)
            return

        if self.reprfuncargs:
            self.reprfuncargs.toterminal(tw)

        self._write_entry_lines(tw)

        if self.reprlocals:
            tw.line("")
            self.reprlocals.toterminal(tw)
        if self.reprfileloc:
            if self.lines:
                tw.line("")
            self.reprfileloc.toterminal(tw)

    def __str__(self) -> str:
        return "{}\n{}\n{}".format(
            "\n".join(self.lines), self.reprlocals, self.reprfileloc
        )


@dataclasses.dataclass(eq=False)
class ReprFileLocation(TerminalRepr):
    """A message at a file location, using the `<path>:<lineno>: <message>`
    format that most editors understand.

    Only the first line of the message is emitted.
    """

    path: str
    lineno: int
    message: str

    def __post_init__(self) -> None:
        self.path = str(self.path)

    def toterminal(self, tw: TerminalWriter) -> None:
        msg = self.message
        i = msg.find("\n")
        if i != -1:
            msg = msg[:i]
        tw.write(self.path, bold=True, red=True)
        tw.line(f":{self.lineno}: {msg}")


@dataclasses.dataclass(eq=False)
class ReprLocals(TerminalRepr):
    """Function local variables (pre-formatted)."""

    lines: Sequence[str]

    def toterminal(self, tw: TerminalWriter, indent: str = "") -> None:
        for line in self.lines:
            tw.line(indent + line)


@dataclasses.dataclass(eq=False)
class ReprFuncArgs(TerminalRepr):
    """Function arguments - name = value, comma separated."""

    args: Sequence[tuple[str, object]]

    def toterminal(self, tw: TerminalWriter) -> None:
        if self.args:
            linesofar = ""
            for name, value in self.args:
                ns = f"{name} = {value}"
                if len(ns) + len(linesofar) + 2 > tw.fullwidth:
                    if linesofar:
                        tw.line(linesofar)
                    linesofar = ns
                else:
                    if linesofar:
                        linesofar += ", " + ns
                    else:
                        linesofar = ns
            if linesofar:
                tw.line(linesofar)
            tw.line("")


def getfslineno(obj: object) -> tuple[str | Path, int]:
    """Return source location (path, lineno) for the given object.

    If the source cannot be determined return ("", -1).

    The line number is 0-based.
    """
    # xxx let decorators etc specify a sane ordering
    # NOTE: this used to be done in _pytest.compat.getfslineno, initially added
    #       in 6ec13a2b9.  It ("place_as") appears to be something very custom.
    obj = get_real_func(obj)
    if hasattr(obj, "place_as"):
        obj = obj.place_as

    try:
        code = Code.from_function(obj)
    except TypeError:
        try:
            fn = inspect.getsourcefile(obj) or inspect.getfile(obj)  # type: ignore[arg-type]
        except TypeError:
            return "", -1

        fspath = (fn and absolutepath(fn)) or ""
        lineno = -1
        if fspath:
            try:
                _, lineno = findsource(obj)
            except OSError:
                pass
        return fspath, lineno

    return code.path, code.firstlineno


def _byte_offset_to_character_offset(str, offset):
    """Converts a byte based offset in a string to a code-point."""
    as_utf8 = str.encode("utf-8")
    return len(as_utf8[:offset].decode("utf-8", errors="replace"))


# Relative paths that we use to filter traceback entries from appearing to the user;
# see filter_traceback.
# note: if we need to add more paths than what we have now we should probably use a list
# for better maintenance.

_PLUGGY_DIR = Path(pluggy.__file__.rstrip("oc"))
# pluggy is either a package or a single module depending on the version
if _PLUGGY_DIR.name == "__init__.py":
    _PLUGGY_DIR = _PLUGGY_DIR.parent
_PYTEST_DIR = Path(_pytest.__file__).parent


def filter_traceback(entry: TracebackEntry) -> bool:
    """Return True if a TracebackEntry instance should be included in tracebacks.

    We hide traceback entries of:

    * dynamically generated code (no code to show up for it);
    * internal traceback from pytest or its internal libraries, py and pluggy.
    """
    # entry.path might sometimes return a str object when the entry
    # points to dynamically generated code.
    # See https://bitbucket.org/pytest-dev/py/issues/71.
    raw_filename = entry.frame.code.raw.co_filename
    is_generated = "<" in raw_filename and ">" in raw_filename
    if is_generated:
        return False

    # entry.path might point to a non-existing file, in which case it will
    # also return a str object. See #1133.
    p = Path(entry.path)

    parents = p.parents
    if _PLUGGY_DIR in parents:
        return False
    if _PYTEST_DIR in parents:
        return False

    return True


def filter_excinfo_traceback(
    tbfilter: TracebackFilter, excinfo: ExceptionInfo[BaseException]
) -> Traceback:
    """Filter the exception traceback in ``excinfo`` according to ``tbfilter``."""
    if callable(tbfilter):
        return tbfilter(excinfo)
    elif tbfilter:
        return excinfo.traceback.filter(excinfo)
    else:
        return excinfo.traceback
