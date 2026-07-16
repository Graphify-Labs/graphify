from typing import Any

import numpy as np
import numpy.typing as npt

from typing_extensions import assert_type

b1_0d: np.ndarray[tuple[()], np.dtype[np.bool]]
u2_1d: np.ndarray[tuple[int], np.dtype[np.uint16]]
i4_2d: np.ndarray[tuple[int, int], np.dtype[np.int32]]
f8_3d: np.ndarray[tuple[int, int, int], np.dtype[np.float64]]
cG_4d: np.ndarray[tuple[int, int, int, int], np.dtype[np.clongdouble]]
i0_nd: npt.NDArray[np.int_]
uncertain_dtype: np.int32 | np.float64 | np.str_

# item
assert_type(i0_nd.item(), int)
assert_type(i0_nd.item(1), int)
assert_type(i0_nd.item(0, 1), int)
assert_type(i0_nd.item((0, 1)), int)

assert_type(b1_0d.item(()), bool)
assert_type(u2_1d.item((0,)), int)
assert_type(i4_2d.item(-1, 2), int)
assert_type(f8_3d.item(2, 1, -1), float)
assert_type(cG_4d.item(-0xEd_fed_Deb_a_dead_bee), complex)  # c'mon Ed, we talked about this...

# tolist
assert_type(b1_0d.tolist(), bool)
assert_type(u2_1d.tolist(), list[int])
assert_type(i4_2d.tolist(), list[list[int]])
assert_type(f8_3d.tolist(), list[list[list[float]]])
assert_type(cG_4d.tolist(), Any)
assert_type(i0_nd.tolist(), Any)

# regression tests for numpy/numpy#27944
any_dtype: np.ndarray[Any, Any]
any_sctype: np.ndarray[Any, Any]
assert_type(any_dtype.tolist(), Any)
assert_type(any_sctype.tolist(), Any)


# itemset does not return a value
# tostring is pretty simple
# tobytes is pretty simple
# tofile does not return a value
# dump does not return a value
# dumps is pretty simple

# astype
assert_type(i0_nd.astype("float"), npt.NDArray[Any])
assert_type(i0_nd.astype(float), npt.NDArray[Any])
assert_type(i0_nd.astype(np.float64), npt.NDArray[np.float64])
assert_type(i0_nd.astype(np.float64, "K"), npt.NDArray[np.float64])
assert_type(i0_nd.astype(np.float64, "K", "unsafe"), npt.NDArray[np.float64])
assert_type(i0_nd.astype(np.float64, "K", "unsafe", True), npt.NDArray[np.float64])
assert_type(i0_nd.astype(np.float64, "K", "unsafe", True, True), npt.NDArray[np.float64])

assert_type(np.astype(i0_nd, np.float64), npt.NDArray[np.float64])

assert_type(i4_2d.astype(np.uint16), np.ndarray[tuple[int, int], np.dtype[np.uint16]])
assert_type(np.astype(i4_2d, np.uint16), np.ndarray[tuple[int, int], np.dtype[np.uint16]])
assert_type(f8_3d.astype(np.int16), np.ndarray[tuple[int, int, int], np.dtype[np.int16]])
assert_type(np.astype(f8_3d, np.int16), np.ndarray[tuple[int, int, int], np.dtype[np.int16]])
assert_type(i4_2d.astype(uncertain_dtype), np.ndarray[tuple[int, int], np.dtype[np.generic[Any]]])
assert_type(np.astype(i4_2d, uncertain_dtype), np.ndarray[tuple[int, int], np.dtype[Any]])

# byteswap
assert_type(i0_nd.byteswap(), npt.NDArray[np.int_])
assert_type(i0_nd.byteswap(True), npt.NDArray[np.int_])

# copy
assert_type(i0_nd.copy(), npt.NDArray[np.int_])
assert_type(i0_nd.copy("C"), npt.NDArray[np.int_])

assert_type(i0_nd.view(), npt.NDArray[np.int_])
assert_type(i0_nd.view(np.float64), npt.NDArray[np.float64])
assert_type(i0_nd.view(float), npt.NDArray[Any])
assert_type(i0_nd.view(np.float64, np.matrix), np.matrix[tuple[int, int], Any])

# getfield
assert_type(i0_nd.getfield("float"), npt.NDArray[Any])
assert_type(i0_nd.getfield(float), npt.NDArray[Any])
assert_type(i0_nd.getfield(np.float64), npt.NDArray[np.float64])
assert_type(i0_nd.getfield(np.float64, 8), npt.NDArray[np.float64])

# setflags does not return a value
# fill does not return a value
