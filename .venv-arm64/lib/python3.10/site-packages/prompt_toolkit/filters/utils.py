from __future__ import annotations

from .base import Always, Filter, FilterOrBool, Never

__all__ = [
    "to_filter",
    "is_true",
]


_always = Always()
_never = Never()


_bool_to_filter: dict[bool, Filter] = {
    True: _always,
    False: _never,
}


def to_filter(bool_or_filter: FilterOrBool) -> Filter:
    """
    Accept both booleans and Filters as input and
    turn it into a Filter.
    """
    if isinstance(bool_or_filter, bool):
        return _bool_to_filter[bool_or_filter]

    if isinstance(bool_or_filter, Filter):
        return bool_or_filter

    raise TypeError(f"Expecting a bool or a Filter instance. Got {bool_or_filter!r}")


def is_true(value: FilterOrBool) -> bool:
    """
    Test whether `value` is True. In case of a Filter, call it.

    :param value: Boolean or `Filter` instance.
    """
    return to_filter(value)()
