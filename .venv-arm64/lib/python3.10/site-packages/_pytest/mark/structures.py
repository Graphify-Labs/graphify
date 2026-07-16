# mypy: allow-untyped-defs
from __future__ import annotations

import collections.abc
from collections.abc import Callable
from collections.abc import Collection
from collections.abc import Iterable
from collections.abc import Iterator
from collections.abc import Mapping
from collections.abc import MutableMapping
from collections.abc import Sequence
import dataclasses
import enum
import inspect
from typing import Any
from typing import final
from typing import NamedTuple
from typing import overload
from typing import TYPE_CHECKING
from typing import TypeVar
import warnings

from .._code import getfslineno
from ..compat import NOTSET
from ..compat import NotSetType
from _pytest.config import Config
from _pytest.deprecated import check_ispytest
from _pytest.deprecated import PARAMETRIZE_NON_COLLECTION_ITERABLE
from _pytest.outcomes import fail
from _pytest.raises import AbstractRaises
from _pytest.scope import ScopeName
from _pytest.warning_types import PytestCollectionWarning
from _pytest.warning_types import PytestUnknownMarkWarning


if TYPE_CHECKING:
    from ..nodes import Node


EMPTY_PARAMETERSET_OPTION = "empty_parameter_set_mark"


# Singleton type for HIDDEN_PARAM, as described in:
# https://www.python.org/dev/peps/pep-0484/#support-for-singleton-types-in-unions
class _HiddenParam(enum.Enum):
    token = 0


#: Can be used as a parameter set id to hide it from the test name.
HIDDEN_PARAM = _HiddenParam.token


def istestfunc(func) -> bool:
    return callable(func) and getattr(func, "__name__", "<lambda>") != "<lambda>"


def get_empty_parameterset_mark(
    config: Config, argnames: Sequence[str], func
) -> MarkDecorator:
    from ..nodes import Collector

    argslisting = ", ".join(argnames)

    _fs, lineno = getfslineno(func)
    reason = f"got empty parameter set for ({argslisting})"
    requested_mark = config.getini(EMPTY_PARAMETERSET_OPTION)
    if requested_mark in ("", None, "skip"):
        mark = MARK_GEN.skip(reason=reason)
    elif requested_mark == "xfail":
        mark = MARK_GEN.xfail(reason=reason, run=False)
    elif requested_mark == "fail_at_collect":
        raise Collector.CollectError(
            f"Empty parameter set in '{func.__name__}' at line {lineno + 1}"
        )
    else:
        raise LookupError(requested_mark)
    return mark


class ParameterSet(NamedTuple):
    """A set of values for a set of parameters along with associated marks and
    an optional ID for the set.

    Examples::

        pytest.param(1, 2, 3)
        # ParameterSet(values=(1, 2, 3), marks=(), id=None)

        pytest.param("hello", id="greeting")
        # ParameterSet(values=("hello",), marks=(), id="greeting")

        # Parameter set with marks
        pytest.param(42, marks=pytest.mark.xfail)
        # ParameterSet(values=(42,), marks=(MarkDecorator(...),), id=None)

        # From parametrize mark (parameter names + list of parameter sets)
        pytest.mark.parametrize(
            ("a", "b", "expected"),
            [
                (1, 2, 3),
                pytest.param(40, 2, 42, id="everything"),
            ],
        )
        # ParameterSet(values=(1, 2, 3), marks=(), id=None)
        # ParameterSet(values=(40, 2, 42), marks=(), id="everything")
    """

    values: Sequence[object | NotSetType]
    marks: Collection[MarkDecorator | Mark]
    id: str | _HiddenParam | None

    @classmethod
    def param(
        cls,
        *values: object,
        marks: MarkDecorator | Collection[MarkDecorator | Mark] = (),
        id: str | _HiddenParam | None = None,
    ) -> ParameterSet:
        if isinstance(marks, MarkDecorator):
            marks = (marks,)
        else:
            assert isinstance(marks, collections.abc.Collection)
        if any(i.name == "usefixtures" for i in marks):
            raise ValueError(
                "pytest.param cannot add pytest.mark.usefixtures; see "
                "https://docs.pytest.org/en/stable/reference/reference.html#pytest-param"
            )

        if id is not None:
            if not isinstance(id, str) and id is not HIDDEN_PARAM:
                raise TypeError(
                    "Expected id to be a string or a `pytest.HIDDEN_PARAM` sentinel, "
                    f"got {type(id)}: {id!r}",
                )
        return cls(values, marks, id)

    @classmethod
    def extract_from(
        cls,
        parameterset: ParameterSet | Sequence[object] | object,
        force_tuple: bool = False,
    ) -> ParameterSet:
        """Extract from an object or objects.

        :param parameterset:
            A legacy style parameterset that may or may not be a tuple,
            and may or may not be wrapped into a mess of mark objects.

        :param force_tuple:
            Enforce tuple wrapping so single argument tuple values
            don't get decomposed and break tests.
        """
        if isinstance(parameterset, cls):
            return parameterset
        if force_tuple:
            return cls.param(parameterset)
        else:
            # TODO: Refactor to fix this type-ignore. Currently the following
            # passes type-checking but crashes:
            #
            #   @pytest.mark.parametrize(('x', 'y'), [1, 2])
            #   def test_foo(x, y): pass
            return cls(parameterset, marks=[], id=None)  # type: ignore[arg-type]

    @staticmethod
    def _parse_parametrize_args(
        argnames: str | Sequence[str],
        argvalues: Iterable[ParameterSet | Sequence[object] | object],
        *args,
        **kwargs,
    ) -> tuple[Sequence[str], bool]:
        if isinstance(argnames, str):
            # A trailing comma indicates tuple-style: "arg," is equivalent to ("arg",)
            # In this case, argvalues should be a list of tuples, not wrapped values.
            # See https://github.com/pytest-dev/pytest/issues/719
            has_trailing_comma = argnames.rstrip().endswith(",")
            argnames = [x.strip() for x in argnames.split(",") if x.strip()]
            force_tuple = len(argnames) == 1 and not has_trailing_comma
        else:
            force_tuple = False
        return argnames, force_tuple

    @staticmethod
    def _parse_parametrize_parameters(
        argvalues: Iterable[ParameterSet | Sequence[object] | object],
        force_tuple: bool,
    ) -> list[ParameterSet]:
        return [
            ParameterSet.extract_from(x, force_tuple=force_tuple) for x in argvalues
        ]

    @classmethod
    def _for_parametrize(
        cls,
        argnames: str | Sequence[str],
        argvalues: Iterable[ParameterSet | Sequence[object] | object],
        func,
        config: Config,
        nodeid: str,
    ) -> tuple[Sequence[str], list[ParameterSet]]:
        if not isinstance(argvalues, Collection):
            warnings.warn(
                PARAMETRIZE_NON_COLLECTION_ITERABLE.format(
                    nodeid=nodeid,
                    type_name=type(argvalues).__name__,
                ),
                stacklevel=3,
            )

        argnames, force_tuple = cls._parse_parametrize_args(argnames, argvalues)
        parameters = cls._parse_parametrize_parameters(argvalues, force_tuple)
        del argvalues

        if parameters:
            # Check all parameter sets have the correct number of values.
            for param in parameters:
                if len(param.values) != len(argnames):
                    msg = (
                        '{nodeid}: in "parametrize" the number of names ({names_len}):\n'
                        "  {names}\n"
                        "must be equal to the number of values ({values_len}):\n"
                        "  {values}"
                    )
                    fail(
                        msg.format(
                            nodeid=nodeid,
                            values=param.values,
                            names=argnames,
                            names_len=len(argnames),
                            values_len=len(param.values),
                        ),
                        pytrace=False,
                    )
        else:
            # Empty parameter set (likely computed at runtime): create a single
            # parameter set with NOTSET values, with the "empty parameter set" mark applied to it.
            mark = get_empty_parameterset_mark(config, argnames, func)
            parameters.append(
                ParameterSet(
                    values=(NOTSET,) * len(argnames), marks=[mark], id="NOTSET"
                )
            )
        return argnames, parameters


@final
@dataclasses.dataclass(frozen=True)
class Mark:
    """A pytest mark."""

    #: Name of the mark.
    name: str
    #: Positional arguments of the mark decorator.
    args: tuple[Any, ...]
    #: Keyword arguments of the mark decorator.
    kwargs: Mapping[str, Any]

    #: Source Mark for ids with parametrize Marks.
    _param_ids_from: Mark | None = dataclasses.field(default=None, repr=False)
    #: Resolved/generated ids with parametrize Marks.
    _param_ids_generated: Sequence[str] | None = dataclasses.field(
        default=None, repr=False
    )

    def __init__(
        self,
        name: str,
        args: tuple[Any, ...],
        kwargs: Mapping[str, Any],
        param_ids_from: Mark | None = None,
        param_ids_generated: Sequence[str] | None = None,
        *,
        _ispytest: bool = False,
    ) -> None:
        """:meta private:"""
        check_ispytest(_ispytest)
        # Weirdness to bypass frozen=True.
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "args", args)
        object.__setattr__(self, "kwargs", kwargs)
        object.__setattr__(self, "_param_ids_from", param_ids_from)
        object.__setattr__(self, "_param_ids_generated", param_ids_generated)

    def _has_param_ids(self) -> bool:
        return "ids" in self.kwargs or len(self.args) >= 4

    def combined_with(self, other: Mark) -> Mark:
        """Return a new Mark which is a combination of this
        Mark and another Mark.

        Combines by appending args and merging kwargs.

        :param Mark other: The mark to combine with.
        :rtype: Mark
        """
        assert self.name == other.name

        # Remember source of ids with parametrize Marks.
        param_ids_from: Mark | None = None
        if self.name == "parametrize":
            if other._has_param_ids():
                param_ids_from = other
            elif self._has_param_ids():
                param_ids_from = self

        return Mark(
            self.name,
            self.args + other.args,
            dict(self.kwargs, **other.kwargs),
            param_ids_from=param_ids_from,
            _ispytest=True,
        )


# A generic parameter designating an object to which a Mark may
# be applied -- a test function (callable) or class.
# Note: a lambda is not allowed, but this can't be represented.
Markable = TypeVar("Markable", bound=Callable[..., object] | type)


@dataclasses.dataclass
class MarkDecorator:
    """A decorator for applying a mark on test functions and classes.

    ``MarkDecorators`` are created with ``pytest.mark``::

        mark1 = pytest.mark.NAME  # Simple MarkDecorator
        mark2 = pytest.mark.NAME(name1=value)  # Parametrized MarkDecorator

    and can then be applied as decorators to test functions::

        @mark2
        def test_function():
            pass

    When a ``MarkDecorator`` is called, it does the following:

    1. If called with a single class as its only positional argument and no
       additional keyword arguments, it attaches the mark to the class so it
       gets applied automatically to all test cases found in that class.

    2. If called with a single function as its only positional argument and
       no additional keyword arguments, it attaches the mark to the function,
       containing all the arguments already stored internally in the
       ``MarkDecorator``.

    3. When called in any other case, it returns a new ``MarkDecorator``
       instance with the original ``MarkDecorator``'s content updated with
       the arguments passed to this call.

    Note: The rules above prevent a ``MarkDecorator`` from storing only a
    single function or class reference as its positional argument with no
    additional keyword or positional arguments. You can work around this by
    using `with_args()`.
    """

    mark: Mark

    def __init__(self, mark: Mark, *, _ispytest: bool = False) -> None:
        """:meta private:"""
        check_ispytest(_ispytest)
        self.mark = mark

    @property
    def name(self) -> str:
        """Alias for mark.name."""
        return self.mark.name

    @property
    def args(self) -> tuple[Any, ...]:
        """Alias for mark.args."""
        return self.mark.args

    @property
    def kwargs(self) -> Mapping[str, Any]:
        """Alias for mark.kwargs."""
        return self.mark.kwargs

    @property
    def markname(self) -> str:
        """:meta private:"""
        return self.name  # for backward-compat (2.4.1 had this attr)

    def with_args(self, *args: object, **kwargs: object) -> MarkDecorator:
        """Return a MarkDecorator with extra arguments added.

        Unlike calling the MarkDecorator, with_args() can be used even
        if the sole argument is a callable/class.
        """
        mark = Mark(self.name, args, kwargs, _ispytest=True)
        return MarkDecorator(self.mark.combined_with(mark), _ispytest=True)

    # Type ignored because the overloads overlap with an incompatible
    # return type. Not much we can do about that. Thankfully mypy picks
    # the first match so it works out even if we break the rules.
    @overload
    def __call__(self, arg: Markable) -> Markable:  # type: ignore[overload-overlap]
        pass

    @overload
    def __call__(self, *args: object, **kwargs: object) -> MarkDecorator:
        pass

    def __call__(self, *args: object, **kwargs: object):
        """Call the MarkDecorator."""
        if args and not kwargs:
            func = args[0]
            is_class = inspect.isclass(func)
            # For staticmethods/classmethods, the marks are eventually fetched from the
            # function object, not the descriptor, so unwrap.
            unwrapped_func = func
            if isinstance(func, staticmethod | classmethod):
                unwrapped_func = func.__func__
            if len(args) == 1 and (istestfunc(unwrapped_func) or is_class):
                store_mark(unwrapped_func, self.mark)
                return func
        return self.with_args(*args, **kwargs)


def get_unpacked_marks(
    obj: object | type,
    *,
    consider_mro: bool = True,
) -> list[Mark]:
    """Obtain the unpacked marks that are stored on an object.

    If obj is a class and consider_mro is true, return marks applied to
    this class and all of its super-classes in MRO order. If consider_mro
    is false, only return marks applied directly to this class.
    """
    if isinstance(obj, type):
        if not consider_mro:
            mark_lists = [obj.__dict__.get("pytestmark", [])]
        else:
            mark_lists = [
                x.__dict__.get("pytestmark", []) for x in reversed(obj.__mro__)
            ]
        mark_list = []
        for item in mark_lists:
            if isinstance(item, list):
                mark_list.extend(item)
            else:
                mark_list.append(item)
    else:
        mark_attribute = getattr(obj, "pytestmark", [])
        if mark_attribute is None:
            warnings.warn(
                "Module defines a `__getattr__` which returns None for "
                "'pytestmark' instead of raising AttributeError. "
                "Make sure `__getattr__` raises AttributeError for "
                "attributes it does not provide. "
                "See https://github.com/pytest-dev/pytest/issues/8265",
                PytestCollectionWarning,
                stacklevel=2,
            )
            mark_list = []
        elif isinstance(mark_attribute, list):
            mark_list = mark_attribute
        else:
            mark_list = [mark_attribute]
    return list(normalize_mark_list(mark_list))


def normalize_mark_list(
    mark_list: Iterable[Mark | MarkDecorator],
) -> Iterable[Mark]:
    """
    Normalize an iterable of Mark or MarkDecorator objects into a list of marks
    by retrieving the `mark` attribute on MarkDecorator instances.

    :param mark_list: marks to normalize
    :returns: A new list of the extracted Mark objects
    """
    for mark in mark_list:
        mark_obj = getattr(mark, "mark", mark)
        if not isinstance(mark_obj, Mark):
            raise TypeError(f"got {mark_obj!r} instead of Mark")
        yield mark_obj


def store_mark(obj, mark: Mark) -> None:
    """Store a Mark on an object.

    This is used to implement the Mark declarations/decorators correctly.
    """
    assert isinstance(mark, Mark), mark

    from ..fixtures import getfixturemarker

    if getfixturemarker(obj) is not None:
        fail(
            "Marks cannot be applied to fixtures.\n"
            "See docs: https://docs.pytest.org/en/stable/deprecations.html#applying-a-mark-to-a-fixture-function"
        )

    # Always reassign name to avoid updating pytestmark in a reference that
    # was only borrowed.
    obj.pytestmark = [*get_unpacked_marks(obj, consider_mro=False), mark]


# Typing for builtin pytest marks. This is cheating; it gives builtin marks
# special privilege, and breaks modularity. But practicality beats purity...
if TYPE_CHECKING:

    class _SkipMarkDecorator(MarkDecorator):
        @overload  # type: ignore[override,no-overload-impl]
        def __call__(self, arg: Markable) -> Markable: ...

        @overload
        def __call__(self, reason: str = ...) -> MarkDecorator: ...

    class _SkipifMarkDecorator(MarkDecorator):
        def __call__(  # type: ignore[override]
            self,
            condition: str | bool = ...,
            *conditions: str | bool,
            reason: str = ...,
        ) -> MarkDecorator: ...

    class _XfailMarkDecorator(MarkDecorator):
        @overload  # type: ignore[override,no-overload-impl]
        def __call__(self, arg: Markable) -> Markable: ...

        @overload
        def __call__(
            self,
            condition: str | bool = True,
            *conditions: str | bool,
            reason: str = ...,
            run: bool = ...,
            raises: None
            | type[BaseException]
            | tuple[type[BaseException], ...]
            | AbstractRaises[BaseException] = ...,
            strict: bool = ...,
        ) -> MarkDecorator: ...

    class _ParametrizeMarkDecorator(MarkDecorator):
        def __call__(  # type: ignore[override]
            self,
            argnames: str | Sequence[str],
            argvalues: Iterable[ParameterSet | Sequence[object] | object],
            # TODO(pytest10): Change to below after PARAMETRIZE_NON_COLLECTION_ITERABLE deprecation.
            #                 Overload doesn't work, see #14606.
            # argvalues: Collection[ParameterSet | Sequence[object] | object],
            *,
            indirect: bool | Sequence[str] = ...,
            ids: Iterable[None | str | float | int | bool | _HiddenParam]
            | Callable[[Any], object | None]
            | None = ...,
            scope: ScopeName | None = ...,
        ) -> MarkDecorator: ...

    class _UsefixturesMarkDecorator(MarkDecorator):
        def __call__(self, *fixtures: str) -> MarkDecorator:  # type: ignore[override]
            ...

    class _FilterwarningsMarkDecorator(MarkDecorator):
        def __call__(self, *filters: str) -> MarkDecorator:  # type: ignore[override]
            ...


@final
class MarkGenerator:
    """Factory for :class:`MarkDecorator` objects - exposed as
    a ``pytest.mark`` singleton instance.

    Example::

         import pytest


         @pytest.mark.slowtest
         def test_function():
             pass

    applies a 'slowtest' :class:`Mark` on ``test_function``.
    """

    # See TYPE_CHECKING above.
    if TYPE_CHECKING:
        skip: _SkipMarkDecorator
        skipif: _SkipifMarkDecorator
        xfail: _XfailMarkDecorator
        parametrize: _ParametrizeMarkDecorator
        usefixtures: _UsefixturesMarkDecorator
        filterwarnings: _FilterwarningsMarkDecorator

    def __init__(self, *, _ispytest: bool = False) -> None:
        check_ispytest(_ispytest)
        self._config: Config | None = None
        self._markers: set[str] = set()

    def __getattr__(self, name: str) -> MarkDecorator:
        """Generate a new :class:`MarkDecorator` with the given name."""
        if name[0] == "_":
            raise AttributeError("Marker name must NOT start with underscore")

        if self._config is not None:
            # We store a set of markers as a performance optimisation - if a mark
            # name is in the set we definitely know it, but a mark may be known and
            # not in the set.  We therefore start by updating the set!
            if name not in self._markers:
                for line in self._config.getini("markers"):
                    # example lines: "skipif(condition): skip the given test if..."
                    # or "hypothesis: tests which use Hypothesis", so to get the
                    # marker name we split on both `:` and `(`.
                    marker = line.split(":")[0].split("(")[0].strip()
                    self._markers.add(marker)

            # If the name is not in the set of known marks after updating,
            # then it really is time to issue a warning or an error.
            if name not in self._markers:
                # Raise a specific error for common misspellings of "parametrize".
                if name in ["parameterize", "parametrise", "parameterise"]:
                    __tracebackhide__ = True
                    fail(f"Unknown '{name}' mark, did you mean 'parametrize'?")

                strict_markers = self._config.getini("strict_markers")
                if strict_markers is None:
                    strict_markers = self._config.getini("strict")
                if strict_markers:
                    fail(
                        f"{name!r} not found in `markers` configuration option",
                        pytrace=False,
                    )

                warnings.warn(
                    f"Unknown pytest.mark.{name} - is this a typo?  You can register "
                    "custom marks to avoid this warning - for details, see "
                    "https://docs.pytest.org/en/stable/how-to/mark.html",
                    PytestUnknownMarkWarning,
                    2,
                )

        return MarkDecorator(Mark(name, (), {}, _ispytest=True), _ispytest=True)


MARK_GEN = MarkGenerator(_ispytest=True)


@final
class NodeKeywords(MutableMapping[str, Any]):
    __slots__ = ("_markers", "node", "parent")

    def __init__(self, node: Node) -> None:
        self.node = node
        self.parent = node.parent
        self._markers = {node.name: True}

    def __getitem__(self, key: str) -> Any:
        try:
            return self._markers[key]
        except KeyError:
            if self.parent is None:
                raise
            return self.parent.keywords[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._markers[key] = value

    # Note: we could've avoided explicitly implementing some of the methods
    # below and use the collections.abc fallback, but that would be slow.

    def __contains__(self, key: object) -> bool:
        return key in self._markers or (
            self.parent is not None and key in self.parent.keywords
        )

    def update(  # type: ignore[override]
        self,
        other: Mapping[str, Any] | Iterable[tuple[str, Any]] = (),
        **kwds: Any,
    ) -> None:
        self._markers.update(other)
        self._markers.update(kwds)

    def __delitem__(self, key: str) -> None:
        raise ValueError("cannot delete key in keywords dict")

    def __iter__(self) -> Iterator[str]:
        # Doesn't need to be fast.
        yield from self._markers
        if self.parent is not None:
            for keyword in self.parent.keywords:
                # self._marks and self.parent.keywords can have duplicates.
                if keyword not in self._markers:
                    yield keyword

    def __len__(self) -> int:
        # Doesn't need to be fast.
        return sum(1 for keyword in self)

    def __repr__(self) -> str:
        return f"<NodeKeywords for node {self.node}>"
