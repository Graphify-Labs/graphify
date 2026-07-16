# SPDX-License-Identifier: MIT
# Copyright (C) 2022 Max Bachmann

from __future__ import annotations

import sys
from math import isnan
from typing import Any, Callable

pandas_NA = None


def setupPandas():
    global pandas_NA  # noqa: PLW0603
    if pandas_NA is None:
        pandas = sys.modules.get("pandas")
        if hasattr(pandas, "NA"):
            pandas_NA = pandas.NA


setupPandas()


class ScorerFlag:
    RESULT_F64 = 1 << 5
    RESULT_I64 = 1 << 6
    RESULT_SIZE_T = 1 << 7
    SYMMETRIC = 1 << 11


def _get_scorer_flags_distance(**_kwargs: Any) -> dict[str, Any]:
    return {
        "optimal_score": 0,
        "worst_score": 2**63 - 1,
        "flags": ScorerFlag.RESULT_SIZE_T | ScorerFlag.SYMMETRIC,
    }


def _get_scorer_flags_similarity(**_kwargs: Any) -> dict[str, Any]:
    return {
        "optimal_score": 2**63 - 1,
        "worst_score": 0,
        "flags": ScorerFlag.RESULT_SIZE_T | ScorerFlag.SYMMETRIC,
    }


def _get_scorer_flags_normalized_distance(**_kwargs: Any) -> dict[str, Any]:
    return {
        "optimal_score": 0,
        "worst_score": 1,
        "flags": ScorerFlag.RESULT_F64 | ScorerFlag.SYMMETRIC,
    }


def _get_scorer_flags_normalized_similarity(**_kwargs: Any) -> dict[str, Any]:
    return {
        "optimal_score": 1,
        "worst_score": 0,
        "flags": ScorerFlag.RESULT_F64 | ScorerFlag.SYMMETRIC,
    }


def is_none(s: Any) -> bool:
    if s is None or s is pandas_NA:
        return True

    return isinstance(s, float) and isnan(s)


def add_scorer_attrs(func: Any, cached_scorer_call: dict[str, Callable[..., dict[str, Any]]]):
    func._RF_ScorerPy = cached_scorer_call
    # used to detect the function hasn't been wrapped afterwards
    func._RF_OriginalScorer = func


default_distance_attribute: dict[str, Callable[..., dict[str, Any]]] = {"get_scorer_flags": _get_scorer_flags_distance}
default_similarity_attribute: dict[str, Callable[..., dict[str, Any]]] = {
    "get_scorer_flags": _get_scorer_flags_similarity
}
default_normalized_distance_attribute: dict[str, Callable[..., dict[str, Any]]] = {
    "get_scorer_flags": _get_scorer_flags_normalized_distance
}
default_normalized_similarity_attribute: dict[str, Callable[..., dict[str, Any]]] = {
    "get_scorer_flags": _get_scorer_flags_normalized_similarity
}
