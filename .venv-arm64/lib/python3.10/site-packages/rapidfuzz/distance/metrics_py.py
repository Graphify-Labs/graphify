# SPDX-License-Identifier: MIT
# Copyright (C) 2022 Max Bachmann

from __future__ import annotations

from typing import Any, Callable

from rapidfuzz._utils import (
    ScorerFlag,
    add_scorer_attrs,
    default_distance_attribute as dist_attr,
    default_normalized_distance_attribute as norm_dist_attr,
    default_normalized_similarity_attribute as norm_sim_attr,
    default_similarity_attribute as sim_attr,
)

# DamerauLevenshtein
from rapidfuzz.distance.DamerauLevenshtein_py import (
    distance as damerau_levenshtein_distance,
    normalized_distance as damerau_levenshtein_normalized_distance,
    normalized_similarity as damerau_levenshtein_normalized_similarity,
    similarity as damerau_levenshtein_similarity,
)

# Hamming
from rapidfuzz.distance.Hamming_py import (
    distance as hamming_distance,
    editops as hamming_editops,
    normalized_distance as hamming_normalized_distance,
    normalized_similarity as hamming_normalized_similarity,
    opcodes as hamming_opcodes,
    similarity as hamming_similarity,
)

# Indel
from rapidfuzz.distance.Indel_py import (
    distance as indel_distance,
    editops as indel_editops,
    normalized_distance as indel_normalized_distance,
    normalized_similarity as indel_normalized_similarity,
    opcodes as indel_opcodes,
    similarity as indel_similarity,
)

# Jaro
from rapidfuzz.distance.Jaro_py import (
    distance as jaro_distance,
    normalized_distance as jaro_normalized_distance,
    normalized_similarity as jaro_normalized_similarity,
    similarity as jaro_similarity,
)

# JaroWinkler
from rapidfuzz.distance.JaroWinkler_py import (
    distance as jaro_winkler_distance,
    normalized_distance as jaro_winkler_normalized_distance,
    normalized_similarity as jaro_winkler_normalized_similarity,
    similarity as jaro_winkler_similarity,
)

# LCSseq
from rapidfuzz.distance.LCSseq_py import (
    distance as lcs_seq_distance,
    editops as lcs_seq_editops,
    normalized_distance as lcs_seq_normalized_distance,
    normalized_similarity as lcs_seq_normalized_similarity,
    opcodes as lcs_seq_opcodes,
    similarity as lcs_seq_similarity,
)

# Levenshtein
from rapidfuzz.distance.Levenshtein_py import (
    distance as levenshtein_distance,
    editops as levenshtein_editops,
    normalized_distance as levenshtein_normalized_distance,
    normalized_similarity as levenshtein_normalized_similarity,
    opcodes as levenshtein_opcodes,
    similarity as levenshtein_similarity,
)

# OSA
from rapidfuzz.distance.OSA_py import (
    distance as osa_distance,
    normalized_distance as osa_normalized_distance,
    normalized_similarity as osa_normalized_similarity,
    similarity as osa_similarity,
)

# Postfix
from rapidfuzz.distance.Postfix_py import (
    distance as postfix_distance,
    normalized_distance as postfix_normalized_distance,
    normalized_similarity as postfix_normalized_similarity,
    similarity as postfix_similarity,
)

# Prefix
from rapidfuzz.distance.Prefix_py import (
    distance as prefix_distance,
    normalized_distance as prefix_normalized_distance,
    normalized_similarity as prefix_normalized_similarity,
    similarity as prefix_similarity,
)

__all__ = []

add_scorer_attrs(osa_distance, dist_attr)
add_scorer_attrs(osa_similarity, sim_attr)
add_scorer_attrs(osa_normalized_distance, norm_dist_attr)
add_scorer_attrs(osa_normalized_similarity, norm_sim_attr)

__all__ += [
    "osa_distance",
    "osa_normalized_distance",
    "osa_normalized_similarity",
    "osa_similarity",
]


add_scorer_attrs(prefix_distance, dist_attr)
add_scorer_attrs(prefix_similarity, sim_attr)
add_scorer_attrs(prefix_normalized_distance, norm_dist_attr)
add_scorer_attrs(prefix_normalized_similarity, norm_sim_attr)

__all__ += [
    "prefix_distance",
    "prefix_normalized_distance",
    "prefix_normalized_similarity",
    "prefix_similarity",
]


add_scorer_attrs(postfix_distance, dist_attr)
add_scorer_attrs(postfix_similarity, sim_attr)
add_scorer_attrs(postfix_normalized_distance, norm_dist_attr)
add_scorer_attrs(postfix_normalized_similarity, norm_sim_attr)

__all__ += [
    "postfix_distance",
    "postfix_normalized_distance",
    "postfix_normalized_similarity",
    "postfix_similarity",
]


add_scorer_attrs(jaro_distance, norm_dist_attr)
add_scorer_attrs(jaro_similarity, norm_sim_attr)
add_scorer_attrs(jaro_normalized_distance, norm_dist_attr)
add_scorer_attrs(jaro_normalized_similarity, norm_sim_attr)

__all__ += [
    "jaro_distance",
    "jaro_normalized_distance",
    "jaro_normalized_similarity",
    "jaro_similarity",
]


add_scorer_attrs(jaro_winkler_distance, norm_dist_attr)
add_scorer_attrs(jaro_winkler_similarity, norm_sim_attr)
add_scorer_attrs(jaro_winkler_normalized_distance, norm_dist_attr)
add_scorer_attrs(jaro_winkler_normalized_similarity, norm_sim_attr)

__all__ += [
    "jaro_winkler_distance",
    "jaro_winkler_normalized_distance",
    "jaro_winkler_normalized_similarity",
    "jaro_winkler_similarity",
]


add_scorer_attrs(damerau_levenshtein_distance, dist_attr)
add_scorer_attrs(damerau_levenshtein_similarity, sim_attr)
add_scorer_attrs(damerau_levenshtein_normalized_distance, norm_dist_attr)
add_scorer_attrs(damerau_levenshtein_normalized_similarity, norm_sim_attr)

__all__ += [
    "damerau_levenshtein_distance",
    "damerau_levenshtein_normalized_distance",
    "damerau_levenshtein_normalized_similarity",
    "damerau_levenshtein_similarity",
]


def _get_scorer_flags_levenshtein_distance(weights: tuple[int, int, int] | None = (1, 1, 1)) -> dict[str, Any]:
    flags = ScorerFlag.RESULT_SIZE_T
    if weights is None or weights[0] == weights[1]:
        flags |= ScorerFlag.SYMMETRIC

    return {
        "optimal_score": 0,
        "worst_score": 2**63 - 1,
        "flags": flags,
    }


def _get_scorer_flags_levenshtein_similarity(weights: tuple[int, int, int] | None = (1, 1, 1)) -> dict[str, Any]:
    flags = ScorerFlag.RESULT_SIZE_T
    if weights is None or weights[0] == weights[1]:
        flags |= ScorerFlag.SYMMETRIC

    return {
        "optimal_score": 2**63 - 1,
        "worst_score": 0,
        "flags": flags,
    }


def _get_scorer_flags_levenshtein_normalized_distance(
    weights: tuple[int, int, int] | None = (1, 1, 1)
) -> dict[str, Any]:
    flags = ScorerFlag.RESULT_F64
    if weights is None or weights[0] == weights[1]:
        flags |= ScorerFlag.SYMMETRIC

    return {"optimal_score": 0, "worst_score": 1, "flags": flags}


def _get_scorer_flags_levenshtein_normalized_similarity(
    weights: tuple[int, int, int] | None = (1, 1, 1)
) -> dict[str, Any]:
    flags = ScorerFlag.RESULT_F64
    if weights is None or weights[0] == weights[1]:
        flags |= ScorerFlag.SYMMETRIC

    return {"optimal_score": 1, "worst_score": 0, "flags": flags}


levenshtein_dist_attr: dict[str, Callable[..., dict[str, Any]]] = {
    "get_scorer_flags": _get_scorer_flags_levenshtein_distance
}
levenshtein_sim_attr: dict[str, Callable[..., dict[str, Any]]] = {
    "get_scorer_flags": _get_scorer_flags_levenshtein_similarity
}
levenshtein_norm_dist_attr: dict[str, Callable[..., dict[str, Any]]] = {
    "get_scorer_flags": _get_scorer_flags_levenshtein_normalized_distance
}
levenshtein_norm_sim_attr: dict[str, Callable[..., dict[str, Any]]] = {
    "get_scorer_flags": _get_scorer_flags_levenshtein_normalized_similarity
}

add_scorer_attrs(levenshtein_distance, levenshtein_dist_attr)
add_scorer_attrs(levenshtein_similarity, levenshtein_sim_attr)
add_scorer_attrs(levenshtein_normalized_distance, levenshtein_norm_dist_attr)
add_scorer_attrs(levenshtein_normalized_similarity, levenshtein_norm_sim_attr)

__all__ += [
    "levenshtein_distance",
    "levenshtein_editops",
    "levenshtein_normalized_distance",
    "levenshtein_normalized_similarity",
    "levenshtein_opcodes",
    "levenshtein_similarity",
]


add_scorer_attrs(lcs_seq_distance, dist_attr)
add_scorer_attrs(lcs_seq_similarity, sim_attr)
add_scorer_attrs(lcs_seq_normalized_distance, norm_dist_attr)
add_scorer_attrs(lcs_seq_normalized_similarity, norm_sim_attr)

__all__ += [
    "lcs_seq_distance",
    "lcs_seq_editops",
    "lcs_seq_normalized_distance",
    "lcs_seq_normalized_similarity",
    "lcs_seq_opcodes",
    "lcs_seq_similarity",
]


add_scorer_attrs(indel_distance, dist_attr)
add_scorer_attrs(indel_similarity, sim_attr)
add_scorer_attrs(indel_normalized_distance, norm_dist_attr)
add_scorer_attrs(indel_normalized_similarity, norm_sim_attr)

__all__ += [
    "indel_distance",
    "indel_editops",
    "indel_normalized_distance",
    "indel_normalized_similarity",
    "indel_opcodes",
    "indel_similarity",
]


add_scorer_attrs(hamming_distance, dist_attr)
add_scorer_attrs(hamming_similarity, sim_attr)
add_scorer_attrs(hamming_normalized_distance, norm_dist_attr)
add_scorer_attrs(hamming_normalized_similarity, norm_sim_attr)

__all__ += [
    "hamming_distance",
    "hamming_editops",
    "hamming_normalized_distance",
    "hamming_normalized_similarity",
    "hamming_opcodes",
    "hamming_similarity",
]
