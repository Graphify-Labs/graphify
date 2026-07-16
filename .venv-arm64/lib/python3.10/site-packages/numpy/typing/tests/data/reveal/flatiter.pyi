from typing import Literal, TypeAlias

import numpy as np
import numpy.typing as npt

from typing_extensions import assert_type

a: np.flatiter[npt.NDArray[np.str_]]
a_1d: np.flatiter[np.ndarray[tuple[int], np.dtype[np.bytes_]]]

Size: TypeAlias = Literal[42]
a_1d_fixed: np.flatiter[np.ndarray[tuple[Size], np.dtype[np.object_]]]

assert_type(a.base, npt.NDArray[np.str_])
assert_type(a.copy(), npt.NDArray[np.str_])
assert_type(a.coords, tuple[int, ...])
assert_type(a.index, int)
assert_type(iter(a), np.flatiter[npt.NDArray[np.str_]])
assert_type(next(a), np.str_)
assert_type(a[0], np.str_)
assert_type(a[[0, 1, 2]], npt.NDArray[np.str_])
assert_type(a[...], npt.NDArray[np.str_])
assert_type(a[:], npt.NDArray[np.str_])
assert_type(a[(...,)], npt.NDArray[np.str_])
assert_type(a[(0,)], np.str_)

assert_type(a.__array__(), npt.NDArray[np.str_])
assert_type(a.__array__(np.dtype(np.float64)), npt.NDArray[np.float64])
assert_type(
    a_1d.__array__(),
    np.ndarray[tuple[int], np.dtype[np.bytes_]],
)
assert_type(
    a_1d.__array__(np.dtype(np.float64)),
    np.ndarray[tuple[int], np.dtype[np.float64]],
)
assert_type(
    a_1d_fixed.__array__(),
    np.ndarray[tuple[Size], np.dtype[np.object_]],
)
assert_type(
    a_1d_fixed.__array__(np.dtype(np.float64)),
    np.ndarray[tuple[Size], np.dtype[np.float64]],
)

a[0] = "a"
a[:5] = "a"
a[...] = "a"
a[(...,)] = "a"
