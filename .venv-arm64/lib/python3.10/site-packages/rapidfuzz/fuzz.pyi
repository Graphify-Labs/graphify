# SPDX-License-Identifier: MIT
# Copyright (C) 2021 Max Bachmann

from __future__ import annotations

from collections.abc import Hashable, Sequence
from typing import Callable, TypeVar, overload

from rapidfuzz.distance import ScoreAlignment

_UnprocessedType1 = TypeVar("_UnprocessedType1")
_UnprocessedType2 = TypeVar("_UnprocessedType2")

@overload
def ratio(
    s1: Sequence[Hashable],
    s2: Sequence[Hashable],
    *,
    processor: None = None,
    score_cutoff: float | None = 0,
) -> float: ...
@overload
def ratio(
    s1: _UnprocessedType1,
    s2: _UnprocessedType2,
    *,
    processor: Callable[[_UnprocessedType1 | _UnprocessedType2], Sequence[Hashable]],
    score_cutoff: float | None = 0,
) -> float: ...
@overload
def partial_ratio(
    s1: Sequence[Hashable],
    s2: Sequence[Hashable],
    *,
    processor: None = None,
    score_cutoff: float | None = 0,
) -> float: ...
@overload
def partial_ratio(
    s1: _UnprocessedType1,
    s2: _UnprocessedType2,
    *,
    processor: Callable[[_UnprocessedType1 | _UnprocessedType2], Sequence[Hashable]],
    score_cutoff: float | None = 0,
) -> float: ...
@overload
def partial_ratio_alignment(
    s1: Sequence[Hashable],
    s2: Sequence[Hashable],
    *,
    processor: None = None,
    score_cutoff: float | None = 0,
) -> ScoreAlignment | None: ...
@overload
def partial_ratio_alignment(
    s1: _UnprocessedType1,
    s2: _UnprocessedType2,
    *,
    processor: Callable[[_UnprocessedType1 | _UnprocessedType2], Sequence[Hashable]],
    score_cutoff: float | None = 0,
) -> ScoreAlignment | None: ...
@overload
def token_sort_ratio(
    s1: Sequence[Hashable],
    s2: Sequence[Hashable],
    *,
    processor: None = None,
    score_cutoff: float | None = 0,
) -> float: ...
@overload
def token_sort_ratio(
    s1: _UnprocessedType1,
    s2: _UnprocessedType2,
    *,
    processor: Callable[[_UnprocessedType1 | _UnprocessedType2], Sequence[Hashable]],
    score_cutoff: float | None = 0,
) -> float: ...
@overload
def token_set_ratio(
    s1: Sequence[Hashable],
    s2: Sequence[Hashable],
    *,
    processor: None = None,
    score_cutoff: float | None = 0,
) -> float: ...
@overload
def token_set_ratio(
    s1: _UnprocessedType1,
    s2: _UnprocessedType2,
    *,
    processor: Callable[[_UnprocessedType1 | _UnprocessedType2], Sequence[Hashable]],
    score_cutoff: float | None = 0,
) -> float: ...
@overload
def token_ratio(
    s1: Sequence[Hashable],
    s2: Sequence[Hashable],
    *,
    processor: None = None,
    score_cutoff: float | None = 0,
) -> float: ...
@overload
def token_ratio(
    s1: _UnprocessedType1,
    s2: _UnprocessedType2,
    *,
    processor: Callable[[_UnprocessedType1 | _UnprocessedType2], Sequence[Hashable]],
    score_cutoff: float | None = 0,
) -> float: ...
@overload
def partial_token_sort_ratio(
    s1: Sequence[Hashable],
    s2: Sequence[Hashable],
    *,
    processor: None = None,
    score_cutoff: float | None = 0,
) -> float: ...
@overload
def partial_token_sort_ratio(
    s1: _UnprocessedType1,
    s2: _UnprocessedType2,
    *,
    processor: Callable[[_UnprocessedType1 | _UnprocessedType2], Sequence[Hashable]],
    score_cutoff: float | None = 0,
) -> float: ...
@overload
def partial_token_set_ratio(
    s1: Sequence[Hashable],
    s2: Sequence[Hashable],
    *,
    processor: None = None,
    score_cutoff: float | None = 0,
) -> float: ...
@overload
def partial_token_set_ratio(
    s1: _UnprocessedType1,
    s2: _UnprocessedType2,
    *,
    processor: Callable[[_UnprocessedType1 | _UnprocessedType2], Sequence[Hashable]],
    score_cutoff: float | None = 0,
) -> float: ...
@overload
def partial_token_ratio(
    s1: Sequence[Hashable],
    s2: Sequence[Hashable],
    *,
    processor: None = None,
    score_cutoff: float | None = 0,
) -> float: ...
@overload
def partial_token_ratio(
    s1: _UnprocessedType1,
    s2: _UnprocessedType2,
    *,
    processor: Callable[[_UnprocessedType1 | _UnprocessedType2], Sequence[Hashable]],
    score_cutoff: float | None = 0,
) -> float: ...
@overload
def WRatio(
    s1: Sequence[Hashable],
    s2: Sequence[Hashable],
    *,
    processor: None = None,
    score_cutoff: float | None = 0,
) -> float: ...
@overload
def WRatio(
    s1: _UnprocessedType1,
    s2: _UnprocessedType2,
    *,
    processor: Callable[[_UnprocessedType1 | _UnprocessedType2], Sequence[Hashable]],
    score_cutoff: float | None = 0,
) -> float: ...
@overload
def QRatio(
    s1: Sequence[Hashable],
    s2: Sequence[Hashable],
    *,
    processor: None = None,
    score_cutoff: float | None = 0,
) -> float: ...
@overload
def QRatio(
    s1: _UnprocessedType1,
    s2: _UnprocessedType2,
    *,
    processor: Callable[[_UnprocessedType1 | _UnprocessedType2], Sequence[Hashable]],
    score_cutoff: float | None = 0,
) -> float: ...
