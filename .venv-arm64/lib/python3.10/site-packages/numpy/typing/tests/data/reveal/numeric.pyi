"""
Tests for :mod:`_core.numeric`.

Does not include tests which fall under ``array_constructors``.

"""

from typing import Any

import numpy as np
import numpy.typing as npt

from typing_extensions import assert_type

class SubClass(npt.NDArray[np.int64]):
    ...

i8: np.int64

AR_b: npt.NDArray[np.bool]
AR_u8: npt.NDArray[np.uint64]
AR_i8: npt.NDArray[np.int64]
AR_f8: npt.NDArray[np.float64]
AR_c16: npt.NDArray[np.complex128]
AR_m: npt.NDArray[np.timedelta64]
AR_O: npt.NDArray[np.object_]

B: list[int]
C: SubClass

assert_type(np.count_nonzero(i8), int)
assert_type(np.count_nonzero(AR_i8), int)
assert_type(np.count_nonzero(B), int)
assert_type(np.count_nonzero(AR_i8, keepdims=True), npt.NDArray[np.intp])
assert_type(np.count_nonzero(AR_i8, axis=0), Any)

assert_type(np.isfortran(i8), bool)
assert_type(np.isfortran(AR_i8), bool)

assert_type(np.argwhere(i8), npt.NDArray[np.intp])
assert_type(np.argwhere(AR_i8), npt.NDArray[np.intp])

assert_type(np.flatnonzero(i8), npt.NDArray[np.intp])
assert_type(np.flatnonzero(AR_i8), npt.NDArray[np.intp])

assert_type(np.correlate(B, AR_i8, mode="valid"), npt.NDArray[np.signedinteger[Any]])
assert_type(np.correlate(AR_i8, AR_i8, mode="same"), npt.NDArray[np.signedinteger[Any]])
assert_type(np.correlate(AR_b, AR_b), npt.NDArray[np.bool])
assert_type(np.correlate(AR_b, AR_u8), npt.NDArray[np.unsignedinteger[Any]])
assert_type(np.correlate(AR_i8, AR_b), npt.NDArray[np.signedinteger[Any]])
assert_type(np.correlate(AR_i8, AR_f8), npt.NDArray[np.floating[Any]])
assert_type(np.correlate(AR_i8, AR_c16), npt.NDArray[np.complexfloating[Any, Any]])
assert_type(np.correlate(AR_i8, AR_m), npt.NDArray[np.timedelta64])
assert_type(np.correlate(AR_O, AR_O), npt.NDArray[np.object_])

assert_type(np.convolve(B, AR_i8, mode="valid"), npt.NDArray[np.signedinteger[Any]])
assert_type(np.convolve(AR_i8, AR_i8, mode="same"), npt.NDArray[np.signedinteger[Any]])
assert_type(np.convolve(AR_b, AR_b), npt.NDArray[np.bool])
assert_type(np.convolve(AR_b, AR_u8), npt.NDArray[np.unsignedinteger[Any]])
assert_type(np.convolve(AR_i8, AR_b), npt.NDArray[np.signedinteger[Any]])
assert_type(np.convolve(AR_i8, AR_f8), npt.NDArray[np.floating[Any]])
assert_type(np.convolve(AR_i8, AR_c16), npt.NDArray[np.complexfloating[Any, Any]])
assert_type(np.convolve(AR_i8, AR_m), npt.NDArray[np.timedelta64])
assert_type(np.convolve(AR_O, AR_O), npt.NDArray[np.object_])

assert_type(np.outer(i8, AR_i8), npt.NDArray[np.signedinteger[Any]])
assert_type(np.outer(B, AR_i8), npt.NDArray[np.signedinteger[Any]])
assert_type(np.outer(AR_i8, AR_i8), npt.NDArray[np.signedinteger[Any]])
assert_type(np.outer(AR_i8, AR_i8, out=C), SubClass)
assert_type(np.outer(AR_b, AR_b), npt.NDArray[np.bool])
assert_type(np.outer(AR_b, AR_u8), npt.NDArray[np.unsignedinteger[Any]])
assert_type(np.outer(AR_i8, AR_b), npt.NDArray[np.signedinteger[Any]])
assert_type(np.convolve(AR_i8, AR_f8), npt.NDArray[np.floating[Any]])
assert_type(np.outer(AR_i8, AR_c16), npt.NDArray[np.complexfloating[Any, Any]])
assert_type(np.outer(AR_i8, AR_m), npt.NDArray[np.timedelta64])
assert_type(np.outer(AR_O, AR_O), npt.NDArray[np.object_])

assert_type(np.tensordot(B, AR_i8), npt.NDArray[np.signedinteger[Any]])
assert_type(np.tensordot(AR_i8, AR_i8), npt.NDArray[np.signedinteger[Any]])
assert_type(np.tensordot(AR_i8, AR_i8, axes=0), npt.NDArray[np.signedinteger[Any]])
assert_type(np.tensordot(AR_i8, AR_i8, axes=(0, 1)), npt.NDArray[np.signedinteger[Any]])
assert_type(np.tensordot(AR_b, AR_b), npt.NDArray[np.bool])
assert_type(np.tensordot(AR_b, AR_u8), npt.NDArray[np.unsignedinteger[Any]])
assert_type(np.tensordot(AR_i8, AR_b), npt.NDArray[np.signedinteger[Any]])
assert_type(np.tensordot(AR_i8, AR_f8), npt.NDArray[np.floating[Any]])
assert_type(np.tensordot(AR_i8, AR_c16), npt.NDArray[np.complexfloating[Any, Any]])
assert_type(np.tensordot(AR_i8, AR_m), npt.NDArray[np.timedelta64])
assert_type(np.tensordot(AR_O, AR_O), npt.NDArray[np.object_])

assert_type(np.isscalar(i8), bool)
assert_type(np.isscalar(AR_i8), bool)
assert_type(np.isscalar(B), bool)

assert_type(np.roll(AR_i8, 1), npt.NDArray[np.int64])
assert_type(np.roll(AR_i8, (1, 2)), npt.NDArray[np.int64])
assert_type(np.roll(B, 1), npt.NDArray[Any])

assert_type(np.rollaxis(AR_i8, 0, 1), npt.NDArray[np.int64])

assert_type(np.moveaxis(AR_i8, 0, 1), npt.NDArray[np.int64])
assert_type(np.moveaxis(AR_i8, (0, 1), (1, 2)), npt.NDArray[np.int64])

assert_type(np.cross(B, AR_i8), npt.NDArray[np.signedinteger[Any]])
assert_type(np.cross(AR_i8, AR_i8), npt.NDArray[np.signedinteger[Any]])
assert_type(np.cross(AR_b, AR_u8), npt.NDArray[np.unsignedinteger[Any]])
assert_type(np.cross(AR_i8, AR_b), npt.NDArray[np.signedinteger[Any]])
assert_type(np.cross(AR_i8, AR_f8), npt.NDArray[np.floating[Any]])
assert_type(np.cross(AR_i8, AR_c16), npt.NDArray[np.complexfloating[Any, Any]])
assert_type(np.cross(AR_O, AR_O), npt.NDArray[np.object_])

assert_type(np.indices([0, 1, 2]), npt.NDArray[np.int_])
assert_type(np.indices([0, 1, 2], sparse=True), tuple[npt.NDArray[np.int_], ...])
assert_type(np.indices([0, 1, 2], dtype=np.float64), npt.NDArray[np.float64])
assert_type(np.indices([0, 1, 2], sparse=True, dtype=np.float64), tuple[npt.NDArray[np.float64], ...])
assert_type(np.indices([0, 1, 2], dtype=float), npt.NDArray[Any])
assert_type(np.indices([0, 1, 2], sparse=True, dtype=float), tuple[npt.NDArray[Any], ...])

assert_type(np.binary_repr(1), str)

assert_type(np.base_repr(1), str)

assert_type(np.allclose(i8, AR_i8), bool)
assert_type(np.allclose(B, AR_i8), bool)
assert_type(np.allclose(AR_i8, AR_i8), bool)

assert_type(np.isclose(i8, i8), np.bool)
assert_type(np.isclose(i8, AR_i8), npt.NDArray[np.bool])
assert_type(np.isclose(B, AR_i8), npt.NDArray[np.bool])
assert_type(np.isclose(AR_i8, AR_i8), npt.NDArray[np.bool])

assert_type(np.array_equal(i8, AR_i8), bool)
assert_type(np.array_equal(B, AR_i8), bool)
assert_type(np.array_equal(AR_i8, AR_i8), bool)

assert_type(np.array_equiv(i8, AR_i8), bool)
assert_type(np.array_equiv(B, AR_i8), bool)
assert_type(np.array_equiv(AR_i8, AR_i8), bool)
