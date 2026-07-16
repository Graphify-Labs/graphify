from __future__ import annotations

from abc import ABCMeta, abstractmethod
from typing import Callable, Iterable, Union

__all__ = ["Filter", "Never", "Always", "Condition", "FilterOrBool"]


class Filter(metaclass=ABCMeta):
    """
    Base class for any filter to activate/deactivate a feature, depending on a
    condition.

    The return value of ``__call__`` will tell if the feature should be active.
    """

    def __init__(self) -> None:
        self._and_cache: dict[Filter, Filter] = {}
        self._or_cache: dict[Filter, Filter] = {}
        self._invert_result: Filter | None = None

    @abstractmethod
    def __call__(self) -> bool:
        """
        The actual call to evaluate the filter.
        """
        return True

    def __and__(self, other: Filter) -> Filter:
        """
        Chaining of filters using the & operator.
        """
        assert isinstance(other, Filter), f"Expecting filter, got {other!r}"

        if isinstance(other, Always):
            return self
        if isinstance(other, Never):
            return other

        if other in self._and_cache:
            return self._and_cache[other]

        result = _AndList.create([self, other])
        self._and_cache[other] = result
        return result

    def __or__(self, other: Filter) -> Filter:
        """
        Chaining of filters using the | operator.
        """
        assert isinstance(other, Filter), f"Expecting filter, got {other!r}"

        if isinstance(other, Always):
            return other
        if isinstance(other, Never):
            return self

        if other in self._or_cache:
            return self._or_cache[other]

        result = _OrList.create([self, other])
        self._or_cache[other] = result
        return result

    def __invert__(self) -> Filter:
        """
        Inverting of filters using the ~ operator.
        """
        if self._invert_result is None:
            self._invert_result = _Invert(self)

        return self._invert_result

    def __bool__(self) -> None:
        """
        By purpose, we don't allow bool(...) operations directly on a filter,
        because the meaning is ambiguous.

        Executing a filter has to be done always by calling it. Providing
        defaults for `None` values should be done through an `is None` check
        instead of for instance ``filter1 or Always()``.
        """
        raise ValueError(
            "The truth value of a Filter is ambiguous. Instead, call it as a function."
        )


def _remove_duplicates(filters: list[Filter]) -> list[Filter]:
    result = []
    for f in filters:
        if f not in result:
            result.append(f)
    return result


class _AndList(Filter):
    """
    Result of &-operation between several filters.
    """

    def __init__(self, filters: list[Filter]) -> None:
        super().__init__()
        self.filters = filters

    @classmethod
    def create(cls, filters: Iterable[Filter]) -> Filter:
        """
        Create a new filter by applying an `&` operator between them.

        If there's only one unique filter in the given iterable, it will return
        that one filter instead of an `_AndList`.
        """
        filters_2: list[Filter] = []

        for f in filters:
            if isinstance(f, _AndList):  # Turn nested _AndLists into one.
                filters_2.extend(f.filters)
            else:
                filters_2.append(f)

        # Remove duplicates. This could speed up execution, and doesn't make a
        # difference for the evaluation.
        filters = _remove_duplicates(filters_2)

        # If only one filter is left, return that without wrapping into an
        # `_AndList`.
        if len(filters) == 1:
            return filters[0]

        return cls(filters)

    def __call__(self) -> bool:
        return all(f() for f in self.filters)

    def __repr__(self) -> str:
        return "&".join(repr(f) for f in self.filters)


class _OrList(Filter):
    """
    Result of |-operation between several filters.
    """

    def __init__(self, filters: list[Filter]) -> None:
        super().__init__()
        self.filters = filters

    @classmethod
    def create(cls, filters: Iterable[Filter]) -> Filter:
        """
        Create a new filter by applying an `|` operator between them.

        If there's only one unique filter in the given iterable, it will return
        that one filter instead of an `_OrList`.
        """
        filters_2: list[Filter] = []

        for f in filters:
            if isinstance(f, _OrList):  # Turn nested _AndLists into one.
                filters_2.extend(f.filters)
            else:
                filters_2.append(f)

        # Remove duplicates. This could speed up execution, and doesn't make a
        # difference for the evaluation.
        filters = _remove_duplicates(filters_2)

        # If only one filter is left, return that without wrapping into an
        # `_AndList`.
        if len(filters) == 1:
            return filters[0]

        return cls(filters)

    def __call__(self) -> bool:
        return any(f() for f in self.filters)

    def __repr__(self) -> str:
        return "|".join(repr(f) for f in self.filters)


class _Invert(Filter):
    """
    Negation of another filter.
    """

    def __init__(self, filter: Filter) -> None:
        super().__init__()
        self.filter = filter

    def __call__(self) -> bool:
        return not self.filter()

    def __repr__(self) -> str:
        return f"~{self.filter!r}"


class Always(Filter):
    """
    Always enable feature.
    """

    def __call__(self) -> bool:
        return True

    def __or__(self, other: Filter) -> Filter:
        return self

    def __and__(self, other: Filter) -> Filter:
        return other

    def __invert__(self) -> Never:
        return Never()


class Never(Filter):
    """
    Never enable feature.
    """

    def __call__(self) -> bool:
        return False

    def __and__(self, other: Filter) -> Filter:
        return self

    def __or__(self, other: Filter) -> Filter:
        return other

    def __invert__(self) -> Always:
        return Always()


class Condition(Filter):
    """
    Turn any callable into a Filter. The callable is supposed to not take any
    arguments.

    This can be used as a decorator::

        @Condition
        def feature_is_active():  # `feature_is_active` becomes a Filter.
            return True

    :param func: Callable which takes no inputs and returns a boolean.
    """

    def __init__(self, func: Callable[[], bool]) -> None:
        super().__init__()
        self.func = func

    def __call__(self) -> bool:
        return self.func()

    def __repr__(self) -> str:
        return f"Condition({self.func!r})"


# Often used as type annotation.
FilterOrBool = Union[Filter, bool]
