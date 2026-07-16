# SPDX-License-Identifier: MIT
# Copyright (C) 2022 Max Bachmann
from __future__ import annotations

from rapidfuzz._common_py import common_affix, conv_sequences
from rapidfuzz._utils import is_none, setupPandas
from rapidfuzz.distance import Indel_py as Indel
from rapidfuzz.distance._initialize_py import Editop, Editops


def _levenshtein_maximum(s1, s2, weights):
    len1 = len(s1)
    len2 = len(s2)
    insert, delete, replace = weights

    max_dist = len1 * delete + len2 * insert

    if len1 >= len2:
        max_dist = min(max_dist, len2 * replace + (len1 - len2) * delete)
    else:
        max_dist = min(max_dist, len1 * replace + (len2 - len1) * insert)

    return max_dist


def _uniform_generic(s1, s2, weights):
    len1 = len(s1)
    insert, delete, replace = weights
    cache = list(range(0, (len1 + 1) * delete, delete))

    for ch2 in s2:
        temp = cache[0]
        cache[0] += insert
        for i in range(len1):
            x = temp
            if s1[i] != ch2:
                x = min(cache[i] + delete, cache[i + 1] + insert, temp + replace)
            temp = cache[i + 1]
            cache[i + 1] = x

    return cache[-1]


def _uniform_distance(s1, s2):
    if not s1:
        return len(s2)

    VP = (1 << len(s1)) - 1
    VN = 0
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
        X = PM_j
        D0 = (((X & VP) + VP) ^ VP) | X | VN
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

    return currDist


def distance(
    s1,
    s2,
    *,
    weights=(1, 1, 1),
    processor=None,
    score_cutoff=None,
    score_hint=None,
):
    """
    Calculates the minimum number of insertions, deletions, and substitutions
    required to change one sequence into the other according to Levenshtein with custom
    costs for insertion, deletion and substitution

    Parameters
    ----------
    s1 : Sequence[Hashable]
        First string to compare.
    s2 : Sequence[Hashable]
        Second string to compare.
    weights : tuple[int, int, int] or None, optional
        The weights for the three operations in the form
        (insertion, deletion, substitution). Default is (1, 1, 1),
        which gives all three operations a weight of 1.
    processor : callable, optional
        Optional callable that is used to preprocess the strings before
        comparing them. Default is None, which deactivates this behaviour.
    score_cutoff : int, optional
        Maximum distance between s1 and s2, that is
        considered as a result. If the distance is bigger than score_cutoff,
        score_cutoff + 1 is returned instead. Default is None, which deactivates
        this behaviour.
    score_hint : int, optional
        Expected distance between s1 and s2. This is used to select a
        faster implementation. Default is None, which deactivates this behaviour.

    Returns
    -------
    distance : int
        distance between s1 and s2

    Raises
    ------
    ValueError
        If unsupported weights are provided a ValueError is thrown

    Examples
    --------
    Find the Levenshtein distance between two strings:

    >>> from rapidfuzz.distance import Levenshtein
    >>> Levenshtein.distance("lewenstein", "levenshtein")
    2

    Setting a maximum distance allows the implementation to select
    a more efficient implementation:

    >>> Levenshtein.distance("lewenstein", "levenshtein", score_cutoff=1)
    2

    It is possible to select different weights by passing a `weight`
    tuple.

    >>> Levenshtein.distance("lewenstein", "levenshtein", weights=(1,1,2))
    3
    """
    _ = score_hint
    if processor is not None:
        s1 = processor(s1)
        s2 = processor(s2)

    s1, s2 = conv_sequences(s1, s2)
    if weights is None or weights == (1, 1, 1):
        dist = _uniform_distance(s1, s2)
    elif weights == (1, 1, 2):
        dist = Indel.distance(s1, s2)
    else:
        dist = _uniform_generic(s1, s2, weights)

    return dist if (score_cutoff is None or dist <= score_cutoff) else score_cutoff + 1


def similarity(
    s1,
    s2,
    *,
    weights=(1, 1, 1),
    processor=None,
    score_cutoff=None,
    score_hint=None,
):
    """
    Calculates the levenshtein similarity in the range [max, 0] using custom
    costs for insertion, deletion and substitution.

    This is calculated as ``max - distance``, where max is the maximal possible
    Levenshtein distance given the lengths of the sequences s1/s2 and the weights.

    Parameters
    ----------
    s1 : Sequence[Hashable]
        First string to compare.
    s2 : Sequence[Hashable]
        Second string to compare.
    weights : tuple[int, int, int] or None, optional
        The weights for the three operations in the form
        (insertion, deletion, substitution). Default is (1, 1, 1),
        which gives all three operations a weight of 1.
    processor : callable, optional
        Optional callable that is used to preprocess the strings before
        comparing them. Default is None, which deactivates this behaviour.
    score_cutoff : int, optional
        Maximum distance between s1 and s2, that is
        considered as a result. If the similarity is smaller than score_cutoff,
        0 is returned instead. Default is None, which deactivates
        this behaviour.
    score_hint : int, optional
        Expected similarity between s1 and s2. This is used to select a
        faster implementation. Default is None, which deactivates this behaviour.

    Returns
    -------
    similarity : int
        similarity between s1 and s2

    Raises
    ------
    ValueError
        If unsupported weights are provided a ValueError is thrown
    """
    _ = score_hint
    if processor is not None:
        s1 = processor(s1)
        s2 = processor(s2)

    s1, s2 = conv_sequences(s1, s2)
    weights = weights or (1, 1, 1)
    maximum = _levenshtein_maximum(s1, s2, weights)
    dist = distance(s1, s2, weights=weights)
    sim = maximum - dist
    return sim if (score_cutoff is None or sim >= score_cutoff) else 0


def normalized_distance(
    s1,
    s2,
    *,
    weights=(1, 1, 1),
    processor=None,
    score_cutoff=None,
    score_hint=None,
):
    """
    Calculates a normalized levenshtein distance in the range [1, 0] using custom
    costs for insertion, deletion and substitution.

    This is calculated as ``distance / max``, where max is the maximal possible
    Levenshtein distance given the lengths of the sequences s1/s2 and the weights.

    Parameters
    ----------
    s1 : Sequence[Hashable]
        First string to compare.
    s2 : Sequence[Hashable]
        Second string to compare.
    weights : tuple[int, int, int] or None, optional
        The weights for the three operations in the form
        (insertion, deletion, substitution). Default is (1, 1, 1),
        which gives all three operations a weight of 1.
    processor : callable, optional
        Optional callable that is used to preprocess the strings before
        comparing them. Default is None, which deactivates this behaviour.
    score_cutoff : float, optional
        Optional argument for a score threshold as a float between 0 and 1.0.
        For norm_dist > score_cutoff 1.0 is returned instead. Default is None,
        which deactivates this behaviour.
    score_hint : float, optional
        Expected normalized distance between s1 and s2. This is used to select a
        faster implementation. Default is None, which deactivates this behaviour.

    Returns
    -------
    norm_dist : float
        normalized distance between s1 and s2 as a float between 1.0 and 0.0

    Raises
    ------
    ValueError
        If unsupported weights are provided a ValueError is thrown
    """
    _ = score_hint
    setupPandas()
    if is_none(s1) or is_none(s2):
        return 1.0

    if processor is not None:
        s1 = processor(s1)
        s2 = processor(s2)

    s1, s2 = conv_sequences(s1, s2)
    weights = weights or (1, 1, 1)
    maximum = _levenshtein_maximum(s1, s2, weights)
    dist = distance(s1, s2, weights=weights)
    norm_dist = dist / maximum if maximum else 0
    return norm_dist if (score_cutoff is None or norm_dist <= score_cutoff) else 1


def normalized_similarity(
    s1,
    s2,
    *,
    weights=(1, 1, 1),
    processor=None,
    score_cutoff=None,
    score_hint=None,
):
    """
    Calculates a normalized levenshtein similarity in the range [0, 1] using custom
    costs for insertion, deletion and substitution.

    This is calculated as ``1 - normalized_distance``

    Parameters
    ----------
    s1 : Sequence[Hashable]
        First string to compare.
    s2 : Sequence[Hashable]
        Second string to compare.
    weights : tuple[int, int, int] or None, optional
        The weights for the three operations in the form
        (insertion, deletion, substitution). Default is (1, 1, 1),
        which gives all three operations a weight of 1.
    processor : callable, optional
        Optional callable that is used to preprocess the strings before
        comparing them. Default is None, which deactivates this behaviour.
    score_cutoff : float, optional
        Optional argument for a score threshold as a float between 0 and 1.0.
        For norm_sim < score_cutoff 0 is returned instead. Default is None,
        which deactivates this behaviour.
    score_hint : int, optional
        Expected normalized similarity between s1 and s2. This is used to select a
        faster implementation. Default is None, which deactivates this behaviour.

    Returns
    -------
    norm_sim : float
        normalized similarity between s1 and s2 as a float between 0 and 1.0

    Raises
    ------
    ValueError
        If unsupported weights are provided a ValueError is thrown

    Examples
    --------
    Find the normalized Levenshtein similarity between two strings:

    >>> from rapidfuzz.distance import Levenshtein
    >>> Levenshtein.normalized_similarity("lewenstein", "levenshtein")
    0.81818181818181

    Setting a score_cutoff allows the implementation to select
    a more efficient implementation:

    >>> Levenshtein.normalized_similarity("lewenstein", "levenshtein", score_cutoff=0.85)
    0.0

    It is possible to select different weights by passing a `weight`
    tuple.

    >>> Levenshtein.normalized_similarity("lewenstein", "levenshtein", weights=(1,1,2))
    0.85714285714285

    When a different processor is used s1 and s2 do not have to be strings

    >>> Levenshtein.normalized_similarity(["lewenstein"], ["levenshtein"], processor=lambda s: s[0])
    0.81818181818181
    """
    _ = score_hint
    setupPandas()
    if is_none(s1) or is_none(s2):
        return 0.0

    if processor is not None:
        s1 = processor(s1)
        s2 = processor(s2)

    s1, s2 = conv_sequences(s1, s2)
    weights = weights or (1, 1, 1)
    norm_dist = normalized_distance(s1, s2, weights=weights)
    norm_sim = 1.0 - norm_dist
    return norm_sim if (score_cutoff is None or norm_sim >= score_cutoff) else 0


def _matrix(s1, s2):
    if not s1:
        return (len(s2), [], [])

    VP = (1 << len(s1)) - 1
    VN = 0
    currDist = len(s1)
    mask = 1 << (len(s1) - 1)

    block = {}
    block_get = block.get
    x = 1
    for ch1 in s1:
        block[ch1] = block_get(ch1, 0) | x
        x <<= 1

    matrix_VP = []
    matrix_VN = []
    for ch2 in s2:
        # Step 1: Computing D0
        PM_j = block_get(ch2, 0)
        X = PM_j
        D0 = (((X & VP) + VP) ^ VP) | X | VN
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

        matrix_VP.append(VP)
        matrix_VN.append(VN)

    return (currDist, matrix_VP, matrix_VN)


def editops(
    s1,
    s2,
    *,
    processor=None,
    score_hint=None,
):
    """
    Return Editops describing how to turn s1 into s2.

    Parameters
    ----------
    s1 : Sequence[Hashable]
        First string to compare.
    s2 : Sequence[Hashable]
        Second string to compare.
    processor : callable, optional
        Optional callable that is used to preprocess the strings before
        comparing them. Default is None, which deactivates this behaviour.
    score_hint : int, optional
        Expected distance between s1 and s2. This is used to select a
        faster implementation. Default is None, which deactivates this behaviour.

    Returns
    -------
    editops : Editops
        edit operations required to turn s1 into s2

    Notes
    -----
    The alignment is calculated using an algorithm of Heikki Hyyrö, which is
    described [8]_. It has a time complexity and memory usage of ``O([N/64] * M)``.

    References
    ----------
    .. [8] Hyyrö, Heikki. "A Note on Bit-Parallel Alignment Computation."
           Stringology (2004).

    Examples
    --------
    >>> from rapidfuzz.distance import Levenshtein
    >>> for tag, src_pos, dest_pos in Levenshtein.editops("qabxcd", "abycdf"):
    ...    print(("%7s s1[%d] s2[%d]" % (tag, src_pos, dest_pos)))
     delete s1[1] s2[0]
    replace s1[3] s2[2]
     insert s1[6] s2[5]
    """
    _ = score_hint
    if processor is not None:
        s1 = processor(s1)
        s2 = processor(s2)

    s1, s2 = conv_sequences(s1, s2)
    prefix_len, suffix_len = common_affix(s1, s2)
    s1 = s1[prefix_len : len(s1) - suffix_len]
    s2 = s2[prefix_len : len(s2) - suffix_len]
    dist, VP, VN = _matrix(s1, s2)

    editops = Editops([], 0, 0)
    editops._src_len = len(s1) + prefix_len + suffix_len
    editops._dest_len = len(s2) + prefix_len + suffix_len

    if dist == 0:
        return editops

    editop_list = [None] * dist
    col = len(s1)
    row = len(s2)
    while row != 0 and col != 0:
        # deletion
        if VP[row - 1] & (1 << (col - 1)):
            dist -= 1
            col -= 1
            editop_list[dist] = Editop("delete", col + prefix_len, row + prefix_len)
        else:
            row -= 1

            # insertion
            if row and (VN[row - 1] & (1 << (col - 1))):
                dist -= 1
                editop_list[dist] = Editop("insert", col + prefix_len, row + prefix_len)
            else:
                col -= 1

                # replace (Matches are not recorded)
                if s1[col] != s2[row]:
                    dist -= 1
                    editop_list[dist] = Editop("replace", col + prefix_len, row + prefix_len)

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
    score_hint=None,
):
    """
    Return Opcodes describing how to turn s1 into s2.

    Parameters
    ----------
    s1 : Sequence[Hashable]
        First string to compare.
    s2 : Sequence[Hashable]
        Second string to compare.
    processor : callable, optional
        Optional callable that is used to preprocess the strings before
        comparing them. Default is None, which deactivates this behaviour.
    score_hint : int, optional
        Expected distance between s1 and s2. This is used to select a
        faster implementation. Default is None, which deactivates this behaviour.

    Returns
    -------
    opcodes : Opcodes
        edit operations required to turn s1 into s2

    Notes
    -----
    The alignment is calculated using an algorithm of Heikki Hyyrö, which is
    described [9]_. It has a time complexity and memory usage of ``O([N/64] * M)``.

    References
    ----------
    .. [9] Hyyrö, Heikki. "A Note on Bit-Parallel Alignment Computation."
           Stringology (2004).

    Examples
    --------
    >>> from rapidfuzz.distance import Levenshtein

    >>> a = "qabxcd"
    >>> b = "abycdf"
    >>> for tag, i1, i2, j1, j2 in Levenshtein.opcodes("qabxcd", "abycdf"):
    ...    print(("%7s a[%d:%d] (%s) b[%d:%d] (%s)" %
    ...           (tag, i1, i2, a[i1:i2], j1, j2, b[j1:j2])))
     delete a[0:1] (q) b[0:0] ()
      equal a[1:3] (ab) b[0:2] (ab)
    replace a[3:4] (x) b[2:3] (y)
      equal a[4:6] (cd) b[3:5] (cd)
     insert a[6:6] () b[5:6] (f)
    """
    return editops(s1, s2, processor=processor, score_hint=score_hint).as_opcodes()
