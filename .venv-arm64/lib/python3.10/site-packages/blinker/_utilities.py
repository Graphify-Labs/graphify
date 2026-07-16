from __future__ import annotations

import collections.abc as c
import inspect
import typing as t
from weakref import ref
from weakref import WeakMethod

T = t.TypeVar("T")


class Symbol:
    """A constant symbol, nicer than ``object()``. Repeated calls return the
    same instance.

    >>> Symbol('foo') is Symbol('foo')
    True
    >>> Symbol('foo')
    foo
    """

    symbols: t.ClassVar[dict[str, Symbol]] = {}

    def __new__(cls, name: str) -> Symbol:
        if name in cls.symbols:
            return cls.symbols[name]

        obj = super().__new__(cls)
        cls.symbols[name] = obj
        return obj

    def __init__(self, name: str) -> None:
        self.name = name

    def __repr__(self) -> str:
        return self.name

    def __getnewargs__(self) -> tuple[t.Any, ...]:
        return (self.name,)


def make_id(obj: object) -> c.Hashable:
    """Get a stable identifier for a receiver or sender, to be used as a dict
    key or in a set.
    """
    if inspect.ismethod(obj):
        # The id of a bound method is not stable, but the id of the unbound
        # function and instance are.
        return id(obj.__func__), id(obj.__self__)

    if isinstance(obj, (str, int)):
        # Instances with the same value always compare equal and have the same
        # hash, even if the id may change.
        return obj

    # Assume other types are not hashable but will always be the same instance.
    return id(obj)


def make_ref(obj: T, callback: c.Callable[[ref[T]], None] | None = None) -> ref[T]:
    if inspect.ismethod(obj):
        return WeakMethod(obj, callback)  # type: ignore[arg-type, return-value]

    return ref(obj, callback)
