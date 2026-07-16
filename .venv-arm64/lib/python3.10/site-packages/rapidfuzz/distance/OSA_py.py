# SPDX-License-Identifier: MIT
# Copyright (C) 2022 Max Bachmann
from __future__ import annotations

from rapidfuzz._common_py import conv_sequences
from rapidfuzz._utils import is_none, setupPandas


def _osa_distance_hyrroe2003(s1, s2):
    if not s1:
        return len(s2)

    VP = (1 << len(s1)) - 1
    VN = 0
    D0 = 0
    PM_j_old = 0
    currDist = len(s1)
    mask = 1 << (len(s1) - 1)

    block = {}
    block_get = block.get
    x = 1
    for ch1 in s1:
        block[ch1] = block_get(ch1, 0) | x
        x <<= 1

    for ch2 in s2:
        # Step 1: Computing D0
        PM_j = block_get(ch2, 0)
        TR = (((~D0) & PM_j) << 1) & PM_j_old
        D0 = (((PM_j & VP) + VP) ^ VP) | PM_j | VN
        D0 = D0 | TR

        # Step 2: Computing HP and HN
        HP = VN | ~(D0 | VP)
        HN = D0 & VP

        # Step 3: Computing the value D[m,j]
        currDist += (HP & mask) != 0
        currDist -= (HN & mask) != 0

        # Step 4: Computing Vp and VN
        HP = (HP << 1) | 1
        HN = HN << 1
        VP = HN | ~(D0 | HP)
        VN = HP & D0
        PM_j_old = PM_j

    return currDist


def distance(
    s1,
    s2,
    *,
    processor=None,
    score_cutoff=None,
):
    """
    Calculates the optimal string alignment (OSA) distance.

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
    Find the OSA distance between two strings:

    >>> from rapidfuzz.distance import OSA
    >>> OSA.distance("CA", "AC")
    2
    >>> OSA.distance("CA", "ABC")
    3
    """
    if processor is not None:
        s1 = processor(s1)
        s2 = processor(s2)

    s1, s2 = conv_sequences(s1, s2)
    dist = _osa_distance_hyrroe2003(s1, s2)
    return dist if (score_cutoff is None or dist <= score_cutoff) else score_cutoff + 1


def similarity(
    s1,
    s2,
    *,
    processor=None,
    score_cutoff=None,
):
    """
    Calculates the optimal string alignment (OSA) similarity in the range [max, 0].

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
    Calculates a normalized optimal string alignment (OSA) similarity in the range [1, 0].

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
    Calculates a normalized optimal string alignment (OSA) similarity in the range [0, 1].

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
