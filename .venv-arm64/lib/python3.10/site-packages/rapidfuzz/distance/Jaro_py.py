# SPDX-License-Identifier: MIT
# Copyright (C) 2022 Max Bachmann
from __future__ import annotations

from rapidfuzz._common_py import conv_sequences
from rapidfuzz._utils import is_none, setupPandas


def _jaro_calculate_similarity(pattern_len, text_len, common_chars, transpositions):
    transpositions //= 2
    sim = 0.0
    sim += common_chars / pattern_len
    sim += common_chars / text_len
    sim += (common_chars - transpositions) / common_chars
    return sim / 3.0


def _jaro_length_filter(pattern_len, text_len, score_cutoff):
    """
    filter matches below score_cutoff based on string lengths
    """
    if not pattern_len or not text_len:
        return False

    sim = _jaro_calculate_similarity(pattern_len, text_len, min(pattern_len, text_len), 0)
    return sim >= score_cutoff


def _jaro_common_char_filter(pattern_len, text_len, common_chars, score_cutoff):
    """
    filter matches below score_cutoff based on string lengths and common characters
    """
    if not common_chars:
        return False

    sim = _jaro_calculate_similarity(pattern_len, text_len, common_chars, 0)
    return sim >= score_cutoff


def _jaro_bounds(s1, s2):
    """
    find bounds and skip out of bound parts of the sequences
    """
    pattern_len = len(s1)
    text_len = len(s2)

    # since jaro uses a sliding window some parts of T/P might never be in
    # range an can be removed ahead of time
    bound = 0
    if text_len > pattern_len:
        bound = text_len // 2 - 1
        if text_len > pattern_len + bound:
            s2 = s2[: pattern_len + bound]
    else:
        bound = pattern_len // 2 - 1
        if pattern_len > text_len + bound:
            s1 = s1[: text_len + bound]
    return s1, s2, bound


def similarity(
    s1,
    s2,
    *,
    processor=None,
    score_cutoff=None,
):
    """
    Calculates the jaro similarity

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
        For ratio < score_cutoff 0 is returned instead. Default is None,
        which deactivates this behaviour.

    Returns
    -------
    similarity : float
        similarity between s1 and s2 as a float between 0 and 1.0
    """
    setupPandas()
    if is_none(s1) or is_none(s2):
        return 0.0

    if processor is not None:
        s1 = processor(s1)
        s2 = processor(s2)

    if not s1 and not s2:
        return 1.0

    if score_cutoff is None:
        score_cutoff = 0

    s1, s2 = conv_sequences(s1, s2)
    pattern_len = len(s1)
    text_len = len(s2)

    # short circuit if score_cutoff can not be reached
    if not _jaro_length_filter(pattern_len, text_len, score_cutoff):
        return 0

    if pattern_len == 1 and text_len == 1:
        return float(s1[0] == s2[0])

    s1, s2, bound = _jaro_bounds(s1, s2)

    s1_flags = [False] * pattern_len
    s2_flags = [False] * text_len

    # todo use bitparallel implementation
    # looking only within search range, count & flag matched pairs
    common_chars = 0
    for i, s1_ch in enumerate(s1):
        low = max(0, i - bound)
        hi = min(i + bound, text_len - 1)
        for j in range(low, hi + 1):
            if not s2_flags[j] and s2[j] == s1_ch:
                s1_flags[i] = s2_flags[j] = True
                common_chars += 1
                break

    # short circuit if score_cutoff can not be reached
    if not _jaro_common_char_filter(pattern_len, text_len, common_chars, score_cutoff):
        return 0

    # todo use bitparallel implementation
    # count transpositions
    k = trans_count = 0
    for i, s1_f in enumerate(s1_flags):
        if s1_f:
            for j in range(k, text_len):
                if s2_flags[j]:
                    k = j + 1
                    break
            if s1[i] != s2[j]:
                trans_count += 1

    return _jaro_calculate_similarity(pattern_len, text_len, common_chars, trans_count)


def normalized_similarity(
    s1,
    s2,
    *,
    processor=None,
    score_cutoff=None,
):
    """
    Calculates the normalized jaro similarity

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
        For ratio < score_cutoff 0 is returned instead. Default is None,
        which deactivates this behaviour.

    Returns
    -------
    normalized similarity : float
        normalized similarity between s1 and s2 as a float between 0 and 1.0
    """
    return similarity(s1, s2, processor=processor, score_cutoff=score_cutoff)


def distance(
    s1,
    s2,
    *,
    processor=None,
    score_cutoff=None,
):
    """
    Calculates the jaro distance

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
        For ratio < score_cutoff 0 is returned instead. Default is None,
        which deactivates this behaviour.

    Returns
    -------
    distance : float
        distance between s1 and s2 as a float between 1.0 and 0.0
    """
    setupPandas()
    if is_none(s1) or is_none(s2):
        return 1.0

    if processor is not None:
        s1 = processor(s1)
        s2 = processor(s2)

    cutoff_distance = None if (score_cutoff is None or score_cutoff > 1.0) else 1.0 - score_cutoff
    sim = similarity(s1, s2, score_cutoff=cutoff_distance)
    dist = 1.0 - sim
    return dist if (score_cutoff is None or dist <= score_cutoff) else 1.0


def normalized_distance(
    s1,
    s2,
    *,
    processor=None,
    score_cutoff=None,
):
    """
    Calculates the normalized jaro distance

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
        For ratio < score_cutoff 0 is returned instead. Default is None,
        which deactivates this behaviour.

    Returns
    -------
    normalized distance : float
        normalized distance between s1 and s2 as a float between 1.0 and 0.0
    """
    return distance(s1, s2, processor=processor, score_cutoff=score_cutoff)
