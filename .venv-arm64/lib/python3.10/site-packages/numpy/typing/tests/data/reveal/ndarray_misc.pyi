"""
Tests for miscellaneous (non-magic) ``np.ndarray``/``np.generic`` methods.

More extensive tests are performed for the methods'
function-based counterpart in `../from_numeric.py`.

"""

import operator
import ctypes as ct
from types import ModuleType
from typing import Any, Literal

import numpy as np
import numpy.typing as npt

from typing_extensions import CapsuleType, assert_type

class SubClass(npt.NDArray[np.object_]): ...

f8: np.float64
i8: np.int64
B: SubClass
AR_f8: npt.NDArray[np.float64]
AR_i8: npt.NDArray[np.int64]
AR_u1: npt.NDArray[np.uint8]
AR_c8: npt.NDArray[np.complex64]
AR_m: npt.NDArray[np.timedelta64]
AR_U: npt.NDArray[np.str_]
AR_V: npt.NDArray[np.void]

ctypes_obj = AR_f8.ctypes

assert_type(AR_f8.__dlpack__(), CapsuleType)
assert_type(AR_f8.__dlpack_device__(), tuple[Literal[1], Literal[0]])

assert_type(ctypes_obj.data, int)
assert_type(ctypes_obj.shape, ct.Array[np.ctypeslib.c_intp])
assert_type(ctypes_obj.strides, ct.Array[np.ctypeslib.c_intp])
assert_type(ctypes_obj._as_parameter_, ct.c_void_p)

assert_type(ctypes_obj.data_as(ct.c_void_p), ct.c_void_p)
assert_type(ctypes_obj.shape_as(ct.c_longlong), ct.Array[ct.c_longlong])
assert_type(ctypes_obj.strides_as(ct.c_ubyte), ct.Array[ct.c_ubyte])

assert_type(f8.all(), np.bool)
assert_type(AR_f8.all(), np.bool)
assert_type(AR_f8.all(axis=0), np.bool | npt.NDArray[np.bool])
assert_type(AR_f8.all(keepdims=True), np.bool | npt.NDArray[np.bool])
assert_type(AR_f8.all(out=B), SubClass)

assert_type(f8.any(), np.bool)
assert_type(AR_f8.any(), np.bool)
assert_type(AR_f8.any(axis=0), np.bool | npt.NDArray[np.bool])
assert_type(AR_f8.any(keepdims=True), np.bool | npt.NDArray[np.bool])
assert_type(AR_f8.any(out=B), SubClass)

assert_type(f8.argmax(), np.intp)
assert_type(AR_f8.argmax(), np.intp)
assert_type(AR_f8.argmax(axis=0), Any)
assert_type(AR_f8.argmax(out=B), SubClass)

assert_type(f8.argmin(), np.intp)
assert_type(AR_f8.argmin(), np.intp)
assert_type(AR_f8.argmin(axis=0), Any)
assert_type(AR_f8.argmin(out=B), SubClass)

assert_type(f8.argsort(), npt.NDArray[Any])
assert_type(AR_f8.argsort(), npt.NDArray[Any])

assert_type(f8.astype(np.int64).choose([()]), npt.NDArray[Any])
assert_type(AR_f8.choose([0]), npt.NDArray[Any])
assert_type(AR_f8.choose([0], out=B), SubClass)

assert_type(f8.clip(1), npt.NDArray[Any])
assert_type(AR_f8.clip(1), npt.NDArray[Any])
assert_type(AR_f8.clip(None, 1), npt.NDArray[Any])
assert_type(AR_f8.clip(1, out=B), SubClass)
assert_type(AR_f8.clip(None, 1, out=B), SubClass)

assert_type(f8.compress([0]), npt.NDArray[Any])
assert_type(AR_f8.compress([0]), npt.NDArray[Any])
assert_type(AR_f8.compress([0], out=B), SubClass)

assert_type(f8.conj(), np.float64)
assert_type(AR_f8.conj(), npt.NDArray[np.float64])
assert_type(B.conj(), SubClass)

assert_type(f8.conjugate(), np.float64)
assert_type(AR_f8.conjugate(), npt.NDArray[np.float64])
assert_type(B.conjugate(), SubClass)

assert_type(f8.cumprod(), npt.NDArray[Any])
assert_type(AR_f8.cumprod(), npt.NDArray[Any])
assert_type(AR_f8.cumprod(out=B), SubClass)

assert_type(f8.cumsum(), npt.NDArray[Any])
assert_type(AR_f8.cumsum(), npt.NDArray[Any])
assert_type(AR_f8.cumsum(out=B), SubClass)

assert_type(f8.max(), Any)
assert_type(AR_f8.max(), Any)
assert_type(AR_f8.max(axis=0), Any)
assert_type(AR_f8.max(keepdims=True), Any)
assert_type(AR_f8.max(out=B), SubClass)

assert_type(f8.mean(), Any)
assert_type(AR_f8.mean(), Any)
assert_type(AR_f8.mean(axis=0), Any)
assert_type(AR_f8.mean(keepdims=True), Any)
assert_type(AR_f8.mean(out=B), SubClass)

assert_type(f8.min(), Any)
assert_type(AR_f8.min(), Any)
assert_type(AR_f8.min(axis=0), Any)
assert_type(AR_f8.min(keepdims=True), Any)
assert_type(AR_f8.min(out=B), SubClass)

assert_type(f8.prod(), Any)
assert_type(AR_f8.prod(), Any)
assert_type(AR_f8.prod(axis=0), Any)
assert_type(AR_f8.prod(keepdims=True), Any)
assert_type(AR_f8.prod(out=B), SubClass)

assert_type(f8.round(), np.float64)
assert_type(AR_f8.round(), npt.NDArray[np.float64])
assert_type(AR_f8.round(out=B), SubClass)

assert_type(f8.repeat(1), npt.NDArray[np.float64])
assert_type(AR_f8.repeat(1), npt.NDArray[np.float64])
assert_type(B.repeat(1), npt.NDArray[np.object_])

assert_type(f8.std(), Any)
assert_type(AR_f8.std(), Any)
assert_type(AR_f8.std(axis=0), Any)
assert_type(AR_f8.std(keepdims=True), Any)
assert_type(AR_f8.std(out=B), SubClass)

assert_type(f8.sum(), Any)
assert_type(AR_f8.sum(), Any)
assert_type(AR_f8.sum(axis=0), Any)
assert_type(AR_f8.sum(keepdims=True), Any)
assert_type(AR_f8.sum(out=B), SubClass)

assert_type(f8.take(0), np.float64)
assert_type(AR_f8.take(0), np.float64)
assert_type(AR_f8.take([0]), npt.NDArray[np.float64])
assert_type(AR_f8.take(0, out=B), SubClass)
assert_type(AR_f8.take([0], out=B), SubClass)

assert_type(f8.var(), Any)
assert_type(AR_f8.var(), Any)
assert_type(AR_f8.var(axis=0), Any)
assert_type(AR_f8.var(keepdims=True), Any)
assert_type(AR_f8.var(out=B), SubClass)

assert_type(AR_f8.argpartition([0]), npt.NDArray[np.intp])

assert_type(AR_f8.diagonal(), npt.NDArray[np.float64])

assert_type(AR_f8.dot(1), npt.NDArray[Any])
assert_type(AR_f8.dot([1]), Any)
assert_type(AR_f8.dot(1, out=B), SubClass)

assert_type(AR_f8.nonzero(), tuple[npt.NDArray[np.intp], ...])

assert_type(AR_f8.searchsorted(1), np.intp)
assert_type(AR_f8.searchsorted([1]), npt.NDArray[np.intp])

assert_type(AR_f8.trace(), Any)
assert_type(AR_f8.trace(out=B), SubClass)

assert_type(AR_f8.item(), float)
assert_type(AR_U.item(), str)

assert_type(AR_f8.ravel(), np.ndarray[tuple[int], np.dtype[np.float64]])
assert_type(AR_U.ravel(), np.ndarray[tuple[int], np.dtype[np.str_]])

assert_type(AR_f8.flatten(), np.ndarray[tuple[int], np.dtype[np.float64]])
assert_type(AR_U.flatten(), np.ndarray[tuple[int], np.dtype[np.str_]])

assert_type(AR_i8.reshape(None), npt.NDArray[np.int64])
assert_type(AR_f8.reshape(-1), np.ndarray[tuple[int], np.dtype[np.float64]])
assert_type(AR_c8.reshape(2, 3, 4, 5), np.ndarray[tuple[int, int, int, int], np.dtype[np.complex64]])
assert_type(AR_m.reshape(()), np.ndarray[tuple[()], np.dtype[np.timedelta64]])
assert_type(AR_U.reshape([]), np.ndarray[tuple[()], np.dtype[np.str_]])
assert_type(AR_V.reshape((480, 720, 4)), np.ndarray[tuple[int, int, int], np.dtype[np.void]])

assert_type(int(AR_f8), int)
assert_type(int(AR_U), int)

assert_type(float(AR_f8), float)
assert_type(float(AR_U), float)

assert_type(complex(AR_f8), complex)

assert_type(operator.index(AR_i8), int)

assert_type(AR_f8.__array_wrap__(B), npt.NDArray[np.object_])

assert_type(AR_V[0], Any)
assert_type(AR_V[0, 0], Any)
assert_type(AR_V[AR_i8], npt.NDArray[np.void])
assert_type(AR_V[AR_i8, AR_i8], npt.NDArray[np.void])
assert_type(AR_V[AR_i8, None], npt.NDArray[np.void])
assert_type(AR_V[0, ...], npt.NDArray[np.void])
assert_type(AR_V[[0]], npt.NDArray[np.void])
assert_type(AR_V[[0], [0]], npt.NDArray[np.void])
assert_type(AR_V[:], npt.NDArray[np.void])
assert_type(AR_V["a"], npt.NDArray[Any])
assert_type(AR_V[["a", "b"]], npt.NDArray[np.void])

assert_type(AR_f8.dump("test_file"), None)
assert_type(AR_f8.dump(b"test_file"), None)
with open("test_file", "wb") as f:
    assert_type(AR_f8.dump(f), None)

assert_type(AR_f8.__array_finalize__(None), None)
assert_type(AR_f8.__array_finalize__(B), None)
assert_type(AR_f8.__array_finalize__(AR_f8), None)

assert_type(f8.device, Literal["cpu"])
assert_type(AR_f8.device, Literal["cpu"])

assert_type(f8.to_device("cpu"), np.float64)
assert_type(i8.to_device("cpu"), np.int64)
assert_type(AR_f8.to_device("cpu"), npt.NDArray[np.float64])
assert_type(AR_i8.to_device("cpu"), npt.NDArray[np.int64])
assert_type(AR_u1.to_device("cpu"), npt.NDArray[np.uint8])
assert_type(AR_c8.to_device("cpu"), npt.NDArray[np.complex64])
assert_type(AR_m.to_device("cpu"), npt.NDArray[np.timedelta64])

assert_type(f8.__array_namespace__(), ModuleType)
assert_type(AR_f8.__array_namespace__(), ModuleType)
