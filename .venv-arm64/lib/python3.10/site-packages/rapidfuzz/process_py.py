# SPDX-License-Identifier: MIT
# Copyright (C) 2022 Max Bachmann
from __future__ import annotations

import heapq

from rapidfuzz._utils import ScorerFlag, is_none, setupPandas
from rapidfuzz.fuzz import WRatio, ratio

__all__ = ["cdist", "extract", "extractOne", "extract_iter"]


def _get_scorer_flags_py(scorer, scorer_kwargs):
    params = getattr(scorer, "_RF_ScorerPy", None)
    if params is not None:
        flags = params["get_scorer_flags"](**scorer_kwargs)
        return (flags["worst_score"], flags["optimal_score"])
    return (0, 100)


def extract_iter(
    query,
    choices,
    *,
    scorer=WRatio,
    processor=None,
    score_cutoff=None,
    score_hint=None,
    scorer_kwargs=None,
):
    """
    Find the best match in a list of choices

    Parameters
    ----------
    query : Sequence[Hashable]
        string we want to find
    choices : Iterable[Sequence[Hashable]] | Mapping[Sequence[Hashable]]
        list of all strings the query should be compared with or dict with a mapping
        {<result>: <string to compare>}
    scorer : Callable, optional
        Optional callable that is used to calculate the matching score between
        the query and each choice. This can be any of the scorers included in RapidFuzz
        (both scorers that calculate the edit distance or the normalized edit distance), or
        a custom function, which returns a normalized edit distance.
        fuzz.WRatio is used by default.
    processor : Callable, optional
        Optional callable that is used to preprocess the strings before
        comparing them. Default is None, which deactivates this behaviour.
    score_cutoff : Any, optional
        Optional argument for a score threshold. When an edit distance is used this represents the maximum
        edit distance and matches with a `distance > score_cutoff` are ignored. When a
        normalized edit distance is used this represents the minimal similarity
        and matches with a `similarity < score_cutoff` are ignored. Default is None, which deactivates this behaviour.
    score_hint : Any, optional
        Optional argument for an expected score to be passed to the scorer.
        This is used to select a faster implementation. Default is None,
        which deactivates this behaviour.
    scorer_kwargs : dict[str, Any], optional
        any other named parameters are passed to the scorer. This can be used to pass
        e.g. weights to `Levenshtein.distance`

    Yields
    -------
    tuple[Sequence[Hashable], Any, Any]
        Yields similarity between the query and each choice in form of a Tuple with 3 elements.
        The values stored in the tuple depend on the types of the input arguments.

        * The first element is always the current `choice`, which is the value that's compared to the query.

        * The second value represents the similarity calculated by the scorer. This can be:

          * An edit distance (distance is 0 for a perfect match and > 0 for non perfect matches).
            In this case only choices which have a `distance <= score_cutoff` are yielded.
            An example of a scorer with this behavior is `Levenshtein.distance`.
          * A normalized edit distance (similarity is a score between 0 and 100, with 100 being a perfect match).
            In this case only choices which have a `similarity >= score_cutoff` are yielded.
            An example of a scorer with this behavior is `Levenshtein.normalized_similarity`.

          Note, that for all scorers, which are not provided by RapidFuzz, only normalized edit distances are supported.

        * The third parameter depends on the type of the `choices` argument it is:

          * The `index of choice` when choices is a simple iterable like a list
          * The `key of choice` when choices is a mapping like a dict, or a pandas Series

    """
    _ = score_hint
    scorer_kwargs = scorer_kwargs or {}
    worst_score, optimal_score = _get_scorer_flags_py(scorer, scorer_kwargs)
    lowest_score_worst = optimal_score > worst_score

    setupPandas()

    if is_none(query):
        return

    if score_cutoff is None:
        score_cutoff = worst_score

    # preprocess the query
    if processor is not None:
        query = processor(query)

    choices_iter = choices.items() if hasattr(choices, "items") else enumerate(choices)
    for key, choice in choices_iter:
        if is_none(choice):
            continue

        if processor is None:
            score = scorer(query, choice, score_cutoff=score_cutoff, **scorer_kwargs)
        else:
            score = scorer(
                query,
                processor(choice),
                score_cutoff=score_cutoff,
                **scorer_kwargs,
            )

        if lowest_score_worst:
            if score >= score_cutoff:
                yield (choice, score, key)
        else:
            if score <= score_cutoff:
                yield (choice, score, key)


def extractOne(
    query,
    choices,
    *,
    scorer=WRatio,
    processor=None,
    score_cutoff=None,
    score_hint=None,
    scorer_kwargs=None,
):
    """
    Find the best match in a list of choices. When multiple elements have the same similarity,
    the first element is returned.

    Parameters
    ----------
    query : Sequence[Hashable]
        string we want to find
    choices : Iterable[Sequence[Hashable]] | Mapping[Sequence[Hashable]]
        list of all strings the query should be compared with or dict with a mapping
        {<result>: <string to compare>}
    scorer : Callable, optional
        Optional callable that is used to calculate the matching score between
        the query and each choice. This can be any of the scorers included in RapidFuzz
        (both scorers that calculate the edit distance or the normalized edit distance), or
        a custom function, which returns a normalized edit distance.
        fuzz.WRatio is used by default.
    processor : Callable, optional
        Optional callable that is used to preprocess the strings before
        comparing them. Default is None, which deactivates this behaviour.
    score_cutoff : Any, optional
        Optional argument for a score threshold. When an edit distance is used this represents the maximum
        edit distance and matches with a `distance > score_cutoff` are ignored. When a
        normalized edit distance is used this represents the minimal similarity
        and matches with a `similarity < score_cutoff` are ignored. Default is None, which deactivates this behaviour.
    score_hint : Any, optional
        Optional argument for an expected score to be passed to the scorer.
        This is used to select a faster implementation. Default is None,
        which deactivates this behaviour.
    scorer_kwargs : dict[str, Any], optional
        any other named parameters are passed to the scorer. This can be used to pass
        e.g. weights to `Levenshtein.distance`

    Returns
    -------
    tuple[Sequence[Hashable], Any, Any]
        Returns the best match in form of a Tuple with 3 elements. The values stored in the
        tuple depend on the types of the input arguments.

        * The first element is always the `choice`, which is the value that's compared to the query.

        * The second value represents the similarity calculated by the scorer. This can be:

          * An edit distance (distance is 0 for a perfect match and > 0 for non perfect matches).
            In this case only choices which have a `distance <= score_cutoff` are returned.
            An example of a scorer with this behavior is `Levenshtein.distance`.
          * A normalized edit distance (similarity is a score between 0 and 100, with 100 being a perfect match).
            In this case only choices which have a `similarity >= score_cutoff` are returned.
            An example of a scorer with this behavior is `Levenshtein.normalized_similarity`.

          Note, that for all scorers, which are not provided by RapidFuzz, only normalized edit distances are supported.

        * The third parameter depends on the type of the `choices` argument it is:

          * The `index of choice` when choices is a simple iterable like a list
          * The `key of choice` when choices is a mapping like a dict, or a pandas Series

    None
        When no choice has a `similarity >= score_cutoff`/`distance <= score_cutoff` None is returned

    Examples
    --------

    >>> from rapidfuzz.process import extractOne
    >>> from rapidfuzz.distance import Levenshtein
    >>> from rapidfuzz.fuzz import ratio

    extractOne can be used with normalized edit distances.

    >>> extractOne("abcd", ["abce"], scorer=ratio)
    ("abcd", 75.0, 1)
    >>> extractOne("abcd", ["abce"], scorer=Levenshtein.normalized_similarity)
    ("abcd", 0.75, 1)

    extractOne can be used with edit distances as well.

    >>> extractOne("abcd", ["abce"], scorer=Levenshtein.distance)
    ("abce", 1, 0)

    additional settings of the scorer can be passed via the scorer_kwargs argument to extractOne

    >>> extractOne("abcd", ["abce"], scorer=Levenshtein.distance, scorer_kwargs={"weights":(1,1,2)})
    ("abcde", 2, 1)

    when a mapping is used for the choices the key of the choice is returned instead of the List index

    >>> extractOne("abcd", {"key": "abce"}, scorer=ratio)
    ("abcd", 75.0, "key")

    It is possible to specify a processor function which is used to preprocess the strings before comparing them.

    >>> extractOne("abcd", ["abcD"], scorer=ratio)
    ("abcD", 75.0, 0)
    >>> extractOne("abcd", ["abcD"], scorer=ratio, processor=utils.default_process)
    ("abcD", 100.0, 0)
    >>> extractOne("abcd", ["abcD"], scorer=ratio, processor=lambda s: s.upper())
    ("abcD", 100.0, 0)

    When only results with a similarity above a certain threshold are relevant, the parameter score_cutoff can be
    used to filter out results with a lower similarity. This threshold is used by some of the scorers to exit early,
    when they are sure, that the similarity is below the threshold.
    For normalized edit distances all results with a similarity below score_cutoff are filtered out

    >>> extractOne("abcd", ["abce"], scorer=ratio)
    ("abce", 75.0, 0)
    >>> extractOne("abcd", ["abce"], scorer=ratio, score_cutoff=80)
    None

    For edit distances all results with an edit distance above the score_cutoff are filtered out

    >>> extractOne("abcd", ["abce"], scorer=Levenshtein.distance, scorer_kwargs={"weights":(1,1,2)})
    ("abce", 2, 0)
    >>> extractOne("abcd", ["abce"], scorer=Levenshtein.distance, scorer_kwargs={"weights":(1,1,2)}, score_cutoff=1)
    None

    """
    _ = score_hint
    scorer_kwargs = scorer_kwargs or {}
    worst_score, optimal_score = _get_scorer_flags_py(scorer, scorer_kwargs)
    lowest_score_worst = optimal_score > worst_score

    setupPandas()

    if is_none(query):
        return None

    if score_cutoff is None:
        score_cutoff = worst_score

    # preprocess the query
    if processor is not None:
        query = processor(query)

    result = None

    choices_iter = choices.items() if hasattr(choices, "items") else enumerate(choices)
    for key, choice in choices_iter:
        if is_none(choice):
            continue

        if processor is None:
            score = scorer(query, choice, score_cutoff=score_cutoff, **scorer_kwargs)
        else:
            score = scorer(
                query,
                processor(choice),
                score_cutoff=score_cutoff,
                **scorer_kwargs,
            )

        if lowest_score_worst:
            if score >= score_cutoff and (result is None or score > result[1]):
                score_cutoff = score
                result = (choice, score, key)
        else:
            if score <= score_cutoff and (result is None or score < result[1]):
                score_cutoff = score
                result = (choice, score, key)

        if score == optimal_score:
            break

    return result


def extract(
    query,
    choices,
    *,
    scorer=WRatio,
    processor=None,
    limit=5,
    score_cutoff=None,
    score_hint=None,
    scorer_kwargs=None,
):
    """
    Find the best matches in a list of choices. The list is sorted by the similarity.
    When multiple choices have the same similarity, they are sorted by their index

    Parameters
    ----------
    query : Sequence[Hashable]
        string we want to find
    choices : Collection[Sequence[Hashable]] | Mapping[Sequence[Hashable]]
        list of all strings the query should be compared with or dict with a mapping
        {<result>: <string to compare>}
    scorer : Callable, optional
        Optional callable that is used to calculate the matching score between
        the query and each choice. This can be any of the scorers included in RapidFuzz
        (both scorers that calculate the edit distance or the normalized edit distance), or
        a custom function, which returns a normalized edit distance.
        fuzz.WRatio is used by default.
    processor : Callable, optional
        Optional callable that is used to preprocess the strings before
        comparing them. Default is None, which deactivates this behaviour.
    limit : int, optional
        maximum amount of results to return. None can be passed to disable this behavior.
        Default is 5.
    score_cutoff : Any, optional
        Optional argument for a score threshold. When an edit distance is used this represents the maximum
        edit distance and matches with a `distance > score_cutoff` are ignored. When a
        normalized edit distance is used this represents the minimal similarity
        and matches with a `similarity < score_cutoff` are ignored. Default is None, which deactivates this behaviour.
    score_hint : Any, optional
        Optional argument for an expected score to be passed to the scorer.
        This is used to select a faster implementation. Default is None,
        which deactivates this behaviour.
    scorer_kwargs : dict[str, Any], optional
        any other named parameters are passed to the scorer. This can be used to pass
        e.g. weights to `Levenshtein.distance`

    Returns
    -------
    list[tuple[Sequence[Hashable], Any, Any]]
        The return type is always a List of Tuples with 3 elements. However the values stored in the
        tuple depend on the types of the input arguments.

        * The first element is always the `choice`, which is the value that's compared to the query.

        * The second value represents the similarity calculated by the scorer. This can be:

          * An edit distance (distance is 0 for a perfect match and > 0 for non perfect matches).
            In this case only choices which have a `distance <= score_cutoff` are returned.
            An example of a scorer with this behavior is `Levenshtein.distance`.
          * A normalized edit distance (similarity is a score between 0 and 100, with 100 being a perfect match).
            In this case only choices which have a `similarity >= score_cutoff` are returned.
            An example of a scorer with this behavior is `Levenshtein.normalized_similarity`.

          Note, that for all scorers, which are not provided by RapidFuzz, only normalized edit distances are supported.

        * The third parameter depends on the type of the `choices` argument it is:

          * The `index of choice` when choices is a simple iterable like a list
          * The `key of choice` when choices is a mapping like a dict, or a pandas Series

        The list is sorted by similarity or distance depending on the scorer used. The first element in the list
        has the `highest similarity`/`smallest distance`.

    """
    scorer_kwargs = scorer_kwargs or {}
    worst_score, optimal_score = _get_scorer_flags_py(scorer, scorer_kwargs)
    lowest_score_worst = optimal_score > worst_score

    if limit == 1:
        res = extractOne(
            query,
            choices,
            processor=processor,
            scorer=scorer,
            score_cutoff=score_cutoff,
            score_hint=score_hint,
            scorer_kwargs=scorer_kwargs,
        )
        if res is None:
            return []
        return [res]

    result_iter = extract_iter(
        query,
        choices,
        processor=processor,
        scorer=scorer,
        score_cutoff=score_cutoff,
        score_hint=score_hint,
        scorer_kwargs=scorer_kwargs,
    )

    if limit is None:
        return sorted(result_iter, key=lambda i: i[1], reverse=lowest_score_worst)

    if lowest_score_worst:
        return heapq.nlargest(limit, result_iter, key=lambda i: i[1])
    return heapq.nsmallest(limit, result_iter, key=lambda i: i[1])


def _dtype_to_type_num(
    dtype,
    scorer,
    scorer_kwargs,
):
    import numpy as np

    if dtype is not None:
        return np.dtype(dtype)

    params = getattr(scorer, "_RF_ScorerPy", None)
    if params is not None:
        flags = params["get_scorer_flags"](**scorer_kwargs)
        if flags["flags"] & ScorerFlag.RESULT_I64:
            return np.int32
        if flags["flags"] & ScorerFlag.RESULT_SIZE_T:
            return np.uint32
        return np.float32

    return np.float32


def _is_symmetric(scorer, scorer_kwargs):
    params = getattr(scorer, "_RF_ScorerPy", None)
    if params is not None:
        flags = params["get_scorer_flags"](**scorer_kwargs)
        if flags["flags"] & ScorerFlag.SYMMETRIC:
            return True

    return False


def cdist(
    queries,
    choices,
    *,
    scorer=ratio,
    processor=None,
    score_cutoff=None,
    score_hint=None,
    score_multiplier=1,
    dtype=None,
    workers=1,
    scorer_kwargs=None,
):
    """
    Compute distance/similarity between each pair of the two collections of inputs.

    Parameters
    ----------
    queries : Collection[Sequence[Hashable]]
        list of all strings the queries
    choices : Collection[Sequence[Hashable]]
        list of all strings the query should be compared
    scorer : Callable, optional
        Optional callable that is used to calculate the matching score between
        the query and each choice. This can be any of the scorers included in RapidFuzz
        (both scorers that calculate the edit distance or the normalized edit distance), or
        a custom function, which returns a normalized edit distance.
        fuzz.ratio is used by default.
    processor : Callable, optional
        Optional callable that is used to preprocess the strings before
        comparing them. Default is None, which deactivates this behaviour.
    score_cutoff : Any, optional
        Optional argument for a score threshold to be passed to the scorer.
        Default is None, which deactivates this behaviour.
    score_hint : Any, optional
        Optional argument for an expected score to be passed to the scorer.
        This is used to select a faster implementation. Default is None,
        which deactivates this behaviour.
    score_multiplier: Any, optional
        Optional argument to multiply the calculated score with. This is applied as the final step,
        so e.g. score_cutoff is applied on the unmodified score. This is mostly useful to map from
        a floating point range to an integer to reduce the memory usage. Default is 1,
        which deactivates this behaviour.
    dtype : data-type, optional
        The desired data-type for the result array. Depending on the scorer type the following
        dtypes are supported:

        - similarity:
          - np.float32, np.float64
          - np.uint8 -> stores fixed point representation of the result scaled to a range 0-100
        - distance:
          - np.int8, np.int16, np.int32, np.int64

        If not given, then the type will be np.float32 for similarities and np.int32 for distances.
    workers : int, optional
        The calculation is subdivided into workers sections and evaluated in parallel.
        Supply -1 to use all available CPU cores.
        This argument is only available for scorers using the RapidFuzz C-API so far, since it
        releases the Python GIL.
    scorer_kwargs : dict[str, Any], optional
        any other named parameters are passed to the scorer. This can be used to pass
        e.g. weights to `Levenshtein.distance`

    Returns
    -------
    ndarray
        Returns a matrix of dtype with the distance/similarity between each pair
        of the two collections of inputs.
    """
    import numpy as np

    _ = workers, score_hint
    scorer_kwargs = scorer_kwargs or {}
    dtype = _dtype_to_type_num(dtype, scorer, scorer_kwargs)
    results = np.zeros((len(queries), len(choices)), dtype=dtype)

    setupPandas()

    if processor is None:
        proc_choices = list(choices)
    else:
        proc_choices = [x if is_none(x) else processor(x) for x in choices]

    if queries is choices and _is_symmetric(scorer, scorer_kwargs):
        for i, proc_query in enumerate(proc_choices):
            score = scorer(proc_query, proc_query, score_cutoff=score_cutoff, **scorer_kwargs) * score_multiplier

            if np.issubdtype(dtype, np.integer):
                score = round(score)

            results[i, i] = score
            for j in range(i + 1, len(proc_choices)):
                score = (
                    scorer(
                        proc_query,
                        proc_choices[j],
                        score_cutoff=score_cutoff,
                        **scorer_kwargs,
                    )
                    * score_multiplier
                )

                if np.issubdtype(dtype, np.integer):
                    score = round(score)

                results[i, j] = results[j, i] = score
    else:
        for i, query in enumerate(queries):
            proc_query = processor(query) if (processor and not is_none(query)) else query
            for j, choice in enumerate(proc_choices):
                score = (
                    scorer(
                        proc_query,
                        choice,
                        score_cutoff=score_cutoff,
                        **scorer_kwargs,
                    )
                    * score_multiplier
                )

                if np.issubdtype(dtype, np.integer):
                    score = round(score)

                results[i, j] = score

    return results


def cpdist(
    queries,
    choices,
    *,
    scorer=ratio,
    processor=None,
    score_cutoff=None,
    score_hint=None,
    score_multiplier=1,
    dtype=None,
    workers=1,
    scorer_kwargs=None,
):
    """
    Compute the pairwise distance/similarity between corresponding elements of the queries & choices.

    Parameters
    ----------
    queries : Collection[Sequence[Hashable]]
        list of strings used to compute the distance/similarity.
    choices : Collection[Sequence[Hashable]]
        list of strings the queries should be compared with. Must be the same length as the queries.
    scorer : Callable, optional
        Optional callable that is used to calculate the matching score between
        the query and each choice. This can be any of the scorers included in RapidFuzz
        (both scorers that calculate the edit distance or the normalized edit distance), or
        a custom function, which returns a normalized edit distance.
        fuzz.ratio is used by default.
    processor : Callable, optional
        Optional callable that is used to preprocess the strings before
        comparing them. Default is None, which deactivates this behaviour.
    score_cutoff : Any, optional
        Optional argument for a score threshold to be passed to the scorer.
        Default is None, which deactivates this behaviour.
    score_hint : Any, optional
        Optional argument for an expected score to be passed to the scorer.
        This is used to select a faster implementation. Default is None,
        which deactivates this behaviour.
    score_multiplier: Any, optional
        Optional argument to multiply the calculated score with. This is applied as the final step,
        so e.g. score_cutoff is applied on the unmodified score. This is mostly useful to map from
        a floating point range to an integer to reduce the memory usage. Default is 1,
        which deactivates this behaviour.
    dtype : data-type, optional
        The desired data-type for the result array. Depending on the scorer type the following
        dtypes are supported:

        - similarity:
          - np.float32, np.float64
          - np.uint8 -> stores fixed point representation of the result scaled to a range 0-100
        - distance:
          - np.int8, np.int16, np.int32, np.int64

        If not given, then the type will be np.float32 for similarities and np.int32 for distances.
    workers : int, optional
        The calculation is subdivided into workers sections and evaluated in parallel.
        Supply -1 to use all available CPU cores.
        This argument is only available for scorers using the RapidFuzz C-API so far, since it
        releases the Python GIL.
    scorer_kwargs : dict[str, Any], optional
        any other named parameters are passed to the scorer. This can be used to pass
        e.g. weights to `Levenshtein.distance`

    Returns
    -------
    ndarray
        Returns a matrix of size (n x 1) of dtype with the distance/similarity between each pair
        of the two collections of inputs.
    """
    import numpy as np

    len_queries = len(queries)
    len_choices = len(choices)

    if len_queries != len_choices:
        error_message = "Length of queries and choices must be the same!"
        raise ValueError(error_message)

    _ = workers, score_hint
    scorer_kwargs = scorer_kwargs or {}
    dtype = _dtype_to_type_num(dtype, scorer, scorer_kwargs)
    results = np.zeros((len_queries,), dtype=dtype)

    setupPandas()

    for i, (query, choice) in enumerate(zip(queries, choices)):
        proc_query = processor(query) if (processor and not is_none(query)) else query
        proc_choice = processor(choice) if (processor and not is_none(choice)) else choice
        score = scorer(
            proc_query,
            proc_choice,
            score_cutoff=score_cutoff,
            **scorer_kwargs,
        )

        # Apply score multiplier
        score *= score_multiplier

        # Round the result if dtype is integral
        if np.issubdtype(dtype, np.integer):
            score = round(score)

        # Store the score in the results matrix
        results[i] = score

    return results
