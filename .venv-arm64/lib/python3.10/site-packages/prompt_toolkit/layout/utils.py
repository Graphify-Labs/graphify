from __future__ import annotations

from typing import TYPE_CHECKING, Iterable, List, TypeVar, cast, overload

from prompt_toolkit.formatted_text.base import OneStyleAndTextTuple

if TYPE_CHECKING:
    from typing_extensions import SupportsIndex

__all__ = [
    "explode_text_fragments",
]

_T = TypeVar("_T", bound=OneStyleAndTextTuple)


class _ExplodedList(List[_T]):
    """
    Wrapper around a list, that marks it as 'exploded'.

    As soon as items are added or the list is extended, the new items are
    automatically exploded as well.
    """

    exploded = True

    def append(self, item: _T) -> None:
        self.extend([item])

    def extend(self, lst: Iterable[_T]) -> None:
        super().extend(explode_text_fragments(lst))

    def insert(self, index: SupportsIndex, item: _T) -> None:
        raise NotImplementedError  # TODO

    # TODO: When creating a copy() or [:], return also an _ExplodedList.

    @overload
    def __setitem__(self, index: SupportsIndex, value: _T) -> None: ...

    @overload
    def __setitem__(self, index: slice, value: Iterable[_T]) -> None: ...

    def __setitem__(
        self, index: SupportsIndex | slice, value: _T | Iterable[_T]
    ) -> None:
        """
        Ensure that when `(style_str, 'long string')` is set, the string will be
        exploded.
        """
        if not isinstance(index, slice):
            int_index = index.__index__()
            index = slice(int_index, int_index + 1)
        if isinstance(value, tuple):  # In case of `OneStyleAndTextTuple`.
            value = cast("List[_T]", [value])

        super().__setitem__(index, explode_text_fragments(value))


def explode_text_fragments(fragments: Iterable[_T]) -> _ExplodedList[_T]:
    """
    Turn a list of (style_str, text) tuples into another list where each string is
    exactly one character.

    It should be fine to call this function several times. Calling this on a
    list that is already exploded, is a null operation.

    :param fragments: List of (style, text) tuples.
    """
    # When the fragments is already exploded, don't explode again.
    if isinstance(fragments, _ExplodedList):
        return fragments

    result: list[_T] = []

    for style, string, *rest in fragments:
        for c in string:
            result.append((style, c, *rest))  # type: ignore

    return _ExplodedList(result)
