"""
Hook wrapper "result" utilities.
"""

from __future__ import annotations

from types import TracebackType
from typing import Callable
from typing import cast
from typing import final
from typing import Generic
from typing import Optional
from typing import TypeVar


_ExcInfo = tuple[type[BaseException], BaseException, Optional[TracebackType]]
ResultType = TypeVar("ResultType")


class HookCallError(Exception):
    """Hook was called incorrectly."""


@final
class Result(Generic[ResultType]):
    """An object used to inspect and set the result in a :ref:`hook wrapper
    <hookwrappers>`."""

    __slots__ = ("_result", "_exception", "_traceback")

    def __init__(
        self,
        result: ResultType | None,
        exception: BaseException | None,
    ) -> None:
        """:meta private:"""
        self._result = result
        self._exception = exception
        # Exception __traceback__ is mutable, this keeps the original.
        self._traceback = exception.__traceback__ if exception is not None else None

    @property
    def excinfo(self) -> _ExcInfo | None:
        """:meta private:"""
        exc = self._exception
        if exc is None:
            return None
        else:
            return (type(exc), exc, self._traceback)

    @property
    def exception(self) -> BaseException | None:
        """:meta private:"""
        return self._exception

    @classmethod
    def from_call(cls, func: Callable[[], ResultType]) -> Result[ResultType]:
        """:meta private:"""
        __tracebackhide__ = True
        result = exception = None
        try:
            result = func()
        except BaseException as exc:
            exception = exc
        return cls(result, exception)

    def force_result(self, result: ResultType) -> None:
        """Force the result(s) to ``result``.

        If the hook was marked as a ``firstresult`` a single value should
        be set, otherwise set a (modified) list of results. Any exceptions
        found during invocation will be deleted.

        This overrides any previous result or exception.
        """
        self._result = result
        self._exception = None
        self._traceback = None

    def force_exception(self, exception: BaseException) -> None:
        """Force the result to fail with ``exception``.

        This overrides any previous result or exception.

        .. versionadded:: 1.1.0
        """
        self._result = None
        self._exception = exception
        self._traceback = exception.__traceback__ if exception is not None else None

    def get_result(self) -> ResultType:
        """Get the result(s) for this hook call.

        If the hook was marked as a ``firstresult`` only a single value
        will be returned, otherwise a list of results.
        """
        __tracebackhide__ = True
        exc = self._exception
        tb = self._traceback
        if exc is None:
            return cast(ResultType, self._result)
        else:
            raise exc.with_traceback(tb)


# Historical name (pluggy<=1.2), kept for backward compatibility.
_Result = Result
