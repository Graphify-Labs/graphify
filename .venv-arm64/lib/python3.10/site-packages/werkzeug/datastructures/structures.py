from __future__ import annotations

import collections.abc as cabc
import typing as t
from copy import deepcopy

from .. import exceptions
from .._internal import _missing
from .mixins import ImmutableDictMixin
from .mixins import ImmutableListMixin
from .mixins import ImmutableMultiDictMixin
from .mixins import UpdateDictMixin

if t.TYPE_CHECKING:
    import typing_extensions as te

K = t.TypeVar("K")
V = t.TypeVar("V")
T = t.TypeVar("T")


def iter_multi_items(
    mapping: (
        MultiDict[K, V]
        | cabc.Mapping[K, V | list[V] | tuple[V, ...] | set[V]]
        | cabc.Iterable[tuple[K, V]]
    ),
) -> cabc.Iterator[tuple[K, V]]:
    """Iterates over the items of a mapping yielding keys and values
    without dropping any from more complex structures.
    """
    if isinstance(mapping, MultiDict):
        yield from mapping.items(multi=True)
    elif isinstance(mapping, cabc.Mapping):
        for key, value in mapping.items():
            if isinstance(value, (list, tuple, set)):
                for v in value:
                    yield key, v
            else:
                yield key, value
    else:
        yield from mapping


class ImmutableList(ImmutableListMixin, list[V]):  # type: ignore[misc]
    """An immutable :class:`list`.

    .. versionadded:: 0.5

    :private:
    """

    def __repr__(self) -> str:
        return f"{type(self).__name__}({list.__repr__(self)})"


class TypeConversionDict(dict[K, V]):
    """Works like a regular dict but the :meth:`get` method can perform
    type conversions.  :class:`MultiDict` and :class:`CombinedMultiDict`
    are subclasses of this class and provide the same feature.

    .. versionadded:: 0.5
    """

    @t.overload  # type: ignore[override]
    def get(self, key: K) -> V | None: ...
    @t.overload
    def get(self, key: K, default: V) -> V: ...
    @t.overload
    def get(self, key: K, default: T) -> V | T: ...
    @t.overload
    def get(self, key: str, type: cabc.Callable[[V], T]) -> T | None: ...
    @t.overload
    def get(self, key: str, default: T, type: cabc.Callable[[V], T]) -> T: ...
    def get(  # type: ignore[misc]
        self,
        key: K,
        default: V | T | None = None,
        type: cabc.Callable[[V], T] | None = None,
    ) -> V | T | None:
        """Return the default value if the requested data doesn't exist.
        If `type` is provided and is a callable it should convert the value,
        return it or raise a :exc:`ValueError` if that is not possible.  In
        this case the function will return the default as if the value was not
        found:

        >>> d = TypeConversionDict(foo='42', bar='blub')
        >>> d.get('foo', type=int)
        42
        >>> d.get('bar', -1, type=int)
        -1

        :param key: The key to be looked up.
        :param default: The default value to be returned if the key can't
                        be looked up.  If not further specified `None` is
                        returned.
        :param type: A callable that is used to cast the value in the
                     :class:`MultiDict`.  If a :exc:`ValueError` or a
                     :exc:`TypeError` is raised by this callable the default
                     value is returned.

        .. versionchanged:: 3.0.2
           Returns the default value on :exc:`TypeError`, too.
        """
        try:
            rv = self[key]
        except KeyError:
            return default

        if type is None:
            return rv

        try:
            return type(rv)
        except (ValueError, TypeError):
            return default


class ImmutableTypeConversionDict(ImmutableDictMixin[K, V], TypeConversionDict[K, V]):  # type: ignore[misc]
    """Works like a :class:`TypeConversionDict` but does not support
    modifications.

    .. versionadded:: 0.5
    """

    def copy(self) -> TypeConversionDict[K, V]:
        """Return a shallow mutable copy of this object.  Keep in mind that
        the standard library's :func:`copy` function is a no-op for this class
        like for any other python immutable type (eg: :class:`tuple`).
        """
        return TypeConversionDict(self)

    def __copy__(self) -> te.Self:
        return self


class MultiDict(TypeConversionDict[K, V]):
    """A :class:`MultiDict` is a dictionary subclass customized to deal with
    multiple values for the same key which is for example used by the parsing
    functions in the wrappers.  This is necessary because some HTML form
    elements pass multiple values for the same key.

    :class:`MultiDict` implements all standard dictionary methods.
    Internally, it saves all values for a key as a list, but the standard dict
    access methods will only return the first value for a key. If you want to
    gain access to the other values, too, you have to use the `list` methods as
    explained below.

    Basic Usage:

    >>> d = MultiDict([('a', 'b'), ('a', 'c')])
    >>> d
    MultiDict([('a', 'b'), ('a', 'c')])
    >>> d['a']
    'b'
    >>> d.getlist('a')
    ['b', 'c']
    >>> 'a' in d
    True

    It behaves like a normal dict thus all dict functions will only return the
    first value when multiple values for one key are found.

    From Werkzeug 0.3 onwards, the `KeyError` raised by this class is also a
    subclass of the :exc:`~exceptions.BadRequest` HTTP exception and will
    render a page for a ``400 BAD REQUEST`` if caught in a catch-all for HTTP
    exceptions.

    A :class:`MultiDict` can be constructed from an iterable of
    ``(key, value)`` tuples, a dict, a :class:`MultiDict` or from Werkzeug 0.2
    onwards some keyword parameters.

    :param mapping: the initial value for the :class:`MultiDict`.  Either a
                    regular dict, an iterable of ``(key, value)`` tuples
                    or `None`.

    .. versionchanged:: 3.1
        Implement ``|`` and ``|=`` operators.
    """

    def __init__(
        self,
        mapping: (
            MultiDict[K, V]
            | cabc.Mapping[K, V | list[V] | tuple[V, ...] | set[V]]
            | cabc.Iterable[tuple[K, V]]
            | None
        ) = None,
    ) -> None:
        if mapping is None:
            super().__init__()
        elif isinstance(mapping, MultiDict):
            super().__init__((k, vs[:]) for k, vs in mapping.lists())  # type: ignore[misc]
        elif isinstance(mapping, cabc.Mapping):
            tmp = {}
            for key, value in mapping.items():
                if isinstance(value, (list, tuple, set)):
                    value = list(value)

                    if not value:
                        continue
                else:
                    value = [value]
                tmp[key] = value
            super().__init__(tmp)  # type: ignore[arg-type]
        else:
            tmp = {}
            for key, value in mapping:
                tmp.setdefault(key, []).append(value)
            super().__init__(tmp)  # type: ignore[arg-type]

    def __getstate__(self) -> t.Any:
        return dict(self.lists())

    def __setstate__(self, value: t.Any) -> None:
        super().clear()
        super().update(value)

    def __iter__(self) -> cabc.Iterator[K]:
        # https://github.com/python/cpython/issues/87412
        # If __iter__ is not overridden, Python uses a fast path for dict(md),
        # taking the data directly and getting lists of values, rather than
        # calling __getitem__ and getting only the first value.
        return super().__iter__()

    def __getitem__(self, key: K) -> V:
        """Return the first data value for this key;
        raises KeyError if not found.

        :param key: The key to be looked up.
        :raise KeyError: if the key does not exist.
        """

        if key in self:
            lst = super().__getitem__(key)
            if len(lst) > 0:  # type: ignore[arg-type]
                return lst[0]  # type: ignore[index,no-any-return]
        raise exceptions.BadRequestKeyError(key)

    def __setitem__(self, key: K, value: V) -> None:
        """Like :meth:`add` but removes an existing key first.

        :param key: the key for the value.
        :param value: the value to set.
        """
        super().__setitem__(key, [value])  # type: ignore[assignment]

    def add(self, key: K, value: V) -> None:
        """Adds a new value for the key.

        .. versionadded:: 0.6

        :param key: the key for the value.
        :param value: the value to add.
        """
        super().setdefault(key, []).append(value)  # type: ignore[arg-type,attr-defined]

    @t.overload
    def getlist(self, key: K) -> list[V]: ...
    @t.overload
    def getlist(self, key: K, type: cabc.Callable[[V], T]) -> list[T]: ...
    def getlist(
        self, key: K, type: cabc.Callable[[V], T] | None = None
    ) -> list[V] | list[T]:
        """Return the list of items for a given key. If that key is not in the
        `MultiDict`, the return value will be an empty list.  Just like `get`,
        `getlist` accepts a `type` parameter.  All items will be converted
        with the callable defined there.

        :param key: The key to be looked up.
        :param type: Callable to convert each value. If a ``ValueError`` or
            ``TypeError`` is raised, the value is omitted.
        :return: a :class:`list` of all the values for the key.

        .. versionchanged:: 3.1
            Catches ``TypeError`` in addition to ``ValueError``.
        """
        try:
            rv: list[V] = super().__getitem__(key)  # type: ignore[assignment]
        except KeyError:
            return []
        if type is None:
            return list(rv)
        result = []
        for item in rv:
            try:
                result.append(type(item))
            except (ValueError, TypeError):
                pass
        return result

    def setlist(self, key: K, new_list: cabc.Iterable[V]) -> None:
        """Remove the old values for a key and add new ones.  Note that the list
        you pass the values in will be shallow-copied before it is inserted in
        the dictionary.

        >>> d = MultiDict()
        >>> d.setlist('foo', ['1', '2'])
        >>> d['foo']
        '1'
        >>> d.getlist('foo')
        ['1', '2']

        :param key: The key for which the values are set.
        :param new_list: An iterable with the new values for the key.  Old values
                         are removed first.
        """
        super().__setitem__(key, list(new_list))  # type: ignore[assignment]

    @t.overload
    def setdefault(self, key: K) -> None: ...
    @t.overload
    def setdefault(self, key: K, default: V) -> V: ...
    def setdefault(self, key: K, default: V | None = None) -> V | None:
        """Returns the value for the key if it is in the dict, otherwise it
        returns `default` and sets that value for `key`.

        :param key: The key to be looked up.
        :param default: The default value to be returned if the key is not
                        in the dict.  If not further specified it's `None`.
        """
        if key not in self:
            self[key] = default  # type: ignore[assignment]

        return self[key]

    def setlistdefault(
        self, key: K, default_list: cabc.Iterable[V] | None = None
    ) -> list[V]:
        """Like `setdefault` but sets multiple values.  The list returned
        is not a copy, but the list that is actually used internally.  This
        means that you can put new values into the dict by appending items
        to the list:

        >>> d = MultiDict({"foo": 1})
        >>> d.setlistdefault("foo").extend([2, 3])
        >>> d.getlist("foo")
        [1, 2, 3]

        :param key: The key to be looked up.
        :param default_list: An iterable of default values.  It is either copied
                             (in case it was a list) or converted into a list
                             before returned.
        :return: a :class:`list`
        """
        if key not in self:
            super().__setitem__(key, list(default_list or ()))  # type: ignore[assignment]

        return super().__getitem__(key)  # type: ignore[return-value]

    def items(self, multi: bool = False) -> cabc.Iterable[tuple[K, V]]:  # type: ignore[override]
        """Return an iterator of ``(key, value)`` pairs.

        :param multi: If set to `True` the iterator returned will have a pair
                      for each value of each key.  Otherwise it will only
                      contain pairs for the first value of each key.
        """
        values: list[V]

        for key, values in super().items():  # type: ignore[assignment]
            if multi:
                for value in values:
                    yield key, value
            else:
                yield key, values[0]

    def lists(self) -> cabc.Iterable[tuple[K, list[V]]]:
        """Return a iterator of ``(key, values)`` pairs, where values is the list
        of all values associated with the key."""
        values: list[V]

        for key, values in super().items():  # type: ignore[assignment]
            yield key, list(values)

    def values(self) -> cabc.Iterable[V]:  # type: ignore[override]
        """Returns an iterator of the first value on every key's value list."""
        values: list[V]

        for values in super().values():  # type: ignore[assignment]
            yield values[0]

    def listvalues(self) -> cabc.Iterable[list[V]]:
        """Return an iterator of all values associated with a key.  Zipping
        :meth:`keys` and this is the same as calling :meth:`lists`:

        >>> d = MultiDict({"foo": [1, 2, 3]})
        >>> zip(d.keys(), d.listvalues()) == d.lists()
        True
        """
        return super().values()  # type: ignore[return-value]

    def copy(self) -> te.Self:
        """Return a shallow copy of this object."""
        return self.__class__(self)

    def deepcopy(self, memo: t.Any = None) -> te.Self:
        """Return a deep copy of this object."""
        return self.__class__(deepcopy(self.to_dict(flat=False), memo))

    @t.overload
    def to_dict(self, flat: t.Literal[True] = ...) -> dict[K, V]: ...
    @t.overload
    def to_dict(self, flat: t.Literal[False]) -> dict[K, list[V]]: ...
    def to_dict(self, flat: bool = True) -> dict[K, V] | dict[K, list[V]]:
        """Return the contents as regular dict.  If `flat` is `True` the
        returned dict will only have the first item present, if `flat` is
        `False` all values will be returned as lists.

        :param flat: If set to `False` the dict returned will have lists
                     with all the values in it.  Otherwise it will only
                     contain the first value for each key.
        :return: a :class:`dict`
        """
        if flat:
            return dict(self.items())
        return dict(self.lists())

    def update(  # type: ignore[override]
        self,
        mapping: (
            MultiDict[K, V]
            | cabc.Mapping[K, V | list[V] | tuple[V, ...] | set[V]]
            | cabc.Iterable[tuple[K, V]]
        ),
    ) -> None:
        """update() extends rather than replaces existing key lists:

        >>> a = MultiDict({'x': 1})
        >>> b = MultiDict({'x': 2, 'y': 3})
        >>> a.update(b)
        >>> a
        MultiDict([('y', 3), ('x', 1), ('x', 2)])

        If the value list for a key in ``other_dict`` is empty, no new values
        will be added to the dict and the key will not be created:

        >>> x = {'empty_list': []}
        >>> y = MultiDict()
        >>> y.update(x)
        >>> y
        MultiDict([])
        """
        for key, value in iter_multi_items(mapping):
            self.add(key, value)

    def __or__(  # type: ignore[override]
        self, other: cabc.Mapping[K, V | list[V] | tuple[V, ...] | set[V]]
    ) -> MultiDict[K, V]:
        if not isinstance(other, cabc.Mapping):
            return NotImplemented

        rv = self.copy()
        rv.update(other)
        return rv

    def __ior__(  # type: ignore[override]
        self,
        other: (
            cabc.Mapping[K, V | list[V] | tuple[V, ...] | set[V]]
            | cabc.Iterable[tuple[K, V]]
        ),
    ) -> te.Self:
        if not isinstance(other, (cabc.Mapping, cabc.Iterable)):
            return NotImplemented

        self.update(other)
        return self

    @t.overload
    def pop(self, key: K) -> V: ...
    @t.overload
    def pop(self, key: K, default: V) -> V: ...
    @t.overload
    def pop(self, key: K, default: T) -> V | T: ...
    def pop(
        self,
        key: K,
        default: V | T = _missing,  # type: ignore[assignment]
    ) -> V | T:
        """Pop the first item for a list on the dict.  Afterwards the
        key is removed from the dict, so additional values are discarded:

        >>> d = MultiDict({"foo": [1, 2, 3]})
        >>> d.pop("foo")
        1
        >>> "foo" in d
        False

        :param key: the key to pop.
        :param default: if provided the value to return if the key was
                        not in the dictionary.
        """
        lst: list[V]

        try:
            lst = super().pop(key)  # type: ignore[assignment]

            if len(lst) == 0:
                raise exceptions.BadRequestKeyError(key)

            return lst[0]
        except KeyError:
            if default is not _missing:
                return default

            raise exceptions.BadRequestKeyError(key) from None

    def popitem(self) -> tuple[K, V]:
        """Pop an item from the dict."""
        item: tuple[K, list[V]]

        try:
            item = super().popitem()  # type: ignore[assignment]

            if len(item[1]) == 0:
                raise exceptions.BadRequestKeyError(item[0])

            return item[0], item[1][0]
        except KeyError as e:
            raise exceptions.BadRequestKeyError(e.args[0]) from None

    def poplist(self, key: K) -> list[V]:
        """Pop the list for a key from the dict.  If the key is not in the dict
        an empty list is returned.

        .. versionchanged:: 0.5
           If the key does no longer exist a list is returned instead of
           raising an error.
        """
        return super().pop(key, [])  # type: ignore[return-value]

    def popitemlist(self) -> tuple[K, list[V]]:
        """Pop a ``(key, list)`` tuple from the dict."""
        try:
            return super().popitem()  # type: ignore[return-value]
        except KeyError as e:
            raise exceptions.BadRequestKeyError(e.args[0]) from None

    def __copy__(self) -> te.Self:
        return self.copy()

    def __deepcopy__(self, memo: t.Any) -> te.Self:
        return self.deepcopy(memo=memo)

    def __repr__(self) -> str:
        return f"{type(self).__name__}({list(self.items(multi=True))!r})"


class _omd_bucket(t.Generic[K, V]):
    """Wraps values in the :class:`OrderedMultiDict`.  This makes it
    possible to keep an order over multiple different keys.  It requires
    a lot of extra memory and slows down access a lot, but makes it
    possible to access elements in O(1) and iterate in O(n).
    """

    __slots__ = ("prev", "key", "value", "next")

    def __init__(self, omd: _OrderedMultiDict[K, V], key: K, value: V) -> None:
        self.prev: _omd_bucket[K, V] | None = omd._last_bucket
        self.key: K = key
        self.value: V = value
        self.next: _omd_bucket[K, V] | None = None

        if omd._first_bucket is None:
            omd._first_bucket = self
        if omd._last_bucket is not None:
            omd._last_bucket.next = self
        omd._last_bucket = self

    def unlink(self, omd: _OrderedMultiDict[K, V]) -> None:
        if self.prev:
            self.prev.next = self.next
        if self.next:
            self.next.prev = self.prev
        if omd._first_bucket is self:
            omd._first_bucket = self.next
        if omd._last_bucket is self:
            omd._last_bucket = self.prev


class _OrderedMultiDict(MultiDict[K, V]):
    """Works like a regular :class:`MultiDict` but preserves the
    order of the fields.  To convert the ordered multi dict into a
    list you can use the :meth:`items` method and pass it ``multi=True``.

    In general an :class:`OrderedMultiDict` is an order of magnitude
    slower than a :class:`MultiDict`.

    .. admonition:: note

       Due to a limitation in Python you cannot convert an ordered
       multi dict into a regular dict by using ``dict(multidict)``.
       Instead you have to use the :meth:`to_dict` method, otherwise
       the internal bucket objects are exposed.

    .. deprecated:: 3.1
        Will be removed in Werkzeug 3.2. Use ``MultiDict`` instead.
    """

    def __init__(
        self,
        mapping: (
            MultiDict[K, V]
            | cabc.Mapping[K, V | list[V] | tuple[V, ...] | set[V]]
            | cabc.Iterable[tuple[K, V]]
            | None
        ) = None,
    ) -> None:
        import warnings

        warnings.warn(
            "'OrderedMultiDict' is deprecated and will be removed in Werkzeug"
            " 3.2. Use 'MultiDict' instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        super().__init__()
        self._first_bucket: _omd_bucket[K, V] | None = None
        self._last_bucket: _omd_bucket[K, V] | None = None
        if mapping is not None:
            self.update(mapping)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, MultiDict):
            return NotImplemented
        if isinstance(other, _OrderedMultiDict):
            iter1 = iter(self.items(multi=True))
            iter2 = iter(other.items(multi=True))
            try:
                for k1, v1 in iter1:
                    k2, v2 = next(iter2)
                    if k1 != k2 or v1 != v2:
                        return False
            except StopIteration:
                return False
            try:
                next(iter2)
            except StopIteration:
                return True
            return False
        if len(self) != len(other):
            return False
        for key, values in self.lists():
            if other.getlist(key) != values:
                return False
        return True

    __hash__ = None  # type: ignore[assignment]

    def __reduce_ex__(self, protocol: t.SupportsIndex) -> t.Any:
        return type(self), (list(self.items(multi=True)),)

    def __getstate__(self) -> t.Any:
        return list(self.items(multi=True))

    def __setstate__(self, values: t.Any) -> None:
        self.clear()

        for key, value in values:
            self.add(key, value)

    def __getitem__(self, key: K) -> V:
        if key in self:
            return dict.__getitem__(self, key)[0].value  # type: ignore[index,no-any-return]
        raise exceptions.BadRequestKeyError(key)

    def __setitem__(self, key: K, value: V) -> None:
        self.poplist(key)
        self.add(key, value)

    def __delitem__(self, key: K) -> None:
        self.pop(key)

    def keys(self) -> cabc.Iterable[K]:  # type: ignore[override]
        return (key for key, _ in self.items())

    def __iter__(self) -> cabc.Iterator[K]:
        return iter(self.keys())

    def values(self) -> cabc.Iterable[V]:  # type: ignore[override]
        return (value for key, value in self.items())

    def items(self, multi: bool = False) -> cabc.Iterable[tuple[K, V]]:  # type: ignore[override]
        ptr = self._first_bucket
        if multi:
            while ptr is not None:
                yield ptr.key, ptr.value
                ptr = ptr.next
        else:
            returned_keys = set()
            while ptr is not None:
                if ptr.key not in returned_keys:
                    returned_keys.add(ptr.key)
                    yield ptr.key, ptr.value
                ptr = ptr.next

    def lists(self) -> cabc.Iterable[tuple[K, list[V]]]:
        returned_keys = set()
        ptr = self._first_bucket
        while ptr is not None:
            if ptr.key not in returned_keys:
                yield ptr.key, self.getlist(ptr.key)
                returned_keys.add(ptr.key)
            ptr = ptr.next

    def listvalues(self) -> cabc.Iterable[list[V]]:
        for _key, values in self.lists():
            yield values

    def add(self, key: K, value: V) -> None:
        dict.setdefault(self, key, []).append(_omd_bucket(self, key, value))  # type: ignore[misc]

    @t.overload
    def getlist(self, key: K) -> list[V]: ...
    @t.overload
    def getlist(self, key: K, type: cabc.Callable[[V], T]) -> list[T]: ...
    def getlist(
        self, key: K, type: cabc.Callable[[V], T] | None = None
    ) -> list[V] | list[T]:
        rv: list[_omd_bucket[K, V]]

        try:
            rv = dict.__getitem__(self, key)  # type: ignore[index]
        except KeyError:
            return []
        if type is None:
            return [x.value for x in rv]
        result = []
        for item in rv:
            try:
                result.append(type(item.value))
            except (ValueError, TypeError):
                pass
        return result

    def setlist(self, key: K, new_list: cabc.Iterable[V]) -> None:
        self.poplist(key)
        for value in new_list:
            self.add(key, value)

    def setlistdefault(self, key: t.Any, default_list: t.Any = None) -> t.NoReturn:
        raise TypeError("setlistdefault is unsupported for ordered multi dicts")

    def update(  # type: ignore[override]
        self,
        mapping: (
            MultiDict[K, V]
            | cabc.Mapping[K, V | list[V] | tuple[V, ...] | set[V]]
            | cabc.Iterable[tuple[K, V]]
        ),
    ) -> None:
        for key, value in iter_multi_items(mapping):
            self.add(key, value)

    def poplist(self, key: K) -> list[V]:
        buckets: cabc.Iterable[_omd_bucket[K, V]] = dict.pop(self, key, ())  # type: ignore[arg-type]
        for bucket in buckets:
            bucket.unlink(self)
        return [x.value for x in buckets]

    @t.overload
    def pop(self, key: K) -> V: ...
    @t.overload
    def pop(self, key: K, default: V) -> V: ...
    @t.overload
    def pop(self, key: K, default: T) -> V | T: ...
    def pop(
        self,
        key: K,
        default: V | T = _missing,  # type: ignore[assignment]
    ) -> V | T:
        buckets: list[_omd_bucket[K, V]]

        try:
            buckets = dict.pop(self, key)  # type: ignore[arg-type]
        except KeyError:
            if default is not _missing:
                return default

            raise exceptions.BadRequestKeyError(key) from None

        for bucket in buckets:
            bucket.unlink(self)

        return buckets[0].value

    def popitem(self) -> tuple[K, V]:
        key: K
        buckets: list[_omd_bucket[K, V]]

        try:
            key, buckets = dict.popitem(self)  # type: ignore[arg-type]
        except KeyError as e:
            raise exceptions.BadRequestKeyError(e.args[0]) from None

        for bucket in buckets:
            bucket.unlink(self)

        return key, buckets[0].value

    def popitemlist(self) -> tuple[K, list[V]]:
        key: K
        buckets: list[_omd_bucket[K, V]]

        try:
            key, buckets = dict.popitem(self)  # type: ignore[arg-type]
        except KeyError as e:
            raise exceptions.BadRequestKeyError(e.args[0]) from None

        for bucket in buckets:
            bucket.unlink(self)

        return key, [x.value for x in buckets]


class CombinedMultiDict(ImmutableMultiDictMixin[K, V], MultiDict[K, V]):  # type: ignore[misc]
    """A read only :class:`MultiDict` that you can pass multiple :class:`MultiDict`
    instances as sequence and it will combine the return values of all wrapped
    dicts:

    >>> from werkzeug.datastructures import CombinedMultiDict, MultiDict
    >>> post = MultiDict([('foo', 'bar')])
    >>> get = MultiDict([('blub', 'blah')])
    >>> combined = CombinedMultiDict([get, post])
    >>> combined['foo']
    'bar'
    >>> combined['blub']
    'blah'

    This works for all read operations and will raise a `TypeError` for
    methods that usually change data which isn't possible.

    From Werkzeug 0.3 onwards, the `KeyError` raised by this class is also a
    subclass of the :exc:`~exceptions.BadRequest` HTTP exception and will
    render a page for a ``400 BAD REQUEST`` if caught in a catch-all for HTTP
    exceptions.
    """

    def __reduce_ex__(self, protocol: t.SupportsIndex) -> t.Any:
        return type(self), (self.dicts,)

    def __init__(self, dicts: cabc.Iterable[MultiDict[K, V]] | None = None) -> None:
        super().__init__()
        self.dicts: list[MultiDict[K, V]] = list(dicts or ())

    @classmethod
    def fromkeys(cls, keys: t.Any, value: t.Any = None) -> t.NoReturn:
        raise TypeError(f"cannot create {cls.__name__!r} instances by fromkeys")

    def __getitem__(self, key: K) -> V:
        for d in self.dicts:
            if key in d:
                return d[key]
        raise exceptions.BadRequestKeyError(key)

    @t.overload  # type: ignore[override]
    def get(self, key: K) -> V | None: ...
    @t.overload
    def get(self, key: K, default: V) -> V: ...
    @t.overload
    def get(self, key: K, default: T) -> V | T: ...
    @t.overload
    def get(self, key: str, type: cabc.Callable[[V], T]) -> T | None: ...
    @t.overload
    def get(self, key: str, default: T, type: cabc.Callable[[V], T]) -> T: ...
    def get(  # type: ignore[misc]
        self,
        key: K,
        default: V | T | None = None,
        type: cabc.Callable[[V], T] | None = None,
    ) -> V | T | None:
        for d in self.dicts:
            if key in d:
                if type is not None:
                    try:
                        return type(d[key])
                    except (ValueError, TypeError):
                        continue
                return d[key]
        return default

    @t.overload
    def getlist(self, key: K) -> list[V]: ...
    @t.overload
    def getlist(self, key: K, type: cabc.Callable[[V], T]) -> list[T]: ...
    def getlist(
        self, key: K, type: cabc.Callable[[V], T] | None = None
    ) -> list[V] | list[T]:
        rv = []
        for d in self.dicts:
            rv.extend(d.getlist(key, type))  # type: ignore[arg-type]
        return rv

    def _keys_impl(self) -> set[K]:
        """This function exists so __len__ can be implemented more efficiently,
        saving one list creation from an iterator.
        """
        return set(k for d in self.dicts for k in d)

    def keys(self) -> cabc.Iterable[K]:  # type: ignore[override]
        return self._keys_impl()

    def __iter__(self) -> cabc.Iterator[K]:
        return iter(self._keys_impl())

    @t.overload  # type: ignore[override]
    def items(self) -> cabc.Iterable[tuple[K, V]]: ...
    @t.overload
    def items(self, multi: t.Literal[True]) -> cabc.Iterable[tuple[K, list[V]]]: ...
    def items(
        self, multi: bool = False
    ) -> cabc.Iterable[tuple[K, V]] | cabc.Iterable[tuple[K, list[V]]]:
        found = set()
        for d in self.dicts:
            for key, value in d.items(multi):
                if multi:
                    yield key, value
                elif key not in found:
                    found.add(key)
                    yield key, value

    def values(self) -> cabc.Iterable[V]:  # type: ignore[override]
        for _, value in self.items():
            yield value

    def lists(self) -> cabc.Iterable[tuple[K, list[V]]]:
        rv: dict[K, list[V]] = {}
        for d in self.dicts:
            for key, values in d.lists():
                rv.setdefault(key, []).extend(values)
        return rv.items()

    def listvalues(self) -> cabc.Iterable[list[V]]:
        return (x[1] for x in self.lists())

    def copy(self) -> MultiDict[K, V]:  # type: ignore[override]
        """Return a shallow mutable copy of this object.

        This returns a :class:`MultiDict` representing the data at the
        time of copying. The copy will no longer reflect changes to the
        wrapped dicts.

        .. versionchanged:: 0.15
            Return a mutable :class:`MultiDict`.
        """
        return MultiDict(self)

    def __len__(self) -> int:
        return len(self._keys_impl())

    def __contains__(self, key: K) -> bool:  # type: ignore[override]
        for d in self.dicts:
            if key in d:
                return True
        return False

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.dicts!r})"


class ImmutableDict(ImmutableDictMixin[K, V], dict[K, V]):  # type: ignore[misc]
    """An immutable :class:`dict`.

    .. versionadded:: 0.5
    """

    def __repr__(self) -> str:
        return f"{type(self).__name__}({dict.__repr__(self)})"

    def copy(self) -> dict[K, V]:
        """Return a shallow mutable copy of this object.  Keep in mind that
        the standard library's :func:`copy` function is a no-op for this class
        like for any other python immutable type (eg: :class:`tuple`).
        """
        return dict(self)

    def __copy__(self) -> te.Self:
        return self


class ImmutableMultiDict(ImmutableMultiDictMixin[K, V], MultiDict[K, V]):  # type: ignore[misc]
    """An immutable :class:`MultiDict`.

    .. versionadded:: 0.5
    """

    def copy(self) -> MultiDict[K, V]:  # type: ignore[override]
        """Return a shallow mutable copy of this object.  Keep in mind that
        the standard library's :func:`copy` function is a no-op for this class
        like for any other python immutable type (eg: :class:`tuple`).
        """
        return MultiDict(self)

    def __copy__(self) -> te.Self:
        return self


class _ImmutableOrderedMultiDict(  # type: ignore[misc]
    ImmutableMultiDictMixin[K, V], _OrderedMultiDict[K, V]
):
    """An immutable :class:`OrderedMultiDict`.

    .. deprecated:: 3.1
        Will be removed in Werkzeug 3.2. Use ``ImmutableMultiDict`` instead.

    .. versionadded:: 0.6
    """

    def __init__(
        self,
        mapping: (
            MultiDict[K, V]
            | cabc.Mapping[K, V | list[V] | tuple[V, ...] | set[V]]
            | cabc.Iterable[tuple[K, V]]
            | None
        ) = None,
    ) -> None:
        super().__init__()

        if mapping is not None:
            for k, v in iter_multi_items(mapping):
                _OrderedMultiDict.add(self, k, v)

    def _iter_hashitems(self) -> cabc.Iterable[t.Any]:
        return enumerate(self.items(multi=True))

    def copy(self) -> _OrderedMultiDict[K, V]:  # type: ignore[override]
        """Return a shallow mutable copy of this object.  Keep in mind that
        the standard library's :func:`copy` function is a no-op for this class
        like for any other python immutable type (eg: :class:`tuple`).
        """
        return _OrderedMultiDict(self)

    def __copy__(self) -> te.Self:
        return self


class CallbackDict(UpdateDictMixin[K, V], dict[K, V]):
    """A dict that calls a function passed every time something is changed.
    The function is passed the dict instance.
    """

    def __init__(
        self,
        initial: cabc.Mapping[K, V] | cabc.Iterable[tuple[K, V]] | None = None,
        on_update: cabc.Callable[[te.Self], None] | None = None,
    ) -> None:
        if initial is None:
            super().__init__()
        else:
            super().__init__(initial)

        self.on_update = on_update

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {super().__repr__()}>"


class HeaderSet(cabc.MutableSet[str]):
    """Similar to the :class:`ETags` class this implements a set-like structure.
    Unlike :class:`ETags` this is case insensitive and used for vary, allow, and
    content-language headers.

    If not constructed using the :func:`parse_set_header` function the
    instantiation works like this:

    >>> hs = HeaderSet(['foo', 'bar', 'baz'])
    >>> hs
    HeaderSet(['foo', 'bar', 'baz'])
    """

    def __init__(
        self,
        headers: cabc.Iterable[str] | None = None,
        on_update: cabc.Callable[[te.Self], None] | None = None,
    ) -> None:
        self._headers = list(headers or ())
        self._set = {x.lower() for x in self._headers}
        self.on_update = on_update

    def add(self, header: str) -> None:
        """Add a new header to the set."""
        self.update((header,))

    def remove(self: te.Self, header: str) -> None:
        """Remove a header from the set.  This raises an :exc:`KeyError` if the
        header is not in the set.

        .. versionchanged:: 0.5
            In older versions a :exc:`IndexError` was raised instead of a
            :exc:`KeyError` if the object was missing.

        :param header: the header to be removed.
        """
        key = header.lower()
        if key not in self._set:
            raise KeyError(header)
        self._set.remove(key)
        for idx, key in enumerate(self._headers):
            if key.lower() == header:
                del self._headers[idx]
                break
        if self.on_update is not None:
            self.on_update(self)

    def update(self: te.Self, iterable: cabc.Iterable[str]) -> None:
        """Add all the headers from the iterable to the set.

        :param iterable: updates the set with the items from the iterable.
        """
        inserted_any = False
        for header in iterable:
            key = header.lower()
            if key not in self._set:
                self._headers.append(header)
                self._set.add(key)
                inserted_any = True
        if inserted_any and self.on_update is not None:
            self.on_update(self)

    def discard(self, header: str) -> None:
        """Like :meth:`remove` but ignores errors.

        :param header: the header to be discarded.
        """
        try:
            self.remove(header)
        except KeyError:
            pass

    def find(self, header: str) -> int:
        """Return the index of the header in the set or return -1 if not found.

        :param header: the header to be looked up.
        """
        header = header.lower()
        for idx, item in enumerate(self._headers):
            if item.lower() == header:
                return idx
        return -1

    def index(self, header: str) -> int:
        """Return the index of the header in the set or raise an
        :exc:`IndexError`.

        :param header: the header to be looked up.
        """
        rv = self.find(header)
        if rv < 0:
            raise IndexError(header)
        return rv

    def clear(self: te.Self) -> None:
        """Clear the set."""
        self._set.clear()
        self._headers.clear()

        if self.on_update is not None:
            self.on_update(self)

    def as_set(self, preserve_casing: bool = False) -> set[str]:
        """Return the set as real python set type.  When calling this, all
        the items are converted to lowercase and the ordering is lost.

        :param preserve_casing: if set to `True` the items in the set returned
                                will have the original case like in the
                                :class:`HeaderSet`, otherwise they will
                                be lowercase.
        """
        if preserve_casing:
            return set(self._headers)
        return set(self._set)

    def to_header(self) -> str:
        """Convert the header set into an HTTP header string."""
        return ", ".join(map(http.quote_header_value, self._headers))

    def __getitem__(self, idx: t.SupportsIndex) -> str:
        return self._headers[idx]

    def __delitem__(self: te.Self, idx: t.SupportsIndex) -> None:
        rv = self._headers.pop(idx)
        self._set.remove(rv.lower())
        if self.on_update is not None:
            self.on_update(self)

    def __setitem__(self: te.Self, idx: t.SupportsIndex, value: str) -> None:
        old = self._headers[idx]
        self._set.remove(old.lower())
        self._headers[idx] = value
        self._set.add(value.lower())
        if self.on_update is not None:
            self.on_update(self)

    def __contains__(self, header: str) -> bool:  # type: ignore[override]
        return header.lower() in self._set

    def __len__(self) -> int:
        return len(self._set)

    def __iter__(self) -> cabc.Iterator[str]:
        return iter(self._headers)

    def __bool__(self) -> bool:
        return bool(self._set)

    def __str__(self) -> str:
        return self.to_header()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self._headers!r})"


# circular dependencies
from .. import http  # noqa: E402


def __getattr__(name: str) -> t.Any:
    import warnings

    if name == "OrderedMultiDict":
        warnings.warn(
            "'OrderedMultiDict' is deprecated and will be removed in Werkzeug"
            " 3.2. Use 'MultiDict' instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return _OrderedMultiDict

    if name == "ImmutableOrderedMultiDict":
        warnings.warn(
            "'ImmutableOrderedMultiDict' is deprecated and will be removed in"
            " Werkzeug 3.2. Use 'ImmutableMultiDict' instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return _ImmutableOrderedMultiDict

    raise AttributeError(name)
