# SPDX-License-Identifier: MIT
# Copyright (C) 2022 Max Bachmann
from __future__ import annotations

from rapidfuzz._common_py import conv_sequences
from rapidfuzz._utils import is_none, setupPandas
from rapidfuzz.distance import Jaro_py as Jaro


def similarity(
    s1,
    s2,
    *,
    prefix_weight=0.1,
    processor=None,
    score_cutoff=None,
):
    """
    Calculates the jaro winkler similarity

    Parameters
    ----------
    s1 : Sequence[Hashable]
        First string to compare.
    s2 : Sequence[Hashable]
        Second string to compare.
    prefix_weight : float, optional
        Weight used for the common prefix of the two strings.
        Has to be between 0 and 0.25. Default is 0.1.
    processor: callable, optional
        Optional callable that is used to preprocess the strings before
        comparing them. Default is None, which deactivates this behaviour.
    score_cutoff : float, optional
        Optional argument for a score threshold as a float between 0 and 1.0.
        For ratio < score_cutoff 0 is returned instead. Default is None,
        which deactivates this behaviour.

    Returns
    -------
    similarity : float
        similarity between s1 and s2 as a float between 0 and 1.0

    Raises
    ------
    ValueError
        If prefix_weight is invalid
    """
    setupPandas()
    if is_none(s1) or is_none(s2):
        return 0.0

    if processor is not None:
        s1 = processor(s1)
        s2 = processor(s2)

    if score_cutoff is None:
        score_cutoff = 0

    if prefix_weight > 1.0 or prefix_weight < 0.0:
        msg = "prefix_weight has to be in the range 0.0 - 1.0"
        raise ValueError(msg)

    s1, s2 = conv_sequences(s1, s2)
    P_len = len(s1)
    T_len = len(s2)
    min_len = min(P_len, T_len)
    prefix = 0
    max_prefix = min(min_len, 4)

    for _ in range(max_prefix):
        if s1[prefix] != s2[prefix]:
            break
        prefix += 1

    jaro_score_cutoff = score_cutoff
    if jaro_score_cutoff > 0.7:
        prefix_sim = prefix * prefix_weight

        if prefix_sim >= 1.0:
            jaro_score_cutoff = 0.7
        else:
            jaro_score_cutoff = max(0.7, (prefix_sim - jaro_score_cutoff) / (prefix_sim - 1.0))

    Sim = Jaro.similarity(s1, s2, score_cutoff=jaro_score_cutoff)
    if Sim > 0.7:
        Sim += prefix * prefix_weight * (1.0 - Sim)
        Sim = min(Sim, 1.0)

    return Sim if Sim >= score_cutoff else 0


def normalized_similarity(
    s1,
    s2,
    *,
    prefix_weight=0.1,
    processor=None,
    score_cutoff=None,
):
    """
    Calculates the normalized jaro winkler similarity

    Parameters
    ----------
    s1 : Sequence[Hashable]
        First string to compare.
    s2 : Sequence[Hashable]
        Second string to compare.
    prefix_weight : float, optional
        Weight used for the common prefix of the two strings.
        Has to be between 0 and 0.25. Default is 0.1.
    processor: callable, optional
        Optional callable that is used to preprocess the strings before
        comparing them. Default is None, which deactivates this behaviour.
    score_cutoff : float, optional
        Optional argument for a score threshold as a float between 0 and 1.0.
        For ratio < score_cutoff 0 is returned instead. Default is None,
        which deactivates this behaviour.

    Returns
    -------
    normalized similarity : float
        normalized similarity between s1 and s2 as a float between 0 and 1.0

    Raises
    ------
    ValueError
        If prefix_weight is invalid
    """
    return similarity(
        s1,
        s2,
        prefix_weight=prefix_weight,
        processor=processor,
        score_cutoff=score_cutoff,
    )


def distance(
    s1,
    s2,
    *,
    prefix_weight=0.1,
    processor=None,
    score_cutoff=None,
):
    """
    Calculates the jaro winkler distance

    Parameters
    ----------
    s1 : Sequence[Hashable]
        First string to compare.
    s2 : Sequence[Hashable]
        Second string to compare.
    prefix_weight : float, optional
        Weight used for the common prefix of the two strings.
        Has to be between 0 and 0.25. Default is 0.1.
    processor: callable, optional
        Optional callable that is used to preprocess the strings before
        comparing them. Default is None, which deactivates this behaviour.
    score_cutoff : float, optional
        Optional argument for a score threshold as a float between 0 and 1.0.
        For ratio < score_cutoff 0 is returned instead. Default is None,
        which deactivates this behaviour.

    Returns
    -------
    distance : float
        distance between s1 and s2 as a float between 1.0 and 0.0

    Raises
    ------
    ValueError
        If prefix_weight is invalid
    """
    setupPandas()
    if is_none(s1) or is_none(s2):
        return 1.0

    if processor is not None:
        s1 = processor(s1)
        s2 = processor(s2)

    cutoff_distance = None if (score_cutoff is None or score_cutoff > 1.0) else 1.0 - score_cutoff
    sim = similarity(s1, s2, prefix_weight=prefix_weight, score_cutoff=cutoff_distance)
    dist = 1.0 - sim
    return dist if (score_cutoff is None or dist <= score_cutoff) else 1.0


def normalized_distance(
    s1,
    s2,
    *,
    prefix_weight=0.1,
    processor=None,
    score_cutoff=None,
):
    """
    Calculates the normalized jaro winkler distance

    Parameters
    ----------
    s1 : Sequence[Hashable]
        First string to compare.
    s2 : Sequence[Hashable]
        Second string to compare.
    prefix_weight : float, optional
        Weight used for the common prefix of the two strings.
        Has to be between 0 and 0.25. Default is 0.1.
    processor: callable, optional
        Optional callable that is used to preprocess the strings before
        comparing them. Default is None, which deactivates this behaviour.
    score_cutoff : float, optional
        Optional argument for a score threshold as a float between 0 and 1.0.
        For ratio < score_cutoff 0 is returned instead. Default is None,
        which deactivates this behaviour.

    Returns
    -------
    normalized distance : float
        normalized distance between s1 and s2 as a float between 1.0 and 0.0

    Raises
    ------
    ValueError
        If prefix_weight is invalid
    """
    return distance(
        s1,
        s2,
        prefix_weight=prefix_weight,
        processor=processor,
        score_cutoff=score_cutoff,
    )
