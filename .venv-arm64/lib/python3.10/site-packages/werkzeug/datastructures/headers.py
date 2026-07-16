from __future__ import annotations

import collections.abc as cabc
import re
import typing as t

from .._internal import _missing
from ..exceptions import BadRequestKeyError
from .mixins import ImmutableHeadersMixin
from .structures import iter_multi_items
from .structures import MultiDict

if t.TYPE_CHECKING:
    import typing_extensions as te
    from _typeshed.wsgi import WSGIEnvironment

T = t.TypeVar("T")


class Headers:
    """An object that stores some headers. It has a dict-like interface,
    but is ordered, can store the same key multiple times, and iterating
    yields ``(key, value)`` pairs instead of only keys.

    This data structure is useful if you want a nicer way to handle WSGI
    headers which are stored as tuples in a list.

    From Werkzeug 0.3 onwards, the :exc:`KeyError` raised by this class is
    also a subclass of the :class:`~exceptions.BadRequest` HTTP exception
    and will render a page for a ``400 BAD REQUEST`` if caught in a
    catch-all for HTTP exceptions.

    Headers is mostly compatible with the Python :class:`wsgiref.headers.Headers`
    class, with the exception of `__getitem__`.  :mod:`wsgiref` will return
    `None` for ``headers['missing']``, whereas :class:`Headers` will raise
    a :class:`KeyError`.

    To create a new ``Headers`` object, pass it a list, dict, or
    other ``Headers`` object with default values. These values are
    validated the same way values added later are.

    :param defaults: The list of default values for the :class:`Headers`.

    .. versionchanged:: 3.1
        Implement ``|`` and ``|=`` operators.

    .. versionchanged:: 2.1.0
        Default values are validated the same as values added later.

    .. versionchanged:: 0.9
       This data structure now stores unicode values similar to how the
       multi dicts do it.  The main difference is that bytes can be set as
       well which will automatically be latin1 decoded.

    .. versionchanged:: 0.9
       The :meth:`linked` function was removed without replacement as it
       was an API that does not support the changes to the encoding model.
    """

    def __init__(
        self,
        defaults: (
            Headers
            | MultiDict[str, t.Any]
            | cabc.Mapping[str, t.Any | list[t.Any] | tuple[t.Any, ...] | set[t.Any]]
            | cabc.Iterable[tuple[str, t.Any]]
            | None
        ) = None,
    ) -> None:
        self._list: list[tuple[str, str]] = []

        if defaults is not None:
            self.extend(defaults)

    @t.overload
    def __getitem__(self, key: str) -> str: ...
    @t.overload
    def __getitem__(self, key: int) -> tuple[str, str]: ...
    @t.overload
    def __getitem__(self, key: slice) -> te.Self: ...
    def __getitem__(self, key: str | int | slice) -> str | tuple[str, str] | te.Self:
        if isinstance(key, str):
            return self._get_key(key)

        if isinstance(key, int):
            return self._list[key]

        return self.__class__(self._list[key])

    def _get_key(self, key: str) -> str:
        ikey = key.lower()

        for k, v in self._list:
            if k.lower() == ikey:
                return v

        raise BadRequestKeyError(key)

    def __eq__(self, other: object) -> bool:
        if other.__class__ is not self.__class__:
            return NotImplemented

        def lowered(item: tuple[str, ...]) -> tuple[str, ...]:
            return item[0].lower(), *item[1:]

        return set(map(lowered, other._list)) == set(map(lowered, self._list))  # type: ignore[attr-defined]

    __hash__ = None  # type: ignore[assignment]

    @t.overload
    def get(self, key: str) -> str | None: ...
    @t.overload
    def get(self, key: str, default: str) -> str: ...
    @t.overload
    def get(self, key: str, default: T) -> str | T: ...
    @t.overload
    def get(self, key: str, type: cabc.Callable[[str], T]) -> T | None: ...
    @t.overload
    def get(self, key: str, default: T, type: cabc.Callable[[str], T]) -> T: ...
    def get(  # type: ignore[misc]
        self,
        key: str,
        default: str | T | None = None,
        type: cabc.Callable[[str], T] | None = None,
    ) -> str | T | None:
        """Return the default value if the requested data doesn't exist.
        If `type` is provided and is a callable it should convert the value,
        return it or raise a :exc:`ValueError` if that is not possible.  In
        this case the function will return the default as if the value was not
        found:

        >>> d = Headers([('Content-Length', '42')])
        >>> d.get('Content-Length', type=int)
        42

        :param key: The key to be looked up.
        :param default: The default value to be returned if the key can't
                        be looked up.  If not further specified `None` is
                        returned.
        :param type: A callable that is used to cast the value in the
                     :class:`Headers`.  If a :exc:`ValueError` is raised
                     by this callable the default value is returned.

        .. versionchanged:: 3.0
            The ``as_bytes`` parameter was removed.

        .. versionchanged:: 0.9
            The ``as_bytes`` parameter was added.
        """
        try:
            rv = self._get_key(key)
        except KeyError:
            return default

        if type is None:
            return rv

        try:
            return type(rv)
        except ValueError:
            return default

    @t.overload
    def getlist(self, key: str) -> list[str]: ...
    @t.overload
    def getlist(self, key: str, type: cabc.Callable[[str], T]) -> list[T]: ...
    def getlist(
        self, key: str, type: cabc.Callable[[str], T] | None = None
    ) -> list[str] | list[T]:
        """Return the list of items for a given key. If that key is not in the
        :class:`Headers`, the return value will be an empty list.  Just like
        :meth:`get`, :meth:`getlist` accepts a `type` parameter.  All items will
        be converted with the callable defined there.

        :param key: The key to be looked up.
        :param type: A callable that is used to cast the value in the
                     :class:`Headers`.  If a :exc:`ValueError` is raised
                     by this callable the value will be removed from the list.
        :return: a :class:`list` of all the values for the key.

        .. versionchanged:: 3.0
            The ``as_bytes`` parameter was removed.

        .. versionchanged:: 0.9
            The ``as_bytes`` parameter was added.
        """
        ikey = key.lower()

        if type is not None:
            result = []

            for k, v in self:
                if k.lower() == ikey:
                    try:
                        result.append(type(v))
                    except ValueError:
                        continue

            return result

        return [v for k, v in self if k.lower() == ikey]

    def get_all(self, name: str) -> list[str]:
        """Return a list of all the values for the named field.

        This method is compatible with the :mod:`wsgiref`
        :meth:`~wsgiref.headers.Headers.get_all` method.
        """
        return self.getlist(name)

    def items(self, lower: bool = False) -> t.Iterable[tuple[str, str]]:
        for key, value in self:
            if lower:
                key = key.lower()
            yield key, value

    def keys(self, lower: bool = False) -> t.Iterable[str]:
        for key, _ in self.items(lower):
            yield key

    def values(self) -> t.Iterable[str]:
        for _, value in self.items():
            yield value

    def extend(
        self,
        arg: (
            Headers
            | MultiDict[str, t.Any]
            | cabc.Mapping[str, t.Any | list[t.Any] | tuple[t.Any, ...] | set[t.Any]]
            | cabc.Iterable[tuple[str, t.Any]]
            | None
        ) = None,
        /,
        **kwargs: str,
    ) -> None:
        """Extend headers in this object with items from another object
        containing header items as well as keyword arguments.

        To replace existing keys instead of extending, use
        :meth:`update` instead.

        If provided, the first argument can be another :class:`Headers`
        object, a :class:`MultiDict`, :class:`dict`, or iterable of
        pairs.

        .. versionchanged:: 1.0
            Support :class:`MultiDict`. Allow passing ``kwargs``.
        """
        if arg is not None:
            for key, value in iter_multi_items(arg):
                self.add(key, value)

        for key, value in iter_multi_items(kwargs):
            self.add(key, value)

    def __delitem__(self, key: str | int | slice) -> None:
        if isinstance(key, str):
            self._del_key(key)
            return

        del self._list[key]

    def _del_key(self, key: str) -> None:
        key = key.lower()
        new = []

        for k, v in self._list:
            if k.lower() != key:
                new.append((k, v))

        self._list[:] = new

    def remove(self, key: str) -> None:
        """Remove a key.

        :param key: The key to be removed.
        """
        return self._del_key(key)

    @t.overload
    def pop(self) -> tuple[str, str]: ...
    @t.overload
    def pop(self, key: str) -> str: ...
    @t.overload
    def pop(self, key: int | None = ...) -> tuple[str, str]: ...
    @t.overload
    def pop(self, key: str, default: str) -> str: ...
    @t.overload
    def pop(self, key: str, default: T) -> str | T: ...
    def pop(
        self,
        key: str | int | None = None,
        default: str | T = _missing,  # type: ignore[assignment]
    ) -> str | tuple[str, str] | T:
        """Removes and returns a key or index.

        :param key: The key to be popped.  If this is an integer the item at
                    that position is removed, if it's a string the value for
                    that key is.  If the key is omitted or `None` the last
                    item is removed.
        :return: an item.
        """
        if key is None:
            return self._list.pop()

        if isinstance(key, int):
            return self._list.pop(key)

        try:
            rv = self._get_key(key)
        except KeyError:
            if default is not _missing:
                return default

            raise

        self.remove(key)
        return rv

    def popitem(self) -> tuple[str, str]:
        """Removes a key or index and returns a (key, value) item."""
        return self._list.pop()

    def __contains__(self, key: str) -> bool:
        """Check if a key is present."""
        try:
            self._get_key(key)
        except KeyError:
            return False

        return True

    def __iter__(self) -> t.Iterator[tuple[str, str]]:
        """Yield ``(key, value)`` tuples."""
        return iter(self._list)

    def __len__(self) -> int:
        return len(self._list)

    def add(self, key: str, value: t.Any, /, **kwargs: t.Any) -> None:
        """Add a new header tuple to the list.

        Keyword arguments can specify additional parameters for the header
        value, with underscores converted to dashes::

        >>> d = Headers()
        >>> d.add('Content-Type', 'text/plain')
        >>> d.add('Content-Disposition', 'attachment', filename='foo.png')

        The keyword argument dumping uses :func:`dump_options_header`
        behind the scenes.

        .. versionchanged:: 0.4.1
            keyword arguments were added for :mod:`wsgiref` compatibility.
        """
        if kwargs:
            value = _options_header_vkw(value, kwargs)

        value_str = _str_header_value(value)
        self._list.append((key, value_str))

    def add_header(self, key: str, value: t.Any, /, **kwargs: t.Any) -> None:
        """Add a new header tuple to the list.

        An alias for :meth:`add` for compatibility with the :mod:`wsgiref`
        :meth:`~wsgiref.headers.Headers.add_header` method.
        """
        self.add(key, value, **kwargs)

    def clear(self) -> None:
        """Clears all headers."""
        self._list.clear()

    def set(self, key: str, value: t.Any, /, **kwargs: t.Any) -> None:
        """Remove all header tuples for `key` and add a new one.  The newly
        added key either appears at the end of the list if there was no
        entry or replaces the first one.

        Keyword arguments can specify additional parameters for the header
        value, with underscores converted to dashes.  See :meth:`add` for
        more information.

        .. versionchanged:: 0.6.1
           :meth:`set` now accepts the same arguments as :meth:`add`.

        :param key: The key to be inserted.
        :param value: The value to be inserted.
        """
        if kwargs:
            value = _options_header_vkw(value, kwargs)

        value_str = _str_header_value(value)

        if not self._list:
            self._list.append((key, value_str))
            return

        iter_list = iter(self._list)
        ikey = key.lower()

        for idx, (old_key, _) in enumerate(iter_list):
            if old_key.lower() == ikey:
                # replace first occurrence
                self._list[idx] = (key, value_str)
                break
        else:
            # no existing occurrences
            self._list.append((key, value_str))
            return

        # remove remaining occurrences
        self._list[idx + 1 :] = [t for t in iter_list if t[0].lower() != ikey]

    def setlist(self, key: str, values: cabc.Iterable[t.Any]) -> None:
        """Remove any existing values for a header and add new ones.

        :param key: The header key to set.
        :param values: An iterable of values to set for the key.

        .. versionadded:: 1.0
        """
        if values:
            values_iter = iter(values)
            self.set(key, next(values_iter))

            for value in values_iter:
                self.add(key, value)
        else:
            self.remove(key)

    def setdefault(self, key: str, default: t.Any) -> str:
        """Return the first value for the key if it is in the headers,
        otherwise set the header to the value given by ``default`` and
        return that.

        :param key: The header key to get.
        :param default: The value to set for the key if it is not in the
            headers.
        """
        try:
            return self._get_key(key)
        except KeyError:
            pass

        self.set(key, default)
        return self._get_key(key)

    def setlistdefault(self, key: str, default: cabc.Iterable[t.Any]) -> list[str]:
        """Return the list of values for the key if it is in the
        headers, otherwise set the header to the list of values given
        by ``default`` and return that.

        Unlike :meth:`MultiDict.setlistdefault`, modifying the returned
        list will not affect the headers.

        :param key: The header key to get.
        :param default: An iterable of values to set for the key if it
            is not in the headers.

        .. versionadded:: 1.0
        """
        if key not in self:
            self.setlist(key, default)

        return self.getlist(key)

    @t.overload
    def __setitem__(self, key: str, value: t.Any) -> None: ...
    @t.overload
    def __setitem__(self, key: int, value: tuple[str, t.Any]) -> None: ...
    @t.overload
    def __setitem__(
        self, key: slice, value: cabc.Iterable[tuple[str, t.Any]]
    ) -> None: ...
    def __setitem__(
        self,
        key: str | int | slice,
        value: t.Any | tuple[str, t.Any] | cabc.Iterable[tuple[str, t.Any]],
    ) -> None:
        """Like :meth:`set` but also supports index/slice based setting."""
        if isinstance(key, str):
            self.set(key, value)
        elif isinstance(key, int):
            self._list[key] = value[0], _str_header_value(value[1])  # type: ignore[index]
        else:
            self._list[key] = [(k, _str_header_value(v)) for k, v in value]  # type: ignore[misc]

    def update(
        self,
        arg: (
            Headers
            | MultiDict[str, t.Any]
            | cabc.Mapping[
                str, t.Any | list[t.Any] | tuple[t.Any, ...] | cabc.Set[t.Any]
            ]
            | cabc.Iterable[tuple[str, t.Any]]
            | None
        ) = None,
        /,
        **kwargs: t.Any | list[t.Any] | tuple[t.Any, ...] | cabc.Set[t.Any],
    ) -> None:
        """Replace headers in this object with items from another
        headers object and keyword arguments.

        To extend existing keys instead of replacing, use :meth:`extend`
        instead.

        If provided, the first argument can be another :class:`Headers`
        object, a :class:`MultiDict`, :class:`dict`, or iterable of
        pairs.

        .. versionadded:: 1.0
        """
        if arg is not None:
            if isinstance(arg, (Headers, MultiDict)):
                for key in arg.keys():
                    self.setlist(key, arg.getlist(key))
            elif isinstance(arg, cabc.Mapping):
                for key, value in arg.items():
                    if isinstance(value, (list, tuple, set)):
                        self.setlist(key, value)
                    else:
                        self.set(key, value)
            else:
                for key, value in arg:
                    self.set(key, value)

        for key, value in kwargs.items():
            if isinstance(value, (list, tuple, set)):
                self.setlist(key, value)
            else:
                self.set(key, value)

    def __or__(
        self,
        other: cabc.Mapping[
            str, t.Any | list[t.Any] | tuple[t.Any, ...] | cabc.Set[t.Any]
        ],
    ) -> te.Self:
        if not isinstance(other, cabc.Mapping):
            return NotImplemented

        rv = self.copy()
        rv.update(other)
        return rv

    def __ior__(
        self,
        other: (
            cabc.Mapping[str, t.Any | list[t.Any] | tuple[t.Any, ...] | cabc.Set[t.Any]]
            | cabc.Iterable[tuple[str, t.Any]]
        ),
    ) -> te.Self:
        if not isinstance(other, (cabc.Mapping, cabc.Iterable)):
            return NotImplemented

        self.update(other)
        return self

    def to_wsgi_list(self) -> list[tuple[str, str]]:
        """Convert the headers into a list suitable for WSGI.

        :return: list
        """
        return list(self)

    def copy(self) -> te.Self:
        return self.__class__(self._list)

    def __copy__(self) -> te.Self:
        return self.copy()

    def __str__(self) -> str:
        """Returns formatted headers suitable for HTTP transmission."""
        strs = []
        for key, value in self.to_wsgi_list():
            strs.append(f"{key}: {value}")
        strs.append("\r\n")
        return "\r\n".join(strs)

    def __repr__(self) -> str:
        return f"{type(self).__name__}({list(self)!r})"


def _options_header_vkw(value: str, kw: dict[str, t.Any]) -> str:
    return http.dump_options_header(
        value, {k.replace("_", "-"): v for k, v in kw.items()}
    )


_newline_re = re.compile(r"[\r\n]")


def _str_header_value(value: t.Any) -> str:
    if not isinstance(value, str):
        value = str(value)

    if _newline_re.search(value) is not None:
        raise ValueError("Header values must not contain newline characters.")

    return value  # type: ignore[no-any-return]


class EnvironHeaders(ImmutableHeadersMixin, Headers):  # type: ignore[misc]
    """Read only version of the headers from a WSGI environment.  This
    provides the same interface as `Headers` and is constructed from
    a WSGI environment.
    From Werkzeug 0.3 onwards, the `KeyError` raised by this class is also a
    subclass of the :exc:`~exceptions.BadRequest` HTTP exception and will
    render a page for a ``400 BAD REQUEST`` if caught in a catch-all for
    HTTP exceptions.
    """

    def __init__(self, environ: WSGIEnvironment) -> None:
        super().__init__()
        self.environ = environ

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, EnvironHeaders):
            return NotImplemented

        return self.environ is other.environ

    __hash__ = None

    def __getitem__(self, key: str) -> str:  # type: ignore[override]
        return self._get_key(key)

    def _get_key(self, key: str) -> str:
        if not isinstance(key, str):
            raise BadRequestKeyError(key)

        key = key.upper().replace("-", "_")

        if key in {"CONTENT_TYPE", "CONTENT_LENGTH"}:
            return self.environ[key]  # type: ignore[no-any-return]

        return self.environ[f"HTTP_{key}"]  # type: ignore[no-any-return]

    def __len__(self) -> int:
        return sum(1 for _ in self)

    def __iter__(self) -> cabc.Iterator[tuple[str, str]]:
        for key, value in self.environ.items():
            if key.startswith("HTTP_") and key not in {
                "HTTP_CONTENT_TYPE",
                "HTTP_CONTENT_LENGTH",
            }:
                yield key[5:].replace("_", "-").title(), value
            elif key in {"CONTENT_TYPE", "CONTENT_LENGTH"} and value:
                yield key.replace("_", "-").title(), value

    def copy(self) -> t.NoReturn:
        raise TypeError(f"cannot create {type(self).__name__!r} copies")

    def __or__(self, other: t.Any) -> t.NoReturn:
        raise TypeError(f"cannot create {type(self).__name__!r} copies")


# circular dependencies
from .. import http  # noqa: E402
