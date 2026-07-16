# SPDX-License-Identifier: MIT
# Copyright (C) 2022 Max Bachmann

from __future__ import annotations

from collections.abc import Hashable, Sequence
from typing import Callable, TypeVar, overload

_UnprocessedType1 = TypeVar("_UnprocessedType1")
_UnprocessedType2 = TypeVar("_UnprocessedType2")

@overload
def distance(
    s1: Sequence[Hashable],
    s2: Sequence[Hashable],
    *,
    processor: None = None,
    score_cutoff: int | None = None,
) -> int: ...
@overload
def distance(
    s1: _UnprocessedType1,
    s2: _UnprocessedType2,
    *,
    processor: Callable[[_UnprocessedType1 | _UnprocessedType2], Sequence[Hashable]],
    score_cutoff: int | None = None,
) -> int: ...
@overload
def normalized_distance(
    s1: Sequence[Hashable],
    s2: Sequence[Hashable],
    *,
    processor: None = None,
    score_cutoff: float | None = 0,
) -> float: ...
@overload
def normalized_distance(
    s1: _UnprocessedType1,
    s2: _UnprocessedType2,
    *,
    processor: Callable[[_UnprocessedType1 | _UnprocessedType2], Sequence[Hashable]],
    score_cutoff: float | None = 0,
) -> float: ...
@overload
def similarity(
    s1: Sequence[Hashable],
    s2: Sequence[Hashable],
    *,
    processor: None = None,
    score_cutoff: int | None = None,
) -> int: ...
@overload
def similarity(
    s1: _UnprocessedType1,
    s2: _UnprocessedType2,
    *,
    processor: Callable[[_UnprocessedType1 | _UnprocessedType2], Sequence[Hashable]],
    score_cutoff: int | None = None,
) -> int: ...
@overload
def normalized_similarity(
    s1: Sequence[Hashable],
    s2: Sequence[Hashable],
    *,
    processor: None = None,
    score_cutoff: float | None = 0,
) -> float: ...
@overload
def normalized_similarity(
    s1: _UnprocessedType1,
    s2: _UnprocessedType2,
    *,
    processor: Callable[[_UnprocessedType1 | _UnprocessedType2], Sequence[Hashable]],
    score_cutoff: float | None = 0,
) -> float: ...
