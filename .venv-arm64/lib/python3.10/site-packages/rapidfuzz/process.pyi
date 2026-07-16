from __future__ import annotations

from collections.abc import Collection, Generator, Hashable, Iterable, Mapping, Sequence
from typing import (
    Any,
    Callable,
    Protocol,
    TypeVar,
    overload,
)

from rapidfuzz.fuzz import WRatio, ratio

_StringType = Sequence[Hashable]
_StringType1 = TypeVar("_StringType1", bound=Sequence[Hashable])
_StringType2 = TypeVar("_StringType2", bound=Sequence[Hashable])
_UnprocessedType1 = TypeVar("_UnprocessedType1")
_UnprocessedType2 = TypeVar("_UnprocessedType2")
_KeyType = TypeVar("_KeyType")
_ResultType = TypeVar("_ResultType", int, float)

_StringType1_contra = TypeVar("_StringType1_contra", contravariant=True, bound=Sequence[Hashable])
_StringType2_contra = TypeVar("_StringType2_contra", contravariant=True, bound=Sequence[Hashable])
_ResultType_contra = TypeVar("_ResultType_contra", int, float, contravariant=True)
_ResultType_co = TypeVar("_ResultType_co", int, float, covariant=True)

class _Scorer(Protocol[_StringType1_contra, _StringType2_contra, _ResultType_contra, _ResultType_co]):
    def __call__(
        self, __s1: _StringType1_contra, __s2: _StringType2_contra, *, score_cutoff: _ResultType_contra | None
    ) -> _ResultType_co: ...

# mypy wants defaults to be valid for every possible parameterization of a generic function
# so add separate overloads for the default version
@overload
def extractOne(
    query: Sequence[Hashable] | None,
    choices: Mapping[_KeyType, _StringType2 | None],
    *,
    scorer: _Scorer[Sequence[Hashable], Sequence[Hashable], float, float] = WRatio,
    processor: None = None,
    score_cutoff: float,
    score_hint: float | None = None,
    scorer_kwargs: dict[str, Any] | None = None,
) -> tuple[_StringType2, float, _KeyType] | None: ...
@overload
def extractOne(
    query: Sequence[Hashable] | None,
    choices: Mapping[_KeyType, _StringType2 | None],
    *,
    scorer: _Scorer[Sequence[Hashable], Sequence[Hashable], float, float] = WRatio,
    processor: None = None,
    score_cutoff: None = None,
    score_hint: float | None = None,
    scorer_kwargs: dict[str, Any] | None = None,
) -> tuple[_StringType2, float, _KeyType]: ...
@overload
def extractOne(
    query: Sequence[Hashable] | None,
    choices: Iterable[_StringType2 | None],
    *,
    scorer: _Scorer[Sequence[Hashable], Sequence[Hashable], float, float] = WRatio,
    processor: None = None,
    score_cutoff: float,
    score_hint: float | None = None,
    scorer_kwargs: dict[str, Any] | None = None,
) -> tuple[_StringType2, float, int] | None: ...
@overload
def extractOne(
    query: Sequence[Hashable] | None,
    choices: Iterable[_StringType2 | None],
    *,
    scorer: _Scorer[Sequence[Hashable], Sequence[Hashable], float, float] = WRatio,
    processor: None = None,
    score_cutoff: None = None,
    score_hint: float | None = None,
    scorer_kwargs: dict[str, Any] | None = None,
) -> tuple[_StringType2, float, int]: ...
@overload
def extractOne(
    query: _UnprocessedType1 | None,
    choices: Mapping[_KeyType, _UnprocessedType2 | None],
    *,
    scorer: _Scorer[Sequence[Hashable], Sequence[Hashable], float, float] = WRatio,
    processor: Callable[[_UnprocessedType1 | _UnprocessedType2], Sequence[Hashable]],
    score_cutoff: float,
    score_hint: float | None = None,
    scorer_kwargs: dict[str, Any] | None = None,
) -> tuple[_UnprocessedType2, float, _KeyType] | None: ...
@overload
def extractOne(
    query: _UnprocessedType1 | None,
    choices: Mapping[_KeyType, _UnprocessedType2 | None],
    *,
    scorer: _Scorer[Sequence[Hashable], Sequence[Hashable], float, float] = WRatio,
    processor: Callable[[_UnprocessedType1 | _UnprocessedType2], Sequence[Hashable]],
    score_cutoff: None = None,
    score_hint: float | None = None,
    scorer_kwargs: dict[str, Any] | None = None,
) -> tuple[_UnprocessedType2, float, _KeyType]: ...
@overload
def extractOne(
    query: _UnprocessedType1 | None,
    choices: Iterable[_UnprocessedType2 | None],
    *,
    scorer: _Scorer[Sequence[Hashable], Sequence[Hashable], float, float] = WRatio,
    processor: Callable[[_UnprocessedType1 | _UnprocessedType2], Sequence[Hashable]],
    score_cutoff: float,
    score_hint: float | None = None,
    scorer_kwargs: dict[str, Any] | None = None,
) -> tuple[_UnprocessedType2, float, int] | None: ...
@overload
def extractOne(
    query: _UnprocessedType1 | None,
    choices: Iterable[_UnprocessedType2 | None],
    *,
    scorer: _Scorer[Sequence[Hashable], Sequence[Hashable], float, float] = WRatio,
    processor: Callable[[_UnprocessedType1 | _UnprocessedType2], Sequence[Hashable]],
    score_cutoff: None = None,
    score_hint: float | None = None,
    scorer_kwargs: dict[str, Any] | None = None,
) -> tuple[_UnprocessedType2, float, int]: ...
@overload
def extractOne(
    query: _StringType1 | None,
    choices: Mapping[_KeyType, _StringType2 | None],
    *,
    scorer: _Scorer[_StringType1, _StringType2, _ResultType, _ResultType],
    processor: None = None,
    score_cutoff: _ResultType,
    score_hint: _ResultType | None = None,
    scorer_kwargs: dict[str, Any] | None = None,
) -> tuple[_StringType2, _ResultType, _KeyType] | None: ...
@overload
def extractOne(
    query: _StringType1 | None,
    choices: Mapping[_KeyType, _StringType2 | None],
    *,
    scorer: _Scorer[_StringType1, _StringType2, _ResultType, _ResultType],
    processor: None = None,
    score_cutoff: None = None,
    score_hint: _ResultType | None = None,
    scorer_kwargs: dict[str, Any] | None = None,
) -> tuple[_StringType2, _ResultType, _KeyType]: ...
@overload
def extractOne(
    query: _StringType1 | None,
    choices: Iterable[_StringType2 | None],
    *,
    scorer: _Scorer[_StringType1, _StringType2, _ResultType, _ResultType],
    processor: None = None,
    score_cutoff: _ResultType,
    score_hint: _ResultType | None = None,
    scorer_kwargs: dict[str, Any] | None = None,
) -> tuple[_StringType2, _ResultType, int] | None: ...
@overload
def extractOne(
    query: _StringType1 | None,
    choices: Iterable[_StringType2 | None],
    *,
    scorer: _Scorer[_StringType1, _StringType2, _ResultType, _ResultType],
    processor: None = None,
    score_cutoff: None = None,
    score_hint: _ResultType | None = None,
    scorer_kwargs: dict[str, Any] | None = None,
) -> tuple[_StringType2, _ResultType, int]: ...
@overload
def extractOne(
    query: _UnprocessedType1 | None,
    choices: Mapping[_KeyType, _UnprocessedType2 | None],
    *,
    scorer: _Scorer[_StringType1, _StringType1, _ResultType, _ResultType],
    processor: Callable[[_UnprocessedType1 | _UnprocessedType2], _StringType1],
    score_cutoff: _ResultType,
    score_hint: _ResultType | None = None,
    scorer_kwargs: dict[str, Any] | None = None,
) -> tuple[_UnprocessedType2, _ResultType, _KeyType] | None: ...
@overload
def extractOne(
    query: _UnprocessedType1 | None,
    choices: Mapping[_KeyType, _UnprocessedType2 | None],
    *,
    scorer: _Scorer[_StringType1, _StringType1, _ResultType, _ResultType],
    processor: Callable[[_UnprocessedType1 | _UnprocessedType2], _StringType1],
    score_cutoff: None = None,
    score_hint: _ResultType | None = None,
    scorer_kwargs: dict[str, Any] | None = None,
) -> tuple[_UnprocessedType2, _ResultType, _KeyType]: ...
@overload
def extractOne(
    query: _UnprocessedType1 | None,
    choices: Iterable[_UnprocessedType2 | None],
    *,
    scorer: _Scorer[_StringType1, _StringType1, _ResultType, _ResultType],
    processor: Callable[[_UnprocessedType1 | _UnprocessedType2], _StringType1],
    score_cutoff: _ResultType,
    score_hint: _ResultType | None = None,
    scorer_kwargs: dict[str, Any] | None = None,
) -> tuple[_UnprocessedType2, _ResultType, int] | None: ...
@overload
def extractOne(
    query: _UnprocessedType1 | None,
    choices: Iterable[_UnprocessedType2 | None],
    *,
    scorer: _Scorer[_StringType1, _StringType1, _ResultType, _ResultType],
    processor: Callable[[_UnprocessedType1 | _UnprocessedType2], _StringType1],
    score_cutoff: None = None,
    score_hint: _ResultType | None = None,
    scorer_kwargs: dict[str, Any] | None = None,
) -> tuple[_UnprocessedType2, _ResultType, int]: ...

# mypy wants defaults to be valid for every possible parameterization of a generic function
# so add separate overloads for the default version
@overload
def extract(
    query: Sequence[Hashable] | None,
    choices: Mapping[_KeyType, _StringType2 | None],
    *,
    scorer: _Scorer[Sequence[Hashable], Sequence[Hashable], float, float] = WRatio,
    processor: None = None,
    limit: int | None = 5,
    score_cutoff: float | None = None,
    score_hint: float | None = None,
    scorer_kwargs: dict[str, Any] | None = None,
) -> list[tuple[_StringType2, float, _KeyType]]: ...
@overload
def extract(
    query: Sequence[Hashable] | None,
    choices: Iterable[_StringType2 | None],
    *,
    scorer: _Scorer[Sequence[Hashable], Sequence[Hashable], float, float] = WRatio,
    processor: None = None,
    limit: int | None = 5,
    score_cutoff: float | None = None,
    score_hint: float | None = None,
    scorer_kwargs: dict[str, Any] | None = None,
) -> list[tuple[_StringType2, float, int]]: ...
@overload
def extract(
    query: _UnprocessedType1 | None,
    choices: Mapping[_KeyType, _UnprocessedType2 | None],
    *,
    scorer: _Scorer[Sequence[Hashable], Sequence[Hashable], float, float] = WRatio,
    processor: Callable[[_UnprocessedType1 | _UnprocessedType2], Sequence[Hashable]],
    limit: int | None = 5,
    score_cutoff: float | None = None,
    score_hint: float | None = None,
    scorer_kwargs: dict[str, Any] | None = None,
) -> list[tuple[_UnprocessedType2, float, _KeyType]]: ...
@overload
def extract(
    query: _UnprocessedType1 | None,
    choices: Iterable[_UnprocessedType2 | None],
    *,
    scorer: _Scorer[Sequence[Hashable], Sequence[Hashable], float, float] = WRatio,
    processor: Callable[[_UnprocessedType1 | _UnprocessedType2], Sequence[Hashable]],
    limit: int | None = 5,
    score_cutoff: float | None = None,
    score_hint: float | None = None,
    scorer_kwargs: dict[str, Any] | None = None,
) -> list[tuple[_UnprocessedType2, float, int]]: ...
@overload
def extract(
    query: _StringType1 | None,
    choices: Mapping[_KeyType, _StringType2 | None],
    *,
    scorer: _Scorer[_StringType1, _StringType2, _ResultType, _ResultType],
    processor: None = None,
    limit: int | None = 5,
    score_cutoff: _ResultType | None = None,
    score_hint: _ResultType | None = None,
    scorer_kwargs: dict[str, Any] | None = None,
) -> list[tuple[_StringType2, _ResultType, _KeyType]]: ...
@overload
def extract(
    query: _StringType1 | None,
    choices: Collection[_StringType2 | None],
    *,
    scorer: _Scorer[_StringType1, _StringType2, _ResultType, _ResultType],
    processor: None = None,
    limit: int | None = 5,
    score_cutoff: _ResultType | None = None,
    score_hint: _ResultType | None = None,
    scorer_kwargs: dict[str, Any] | None = None,
) -> list[tuple[_StringType2, _ResultType, int]]: ...
@overload
def extract(
    query: _UnprocessedType1 | None,
    choices: Mapping[_KeyType, _UnprocessedType2 | None],
    *,
    scorer: _Scorer[_StringType1, _StringType1, _ResultType, _ResultType],
    processor: Callable[[_UnprocessedType1 | _UnprocessedType2], _StringType1],
    limit: int | None = 5,
    score_cutoff: _ResultType | None = None,
    score_hint: _ResultType | None = None,
    scorer_kwargs: dict[str, Any] | None = None,
) -> list[tuple[_UnprocessedType2, _ResultType, _KeyType]]: ...
@overload
def extract(
    query: _UnprocessedType1 | None,
    choices: Collection[_UnprocessedType2 | None],
    *,
    scorer: _Scorer[_StringType1, _StringType1, _ResultType, _ResultType],
    processor: Callable[[_UnprocessedType1 | _UnprocessedType2], _StringType1],
    limit: int | None = 5,
    score_cutoff: _ResultType | None = None,
    score_hint: _ResultType | None = None,
    scorer_kwargs: dict[str, Any] | None = None,
) -> list[tuple[_UnprocessedType2, _ResultType, int]]: ...

# mypy wants defaults to be valid for every possible parameterization of a generic function
# so add separate overloads for the default version
@overload
def extract_iter(
    query: Sequence[Hashable] | None,
    choices: Mapping[_KeyType, _StringType2 | None],
    *,
    scorer: _Scorer[Sequence[Hashable], Sequence[Hashable], float, float] = WRatio,
    processor: None = None,
    score_cutoff: float | None = None,
    score_hint: float | None = None,
    scorer_kwargs: dict[str, Any] | None = None,
) -> Generator[tuple[_StringType2, float, _KeyType], None, None]: ...
@overload
def extract_iter(
    query: Sequence[Hashable] | None,
    choices: Iterable[_StringType2 | None],
    *,
    scorer: _Scorer[Sequence[Hashable], Sequence[Hashable], float, float] = WRatio,
    processor: None = None,
    score_cutoff: float | None = None,
    score_hint: float | None = None,
    scorer_kwargs: dict[str, Any] | None = None,
) -> Generator[tuple[_StringType2, float, int], None, None]: ...
@overload
def extract_iter(
    query: _UnprocessedType1 | None,
    choices: Mapping[_KeyType, _UnprocessedType2 | None],
    *,
    scorer: _Scorer[Sequence[Hashable], Sequence[Hashable], float, float] = WRatio,
    processor: Callable[[_UnprocessedType1 | _UnprocessedType2], Sequence[Hashable]],
    score_cutoff: float | None = None,
    score_hint: float | None = None,
    scorer_kwargs: dict[str, Any] | None = None,
) -> Generator[tuple[_UnprocessedType2, float, _KeyType], None, None]: ...
@overload
def extract_iter(
    query: _UnprocessedType1 | None,
    choices: Iterable[_UnprocessedType2 | None],
    *,
    scorer: _Scorer[Sequence[Hashable], Sequence[Hashable], float, float] = WRatio,
    processor: Callable[[_UnprocessedType1 | _UnprocessedType2], Sequence[Hashable]],
    score_cutoff: float | None = None,
    score_hint: float | None = None,
    scorer_kwargs: dict[str, Any] | None = None,
) -> Generator[tuple[_UnprocessedType2, float, int], None, None]: ...
@overload
def extract_iter(
    query: _StringType1 | None,
    choices: Mapping[_KeyType, _StringType2 | None],
    *,
    scorer: _Scorer[_StringType1, _StringType2, _ResultType, _ResultType],
    processor: None = None,
    score_cutoff: _ResultType | None = None,
    score_hint: _ResultType | None = None,
    scorer_kwargs: dict[str, Any] | None = None,
) -> Generator[tuple[_StringType2, _ResultType, _KeyType], None, None]: ...
@overload
def extract_iter(
    query: _StringType1 | None,
    choices: Iterable[_StringType2 | None],
    *,
    scorer: _Scorer[_StringType1, _StringType2, _ResultType, _ResultType],
    processor: None = None,
    score_cutoff: _ResultType | None = None,
    score_hint: _ResultType | None = None,
    scorer_kwargs: dict[str, Any] | None = None,
) -> Generator[tuple[_StringType2, _ResultType, int], None, None]: ...
@overload
def extract_iter(
    query: _UnprocessedType1 | None,
    choices: Mapping[_KeyType, _UnprocessedType2 | None],
    *,
    scorer: _Scorer[_StringType1, _StringType1, _ResultType, _ResultType],
    processor: Callable[[_UnprocessedType1 | _UnprocessedType2], _StringType1],
    score_cutoff: _ResultType | None = None,
    score_hint: _ResultType | None = None,
    scorer_kwargs: dict[str, Any] | None = None,
) -> Generator[tuple[_UnprocessedType2, _ResultType, _KeyType], None, None]: ...
@overload
def extract_iter(
    query: _UnprocessedType1 | None,
    choices: Iterable[_UnprocessedType2 | None],
    *,
    scorer: _Scorer[_StringType1, _StringType1, _ResultType, _ResultType],
    processor: Callable[[_UnprocessedType1 | _UnprocessedType2], _StringType1],
    score_cutoff: _ResultType | None = None,
    score_hint: _ResultType | None = None,
    scorer_kwargs: dict[str, Any] | None = None,
) -> Generator[tuple[_UnprocessedType2, _ResultType, int], None, None]: ...

try:
    import numpy.typing as npt

    @overload
    def cdist(
        queries: Iterable[Sequence[Hashable] | None],
        choices: Iterable[Sequence[Hashable] | None],
        *,
        scorer: _Scorer[Sequence[Hashable], Sequence[Hashable], float, float] = ratio,
        processor: None = None,
        score_cutoff: float | None = None,
        score_hint: float | None = None,
        score_multiplier: float = 1,
        dtype: npt.DTypeLike | None = None,
        workers: int = 1,
        scorer_kwargs: dict[str, Any] | None = None,
    ) -> npt.NDArray[Any]: ...
    @overload
    def cdist(
        queries: Iterable[_UnprocessedType1 | None],
        choices: Iterable[_UnprocessedType2 | None],
        *,
        scorer: _Scorer[Sequence[Hashable], Sequence[Hashable], float, float] = ratio,
        processor: Callable[[_UnprocessedType1 | _UnprocessedType2], Sequence[Hashable]],
        score_cutoff: float | None = None,
        score_hint: float | None = None,
        score_multiplier: float = 1,
        dtype: npt.DTypeLike | None = None,
        workers: int = 1,
        scorer_kwargs: dict[str, Any] | None = None,
    ) -> npt.NDArray[Any]: ...
    @overload
    def cdist(
        queries: Iterable[_StringType1 | None],
        choices: Iterable[_StringType2 | None],
        *,
        scorer: _Scorer[_StringType1, _StringType2, _ResultType, _ResultType],
        processor: None = None,
        score_cutoff: _ResultType | None = None,
        score_hint: _ResultType | None = None,
        score_multiplier: _ResultType = 1,
        dtype: npt.DTypeLike | None = None,
        workers: int = 1,
        scorer_kwargs: dict[str, Any] | None = None,
    ) -> npt.NDArray[Any]: ...
    @overload
    def cdist(
        queries: Iterable[_UnprocessedType1 | None],
        choices: Iterable[_UnprocessedType2 | None],
        *,
        scorer: _Scorer[_StringType1, _StringType1, _ResultType, _ResultType],
        processor: Callable[[_UnprocessedType1 | _UnprocessedType2], _StringType1],
        score_cutoff: _ResultType | None = None,
        score_hint: _ResultType | None = None,
        score_multiplier: _ResultType = 1,
        dtype: npt.DTypeLike | None = None,
        workers: int = 1,
        scorer_kwargs: dict[str, Any] | None = None,
    ) -> npt.NDArray[Any]: ...
    @overload
    def cpdist(
        queries: Iterable[Sequence[Hashable] | None],
        choices: Iterable[Sequence[Hashable] | None],
        *,
        scorer: _Scorer[Sequence[Hashable], Sequence[Hashable], float, float] = ratio,
        processor: None = None,
        score_cutoff: float | None = None,
        score_hint: float | None = None,
        score_multiplier: float = 1,
        dtype: npt.DTypeLike | None = None,
        workers: int = 1,
        scorer_kwargs: dict[str, Any] | None = None,
    ) -> npt.NDArray[Any]: ...
    @overload
    def cpdist(
        queries: Iterable[_UnprocessedType1 | None],
        choices: Iterable[_UnprocessedType2 | None],
        *,
        scorer: _Scorer[Sequence[Hashable], Sequence[Hashable], float, float] = ratio,
        processor: Callable[[_UnprocessedType1 | _UnprocessedType2], Sequence[Hashable]],
        score_cutoff: float | None = None,
        score_hint: float | None = None,
        score_multiplier: float = 1,
        dtype: npt.DTypeLike | None = None,
        workers: int = 1,
        scorer_kwargs: dict[str, Any] | None = None,
    ) -> npt.NDArray[Any]: ...
    @overload
    def cpdist(
        queries: Iterable[_StringType1 | None],
        choices: Iterable[_StringType2 | None],
        *,
        scorer: _Scorer[_StringType1, _StringType2, _ResultType, _ResultType],
        processor: None = None,
        score_cutoff: _ResultType | None = None,
        score_hint: _ResultType | None = None,
        score_multiplier: _ResultType = 1,
        dtype: npt.DTypeLike | None = None,
        workers: int = 1,
        scorer_kwargs: dict[str, Any] | None = None,
    ) -> npt.NDArray[Any]: ...
    @overload
    def cpdist(
        queries: Iterable[_UnprocessedType1 | None],
        choices: Iterable[_UnprocessedType2 | None],
        *,
        scorer: _Scorer[_StringType1, _StringType1, _ResultType, _ResultType],
        processor: Callable[[_UnprocessedType1 | _UnprocessedType2], _StringType1],
        score_cutoff: _ResultType | None = None,
        score_hint: _ResultType | None = None,
        score_multiplier: _ResultType = 1,
        dtype: npt.DTypeLike | None = None,
        workers: int = 1,
        scorer_kwargs: dict[str, Any] | None = None,
    ) -> npt.NDArray[Any]: ...

except ImportError:
    pass
