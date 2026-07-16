from __future__ import annotations

import codecs
import collections.abc as cabc
import re
import typing as t

from .structures import ImmutableList


class Accept(ImmutableList[tuple[str, float]]):
    """An :class:`Accept` object is just a list subclass for lists of
    ``(value, quality)`` tuples.  It is automatically sorted by specificity
    and quality.

    All :class:`Accept` objects work similar to a list but provide extra
    functionality for working with the data.  Containment checks are
    normalized to the rules of that header:

    >>> a = CharsetAccept([('ISO-8859-1', 1), ('utf-8', 0.7)])
    >>> a.best
    'ISO-8859-1'
    >>> 'iso-8859-1' in a
    True
    >>> 'UTF8' in a
    True
    >>> 'utf7' in a
    False

    To get the quality for an item you can use normal item lookup:

    >>> print a['utf-8']
    0.7
    >>> a['utf7']
    0

    .. versionchanged:: 0.5
       :class:`Accept` objects are forced immutable now.

    .. versionchanged:: 1.0.0
       :class:`Accept` internal values are no longer ordered
       alphabetically for equal quality tags. Instead the initial
       order is preserved.

    """

    def __init__(
        self, values: Accept | cabc.Iterable[tuple[str, float]] | None = ()
    ) -> None:
        if values is None:
            super().__init__()
            self.provided = False
        elif isinstance(values, Accept):
            self.provided = values.provided
            super().__init__(values)
        else:
            self.provided = True
            values = sorted(
                values, key=lambda x: (self._specificity(x[0]), x[1]), reverse=True
            )
            super().__init__(values)

    def _specificity(self, value: str) -> tuple[bool, ...]:
        """Returns a tuple describing the value's specificity."""
        return (value != "*",)

    def _value_matches(self, value: str, item: str) -> bool:
        """Check if a value matches a given accept item."""
        return item == "*" or item.lower() == value.lower()

    @t.overload
    def __getitem__(self, key: str) -> float: ...
    @t.overload
    def __getitem__(self, key: t.SupportsIndex) -> tuple[str, float]: ...
    @t.overload
    def __getitem__(self, key: slice) -> list[tuple[str, float]]: ...
    def __getitem__(
        self, key: str | t.SupportsIndex | slice
    ) -> float | tuple[str, float] | list[tuple[str, float]]:
        """Besides index lookup (getting item n) you can also pass it a string
        to get the quality for the item.  If the item is not in the list, the
        returned quality is ``0``.
        """
        if isinstance(key, str):
            return self.quality(key)
        return list.__getitem__(self, key)

    def quality(self, key: str) -> float:
        """Returns the quality of the key.

        .. versionadded:: 0.6
           In previous versions you had to use the item-lookup syntax
           (eg: ``obj[key]`` instead of ``obj.quality(key)``)
        """
        for item, quality in self:
            if self._value_matches(key, item):
                return quality
        return 0

    def __contains__(self, value: str) -> bool:  # type: ignore[override]
        for item, _quality in self:
            if self._value_matches(value, item):
                return True
        return False

    def __repr__(self) -> str:
        pairs_str = ", ".join(f"({x!r}, {y})" for x, y in self)
        return f"{type(self).__name__}([{pairs_str}])"

    def index(self, key: str | tuple[str, float]) -> int:  # type: ignore[override]
        """Get the position of an entry or raise :exc:`ValueError`.

        :param key: The key to be looked up.

        .. versionchanged:: 0.5
           This used to raise :exc:`IndexError`, which was inconsistent
           with the list API.
        """
        if isinstance(key, str):
            for idx, (item, _quality) in enumerate(self):
                if self._value_matches(key, item):
                    return idx
            raise ValueError(key)
        return list.index(self, key)

    def find(self, key: str | tuple[str, float]) -> int:
        """Get the position of an entry or return -1.

        :param key: The key to be looked up.
        """
        try:
            return self.index(key)
        except ValueError:
            return -1

    def values(self) -> cabc.Iterator[str]:
        """Iterate over all values."""
        for item in self:
            yield item[0]

    def to_header(self) -> str:
        """Convert the header set into an HTTP header string."""
        result = []
        for value, quality in self:
            if quality != 1:
                value = f"{value};q={quality}"
            result.append(value)
        return ",".join(result)

    def __str__(self) -> str:
        return self.to_header()

    def _best_single_match(self, match: str) -> tuple[str, float] | None:
        for client_item, quality in self:
            if self._value_matches(match, client_item):
                # self is sorted by specificity descending, we can exit
                return client_item, quality
        return None

    @t.overload
    def best_match(self, matches: cabc.Iterable[str]) -> str | None: ...
    @t.overload
    def best_match(self, matches: cabc.Iterable[str], default: str = ...) -> str: ...
    def best_match(
        self, matches: cabc.Iterable[str], default: str | None = None
    ) -> str | None:
        """Returns the best match from a list of possible matches based
        on the specificity and quality of the client. If two items have the
        same quality and specificity, the one is returned that comes first.

        :param matches: a list of matches to check for
        :param default: the value that is returned if none match
        """
        result = default
        best_quality: float = -1
        best_specificity: tuple[float, ...] = (-1,)
        for server_item in matches:
            match = self._best_single_match(server_item)
            if not match:
                continue
            client_item, quality = match
            specificity = self._specificity(client_item)
            if quality <= 0 or quality < best_quality:
                continue
            # better quality or same quality but more specific => better match
            if quality > best_quality or specificity > best_specificity:
                result = server_item
                best_quality = quality
                best_specificity = specificity
        return result

    @property
    def best(self) -> str | None:
        """The best match as value."""
        if self:
            return self[0][0]

        return None


_mime_split_re = re.compile(r"/|(?:\s*;\s*)")


def _normalize_mime(value: str) -> list[str]:
    return _mime_split_re.split(value.lower())


class MIMEAccept(Accept):
    """Like :class:`Accept` but with special methods and behavior for
    mimetypes.
    """

    def _specificity(self, value: str) -> tuple[bool, ...]:
        return tuple(x != "*" for x in _mime_split_re.split(value))

    def _value_matches(self, value: str, item: str) -> bool:
        # item comes from the client, can't match if it's invalid.
        if "/" not in item:
            return False

        # value comes from the application, tell the developer when it
        # doesn't look valid.
        if "/" not in value:
            raise ValueError(f"invalid mimetype {value!r}")

        # Split the match value into type, subtype, and a sorted list of parameters.
        normalized_value = _normalize_mime(value)
        value_type, value_subtype = normalized_value[:2]
        value_params = sorted(normalized_value[2:])

        # "*/*" is the only valid value that can start with "*".
        if value_type == "*" and value_subtype != "*":
            raise ValueError(f"invalid mimetype {value!r}")

        # Split the accept item into type, subtype, and parameters.
        normalized_item = _normalize_mime(item)
        item_type, item_subtype = normalized_item[:2]
        item_params = sorted(normalized_item[2:])

        # "*/not-*" from the client is invalid, can't match.
        if item_type == "*" and item_subtype != "*":
            return False

        return (
            (item_type == "*" and item_subtype == "*")
            or (value_type == "*" and value_subtype == "*")
        ) or (
            item_type == value_type
            and (
                item_subtype == "*"
                or value_subtype == "*"
                or (item_subtype == value_subtype and item_params == value_params)
            )
        )

    @property
    def accept_html(self) -> bool:
        """True if this object accepts HTML."""
        return "text/html" in self or self.accept_xhtml  # type: ignore[comparison-overlap]

    @property
    def accept_xhtml(self) -> bool:
        """True if this object accepts XHTML."""
        return "application/xhtml+xml" in self or "application/xml" in self  # type: ignore[comparison-overlap]

    @property
    def accept_json(self) -> bool:
        """True if this object accepts JSON."""
        return "application/json" in self  # type: ignore[comparison-overlap]


_locale_delim_re = re.compile(r"[_-]")


def _normalize_lang(value: str) -> list[str]:
    """Process a language tag for matching."""
    return _locale_delim_re.split(value.lower())


class LanguageAccept(Accept):
    """Like :class:`Accept` but with normalization for language tags."""

    def _value_matches(self, value: str, item: str) -> bool:
        return item == "*" or _normalize_lang(value) == _normalize_lang(item)

    @t.overload
    def best_match(self, matches: cabc.Iterable[str]) -> str | None: ...
    @t.overload
    def best_match(self, matches: cabc.Iterable[str], default: str = ...) -> str: ...
    def best_match(
        self, matches: cabc.Iterable[str], default: str | None = None
    ) -> str | None:
        """Given a list of supported values, finds the best match from
        the list of accepted values.

        Language tags are normalized for the purpose of matching, but
        are returned unchanged.

        If no exact match is found, this will fall back to matching
        the first subtag (primary language only), first with the
        accepted values then with the match values. This partial is not
        applied to any other language subtags.

        The default is returned if no exact or fallback match is found.

        :param matches: A list of supported languages to find a match.
        :param default: The value that is returned if none match.
        """
        # Look for an exact match first. If a client accepts "en-US",
        # "en-US" is a valid match at this point.
        result = super().best_match(matches)

        if result is not None:
            return result

        # Fall back to accepting primary tags. If a client accepts
        # "en-US", "en" is a valid match at this point. Need to use
        # re.split to account for 2 or 3 letter codes.
        fallback = Accept(
            [(_locale_delim_re.split(item[0], 1)[0], item[1]) for item in self]
        )
        result = fallback.best_match(matches)

        if result is not None:
            return result

        # Fall back to matching primary tags. If the client accepts
        # "en", "en-US" is a valid match at this point.
        fallback_matches = [_locale_delim_re.split(item, 1)[0] for item in matches]
        result = super().best_match(fallback_matches)

        # Return a value from the original match list. Find the first
        # original value that starts with the matched primary tag.
        if result is not None:
            return next(item for item in matches if item.startswith(result))

        return default


class CharsetAccept(Accept):
    """Like :class:`Accept` but with normalization for charsets."""

    def _value_matches(self, value: str, item: str) -> bool:
        def _normalize(name: str) -> str:
            try:
                return codecs.lookup(name).name
            except LookupError:
                return name.lower()

        return item == "*" or _normalize(value) == _normalize(item)
