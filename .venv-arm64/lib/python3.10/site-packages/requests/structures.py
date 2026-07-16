"""
requests.structures
~~~~~~~~~~~~~~~~~~~

Data structures that power Requests.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Iterable, Iterator, Mapping
from typing import Any, Generic, TypeVar, overload

from .compat import MutableMapping

_VT = TypeVar("_VT")
_D = TypeVar("_D")


class CaseInsensitiveDict(MutableMapping[str, _VT], Generic[_VT]):
    """A case-insensitive ``dict``-like object.

    Implements all methods and operations of
    ``MutableMapping`` as well as dict's ``copy``. Also
    provides ``lower_items``.

    All keys are expected to be strings. The structure remembers the
    case of the last key to be set, and ``iter(instance)``,
    ``keys()``, ``items()``, ``iterkeys()``, and ``iteritems()``
    will contain case-sensitive keys. However, querying and contains
    testing is case insensitive::

        cid = CaseInsensitiveDict()
        cid['Accept'] = 'application/json'
        cid['aCCEPT'] == 'application/json'  # True
        list(cid) == ['Accept']  # True

    For example, ``headers['content-encoding']`` will return the
    value of a ``'Content-Encoding'`` response header, regardless
    of how the header name was originally stored.

    If the constructor, ``.update``, or equality comparison
    operations are given keys that have equal ``.lower()``s, the
    behavior is undefined.
    """

    _store: OrderedDict[str, tuple[str, _VT]]

    def __init__(
        self,
        data: Mapping[str, _VT] | Iterable[tuple[str, _VT]] | None = None,
        **kwargs: _VT,
    ) -> None:
        self._store = OrderedDict()
        if data is None:
            data = {}
        self.update(data, **kwargs)

    def __setitem__(self, key: str, value: _VT) -> None:
        # Use the lowercased key for lookups, but store the actual
        # key alongside the value.
        self._store[key.lower()] = (key, value)

    def __getitem__(self, key: str) -> _VT:
        return self._store[key.lower()][1]

    def __delitem__(self, key: str) -> None:
        del self._store[key.lower()]

    def __iter__(self) -> Iterator[str]:
        return (casedkey for casedkey, _ in self._store.values())

    def __len__(self) -> int:
        return len(self._store)

    def lower_items(self) -> Iterator[tuple[str, _VT]]:
        """Like iteritems(), but with all lowercase keys."""
        return ((lowerkey, keyval[1]) for (lowerkey, keyval) in self._store.items())

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Mapping):
            other_dict: CaseInsensitiveDict[Any] = CaseInsensitiveDict(other)  # type: ignore[reportUnknownArgumentType]
        else:
            return NotImplemented
        # Compare insensitively
        return dict(self.lower_items()) == dict(other_dict.lower_items())

    # Copy is required
    def copy(self) -> CaseInsensitiveDict[_VT]:
        return CaseInsensitiveDict(self._store.values())

    def __repr__(self) -> str:
        return str(dict(self.items()))


class LookupDict(dict[str, _VT]):
    """Dictionary lookup object."""

    name: Any

    def __init__(self, name: Any = None) -> None:
        self.name = name
        super().__init__()

    def __repr__(self) -> str:
        return f"<lookup '{self.name}'>"

    def __getattr__(self, key: str) -> _VT | None:
        # We need this for type checkers to infer typing
        # on attribute access with status_codes.py
        if key in self.__dict__:
            return self.__dict__[key]
        else:
            raise AttributeError(
                f"'{type(self).__name__}' object has no attribute '{key}'"
            )

    def __getitem__(self, key: str) -> _VT | None:  # type: ignore[override]
        # We allow fall-through here, so values default to None

        return self.__dict__.get(key, None)

    @overload
    def get(self, key: str, default: None = None) -> _VT | None: ...

    @overload
    def get(self, key: str, default: _D | _VT) -> _D | _VT: ...

    def get(self, key: str, default: _D | None = None) -> _VT | _D | None:
        return self.__dict__.get(key, default)
