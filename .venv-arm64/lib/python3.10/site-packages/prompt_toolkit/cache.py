from __future__ import annotations

from collections import deque
from functools import wraps
from typing import Any, Callable, Dict, Generic, Hashable, Tuple, TypeVar, cast

__all__ = [
    "SimpleCache",
    "FastDictCache",
    "memoized",
]

_T = TypeVar("_T", bound=Hashable)
_U = TypeVar("_U")


class SimpleCache(Generic[_T, _U]):
    """
    Very simple cache that discards the oldest item when the cache size is
    exceeded.

    :param maxsize: Maximum size of the cache. (Don't make it too big.)
    """

    def __init__(self, maxsize: int = 8) -> None:
        assert maxsize > 0

        self._data: dict[_T, _U] = {}
        self._keys: deque[_T] = deque()
        self.maxsize: int = maxsize

    def get(self, key: _T, getter_func: Callable[[], _U]) -> _U:
        """
        Get object from the cache.
        If not found, call `getter_func` to resolve it, and put that on the top
        of the cache instead.
        """
        # Look in cache first.
        try:
            return self._data[key]
        except KeyError:
            # Not found? Get it.
            value = getter_func()
            self._data[key] = value
            self._keys.append(key)

            # Remove the oldest key when the size is exceeded.
            if len(self._data) > self.maxsize:
                key_to_remove = self._keys.popleft()
                if key_to_remove in self._data:
                    del self._data[key_to_remove]

            return value

    def clear(self) -> None:
        "Clear cache."
        self._data = {}
        self._keys = deque()


_K = TypeVar("_K", bound=Tuple[Hashable, ...])
_V = TypeVar("_V")


class FastDictCache(Dict[_K, _V]):
    """
    Fast, lightweight cache which keeps at most `size` items.
    It will discard the oldest items in the cache first.

    The cache is a dictionary, which doesn't keep track of access counts.
    It is perfect to cache little immutable objects which are not expensive to
    create, but where a dictionary lookup is still much faster than an object
    instantiation.

    :param get_value: Callable that's called in case of a missing key.
    """

    # NOTE: This cache is used to cache `prompt_toolkit.layout.screen.Char` and
    #       `prompt_toolkit.Document`. Make sure to keep this really lightweight.
    #       Accessing the cache should stay faster than instantiating new
    #       objects.
    #       (Dictionary lookups are really fast.)
    #       SimpleCache is still required for cases where the cache key is not
    #       the same as the arguments given to the function that creates the
    #       value.)
    def __init__(self, get_value: Callable[..., _V], size: int = 1000000) -> None:
        assert size > 0

        self._keys: deque[_K] = deque()
        self.get_value = get_value
        self.size = size

    def __missing__(self, key: _K) -> _V:
        # Remove the oldest key when the size is exceeded.
        if len(self) > self.size:
            key_to_remove = self._keys.popleft()
            if key_to_remove in self:
                del self[key_to_remove]

        result = self.get_value(*key)
        self[key] = result
        self._keys.append(key)
        return result


_F = TypeVar("_F", bound=Callable[..., object])


def memoized(maxsize: int = 1024) -> Callable[[_F], _F]:
    """
    Memoization decorator for immutable classes and pure functions.
    """

    def decorator(obj: _F) -> _F:
        cache: SimpleCache[Hashable, Any] = SimpleCache(maxsize=maxsize)

        @wraps(obj)
        def new_callable(*a: Any, **kw: Any) -> Any:
            def create_new() -> Any:
                return obj(*a, **kw)

            key = (a, tuple(sorted(kw.items())))
            return cache.get(key, create_new)

        return cast(_F, new_callable)

    return decorator
