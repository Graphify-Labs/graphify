from typing import Any

import numpy as np
import numpy.typing as npt

from typing_extensions import assert_type

i8: np.int64
f8: np.float64

AR_b: npt.NDArray[np.bool]
AR_i8: npt.NDArray[np.int64]
AR_f8: npt.NDArray[np.float64]

AR_LIKE_f8: list[float]

assert_type(np.take_along_axis(AR_f8, AR_i8, axis=1), npt.NDArray[np.float64])
assert_type(np.take_along_axis(f8, AR_i8, axis=None), npt.NDArray[np.float64])

assert_type(np.put_along_axis(AR_f8, AR_i8, "1.0", axis=1), None)

assert_type(np.expand_dims(AR_i8, 2), npt.NDArray[np.int64])
assert_type(np.expand_dims(AR_LIKE_f8, 2), npt.NDArray[Any])

assert_type(np.column_stack([AR_i8]), npt.NDArray[np.int64])
assert_type(np.column_stack([AR_LIKE_f8]), npt.NDArray[Any])

assert_type(np.dstack([AR_i8]), npt.NDArray[np.int64])
assert_type(np.dstack([AR_LIKE_f8]), npt.NDArray[Any])

assert_type(np.array_split(AR_i8, [3, 5, 6, 10]), list[npt.NDArray[np.int64]])
assert_type(np.array_split(AR_LIKE_f8, [3, 5, 6, 10]), list[npt.NDArray[Any]])

assert_type(np.split(AR_i8, [3, 5, 6, 10]), list[npt.NDArray[np.int64]])
assert_type(np.split(AR_LIKE_f8, [3, 5, 6, 10]), list[npt.NDArray[Any]])

assert_type(np.hsplit(AR_i8, [3, 5, 6, 10]), list[npt.NDArray[np.int64]])
assert_type(np.hsplit(AR_LIKE_f8, [3, 5, 6, 10]), list[npt.NDArray[Any]])

assert_type(np.vsplit(AR_i8, [3, 5, 6, 10]), list[npt.NDArray[np.int64]])
assert_type(np.vsplit(AR_LIKE_f8, [3, 5, 6, 10]), list[npt.NDArray[Any]])

assert_type(np.dsplit(AR_i8, [3, 5, 6, 10]), list[npt.NDArray[np.int64]])
assert_type(np.dsplit(AR_LIKE_f8, [3, 5, 6, 10]), list[npt.NDArray[Any]])

assert_type(np.kron(AR_b, AR_b), npt.NDArray[np.bool])
assert_type(np.kron(AR_b, AR_i8), npt.NDArray[np.signedinteger[Any]])
assert_type(np.kron(AR_f8, AR_f8), npt.NDArray[np.floating[Any]])

assert_type(np.tile(AR_i8, 5), npt.NDArray[np.int64])
assert_type(np.tile(AR_LIKE_f8, [2, 2]), npt.NDArray[Any])

assert_type(np.unstack(AR_i8, axis=0), tuple[npt.NDArray[np.int64], ...])
assert_type(np.unstack(AR_LIKE_f8, axis=0), tuple[npt.NDArray[Any], ...])
