from __future__ import annotations

import collections.abc as cabc
import typing as t
from inspect import cleandoc

from .mixins import ImmutableDictMixin
from .structures import CallbackDict


def cache_control_property(
    key: str, empty: t.Any, type: type[t.Any] | None, *, doc: str | None = None
) -> t.Any:
    """Return a new property object for a cache header. Useful if you
    want to add support for a cache extension in a subclass.

    :param key: The attribute name present in the parsed cache-control header dict.
    :param empty: The value to use if the key is present without a value.
    :param type: The type to convert the string value to instead of a string. If
        conversion raises a ``ValueError``, the returned value is ``None``.
    :param doc: The docstring for the property. If not given, it is generated
        based on the other params.

    .. versionchanged:: 3.1
        Added the ``doc`` param.

    .. versionchanged:: 2.0
        Renamed from ``cache_property``.
    """
    if doc is None:
        parts = [f"The ``{key}`` attribute."]

        if type is bool:
            parts.append("A ``bool``, either present or not.")
        else:
            if type is None:
                parts.append("A ``str``,")
            else:
                parts.append(f"A ``{type.__name__}``,")

            if empty is not None:
                parts.append(f"``{empty!r}`` if present with no value,")

            parts.append("or ``None`` if not present.")

        doc = " ".join(parts)

    return property(
        lambda x: x._get_cache_value(key, empty, type),
        lambda x, v: x._set_cache_value(key, v, type),
        lambda x: x._del_cache_value(key),
        doc=cleandoc(doc),
    )


class _CacheControl(CallbackDict[str, t.Optional[str]]):
    """Subclass of a dict that stores values for a Cache-Control header.  It
    has accessors for all the cache-control directives specified in RFC 2616.
    The class does not differentiate between request and response directives.

    Because the cache-control directives in the HTTP header use dashes the
    python descriptors use underscores for that.

    To get a header of the :class:`CacheControl` object again you can convert
    the object into a string or call the :meth:`to_header` method.  If you plan
    to subclass it and add your own items have a look at the sourcecode for
    that class.

    .. versionchanged:: 3.1
        Dict values are always ``str | None``. Setting properties will
        convert the value to a string. Setting a non-bool property to
        ``False`` is equivalent to setting it to ``None``. Getting typed
        properties will return ``None`` if conversion raises
        ``ValueError``, rather than the string.

    .. versionchanged:: 2.1
        Setting int properties such as ``max_age`` will convert the
        value to an int.

    .. versionchanged:: 0.4
       Setting ``no_cache`` or ``private`` to ``True`` will set the
       implicit value ``"*"``.
    """

    no_store: bool = cache_control_property("no-store", None, bool)
    max_age: int | None = cache_control_property("max-age", None, int)
    no_transform: bool = cache_control_property("no-transform", None, bool)
    stale_if_error: int | None = cache_control_property("stale-if-error", None, int)

    def __init__(
        self,
        values: cabc.Mapping[str, t.Any] | cabc.Iterable[tuple[str, t.Any]] | None = (),
        on_update: cabc.Callable[[_CacheControl], None] | None = None,
    ):
        super().__init__(values, on_update)
        self.provided = values is not None

    def _get_cache_value(
        self, key: str, empty: t.Any, type: type[t.Any] | None
    ) -> t.Any:
        """Used internally by the accessor properties."""
        if type is bool:
            return key in self

        if key not in self:
            return None

        if (value := self[key]) is None:
            return empty

        if type is not None:
            try:
                value = type(value)
            except ValueError:
                return None

        return value

    def _set_cache_value(
        self, key: str, value: t.Any, type: type[t.Any] | None
    ) -> None:
        """Used internally by the accessor properties."""
        if type is bool:
            if value:
                self[key] = None
            else:
                self.pop(key, None)
        elif value is None or value is False:
            self.pop(key, None)
        elif value is True:
            self[key] = None
        else:
            if type is not None:
                value = type(value)

            self[key] = str(value)

    def _del_cache_value(self, key: str) -> None:
        """Used internally by the accessor properties."""
        if key in self:
            del self[key]

    def to_header(self) -> str:
        """Convert the stored values into a cache control header."""
        return http.dump_header(self)

    def __str__(self) -> str:
        return self.to_header()

    def __repr__(self) -> str:
        kv_str = " ".join(f"{k}={v!r}" for k, v in sorted(self.items()))
        return f"<{type(self).__name__} {kv_str}>"

    cache_property = staticmethod(cache_control_property)


class RequestCacheControl(ImmutableDictMixin[str, t.Optional[str]], _CacheControl):  # type: ignore[misc]
    """A cache control for requests.  This is immutable and gives access
    to all the request-relevant cache control headers.

    To get a header of the :class:`RequestCacheControl` object again you can
    convert the object into a string or call the :meth:`to_header` method.  If
    you plan to subclass it and add your own items have a look at the sourcecode
    for that class.

    .. versionchanged:: 3.1
        Dict values are always ``str | None``. Setting properties will
        convert the value to a string. Setting a non-bool property to
        ``False`` is equivalent to setting it to ``None``. Getting typed
        properties will return ``None`` if conversion raises
        ``ValueError``, rather than the string.

    .. versionchanged:: 3.1
       ``max_age`` is ``None`` if present without a value, rather
       than ``-1``.

    .. versionchanged:: 3.1
        ``no_cache`` is a boolean, it is ``True`` instead of ``"*"``
        when present.

    .. versionchanged:: 3.1
        ``max_stale`` is ``True`` if present without a value, rather
        than ``"*"``.

    .. versionchanged:: 3.1
       ``no_transform`` is a boolean. Previously it was mistakenly
       always ``None``.

    .. versionchanged:: 3.1
       ``min_fresh`` is ``None`` if present without a value, rather
       than ``"*"``.

    .. versionchanged:: 2.1
        Setting int properties such as ``max_age`` will convert the
        value to an int.

    .. versionadded:: 0.5
        Response-only properties are not present on this request class.
    """

    no_cache: bool = cache_control_property("no-cache", None, bool)
    max_stale: int | t.Literal[True] | None = cache_control_property(
        "max-stale",
        True,
        int,
    )
    min_fresh: int | None = cache_control_property("min-fresh", None, int)
    only_if_cached: bool = cache_control_property("only-if-cached", None, bool)


class ResponseCacheControl(_CacheControl):
    """A cache control for responses.  Unlike :class:`RequestCacheControl`
    this is mutable and gives access to response-relevant cache control
    headers.

    To get a header of the :class:`ResponseCacheControl` object again you can
    convert the object into a string or call the :meth:`to_header` method.  If
    you plan to subclass it and add your own items have a look at the sourcecode
    for that class.

    .. versionchanged:: 3.1
        Dict values are always ``str | None``. Setting properties will
        convert the value to a string. Setting a non-bool property to
        ``False`` is equivalent to setting it to ``None``. Getting typed
        properties will return ``None`` if conversion raises
        ``ValueError``, rather than the string.

    .. versionchanged:: 3.1
        ``no_cache`` is ``True`` if present without a value, rather than
        ``"*"``.

    .. versionchanged:: 3.1
        ``private`` is ``True`` if present without a value, rather than
        ``"*"``.

    .. versionchanged:: 3.1
       ``no_transform`` is a boolean. Previously it was mistakenly
       always ``None``.

    .. versionchanged:: 3.1
        Added the ``must_understand``, ``stale_while_revalidate``, and
        ``stale_if_error`` properties.

    .. versionchanged:: 2.1.1
        ``s_maxage`` converts the value to an int.

    .. versionchanged:: 2.1
        Setting int properties such as ``max_age`` will convert the
        value to an int.

    .. versionadded:: 0.5
       Request-only properties are not present on this response class.
    """

    no_cache: str | t.Literal[True] | None = cache_control_property(
        "no-cache", True, None
    )
    public: bool = cache_control_property("public", None, bool)
    private: str | t.Literal[True] | None = cache_control_property(
        "private", True, None
    )
    must_revalidate: bool = cache_control_property("must-revalidate", None, bool)
    proxy_revalidate: bool = cache_control_property("proxy-revalidate", None, bool)
    s_maxage: int | None = cache_control_property("s-maxage", None, int)
    immutable: bool = cache_control_property("immutable", None, bool)
    must_understand: bool = cache_control_property("must-understand", None, bool)
    stale_while_revalidate: int | None = cache_control_property(
        "stale-while-revalidate", None, int
    )


# circular dependencies
from .. import http  # noqa: E402
