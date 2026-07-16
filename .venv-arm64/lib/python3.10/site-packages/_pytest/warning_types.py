from __future__ import annotations

import dataclasses
import inspect
from types import FunctionType
from typing import Any
from typing import final
from typing import Generic
from typing import TypeVar
import warnings


class PytestWarning(UserWarning):
    """Base class for all warnings emitted by pytest."""

    __module__ = "pytest"


@final
class PytestAssertRewriteWarning(PytestWarning):
    """Warning emitted by the pytest assert rewrite module."""

    __module__ = "pytest"


@final
class PytestCacheWarning(PytestWarning):
    """Warning emitted by the cache plugin in various situations."""

    __module__ = "pytest"


@final
class PytestConfigWarning(PytestWarning):
    """Warning emitted for configuration issues."""

    __module__ = "pytest"


@final
class PytestCollectionWarning(PytestWarning):
    """Warning emitted when pytest is not able to collect a file or symbol in a module."""

    __module__ = "pytest"


class PytestDeprecationWarning(PytestWarning, DeprecationWarning):
    """Warning class for features that will be removed in a future version."""

    __module__ = "pytest"


class PytestRemovedIn10Warning(PytestDeprecationWarning):
    """Warning class for features that will be removed in pytest 10."""

    __module__ = "pytest"


@final
class PytestExperimentalApiWarning(PytestWarning, FutureWarning):
    """Warning category used to denote experiments in pytest.

    Use sparingly as the API might change or even be removed completely in a
    future version.
    """

    __module__ = "pytest"

    @classmethod
    def simple(cls, apiname: str) -> PytestExperimentalApiWarning:
        return cls(f"{apiname} is an experimental api that may change over time")


@final
class PytestReturnNotNoneWarning(PytestWarning):
    """
    Warning emitted when a test function returns a value other than ``None``.

    See :ref:`return-not-none` for details.
    """

    __module__ = "pytest"


@final
class PytestUnknownMarkWarning(PytestWarning):
    """Warning emitted on use of unknown markers.

    See :ref:`mark` for details.
    """

    __module__ = "pytest"


@final
class PytestUnraisableExceptionWarning(PytestWarning):
    """An unraisable exception was reported.

    Unraisable exceptions are exceptions raised in :meth:`__del__ <object.__del__>`
    implementations and similar situations when the exception cannot be raised
    as normal.
    """

    __module__ = "pytest"


@final
class PytestUnhandledThreadExceptionWarning(PytestWarning):
    """An unhandled exception occurred in a :class:`~threading.Thread`.

    Such exceptions don't propagate normally.
    """

    __module__ = "pytest"


_W = TypeVar("_W", bound=PytestWarning)


@final
@dataclasses.dataclass
class UnformattedWarning(Generic[_W]):
    """A warning meant to be formatted during runtime.

    This is used to hold warnings that need to format their message at runtime,
    as opposed to a direct message.
    """

    category: type[_W]
    template: str

    def format(self, **kwargs: Any) -> _W:
        """Return an instance of the warning category, formatted with given kwargs."""
        return self.category(self.template.format(**kwargs))


@final
class PytestFDWarning(PytestWarning):
    """When the lsof plugin finds leaked fds."""

    __module__ = "pytest"


def warn_explicit_for(method: FunctionType, message: PytestWarning) -> None:
    """
    Issue the warning :param:`message` for the definition of the given :param:`method`

    this helps to log warnings for functions defined prior to finding an issue with them
    (like hook wrappers being marked in a legacy mechanism)
    """
    lineno = method.__code__.co_firstlineno
    filename = inspect.getfile(method)
    module = method.__module__
    mod_globals = method.__globals__
    try:
        warnings.warn_explicit(
            message,
            type(message),
            filename=filename,
            module=module,
            registry=mod_globals.setdefault("__warningregistry__", {}),
            lineno=lineno,
        )
    except Warning as w:
        # If warnings are errors (e.g. -Werror), location information gets lost, so we add it to the message.
        raise type(w)(f"{w}\n at {filename}:{lineno}") from None
