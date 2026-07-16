from typing import Any
from collections.abc import Generator

import numpy as np
import numpy.typing as npt

from typing_extensions import assert_type

AR_i8: npt.NDArray[np.int64]
ar_iter = np.lib.Arrayterator(AR_i8)

assert_type(ar_iter.var, npt.NDArray[np.int64])
assert_type(ar_iter.buf_size, None | int)
assert_type(ar_iter.start, list[int])
assert_type(ar_iter.stop, list[int])
assert_type(ar_iter.step, list[int])
assert_type(ar_iter.shape, tuple[int, ...])
assert_type(ar_iter.flat, Generator[np.int64, None, None])

assert_type(ar_iter.__array__(), npt.NDArray[np.int64])

for i in ar_iter:
    assert_type(i, npt.NDArray[np.int64])

assert_type(ar_iter[0], np.lib.Arrayterator[tuple[int, ...], np.dtype[np.int64]])
assert_type(ar_iter[...], np.lib.Arrayterator[tuple[int, ...], np.dtype[np.int64]])
assert_type(ar_iter[:], np.lib.Arrayterator[tuple[int, ...], np.dtype[np.int64]])
assert_type(ar_iter[0, 0, 0], np.lib.Arrayterator[tuple[int, ...], np.dtype[np.int64]])
assert_type(ar_iter[..., 0, :], np.lib.Arrayterator[tuple[int, ...], np.dtype[np.int64]])
