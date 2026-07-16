from __future__ import annotations

from typing import Any, TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from numpy._typing import NDArray, ArrayLike, _SupportsArray

x1: ArrayLike = True
x2: ArrayLike = 5
x3: ArrayLike = 1.0
x4: ArrayLike = 1 + 1j
x5: ArrayLike = np.int8(1)
x6: ArrayLike = np.float64(1)
x7: ArrayLike = np.complex128(1)
x8: ArrayLike = np.array([1, 2, 3])
x9: ArrayLike = [1, 2, 3]
x10: ArrayLike = (1, 2, 3)
x11: ArrayLike = "foo"
x12: ArrayLike = memoryview(b'foo')


class A:
    def __array__(
        self, dtype: None | np.dtype[Any] = None
    ) -> NDArray[np.float64]:
        return np.array([1.0, 2.0, 3.0])


x13: ArrayLike = A()

scalar: _SupportsArray[np.dtype[np.int64]] = np.int64(1)
scalar.__array__()
array: _SupportsArray[np.dtype[np.int_]] = np.array(1)
array.__array__()

a: _SupportsArray[np.dtype[np.float64]] = A()
a.__array__()
a.__array__()

# Escape hatch for when you mean to make something like an object
# array.
object_array_scalar: object = (i for i in range(10))
np.array(object_array_scalar)
