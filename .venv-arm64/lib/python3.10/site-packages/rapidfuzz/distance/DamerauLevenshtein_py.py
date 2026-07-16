# SPDX-License-Identifier: MIT
# Copyright (C) 2022 Max Bachmann
from __future__ import annotations

from rapidfuzz._common_py import conv_sequences
from rapidfuzz._utils import is_none, setupPandas


def _damerau_levenshtein_distance_zhao(s1, s2):
    maxVal = max(len(s1), len(s2)) + 1
    last_row_id = {}
    last_row_id_get = last_row_id.get
    size = len(s2) + 2
    FR = [maxVal] * size
    R1 = [maxVal] * size
    R = list(range(size))
    R[-1] = maxVal

    for i in range(1, len(s1) + 1):
        R, R1 = R1, R
        last_col_id = -1
        last_i2l1 = R[0]
        R[0] = i
        T = maxVal

        for j in range(1, len(s2) + 1):
            diag = R1[j - 1] + (s1[i - 1] != s2[j - 1])
            left = R[j - 1] + 1
            up = R1[j] + 1
            temp = min(diag, left, up)

            if s1[i - 1] == s2[j - 1]:
                last_col_id = j  # last occurrence of s1_i
                FR[j] = R1[j - 2]  # save H_k-1,j-2
                T = last_i2l1  # save H_i-2,l-1
            else:
                k = last_row_id_get(s2[j - 1], -1)
                l = last_col_id  # noqa:  E741

                if (j - l) == 1:
                    transpose = FR[j] + (i - k)
                    temp = min(temp, transpose)
                elif (i - k) == 1:
                    transpose = T + (j - l)
                    temp = min(temp, transpose)

            last_i2l1 = R[j]
            R[j] = temp

        last_row_id[s1[i - 1]] = i

    return R[len(s2)]


def distance(
    s1,
    s2,
    *,
    processor=None,
    score_cutoff=None,
):
    """
    Calculates the Damerau-Levenshtein distance.

    Parameters
    ----------
    s1 : Sequence[Hashable]
        First string to compare.
    s2 : Sequence[Hashable]
        Second string to compare.
    processor: callable, optional
        Optional callable that is used to preprocess the strings before
        comparing them. Default is None, which deactivates this behaviour.
    score_cutoff : int, optional
        Maximum distance between s1 and s2, that is
        considered as a result. If the distance is bigger than score_cutoff,
        score_cutoff + 1 is returned instead. Default is None, which deactivates
        this behaviour.

    Returns
    -------
    distance : int
        distance between s1 and s2

    Examples
    --------
    Find the Damerau-Levenshtein distance between two strings:

    >>> from rapidfuzz.distance import DamerauLevenshtein
    >>> DamerauLevenshtein.distance("CA", "ABC")
    2
    """
    if processor is not None:
        s1 = processor(s1)
        s2 = processor(s2)

    s1, s2 = conv_sequences(s1, s2)
    dist = _damerau_levenshtein_distance_zhao(s1, s2)
    return dist if (score_cutoff is None or dist <= score_cutoff) else score_cutoff + 1


def similarity(
    s1,
    s2,
    *,
    processor=None,
    score_cutoff=None,
):
    """
    Calculates the Damerau-Levenshtein similarity in the range [max, 0].

    This is calculated as ``max(len1, len2) - distance``.

    Parameters
    ----------
    s1 : Sequence[Hashable]
        First string to compare.
    s2 : Sequence[Hashable]
        Second string to compare.
    processor: callable, optional
        Optional callable that is used to preprocess the strings before
        comparing them. Default is None, which deactivates this behaviour.
    score_cutoff : int, optional
        Maximum distance between s1 and s2, that is
        considered as a result. If the similarity is smaller than score_cutoff,
        0 is returned instead. Default is None, which deactivates
        this behaviour.

    Returns
    -------
    similarity : int
        similarity between s1 and s2
    """
    if processor is not None:
        s1 = processor(s1)
        s2 = processor(s2)

    s1, s2 = conv_sequences(s1, s2)
    maximum = max(len(s1), len(s2))
    dist = distance(s1, s2)
    sim = maximum - dist
    return sim if (score_cutoff is None or sim >= score_cutoff) else 0


def normalized_distance(
    s1,
    s2,
    *,
    processor=None,
    score_cutoff=None,
):
    """
    Calculates a normalized Damerau-Levenshtein distance in the range [1, 0].

    This is calculated as ``distance / max(len1, len2)``.

    Parameters
    ----------
    s1 : Sequence[Hashable]
        First string to compare.
    s2 : Sequence[Hashable]
        Second string to compare.
    processor: callable, optional
        Optional callable that is used to preprocess the strings before
        comparing them. Default is None, which deactivates this behaviour.
    score_cutoff : float, optional
        Optional argument for a score threshold as a float between 0 and 1.0.
        For norm_dist > score_cutoff 1.0 is returned instead. Default is 1.0,
        which deactivates this behaviour.

    Returns
    -------
    norm_dist : float
        normalized distance between s1 and s2 as a float between 0 and 1.0
    """
    setupPandas()
    if is_none(s1) or is_none(s2):
        return 1.0

    if processor is not None:
        s1 = processor(s1)
        s2 = processor(s2)

    s1, s2 = conv_sequences(s1, s2)
    maximum = max(len(s1), len(s2))
    dist = distance(s1, s2)
    norm_dist = dist / maximum if maximum else 0
    return norm_dist if (score_cutoff is None or norm_dist <= score_cutoff) else 1


def normalized_similarity(
    s1,
    s2,
    *,
    processor=None,
    score_cutoff=None,
):
    """
    Calculates a normalized Damerau-Levenshtein similarity in the range [0, 1].

    This is calculated as ``1 - normalized_distance``

    Parameters
    ----------
    s1 : Sequence[Hashable]
        First string to compare.
    s2 : Sequence[Hashable]
        Second string to compare.
    processor: callable, optional
        Optional callable that is used to preprocess the strings before
        comparing them. Default is None, which deactivates this behaviour.
    score_cutoff : float, optional
        Optional argument for a score threshold as a float between 0 and 1.0.
        For norm_sim < score_cutoff 0 is returned instead. Default is 0,
        which deactivates this behaviour.

    Returns
    -------
    norm_sim : float
        normalized similarity between s1 and s2 as a float between 0 and 1.0
    """
    setupPandas()
    if is_none(s1) or is_none(s2):
        return 0.0

    if processor is not None:
        s1 = processor(s1)
        s2 = processor(s2)

    s1, s2 = conv_sequences(s1, s2)
    norm_dist = normalized_distance(s1, s2)
    norm_sim = 1.0 - norm_dist
    return norm_sim if (score_cutoff is None or norm_sim >= score_cutoff) else 0
