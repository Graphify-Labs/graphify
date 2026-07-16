import numpy as np
import numpy.typing as npt

from typing_extensions import assert_type

nd: npt.NDArray[np.int64]

# reshape
assert_type(nd.reshape(None), npt.NDArray[np.int64])
assert_type(nd.reshape(4), np.ndarray[tuple[int], np.dtype[np.int64]])
assert_type(nd.reshape((4,)), np.ndarray[tuple[int], np.dtype[np.int64]])
assert_type(nd.reshape(2, 2), np.ndarray[tuple[int, int], np.dtype[np.int64]])
assert_type(nd.reshape((2, 2)), np.ndarray[tuple[int, int], np.dtype[np.int64]])

assert_type(nd.reshape((2, 2), order="C"),  np.ndarray[tuple[int, int], np.dtype[np.int64]])
assert_type(nd.reshape(4, order="C"),  np.ndarray[tuple[int], np.dtype[np.int64]])

# resize does not return a value

# transpose
assert_type(nd.transpose(), npt.NDArray[np.int64])
assert_type(nd.transpose(1, 0), npt.NDArray[np.int64])
assert_type(nd.transpose((1, 0)), npt.NDArray[np.int64])

# swapaxes
assert_type(nd.swapaxes(0, 1), npt.NDArray[np.int64])

# flatten
assert_type(nd.flatten(), np.ndarray[tuple[int], np.dtype[np.int64]])
assert_type(nd.flatten("C"), np.ndarray[tuple[int], np.dtype[np.int64]])

# ravel
assert_type(nd.ravel(), np.ndarray[tuple[int], np.dtype[np.int64]])
assert_type(nd.ravel("C"), np.ndarray[tuple[int], np.dtype[np.int64]])

# squeeze
assert_type(nd.squeeze(), npt.NDArray[np.int64])
assert_type(nd.squeeze(0), npt.NDArray[np.int64])
assert_type(nd.squeeze((0, 2)), npt.NDArray[np.int64])
