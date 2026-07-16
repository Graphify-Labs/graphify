# SPDX-License-Identifier: MIT
# Copyright (C) 2022 Max Bachmann
from __future__ import annotations

from rapidfuzz._common_py import common_affix, conv_sequences
from rapidfuzz._utils import is_none, setupPandas
from rapidfuzz.distance._initialize_py import Editop, Editops


def similarity(
    s1,
    s2,
    *,
    processor=None,
    score_cutoff=None,
):
    """
    Calculates the length of the longest common subsequence

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

    if not s1:
        return 0

    s1, s2 = conv_sequences(s1, s2)
    S = (1 << len(s1)) - 1
    block = {}
    block_get = block.get
    x = 1
    for ch1 in s1:
        block[ch1] = block_get(ch1, 0) | x
        x <<= 1

    for ch2 in s2:
        Matches = block_get(ch2, 0)
        u = S & Matches
        S = (S + u) | (S - u)

    # calculate the equivalent of popcount(~S) in C. This breaks for len(s1) == 0
    res = bin(S)[-len(s1) :].count("0")
    return res if (score_cutoff is None or res >= score_cutoff) else 0


def _block_similarity(
    block,
    s1,
    s2,
    score_cutoff=None,
):
    if not s1:
        return 0

    S = (1 << len(s1)) - 1
    block_get = block.get

    for ch2 in s2:
        Matches = block_get(ch2, 0)
        u = S & Matches
        S = (S + u) | (S - u)

    # calculate the equivalent of popcount(~S) in C. This breaks for len(s1) == 0
    res = bin(S)[-len(s1) :].count("0")
    return res if (score_cutoff is None or res >= score_cutoff) else 0


def distance(
    s1,
    s2,
    *,
    processor=None,
    score_cutoff=None,
):
    """
    Calculates the LCS distance in the range [0, max].

    This is calculated as ``max(len1, len2) - similarity``.

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
    Find the LCS distance between two strings:

    >>> from rapidfuzz.distance import LCSseq
    >>> LCSseq.distance("lewenstein", "levenshtein")
    2

    Setting a maximum distance allows the implementation to select
    a more efficient implementation:

    >>> LCSseq.distance("lewenstein", "levenshtein", score_cutoff=1)
    2

    """
    if processor is not None:
        s1 = processor(s1)
        s2 = processor(s2)

    s1, s2 = conv_sequences(s1, s2)
    maximum = max(len(s1), len(s2))
    sim = similarity(s1, s2)
    dist = maximum - sim
    return dist if (score_cutoff is None or dist <= score_cutoff) else score_cutoff + 1


def normalized_distance(
    s1,
    s2,
    *,
    processor=None,
    score_cutoff=None,
):
    """
    Calculates a normalized LCS similarity in the range [1, 0].

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

    if not s1 or not s2:
        return 0

    s1, s2 = conv_sequences(s1, s2)
    maximum = max(len(s1), len(s2))
    norm_sim = distance(s1, s2) / maximum
    return norm_sim if (score_cutoff is None or norm_sim <= score_cutoff) else 1


def normalized_similarity(
    s1,
    s2,
    *,
    processor=None,
    score_cutoff=None,
):
    """
    Calculates a normalized LCS similarity in the range [0, 1].

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

    Examples
    --------
    Find the normalized LCS similarity between two strings:

    >>> from rapidfuzz.distance import LCSseq
    >>> LCSseq.normalized_similarity("lewenstein", "levenshtein")
    0.8181818181818181

    Setting a score_cutoff allows the implementation to select
    a more efficient implementation:

    >>> LCSseq.normalized_similarity("lewenstein", "levenshtein", score_cutoff=0.9)
    0.0

    When a different processor is used s1 and s2 do not have to be strings

    >>> LCSseq.normalized_similarity(["lewenstein"], ["levenshtein"], processor=lambda s: s[0])
    0.81818181818181
    """
    setupPandas()
    if is_none(s1) or is_none(s2):
        return 0.0

    if processor is not None:
        s1 = processor(s1)
        s2 = processor(s2)

    norm_sim = 1.0 - normalized_distance(s1, s2)
    return norm_sim if (score_cutoff is None or norm_sim >= score_cutoff) else 0


def _matrix(s1, s2):
    if not s1:
        return (0, [])

    S = (1 << len(s1)) - 1
    block = {}
    block_get = block.get
    x = 1
    for ch1 in s1:
        block[ch1] = block_get(ch1, 0) | x
        x <<= 1

    matrix = []
    for ch2 in s2:
        Matches = block_get(ch2, 0)
        u = S & Matches
        S = (S + u) | (S - u)
        matrix.append(S)

    # calculate the equivalent of popcount(~S) in C. This breaks for len(s1) == 0
    sim = bin(S)[-len(s1) :].count("0")
    return (sim, matrix)


def editops(
    s1,
    s2,
    *,
    processor=None,
):
    """
    Return Editops describing how to turn s1 into s2.

    Parameters
    ----------
    s1 : Sequence[Hashable]
        First string to compare.
    s2 : Sequence[Hashable]
        Second string to compare.
    processor: callable, optional
        Optional callable that is used to preprocess the strings before
        comparing them. Default is None, which deactivates this behaviour.

    Returns
    -------
    editops : Editops
        edit operations required to turn s1 into s2

    Notes
    -----
    The alignment is calculated using an algorithm of Heikki Hyyrö, which is
    described in [6]_. It has a time complexity and memory usage of ``O([N/64] * M)``.

    References
    ----------
    .. [6] Hyyrö, Heikki. "A Note on Bit-Parallel Alignment Computation."
           Stringology (2004).

    Examples
    --------
    >>> from rapidfuzz.distance import LCSseq
    >>> for tag, src_pos, dest_pos in LCSseq.editops("qabxcd", "abycdf"):
    ...    print(("%7s s1[%d] s2[%d]" % (tag, src_pos, dest_pos)))
     delete s1[0] s2[0]
     delete s1[3] s2[2]
     insert s1[4] s2[2]
     insert s1[6] s2[5]
    """
    if processor is not None:
        s1 = processor(s1)
        s2 = processor(s2)

    s1, s2 = conv_sequences(s1, s2)
    prefix_len, suffix_len = common_affix(s1, s2)
    s1 = s1[prefix_len : len(s1) - suffix_len]
    s2 = s2[prefix_len : len(s2) - suffix_len]
    sim, matrix = _matrix(s1, s2)

    editops = Editops([], 0, 0)
    editops._src_len = len(s1) + prefix_len + suffix_len
    editops._dest_len = len(s2) + prefix_len + suffix_len

    dist = len(s1) + len(s2) - 2 * sim
    if dist == 0:
        return editops

    editop_list = [None] * dist
    col = len(s1)
    row = len(s2)
    while row != 0 and col != 0:
        # deletion
        if matrix[row - 1] & (1 << (col - 1)):
            dist -= 1
            col -= 1
            editop_list[dist] = Editop("delete", col + prefix_len, row + prefix_len)
        else:
            row -= 1

            # insertion
            if row and not (matrix[row - 1] & (1 << (col - 1))):
                dist -= 1
                editop_list[dist] = Editop("insert", col + prefix_len, row + prefix_len)
            # match
            else:
                col -= 1

    while col != 0:
        dist -= 1
        col -= 1
        editop_list[dist] = Editop("delete", col + prefix_len, row + prefix_len)

    while row != 0:
        dist -= 1
        row -= 1
        editop_list[dist] = Editop("insert", col + prefix_len, row + prefix_len)

    editops._editops = editop_list
    return editops


def opcodes(
    s1,
    s2,
    *,
    processor=None,
):
    """
    Return Opcodes describing how to turn s1 into s2.

    Parameters
    ----------
    s1 : Sequence[Hashable]
        First string to compare.
    s2 : Sequence[Hashable]
        Second string to compare.
    processor: callable, optional
        Optional callable that is used to preprocess the strings before
        comparing them. Default is None, which deactivates this behaviour.

    Returns
    -------
    opcodes : Opcodes
        edit operations required to turn s1 into s2

    Notes
    -----
    The alignment is calculated using an algorithm of Heikki Hyyrö, which is
    described in [7]_. It has a time complexity and memory usage of ``O([N/64] * M)``.

    References
    ----------
    .. [7] Hyyrö, Heikki. "A Note on Bit-Parallel Alignment Computation."
           Stringology (2004).

    Examples
    --------
    >>> from rapidfuzz.distance import LCSseq

    >>> a = "qabxcd"
    >>> b = "abycdf"
    >>> for tag, i1, i2, j1, j2 in LCSseq.opcodes(a, b):
    ...    print(("%7s a[%d:%d] (%s) b[%d:%d] (%s)" %
    ...           (tag, i1, i2, a[i1:i2], j1, j2, b[j1:j2])))
     delete a[0:1] (q) b[0:0] ()
      equal a[1:3] (ab) b[0:2] (ab)
     delete a[3:4] (x) b[2:2] ()
     insert a[4:4] () b[2:3] (y)
      equal a[4:6] (cd) b[3:5] (cd)
     insert a[6:6] () b[5:6] (f)
    """
    return editops(s1, s2, processor=processor).as_opcodes()
