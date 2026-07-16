"""
Tests for miscellaneous (non-magic) ``np.ndarray``/``np.generic`` methods.

More extensive tests are performed for the methods'
function-based counterpart in `../from_numeric.py`.

"""

import numpy as np
import numpy.typing as npt

f8: np.float64
AR_f8: npt.NDArray[np.float64]
AR_M: npt.NDArray[np.datetime64]
AR_b: npt.NDArray[np.bool]

ctypes_obj = AR_f8.ctypes

f8.argpartition(0)  # E: has no attribute
f8.diagonal()  # E: has no attribute
f8.dot(1)  # E: has no attribute
f8.nonzero()  # E: has no attribute
f8.partition(0)  # E: has no attribute
f8.put(0, 2)  # E: has no attribute
f8.setfield(2, np.float64)  # E: has no attribute
f8.sort()  # E: has no attribute
f8.trace()  # E: has no attribute

AR_M.__complex__()  # E: Invalid self argument
AR_b.__index__()  # E: Invalid self argument

AR_f8[1.5]  # E: No overload variant
AR_f8["field_a"]  # E: No overload variant
AR_f8[["field_a", "field_b"]]  # E: Invalid index type

AR_f8.__array_finalize__(object())  # E: incompatible type
