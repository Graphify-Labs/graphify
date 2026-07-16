# SPDX-License-Identifier: MIT
# Copyright (C) 2022 Max Bachmann
"""
The Levenshtein (edit) distance is a string metric to measure the
difference between two strings/sequences s1 and s2.
It's defined as the minimum number of insertions, deletions or
substitutions required to transform s1 into s2.
"""

from __future__ import annotations

from collections.abc import Hashable, Sequence
from typing import Callable, TypeVar, overload

from rapidfuzz.distance import Editops, Opcodes

_UnprocessedType1 = TypeVar("_UnprocessedType1")
_UnprocessedType2 = TypeVar("_UnprocessedType2")

@overload
def distance(
    s1: Sequence[Hashable],
    s2: Sequence[Hashable],
    *,
    weights: tuple[int, int, int] | None = (1, 1, 1),
    processor: None = None,
    score_cutoff: int | None = None,
    score_hint: int | None = None,
) -> int: ...
@overload
def distance(
    s1: _UnprocessedType1,
    s2: _UnprocessedType2,
    *,
    weights: tuple[int, int, int] | None = (1, 1, 1),
    processor: Callable[[_UnprocessedType1 | _UnprocessedType2], Sequence[Hashable]],
    score_cutoff: int | None = None,
    score_hint: int | None = None,
) -> int: ...
@overload
def normalized_distance(
    s1: Sequence[Hashable],
    s2: Sequence[Hashable],
    *,
    weights: tuple[int, int, int] | None = (1, 1, 1),
    processor: None = None,
    score_cutoff: float | None = 0,
    score_hint: float | None = 0,
) -> float: ...
@overload
def normalized_distance(
    s1: _UnprocessedType1,
    s2: _UnprocessedType2,
    *,
    weights: tuple[int, int, int] | None = (1, 1, 1),
    processor: Callable[[_UnprocessedType1 | _UnprocessedType2], Sequence[Hashable]],
    score_cutoff: float | None = 0,
    score_hint: float | None = 0,
) -> float: ...
@overload
def similarity(
    s1: Sequence[Hashable],
    s2: Sequence[Hashable],
    *,
    weights: tuple[int, int, int] | None = (1, 1, 1),
    processor: None = None,
    score_cutoff: int | None = None,
    score_hint: int | None = None,
) -> int: ...
@overload
def similarity(
    s1: _UnprocessedType1,
    s2: _UnprocessedType2,
    *,
    weights: tuple[int, int, int] | None = (1, 1, 1),
    processor: Callable[[_UnprocessedType1 | _UnprocessedType2], Sequence[Hashable]],
    score_cutoff: int | None = None,
    score_hint: int | None = None,
) -> int: ...
@overload
def normalized_similarity(
    s1: Sequence[Hashable],
    s2: Sequence[Hashable],
    *,
    weights: tuple[int, int, int] | None = (1, 1, 1),
    processor: None = None,
    score_cutoff: float | None = 0,
    score_hint: float | None = 0,
) -> float: ...
@overload
def normalized_similarity(
    s1: _UnprocessedType1,
    s2: _UnprocessedType2,
    *,
    weights: tuple[int, int, int] | None = (1, 1, 1),
    processor: Callable[[_UnprocessedType1 | _UnprocessedType2], Sequence[Hashable]],
    score_cutoff: float | None = 0,
    score_hint: float | None = 0,
) -> float: ...
@overload
def editops(
    s1: Sequence[Hashable],
    s2: Sequence[Hashable],
    *,
    processor: None = None,
    score_hint: int | None = None,
) -> Editops: ...
@overload
def editops(
    s1: _UnprocessedType1,
    s2: _UnprocessedType2,
    *,
    processor: Callable[[_UnprocessedType1 | _UnprocessedType2], Sequence[Hashable]],
    score_hint: int | None = None,
) -> Editops: ...
@overload
def opcodes(
    s1: Sequence[Hashable],
    s2: Sequence[Hashable],
    *,
    processor: None = None,
    score_hint: int | None = None,
) -> Opcodes: ...
@overload
def opcodes(
    s1: _UnprocessedType1,
    s2: _UnprocessedType2,
    *,
    processor: Callable[[_UnprocessedType1 | _UnprocessedType2], Sequence[Hashable]],
    score_hint: int | None = None,
) -> Opcodes: ...
