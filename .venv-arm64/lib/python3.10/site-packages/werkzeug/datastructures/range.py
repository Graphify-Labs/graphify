from __future__ import annotations

import collections.abc as cabc
import typing as t
from datetime import datetime

if t.TYPE_CHECKING:
    import typing_extensions as te

T = t.TypeVar("T")


class IfRange:
    """Very simple object that represents the `If-Range` header in parsed
    form.  It will either have neither a etag or date or one of either but
    never both.

    .. versionadded:: 0.7
    """

    def __init__(self, etag: str | None = None, date: datetime | None = None):
        #: The etag parsed and unquoted.  Ranges always operate on strong
        #: etags so the weakness information is not necessary.
        self.etag = etag
        #: The date in parsed format or `None`.
        self.date = date

    def to_header(self) -> str:
        """Converts the object back into an HTTP header."""
        if self.date is not None:
            return http.http_date(self.date)
        if self.etag is not None:
            return http.quote_etag(self.etag)
        return ""

    def __str__(self) -> str:
        return self.to_header()

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {str(self)!r}>"


class Range:
    """Represents a ``Range`` header. All methods only support only
    bytes as the unit. Stores a list of ranges if given, but the methods
    only work if only one range is provided.

    :raise ValueError: If the ranges provided are invalid.

    .. versionchanged:: 0.15
        The ranges passed in are validated.

    .. versionadded:: 0.7
    """

    def __init__(
        self, units: str, ranges: cabc.Sequence[tuple[int, int | None]]
    ) -> None:
        #: The units of this range.  Usually "bytes".
        self.units = units
        #: A list of ``(begin, end)`` tuples for the range header provided.
        #: The ranges are non-inclusive.
        self.ranges = ranges

        for start, end in ranges:
            if start is None or (end is not None and (start < 0 or start >= end)):
                raise ValueError(f"{(start, end)} is not a valid range.")

    def range_for_length(self, length: int | None) -> tuple[int, int] | None:
        """If the range is for bytes, the length is not None and there is
        exactly one range and it is satisfiable it returns a ``(start, stop)``
        tuple, otherwise `None`.
        """
        if self.units != "bytes" or length is None or len(self.ranges) != 1:
            return None
        start, end = self.ranges[0]
        if end is None:
            end = length
            if start < 0:
                start += length
        if http.is_byte_range_valid(start, end, length):
            return start, min(end, length)
        return None

    def make_content_range(self, length: int | None) -> ContentRange | None:
        """Creates a :class:`~werkzeug.datastructures.ContentRange` object
        from the current range and given content length.
        """
        rng = self.range_for_length(length)
        if rng is not None:
            return ContentRange(self.units, rng[0], rng[1], length)
        return None

    def to_header(self) -> str:
        """Converts the object back into an HTTP header."""
        ranges = []
        for begin, end in self.ranges:
            if end is None:
                ranges.append(f"{begin}-" if begin >= 0 else str(begin))
            else:
                ranges.append(f"{begin}-{end - 1}")
        return f"{self.units}={','.join(ranges)}"

    def to_content_range_header(self, length: int | None) -> str | None:
        """Converts the object into `Content-Range` HTTP header,
        based on given length
        """
        range = self.range_for_length(length)
        if range is not None:
            return f"{self.units} {range[0]}-{range[1] - 1}/{length}"
        return None

    def __str__(self) -> str:
        return self.to_header()

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {str(self)!r}>"


class _CallbackProperty(t.Generic[T]):
    def __set_name__(self, owner: type[ContentRange], name: str) -> None:
        self.attr = f"_{name}"

    @t.overload
    def __get__(self, instance: None, owner: None) -> te.Self: ...
    @t.overload
    def __get__(self, instance: ContentRange, owner: type[ContentRange]) -> T: ...
    def __get__(
        self, instance: ContentRange | None, owner: type[ContentRange] | None
    ) -> te.Self | T:
        if instance is None:
            return self

        return instance.__dict__[self.attr]  # type: ignore[no-any-return]

    def __set__(self, instance: ContentRange, value: T) -> None:
        instance.__dict__[self.attr] = value

        if instance.on_update is not None:
            instance.on_update(instance)


class ContentRange:
    """Represents the content range header.

    .. versionadded:: 0.7
    """

    def __init__(
        self,
        units: str | None,
        start: int | None,
        stop: int | None,
        length: int | None = None,
        on_update: cabc.Callable[[ContentRange], None] | None = None,
    ) -> None:
        self.on_update = on_update
        self.set(start, stop, length, units)

    #: The units to use, usually "bytes"
    units: str | None = _CallbackProperty()  # type: ignore[assignment]
    #: The start point of the range or `None`.
    start: int | None = _CallbackProperty()  # type: ignore[assignment]
    #: The stop point of the range (non-inclusive) or `None`.  Can only be
    #: `None` if also start is `None`.
    stop: int | None = _CallbackProperty()  # type: ignore[assignment]
    #: The length of the range or `None`.
    length: int | None = _CallbackProperty()  # type: ignore[assignment]

    def set(
        self,
        start: int | None,
        stop: int | None,
        length: int | None = None,
        units: str | None = "bytes",
    ) -> None:
        """Simple method to update the ranges."""
        assert http.is_byte_range_valid(start, stop, length), "Bad range provided"
        self._units: str | None = units
        self._start: int | None = start
        self._stop: int | None = stop
        self._length: int | None = length
        if self.on_update is not None:
            self.on_update(self)

    def unset(self) -> None:
        """Sets the units to `None` which indicates that the header should
        no longer be used.
        """
        self.set(None, None, units=None)

    def to_header(self) -> str:
        if self._units is None:
            return ""
        if self._length is None:
            length: str | int = "*"
        else:
            length = self._length
        if self._start is None:
            return f"{self._units} */{length}"
        return f"{self._units} {self._start}-{self._stop - 1}/{length}"  # type: ignore[operator]

    def __bool__(self) -> bool:
        return self._units is not None

    def __str__(self) -> str:
        return self.to_header()

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {str(self)!r}>"


# circular dependencies
from .. import http  # noqa: E402
