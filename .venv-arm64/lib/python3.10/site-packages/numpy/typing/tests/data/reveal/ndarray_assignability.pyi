from typing import Protocol, TypeAlias, TypeVar
from typing_extensions import assert_type
import numpy as np

from numpy._typing import _64Bit


_T = TypeVar("_T")
_T_co = TypeVar("_T_co", covariant=True)

class CanAbs(Protocol[_T_co]):
    def __abs__(self, /) -> _T_co: ...

class CanInvert(Protocol[_T_co]):
    def __invert__(self, /) -> _T_co: ...

class CanNeg(Protocol[_T_co]):
    def __neg__(self, /) -> _T_co: ...

class CanPos(Protocol[_T_co]):
    def __pos__(self, /) -> _T_co: ...

def do_abs(x: CanAbs[_T]) -> _T: ...
def do_invert(x: CanInvert[_T]) -> _T: ...
def do_neg(x: CanNeg[_T]) -> _T: ...
def do_pos(x: CanPos[_T]) -> _T: ...

_Bool_1d: TypeAlias = np.ndarray[tuple[int], np.dtype[np.bool]]
_UInt8_1d: TypeAlias = np.ndarray[tuple[int], np.dtype[np.uint8]]
_Int16_1d: TypeAlias = np.ndarray[tuple[int], np.dtype[np.int16]]
_LongLong_1d: TypeAlias = np.ndarray[tuple[int], np.dtype[np.longlong]]
_Float32_1d: TypeAlias = np.ndarray[tuple[int], np.dtype[np.float32]]
_Float64_1d: TypeAlias = np.ndarray[tuple[int], np.dtype[np.float64]]
_LongDouble_1d: TypeAlias = np.ndarray[tuple[int], np.dtype[np.longdouble]]
_Complex64_1d: TypeAlias = np.ndarray[tuple[int], np.dtype[np.complex64]]
_Complex128_1d: TypeAlias = np.ndarray[tuple[int], np.dtype[np.complex128]]
_CLongDouble_1d: TypeAlias = np.ndarray[tuple[int], np.dtype[np.clongdouble]]

b1_1d: _Bool_1d
u1_1d: _UInt8_1d
i2_1d: _Int16_1d
q_1d: _LongLong_1d
f4_1d: _Float32_1d
f8_1d: _Float64_1d
g_1d: _LongDouble_1d
c8_1d: _Complex64_1d
c16_1d: _Complex128_1d
G_1d: _CLongDouble_1d

assert_type(do_abs(b1_1d), _Bool_1d)
assert_type(do_abs(u1_1d), _UInt8_1d)
assert_type(do_abs(i2_1d), _Int16_1d)
assert_type(do_abs(q_1d), _LongLong_1d)
assert_type(do_abs(f4_1d), _Float32_1d)
assert_type(do_abs(f8_1d), _Float64_1d)
assert_type(do_abs(g_1d), _LongDouble_1d)

assert_type(do_abs(c8_1d), _Float32_1d)
# NOTE: Unfortunately it's not possible to have this return a `float64` sctype, see
# https://github.com/python/mypy/issues/14070
assert_type(do_abs(c16_1d), np.ndarray[tuple[int], np.dtype[np.floating[_64Bit]]])
assert_type(do_abs(G_1d), _LongDouble_1d)

assert_type(do_invert(b1_1d), _Bool_1d)
assert_type(do_invert(u1_1d), _UInt8_1d)
assert_type(do_invert(i2_1d), _Int16_1d)
assert_type(do_invert(q_1d), _LongLong_1d)

assert_type(do_neg(u1_1d), _UInt8_1d)
assert_type(do_neg(i2_1d), _Int16_1d)
assert_type(do_neg(q_1d), _LongLong_1d)
assert_type(do_neg(f4_1d), _Float32_1d)
assert_type(do_neg(c16_1d), _Complex128_1d)

assert_type(do_pos(u1_1d), _UInt8_1d)
assert_type(do_pos(i2_1d), _Int16_1d)
assert_type(do_pos(q_1d), _LongLong_1d)
assert_type(do_pos(f4_1d), _Float32_1d)
assert_type(do_pos(c16_1d), _Complex128_1d)
