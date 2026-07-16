import sys
import ctypes as ct
from typing import Any

import numpy as np
import numpy.typing as npt
from numpy import ctypeslib

from typing_extensions import assert_type

AR_bool: npt.NDArray[np.bool]
AR_ubyte: npt.NDArray[np.ubyte]
AR_ushort: npt.NDArray[np.ushort]
AR_uintc: npt.NDArray[np.uintc]
AR_ulong: npt.NDArray[np.ulong]
AR_ulonglong: npt.NDArray[np.ulonglong]
AR_byte: npt.NDArray[np.byte]
AR_short: npt.NDArray[np.short]
AR_intc: npt.NDArray[np.intc]
AR_long: npt.NDArray[np.long]
AR_longlong: npt.NDArray[np.longlong]
AR_single: npt.NDArray[np.single]
AR_double: npt.NDArray[np.double]
AR_longdouble: npt.NDArray[np.longdouble]
AR_void: npt.NDArray[np.void]

pointer: ct._Pointer[Any]

assert_type(np.ctypeslib.c_intp(), ctypeslib.c_intp)

assert_type(np.ctypeslib.ndpointer(), type[ctypeslib._ndptr[None]])
assert_type(np.ctypeslib.ndpointer(dtype=np.float64), type[ctypeslib._ndptr[np.dtype[np.float64]]])
assert_type(np.ctypeslib.ndpointer(dtype=float), type[ctypeslib._ndptr[np.dtype[Any]]])
assert_type(np.ctypeslib.ndpointer(shape=(10, 3)), type[ctypeslib._ndptr[None]])
assert_type(np.ctypeslib.ndpointer(np.int64, shape=(10, 3)), type[ctypeslib._concrete_ndptr[np.dtype[np.int64]]])
assert_type(np.ctypeslib.ndpointer(int, shape=(1,)), type[np.ctypeslib._concrete_ndptr[np.dtype[Any]]])

assert_type(np.ctypeslib.as_ctypes_type(np.bool), type[ct.c_bool])
assert_type(np.ctypeslib.as_ctypes_type(np.ubyte), type[ct.c_ubyte])
assert_type(np.ctypeslib.as_ctypes_type(np.ushort), type[ct.c_ushort])
assert_type(np.ctypeslib.as_ctypes_type(np.uintc), type[ct.c_uint])
assert_type(np.ctypeslib.as_ctypes_type(np.byte), type[ct.c_byte])
assert_type(np.ctypeslib.as_ctypes_type(np.short), type[ct.c_short])
assert_type(np.ctypeslib.as_ctypes_type(np.intc), type[ct.c_int])
assert_type(np.ctypeslib.as_ctypes_type(np.single), type[ct.c_float])
assert_type(np.ctypeslib.as_ctypes_type(np.double), type[ct.c_double])
assert_type(np.ctypeslib.as_ctypes_type(ct.c_double), type[ct.c_double])
assert_type(np.ctypeslib.as_ctypes_type("q"), type[ct.c_longlong])
assert_type(np.ctypeslib.as_ctypes_type([("i8", np.int64), ("f8", np.float64)]), type[Any])
assert_type(np.ctypeslib.as_ctypes_type("i8"), type[Any])
assert_type(np.ctypeslib.as_ctypes_type("f8"), type[Any])

assert_type(np.ctypeslib.as_ctypes(AR_bool.take(0)), ct.c_bool)
assert_type(np.ctypeslib.as_ctypes(AR_ubyte.take(0)), ct.c_ubyte)
assert_type(np.ctypeslib.as_ctypes(AR_ushort.take(0)), ct.c_ushort)
assert_type(np.ctypeslib.as_ctypes(AR_uintc.take(0)), ct.c_uint)

assert_type(np.ctypeslib.as_ctypes(AR_byte.take(0)), ct.c_byte)
assert_type(np.ctypeslib.as_ctypes(AR_short.take(0)), ct.c_short)
assert_type(np.ctypeslib.as_ctypes(AR_intc.take(0)), ct.c_int)
assert_type(np.ctypeslib.as_ctypes(AR_single.take(0)), ct.c_float)
assert_type(np.ctypeslib.as_ctypes(AR_double.take(0)), ct.c_double)
assert_type(np.ctypeslib.as_ctypes(AR_void.take(0)), Any)
assert_type(np.ctypeslib.as_ctypes(AR_bool), ct.Array[ct.c_bool])
assert_type(np.ctypeslib.as_ctypes(AR_ubyte), ct.Array[ct.c_ubyte])
assert_type(np.ctypeslib.as_ctypes(AR_ushort), ct.Array[ct.c_ushort])
assert_type(np.ctypeslib.as_ctypes(AR_uintc), ct.Array[ct.c_uint])
assert_type(np.ctypeslib.as_ctypes(AR_byte), ct.Array[ct.c_byte])
assert_type(np.ctypeslib.as_ctypes(AR_short), ct.Array[ct.c_short])
assert_type(np.ctypeslib.as_ctypes(AR_intc), ct.Array[ct.c_int])
assert_type(np.ctypeslib.as_ctypes(AR_single), ct.Array[ct.c_float])
assert_type(np.ctypeslib.as_ctypes(AR_double), ct.Array[ct.c_double])
assert_type(np.ctypeslib.as_ctypes(AR_void), ct.Array[Any])

assert_type(np.ctypeslib.as_array(AR_ubyte), npt.NDArray[np.ubyte])
assert_type(np.ctypeslib.as_array(1), npt.NDArray[Any])
assert_type(np.ctypeslib.as_array(pointer), npt.NDArray[Any])

if sys.platform == "win32":
    # Mainly on windows int is the same size as long but gets picked first:
    assert_type(np.ctypeslib.as_ctypes_type(np.long), type[ct.c_int])
    assert_type(np.ctypeslib.as_ctypes_type(np.ulong), type[ct.c_uint])
    assert_type(np.ctypeslib.as_ctypes(AR_ulong), ct.Array[ct.c_uint])
    assert_type(np.ctypeslib.as_ctypes(AR_long), ct.Array[ct.c_int])
    assert_type(np.ctypeslib.as_ctypes(AR_long.take(0)), ct.c_int)
    assert_type(np.ctypeslib.as_ctypes(AR_ulong.take(0)), ct.c_uint)
else:
    assert_type(np.ctypeslib.as_ctypes_type(np.long), type[ct.c_long])
    assert_type(np.ctypeslib.as_ctypes_type(np.ulong), type[ct.c_ulong])
    assert_type(np.ctypeslib.as_ctypes(AR_ulong), ct.Array[ct.c_ulong])
    assert_type(np.ctypeslib.as_ctypes(AR_long), ct.Array[ct.c_long])
    assert_type(np.ctypeslib.as_ctypes(AR_long.take(0)), ct.c_long)
    assert_type(np.ctypeslib.as_ctypes(AR_ulong.take(0)), ct.c_ulong)
