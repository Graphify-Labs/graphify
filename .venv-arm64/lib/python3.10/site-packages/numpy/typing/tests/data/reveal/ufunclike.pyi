from typing import Any

import numpy as np
import numpy.typing as npt

from typing_extensions import assert_type

AR_LIKE_b: list[bool]
AR_LIKE_u: list[np.uint32]
AR_LIKE_i: list[int]
AR_LIKE_f: list[float]
AR_LIKE_O: list[np.object_]

AR_U: npt.NDArray[np.str_]

assert_type(np.fix(AR_LIKE_b), npt.NDArray[np.floating[Any]])
assert_type(np.fix(AR_LIKE_u), npt.NDArray[np.floating[Any]])
assert_type(np.fix(AR_LIKE_i), npt.NDArray[np.floating[Any]])
assert_type(np.fix(AR_LIKE_f), npt.NDArray[np.floating[Any]])
assert_type(np.fix(AR_LIKE_O), npt.NDArray[np.object_])
assert_type(np.fix(AR_LIKE_f, out=AR_U), npt.NDArray[np.str_])

assert_type(np.isposinf(AR_LIKE_b), npt.NDArray[np.bool])
assert_type(np.isposinf(AR_LIKE_u), npt.NDArray[np.bool])
assert_type(np.isposinf(AR_LIKE_i), npt.NDArray[np.bool])
assert_type(np.isposinf(AR_LIKE_f), npt.NDArray[np.bool])
assert_type(np.isposinf(AR_LIKE_f, out=AR_U), npt.NDArray[np.str_])

assert_type(np.isneginf(AR_LIKE_b), npt.NDArray[np.bool])
assert_type(np.isneginf(AR_LIKE_u), npt.NDArray[np.bool])
assert_type(np.isneginf(AR_LIKE_i), npt.NDArray[np.bool])
assert_type(np.isneginf(AR_LIKE_f), npt.NDArray[np.bool])
assert_type(np.isneginf(AR_LIKE_f, out=AR_U), npt.NDArray[np.str_])
