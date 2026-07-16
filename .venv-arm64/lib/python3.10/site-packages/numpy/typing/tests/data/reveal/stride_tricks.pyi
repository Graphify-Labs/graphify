from typing import Any

import numpy as np
import numpy.typing as npt

from typing_extensions import assert_type

AR_f8: npt.NDArray[np.float64]
AR_LIKE_f: list[float]
interface_dict: dict[str, Any]

assert_type(np.lib.stride_tricks.as_strided(AR_f8), npt.NDArray[np.float64])
assert_type(np.lib.stride_tricks.as_strided(AR_LIKE_f), npt.NDArray[Any])
assert_type(np.lib.stride_tricks.as_strided(AR_f8, strides=(1, 5)), npt.NDArray[np.float64])
assert_type(np.lib.stride_tricks.as_strided(AR_f8, shape=[9, 20]), npt.NDArray[np.float64])

assert_type(np.lib.stride_tricks.sliding_window_view(AR_f8, 5), npt.NDArray[np.float64])
assert_type(np.lib.stride_tricks.sliding_window_view(AR_LIKE_f, (1, 5)), npt.NDArray[Any])
assert_type(np.lib.stride_tricks.sliding_window_view(AR_f8, [9], axis=1), npt.NDArray[np.float64])

assert_type(np.broadcast_to(AR_f8, 5), npt.NDArray[np.float64])
assert_type(np.broadcast_to(AR_LIKE_f, (1, 5)), npt.NDArray[Any])
assert_type(np.broadcast_to(AR_f8, [4, 6], subok=True), npt.NDArray[np.float64])

assert_type(np.broadcast_shapes((1, 2), [3, 1], (3, 2)), tuple[int, ...])
assert_type(np.broadcast_shapes((6, 7), (5, 6, 1), 7, (5, 1, 7)), tuple[int, ...])

assert_type(np.broadcast_arrays(AR_f8, AR_f8), tuple[npt.NDArray[Any], ...])
assert_type(np.broadcast_arrays(AR_f8, AR_LIKE_f), tuple[npt.NDArray[Any], ...])
