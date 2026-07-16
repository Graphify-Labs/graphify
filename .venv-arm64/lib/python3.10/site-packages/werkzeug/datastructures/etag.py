from __future__ import annotations

import collections.abc as cabc


class ETags(cabc.Collection[str]):
    """A set that can be used to check if one etag is present in a collection
    of etags.
    """

    def __init__(
        self,
        strong_etags: cabc.Iterable[str] | None = None,
        weak_etags: cabc.Iterable[str] | None = None,
        star_tag: bool = False,
    ):
        if not star_tag and strong_etags:
            self._strong = frozenset(strong_etags)
        else:
            self._strong = frozenset()

        self._weak = frozenset(weak_etags or ())
        self.star_tag = star_tag

    def as_set(self, include_weak: bool = False) -> set[str]:
        """Convert the `ETags` object into a python set.  Per default all the
        weak etags are not part of this set."""
        rv = set(self._strong)
        if include_weak:
            rv.update(self._weak)
        return rv

    def is_weak(self, etag: str) -> bool:
        """Check if an etag is weak."""
        return etag in self._weak

    def is_strong(self, etag: str) -> bool:
        """Check if an etag is strong."""
        return etag in self._strong

    def contains_weak(self, etag: str) -> bool:
        """Check if an etag is part of the set including weak and strong tags."""
        return self.is_weak(etag) or self.contains(etag)

    def contains(self, etag: str) -> bool:
        """Check if an etag is part of the set ignoring weak tags.
        It is also possible to use the ``in`` operator.
        """
        if self.star_tag:
            return True
        return self.is_strong(etag)

    def contains_raw(self, etag: str) -> bool:
        """When passed a quoted tag it will check if this tag is part of the
        set.  If the tag is weak it is checked against weak and strong tags,
        otherwise strong only."""
        from ..http import unquote_etag

        etag, weak = unquote_etag(etag)
        if weak:
            return self.contains_weak(etag)
        return self.contains(etag)

    def to_header(self) -> str:
        """Convert the etags set into a HTTP header string."""
        if self.star_tag:
            return "*"
        return ", ".join(
            [f'"{x}"' for x in self._strong] + [f'W/"{x}"' for x in self._weak]
        )

    def __call__(
        self,
        etag: str | None = None,
        data: bytes | None = None,
        include_weak: bool = False,
    ) -> bool:
        if etag is None:
            if data is None:
                raise TypeError("'data' is required when 'etag' is not given.")

            from ..http import generate_etag

            etag = generate_etag(data)
        if include_weak:
            if etag in self._weak:
                return True
        return etag in self._strong

    def __bool__(self) -> bool:
        return bool(self.star_tag or self._strong or self._weak)

    def __str__(self) -> str:
        return self.to_header()

    def __len__(self) -> int:
        return len(self._strong)

    def __iter__(self) -> cabc.Iterator[str]:
        return iter(self._strong)

    def __contains__(self, etag: str) -> bool:  # type: ignore[override]
        return self.contains(etag)

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {str(self)!r}>"
