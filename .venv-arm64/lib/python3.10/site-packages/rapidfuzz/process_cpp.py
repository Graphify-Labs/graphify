# SPDX-License-Identifier: MIT
# Copyright (C) 2022 Max Bachmann
from __future__ import annotations

from rapidfuzz.fuzz import ratio
from rapidfuzz.process_cpp_impl import (
    FLOAT32 as _FLOAT32,
    FLOAT64 as _FLOAT64,
    INT8 as _INT8,
    INT16 as _INT16,
    INT32 as _INT32,
    INT64 as _INT64,
    UINT8 as _UINT8,
    UINT16 as _UINT16,
    UINT32 as _UINT32,
    UINT64 as _UINT64,
    cdist as _cdist,
    cpdist as _cpdist,
    extract,
    extract_iter,
    extractOne,
)

__all__ = ["cdist", "cpdist", "extract", "extractOne", "extract_iter"]


def _dtype_to_type_num(dtype):
    import numpy as np

    if dtype is None:
        return None

    dtype = np.dtype(dtype)
    if dtype == np.int32:
        return _INT32
    if dtype == np.int8:
        return _INT8
    if dtype == np.int16:
        return _INT16
    if dtype == np.int64:
        return _INT64
    if dtype == np.uint8:
        return _UINT8
    if dtype == np.uint16:
        return _UINT16
    if dtype == np.uint32:
        return _UINT32
    if dtype == np.uint64:
        return _UINT64
    if dtype == np.float32:
        return _FLOAT32
    if dtype == np.float64:
        return _FLOAT64

    msg = f"unsupported dtype: {dtype}"
    raise TypeError(msg)


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
    **kwargs,
):
    import numpy as np

    dtype = _dtype_to_type_num(dtype)
    return np.asarray(
        _cdist(
            queries,
            choices,
            scorer=scorer,
            processor=processor,
            score_cutoff=score_cutoff,
            score_hint=score_hint,
            score_multiplier=score_multiplier,
            dtype=dtype,
            workers=workers,
            **kwargs,
        )
    )


cdist.__doc__ = _cdist.__doc__


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
    **kwargs,
):
    import numpy as np

    dtype = _dtype_to_type_num(dtype)
    distance_matrix = _cpdist(
        queries,
        choices,
        scorer=scorer,
        processor=processor,
        score_cutoff=score_cutoff,
        score_hint=score_hint,
        score_multiplier=score_multiplier,
        dtype=dtype,
        workers=workers,
        **kwargs,
    )
    return np.asarray(distance_matrix)


cpdist.__doc__ = _cpdist.__doc__
