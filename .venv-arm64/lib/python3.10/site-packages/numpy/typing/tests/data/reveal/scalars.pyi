from typing import Any, Literal, TypeAlias
from typing_extensions import Unpack, assert_type

import numpy as np
import numpy.typing as npt

_1: TypeAlias = Literal[1]

b: np.bool
u8: np.uint64
i8: np.int64
f8: np.float64
c8: np.complex64
c16: np.complex128
m: np.timedelta64
U: np.str_
S: np.bytes_
V: np.void
O: np.object_  # cannot exists at runtime

array_nd: np.ndarray[Any, Any]
array_0d: np.ndarray[tuple[()], Any]
array_2d_2x2: np.ndarray[tuple[Literal[2], Literal[2]], Any]

assert_type(c8.real, np.float32)
assert_type(c8.imag, np.float32)

assert_type(c8.real.real, np.float32)
assert_type(c8.real.imag, np.float32)

assert_type(c8.itemsize, int)
assert_type(c8.shape, tuple[()])
assert_type(c8.strides, tuple[()])

assert_type(c8.ndim, Literal[0])
assert_type(c8.size, Literal[1])

assert_type(c8.squeeze(), np.complex64)
assert_type(c8.byteswap(), np.complex64)
assert_type(c8.transpose(), np.complex64)

assert_type(c8.dtype, np.dtype[np.complex64])

assert_type(c8.real, np.float32)
assert_type(c16.imag, np.float64)

assert_type(np.str_('foo'), np.str_)

assert_type(V[0], Any)
assert_type(V["field1"], Any)
assert_type(V[["field1", "field2"]], np.void)
V[0] = 5

# Aliases
assert_type(np.bool_(), np.bool[Literal[False]])
assert_type(np.byte(), np.byte)
assert_type(np.short(), np.short)
assert_type(np.intc(), np.intc)
assert_type(np.intp(), np.intp)
assert_type(np.int_(), np.int_)
assert_type(np.long(), np.long)
assert_type(np.longlong(), np.longlong)

assert_type(np.ubyte(), np.ubyte)
assert_type(np.ushort(), np.ushort)
assert_type(np.uintc(), np.uintc)
assert_type(np.uintp(), np.uintp)
assert_type(np.uint(), np.uint)
assert_type(np.ulong(), np.ulong)
assert_type(np.ulonglong(), np.ulonglong)

assert_type(np.half(), np.half)
assert_type(np.single(), np.single)
assert_type(np.double(), np.double)
assert_type(np.longdouble(), np.longdouble)

assert_type(np.csingle(), np.csingle)
assert_type(np.cdouble(), np.cdouble)
assert_type(np.clongdouble(), np.clongdouble)

assert_type(b.item(), bool)
assert_type(i8.item(), int)
assert_type(u8.item(), int)
assert_type(f8.item(), float)
assert_type(c16.item(), complex)
assert_type(U.item(), str)
assert_type(S.item(), bytes)

assert_type(b.tolist(), bool)
assert_type(i8.tolist(), int)
assert_type(u8.tolist(), int)
assert_type(f8.tolist(), float)
assert_type(c16.tolist(), complex)
assert_type(U.tolist(), str)
assert_type(S.tolist(), bytes)

assert_type(b.ravel(), np.ndarray[tuple[int], np.dtype[np.bool]])
assert_type(i8.ravel(), np.ndarray[tuple[int], np.dtype[np.int64]])
assert_type(u8.ravel(), np.ndarray[tuple[int], np.dtype[np.uint64]])
assert_type(f8.ravel(), np.ndarray[tuple[int], np.dtype[np.float64]])
assert_type(c16.ravel(), np.ndarray[tuple[int], np.dtype[np.complex128]])
assert_type(U.ravel(), np.ndarray[tuple[int], np.dtype[np.str_]])
assert_type(S.ravel(), np.ndarray[tuple[int], np.dtype[np.bytes_]])

assert_type(b.flatten(), np.ndarray[tuple[int], np.dtype[np.bool]])
assert_type(i8.flatten(), np.ndarray[tuple[int], np.dtype[np.int64]])
assert_type(u8.flatten(), np.ndarray[tuple[int], np.dtype[np.uint64]])
assert_type(f8.flatten(), np.ndarray[tuple[int], np.dtype[np.float64]])
assert_type(c16.flatten(), np.ndarray[tuple[int], np.dtype[np.complex128]])
assert_type(U.flatten(), np.ndarray[tuple[int], np.dtype[np.str_]])
assert_type(S.flatten(), np.ndarray[tuple[int], np.dtype[np.bytes_]])

assert_type(b.reshape(()), np.bool)
assert_type(i8.reshape([]), np.int64)
assert_type(b.reshape(1), np.ndarray[tuple[_1], np.dtype[np.bool]])
assert_type(i8.reshape(-1), np.ndarray[tuple[_1], np.dtype[np.int64]])
assert_type(u8.reshape(1, 1), np.ndarray[tuple[_1, _1], np.dtype[np.uint64]])
assert_type(f8.reshape(1, -1), np.ndarray[tuple[_1, _1], np.dtype[np.float64]])
assert_type(c16.reshape(1, 1, 1), np.ndarray[tuple[_1, _1, _1], np.dtype[np.complex128]])
assert_type(U.reshape(1, 1, 1, 1), np.ndarray[tuple[_1, _1, _1, _1], np.dtype[np.str_]])
assert_type(
    S.reshape(1, 1, 1, 1, 1),
    np.ndarray[
        # len(shape) >= 5
        tuple[_1, _1, _1, _1, _1, Unpack[tuple[_1, ...]]],
        np.dtype[np.bytes_],
    ],
)

assert_type(i8.astype(float), Any)
assert_type(i8.astype(np.float64), np.float64)

assert_type(i8.view(), np.int64)
assert_type(i8.view(np.float64), np.float64)
assert_type(i8.view(float), Any)
assert_type(i8.view(np.float64, np.ndarray), np.float64)

assert_type(i8.getfield(float), Any)
assert_type(i8.getfield(np.float64), np.float64)
assert_type(i8.getfield(np.float64, 8), np.float64)

assert_type(f8.as_integer_ratio(), tuple[int, int])
assert_type(f8.is_integer(), bool)
assert_type(f8.__trunc__(), int)
assert_type(f8.__getformat__("float"), str)
assert_type(f8.hex(), str)
assert_type(np.float64.fromhex("0x0.0p+0"), np.float64)

assert_type(f8.__getnewargs__(), tuple[float])
assert_type(c16.__getnewargs__(), tuple[float, float])

assert_type(i8.numerator, np.int64)
assert_type(i8.denominator, Literal[1])
assert_type(u8.numerator, np.uint64)
assert_type(u8.denominator, Literal[1])
assert_type(m.numerator, np.timedelta64)
assert_type(m.denominator, Literal[1])

assert_type(round(i8), int)
assert_type(round(i8, 3), np.int64)
assert_type(round(u8), int)
assert_type(round(u8, 3), np.uint64)
assert_type(round(f8), int)
assert_type(round(f8, 3), np.float64)

assert_type(f8.__ceil__(), int)
assert_type(f8.__floor__(), int)

assert_type(i8.is_integer(), Literal[True])

assert_type(O.real, np.object_)
assert_type(O.imag, np.object_)
assert_type(int(O), int)
assert_type(float(O), float)
assert_type(complex(O), complex)

# These fail fail because of a mypy __new__ bug:
# https://github.com/python/mypy/issues/15182
# According to the typing spec, the following statements are valid, see
# https://typing.readthedocs.io/en/latest/spec/constructors.html#new-method

# assert_type(np.object_(), None)
# assert_type(np.object_(None), None)
# assert_type(np.object_(array_nd), np.ndarray[Any, np.dtype[np.object_]])
# assert_type(np.object_([]), npt.NDArray[np.object_])
# assert_type(np.object_(()), npt.NDArray[np.object_])
# assert_type(np.object_(range(4)), npt.NDArray[np.object_])
# assert_type(np.object_(+42), int)
# assert_type(np.object_(1 / 137), float)
# assert_type(np.object_('Developers! ' * (1 << 6)), str)
# assert_type(np.object_(object()), object)
# assert_type(np.object_({False, True, NotADirectoryError}), set[Any])
# assert_type(np.object_({'spam': 'food', 'ham': 'food'}), dict[str, str])
