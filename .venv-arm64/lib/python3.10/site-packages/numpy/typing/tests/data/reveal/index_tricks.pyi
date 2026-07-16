from types import EllipsisType
from typing import Any, Literal

import numpy as np
import numpy.typing as npt

from typing_extensions import assert_type

AR_LIKE_b: list[bool]
AR_LIKE_i: list[int]
AR_LIKE_f: list[float]
AR_LIKE_U: list[str]
AR_LIKE_O: list[object]

AR_i8: npt.NDArray[np.int64]
AR_O: npt.NDArray[np.object_]

assert_type(np.ndenumerate(AR_i8), np.ndenumerate[np.int64])
assert_type(np.ndenumerate(AR_LIKE_f), np.ndenumerate[np.float64])
assert_type(np.ndenumerate(AR_LIKE_U), np.ndenumerate[np.str_])
assert_type(np.ndenumerate(AR_LIKE_O), np.ndenumerate[Any])

assert_type(next(np.ndenumerate(AR_i8)), tuple[tuple[int, ...], np.int64])
assert_type(next(np.ndenumerate(AR_LIKE_f)), tuple[tuple[int, ...], np.float64])
assert_type(next(np.ndenumerate(AR_LIKE_U)), tuple[tuple[int, ...], np.str_])
assert_type(next(np.ndenumerate(AR_LIKE_O)), tuple[tuple[int, ...], Any])

assert_type(iter(np.ndenumerate(AR_i8)), np.ndenumerate[np.int64])
assert_type(iter(np.ndenumerate(AR_LIKE_f)), np.ndenumerate[np.float64])
assert_type(iter(np.ndenumerate(AR_LIKE_U)), np.ndenumerate[np.str_])
assert_type(iter(np.ndenumerate(AR_LIKE_O)), np.ndenumerate[Any])

assert_type(np.ndindex(1, 2, 3), np.ndindex)
assert_type(np.ndindex((1, 2, 3)), np.ndindex)
assert_type(iter(np.ndindex(1, 2, 3)), np.ndindex)
assert_type(next(np.ndindex(1, 2, 3)), tuple[int, ...])

assert_type(np.unravel_index([22, 41, 37], (7, 6)), tuple[npt.NDArray[np.intp], ...])
assert_type(np.unravel_index([31, 41, 13], (7, 6), order="F"), tuple[npt.NDArray[np.intp], ...])
assert_type(np.unravel_index(1621, (6, 7, 8, 9)), tuple[np.intp, ...])

assert_type(np.ravel_multi_index([[1]], (7, 6)), npt.NDArray[np.intp])
assert_type(np.ravel_multi_index(AR_LIKE_i, (7, 6)), np.intp)
assert_type(np.ravel_multi_index(AR_LIKE_i, (7, 6), order="F"), np.intp)
assert_type(np.ravel_multi_index(AR_LIKE_i, (4, 6), mode="clip"), np.intp)
assert_type(np.ravel_multi_index(AR_LIKE_i, (4, 4), mode=("clip", "wrap")), np.intp)
assert_type(np.ravel_multi_index((3, 1, 4, 1), (6, 7, 8, 9)), np.intp)

assert_type(np.mgrid[1:1:2], npt.NDArray[Any])
assert_type(np.mgrid[1:1:2, None:10], npt.NDArray[Any])

assert_type(np.ogrid[1:1:2], tuple[npt.NDArray[Any], ...])
assert_type(np.ogrid[1:1:2, None:10], tuple[npt.NDArray[Any], ...])

assert_type(np.index_exp[0:1], tuple[slice[int, int, None]])
assert_type(np.index_exp[0:1, None:3], tuple[slice[int, int, None], slice[None, int, None]])
assert_type(np.index_exp[0, 0:1, ..., [0, 1, 3]], tuple[Literal[0], slice[int, int, None], EllipsisType, list[int]])

assert_type(np.s_[0:1], slice[int, int, None])
assert_type(np.s_[0:1, None:3], tuple[slice[int, int, None], slice[None, int, None]])
assert_type(np.s_[0, 0:1, ..., [0, 1, 3]], tuple[Literal[0], slice[int, int, None], EllipsisType, list[int]])

assert_type(np.ix_(AR_LIKE_b), tuple[npt.NDArray[np.bool], ...])
assert_type(np.ix_(AR_LIKE_i, AR_LIKE_f), tuple[npt.NDArray[np.float64], ...])
assert_type(np.ix_(AR_i8), tuple[npt.NDArray[np.int64], ...])

assert_type(np.fill_diagonal(AR_i8, 5), None)

assert_type(np.diag_indices(4), tuple[npt.NDArray[np.int_], ...])
assert_type(np.diag_indices(2, 3), tuple[npt.NDArray[np.int_], ...])

assert_type(np.diag_indices_from(AR_i8), tuple[npt.NDArray[np.int_], ...])
