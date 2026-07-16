import datetime as dt
from typing import Any

import numpy as np
import numpy.typing as npt
from numpy._typing import _32Bit,_64Bit, _128Bit

from typing_extensions import assert_type

b: bool
c: complex
f: float
i: int

c16: np.complex128
c8: np.complex64

# Can't directly import `np.float128` as it is not available on all platforms
f16: np.floating[_128Bit]
f8: np.float64
f4: np.float32

i8: np.int64
i4: np.int32

u8: np.uint64
u4: np.uint32

b_: np.bool

M8: np.datetime64
M8_none: np.datetime64[None]
M8_date: np.datetime64[dt.date]
M8_time: np.datetime64[dt.datetime]
M8_int: np.datetime64[int]
date: dt.date
time: dt.datetime

m8: np.timedelta64
m8_none: np.timedelta64[None]
m8_int: np.timedelta64[int]
m8_delta: np.timedelta64[dt.timedelta]
delta: dt.timedelta

AR_b: npt.NDArray[np.bool]
AR_u: npt.NDArray[np.uint32]
AR_i: npt.NDArray[np.int64]
AR_f: npt.NDArray[np.float64]
AR_c: npt.NDArray[np.complex128]
AR_m: npt.NDArray[np.timedelta64]
AR_M: npt.NDArray[np.datetime64]
AR_O: npt.NDArray[np.object_]
AR_floating: npt.NDArray[np.floating]
AR_number: npt.NDArray[np.number]
AR_Any: npt.NDArray[Any]

AR_LIKE_b: list[bool]
AR_LIKE_u: list[np.uint32]
AR_LIKE_i: list[int]
AR_LIKE_f: list[float]
AR_LIKE_c: list[complex]
AR_LIKE_m: list[np.timedelta64]
AR_LIKE_M: list[np.datetime64]
AR_LIKE_O: list[np.object_]


# Array subtraction

assert_type(AR_number - AR_number, npt.NDArray[np.number[Any]])

assert_type(AR_b - AR_LIKE_u, npt.NDArray[np.uint32])
assert_type(AR_b - AR_LIKE_i, npt.NDArray[np.signedinteger[Any]])
assert_type(AR_b - AR_LIKE_f, npt.NDArray[np.floating[Any]])
assert_type(AR_b - AR_LIKE_c, npt.NDArray[np.complexfloating[Any, Any]])
assert_type(AR_b - AR_LIKE_m, npt.NDArray[np.timedelta64])
assert_type(AR_b - AR_LIKE_O, Any)

assert_type(AR_LIKE_u - AR_b, npt.NDArray[np.uint32])
assert_type(AR_LIKE_i - AR_b, npt.NDArray[np.signedinteger[Any]])
assert_type(AR_LIKE_f - AR_b, npt.NDArray[np.floating[Any]])
assert_type(AR_LIKE_c - AR_b, npt.NDArray[np.complexfloating[Any, Any]])
assert_type(AR_LIKE_m - AR_b, npt.NDArray[np.timedelta64])
assert_type(AR_LIKE_M - AR_b, npt.NDArray[np.datetime64])
assert_type(AR_LIKE_O - AR_b, Any)

assert_type(AR_u - AR_LIKE_b, npt.NDArray[np.uint32])
assert_type(AR_u - AR_LIKE_u, npt.NDArray[np.unsignedinteger[Any]])
assert_type(AR_u - AR_LIKE_i, npt.NDArray[np.signedinteger[Any]])
assert_type(AR_u - AR_LIKE_f, npt.NDArray[np.floating[Any]])
assert_type(AR_u - AR_LIKE_c, npt.NDArray[np.complexfloating[Any, Any]])
assert_type(AR_u - AR_LIKE_m, npt.NDArray[np.timedelta64])
assert_type(AR_u - AR_LIKE_O, Any)

assert_type(AR_LIKE_b - AR_u, npt.NDArray[np.uint32])
assert_type(AR_LIKE_u - AR_u, npt.NDArray[np.unsignedinteger[Any]])
assert_type(AR_LIKE_i - AR_u, npt.NDArray[np.signedinteger[Any]])
assert_type(AR_LIKE_f - AR_u, npt.NDArray[np.floating[Any]])
assert_type(AR_LIKE_c - AR_u, npt.NDArray[np.complexfloating[Any, Any]])
assert_type(AR_LIKE_m - AR_u, npt.NDArray[np.timedelta64])
assert_type(AR_LIKE_M - AR_u, npt.NDArray[np.datetime64])
assert_type(AR_LIKE_O - AR_u, Any)

assert_type(AR_i - AR_LIKE_b, npt.NDArray[np.int64])
assert_type(AR_i - AR_LIKE_u, npt.NDArray[np.signedinteger[Any]])
assert_type(AR_i - AR_LIKE_i, npt.NDArray[np.signedinteger[Any]])
assert_type(AR_i - AR_LIKE_f, npt.NDArray[np.floating[Any]])
assert_type(AR_i - AR_LIKE_c, npt.NDArray[np.complexfloating[Any, Any]])
assert_type(AR_i - AR_LIKE_m, npt.NDArray[np.timedelta64])
assert_type(AR_i - AR_LIKE_O, Any)

assert_type(AR_LIKE_b - AR_i, npt.NDArray[np.int64])
assert_type(AR_LIKE_u - AR_i, npt.NDArray[np.signedinteger[Any]])
assert_type(AR_LIKE_i - AR_i, npt.NDArray[np.signedinteger[Any]])
assert_type(AR_LIKE_f - AR_i, npt.NDArray[np.floating[Any]])
assert_type(AR_LIKE_c - AR_i, npt.NDArray[np.complexfloating[Any, Any]])
assert_type(AR_LIKE_m - AR_i, npt.NDArray[np.timedelta64])
assert_type(AR_LIKE_M - AR_i, npt.NDArray[np.datetime64])
assert_type(AR_LIKE_O - AR_i, Any)

assert_type(AR_f - AR_LIKE_b, npt.NDArray[np.float64])
assert_type(AR_f - AR_LIKE_u, npt.NDArray[np.float64])
assert_type(AR_f - AR_LIKE_i, npt.NDArray[np.float64])
assert_type(AR_f - AR_LIKE_f, npt.NDArray[np.float64])
assert_type(AR_f - AR_LIKE_c, npt.NDArray[np.complexfloating[Any, Any]])
assert_type(AR_f - AR_LIKE_O, Any)

assert_type(AR_LIKE_b - AR_f, npt.NDArray[np.float64])
assert_type(AR_LIKE_u - AR_f, npt.NDArray[np.float64])
assert_type(AR_LIKE_i - AR_f, npt.NDArray[np.float64])
assert_type(AR_LIKE_f - AR_f, npt.NDArray[np.float64])
assert_type(AR_LIKE_c - AR_f, npt.NDArray[np.complexfloating[Any, Any]])
assert_type(AR_LIKE_O - AR_f, Any)

assert_type(AR_c - AR_LIKE_b, npt.NDArray[np.complex128])
assert_type(AR_c - AR_LIKE_u, npt.NDArray[np.complex128])
assert_type(AR_c - AR_LIKE_i, npt.NDArray[np.complex128])
assert_type(AR_c - AR_LIKE_f, npt.NDArray[np.complex128])
assert_type(AR_c - AR_LIKE_c, npt.NDArray[np.complex128])
assert_type(AR_c - AR_LIKE_O, Any)

assert_type(AR_LIKE_b - AR_c, npt.NDArray[np.complex128])
assert_type(AR_LIKE_u - AR_c, npt.NDArray[np.complex128])
assert_type(AR_LIKE_i - AR_c, npt.NDArray[np.complex128])
assert_type(AR_LIKE_f - AR_c, npt.NDArray[np.complex128])
assert_type(AR_LIKE_c - AR_c, npt.NDArray[np.complex128])
assert_type(AR_LIKE_O - AR_c, Any)

assert_type(AR_m - AR_LIKE_b, npt.NDArray[np.timedelta64])
assert_type(AR_m - AR_LIKE_u, npt.NDArray[np.timedelta64])
assert_type(AR_m - AR_LIKE_i, npt.NDArray[np.timedelta64])
assert_type(AR_m - AR_LIKE_m, npt.NDArray[np.timedelta64])
assert_type(AR_m - AR_LIKE_O, Any)

assert_type(AR_LIKE_b - AR_m, npt.NDArray[np.timedelta64])
assert_type(AR_LIKE_u - AR_m, npt.NDArray[np.timedelta64])
assert_type(AR_LIKE_i - AR_m, npt.NDArray[np.timedelta64])
assert_type(AR_LIKE_m - AR_m, npt.NDArray[np.timedelta64])
assert_type(AR_LIKE_M - AR_m, npt.NDArray[np.datetime64])
assert_type(AR_LIKE_O - AR_m, Any)

assert_type(AR_M - AR_LIKE_b, npt.NDArray[np.datetime64])
assert_type(AR_M - AR_LIKE_u, npt.NDArray[np.datetime64])
assert_type(AR_M - AR_LIKE_i, npt.NDArray[np.datetime64])
assert_type(AR_M - AR_LIKE_m, npt.NDArray[np.datetime64])
assert_type(AR_M - AR_LIKE_M, npt.NDArray[np.timedelta64])
assert_type(AR_M - AR_LIKE_O, Any)

assert_type(AR_LIKE_M - AR_M, npt.NDArray[np.timedelta64])
assert_type(AR_LIKE_O - AR_M, Any)

assert_type(AR_O - AR_LIKE_b, Any)
assert_type(AR_O - AR_LIKE_u, Any)
assert_type(AR_O - AR_LIKE_i, Any)
assert_type(AR_O - AR_LIKE_f, Any)
assert_type(AR_O - AR_LIKE_c, Any)
assert_type(AR_O - AR_LIKE_m, Any)
assert_type(AR_O - AR_LIKE_M, Any)
assert_type(AR_O - AR_LIKE_O, Any)

assert_type(AR_LIKE_b - AR_O, Any)
assert_type(AR_LIKE_u - AR_O, Any)
assert_type(AR_LIKE_i - AR_O, Any)
assert_type(AR_LIKE_f - AR_O, Any)
assert_type(AR_LIKE_c - AR_O, Any)
assert_type(AR_LIKE_m - AR_O, Any)
assert_type(AR_LIKE_M - AR_O, Any)
assert_type(AR_LIKE_O - AR_O, Any)

# Array "true" division

assert_type(AR_f / b, npt.NDArray[np.float64])
assert_type(AR_f / i, npt.NDArray[np.float64])
assert_type(AR_f / f, npt.NDArray[np.float64])

assert_type(b / AR_f, npt.NDArray[np.float64])
assert_type(i / AR_f, npt.NDArray[np.float64])
assert_type(f / AR_f, npt.NDArray[np.float64])

assert_type(AR_b / AR_LIKE_b, npt.NDArray[np.float64])
assert_type(AR_b / AR_LIKE_u, npt.NDArray[np.float64])
assert_type(AR_b / AR_LIKE_i, npt.NDArray[np.float64])
assert_type(AR_b / AR_LIKE_f, npt.NDArray[np.float64])
assert_type(AR_b / AR_LIKE_O, Any)

assert_type(AR_LIKE_b / AR_b, npt.NDArray[np.float64])
assert_type(AR_LIKE_u / AR_b, npt.NDArray[np.float64])
assert_type(AR_LIKE_i / AR_b, npt.NDArray[np.float64])
assert_type(AR_LIKE_f / AR_b, npt.NDArray[np.float64])
assert_type(AR_LIKE_O / AR_b, Any)

assert_type(AR_u / AR_LIKE_b, npt.NDArray[np.float64])
assert_type(AR_u / AR_LIKE_u, npt.NDArray[np.float64])
assert_type(AR_u / AR_LIKE_i, npt.NDArray[np.float64])
assert_type(AR_u / AR_LIKE_f, npt.NDArray[np.float64])
assert_type(AR_u / AR_LIKE_O, Any)

assert_type(AR_LIKE_b / AR_u, npt.NDArray[np.float64])
assert_type(AR_LIKE_u / AR_u, npt.NDArray[np.float64])
assert_type(AR_LIKE_i / AR_u, npt.NDArray[np.float64])
assert_type(AR_LIKE_f / AR_u, npt.NDArray[np.float64])
assert_type(AR_LIKE_m / AR_u, npt.NDArray[np.timedelta64])
assert_type(AR_LIKE_O / AR_u, Any)

assert_type(AR_i / AR_LIKE_b, npt.NDArray[np.float64])
assert_type(AR_i / AR_LIKE_u, npt.NDArray[np.float64])
assert_type(AR_i / AR_LIKE_i, npt.NDArray[np.float64])
assert_type(AR_i / AR_LIKE_f, npt.NDArray[np.float64])
assert_type(AR_i / AR_LIKE_O, Any)

assert_type(AR_LIKE_b / AR_i, npt.NDArray[np.float64])
assert_type(AR_LIKE_u / AR_i, npt.NDArray[np.float64])
assert_type(AR_LIKE_i / AR_i, npt.NDArray[np.float64])
assert_type(AR_LIKE_f / AR_i, npt.NDArray[np.float64])
assert_type(AR_LIKE_m / AR_i, npt.NDArray[np.timedelta64])
assert_type(AR_LIKE_O / AR_i, Any)

assert_type(AR_f / AR_LIKE_b, npt.NDArray[np.float64])
assert_type(AR_f / AR_LIKE_u, npt.NDArray[np.float64])
assert_type(AR_f / AR_LIKE_i, npt.NDArray[np.float64])
assert_type(AR_f / AR_LIKE_f, npt.NDArray[np.float64])
assert_type(AR_f / AR_LIKE_O, Any)

assert_type(AR_LIKE_b / AR_f, npt.NDArray[np.float64])
assert_type(AR_LIKE_u / AR_f, npt.NDArray[np.float64])
assert_type(AR_LIKE_i / AR_f, npt.NDArray[np.float64])
assert_type(AR_LIKE_f / AR_f, npt.NDArray[np.float64])
assert_type(AR_LIKE_m / AR_f, npt.NDArray[np.timedelta64])
assert_type(AR_LIKE_O / AR_f, Any)

assert_type(AR_m / AR_LIKE_u, npt.NDArray[np.timedelta64])
assert_type(AR_m / AR_LIKE_i, npt.NDArray[np.timedelta64])
assert_type(AR_m / AR_LIKE_f, npt.NDArray[np.timedelta64])
assert_type(AR_m / AR_LIKE_m, npt.NDArray[np.float64])
assert_type(AR_m / AR_LIKE_O, Any)

assert_type(AR_LIKE_m / AR_m, npt.NDArray[np.float64])
assert_type(AR_LIKE_O / AR_m, Any)

assert_type(AR_O / AR_LIKE_b, Any)
assert_type(AR_O / AR_LIKE_u, Any)
assert_type(AR_O / AR_LIKE_i, Any)
assert_type(AR_O / AR_LIKE_f, Any)
assert_type(AR_O / AR_LIKE_m, Any)
assert_type(AR_O / AR_LIKE_M, Any)
assert_type(AR_O / AR_LIKE_O, Any)

assert_type(AR_LIKE_b / AR_O, Any)
assert_type(AR_LIKE_u / AR_O, Any)
assert_type(AR_LIKE_i / AR_O, Any)
assert_type(AR_LIKE_f / AR_O, Any)
assert_type(AR_LIKE_m / AR_O, Any)
assert_type(AR_LIKE_M / AR_O, Any)
assert_type(AR_LIKE_O / AR_O, Any)

# Array floor division

assert_type(AR_b // AR_LIKE_b, npt.NDArray[np.int8])
assert_type(AR_b // AR_LIKE_u, npt.NDArray[np.uint32])
assert_type(AR_b // AR_LIKE_i, npt.NDArray[np.signedinteger[Any]])
assert_type(AR_b // AR_LIKE_f, npt.NDArray[np.floating[Any]])
assert_type(AR_b // AR_LIKE_O, Any)

assert_type(AR_LIKE_b // AR_b, npt.NDArray[np.int8])
assert_type(AR_LIKE_u // AR_b, npt.NDArray[np.uint32])
assert_type(AR_LIKE_i // AR_b, npt.NDArray[np.signedinteger[Any]])
assert_type(AR_LIKE_f // AR_b, npt.NDArray[np.floating[Any]])
assert_type(AR_LIKE_O // AR_b, Any)

assert_type(AR_u // AR_LIKE_b, npt.NDArray[np.uint32])
assert_type(AR_u // AR_LIKE_u, npt.NDArray[np.unsignedinteger[Any]])
assert_type(AR_u // AR_LIKE_i, npt.NDArray[np.signedinteger[Any]])
assert_type(AR_u // AR_LIKE_f, npt.NDArray[np.floating[Any]])
assert_type(AR_u // AR_LIKE_O, Any)

assert_type(AR_LIKE_b // AR_u, npt.NDArray[np.uint32])
assert_type(AR_LIKE_u // AR_u, npt.NDArray[np.unsignedinteger[Any]])
assert_type(AR_LIKE_i // AR_u, npt.NDArray[np.signedinteger[Any]])
assert_type(AR_LIKE_f // AR_u, npt.NDArray[np.floating[Any]])
assert_type(AR_LIKE_m // AR_u, npt.NDArray[np.timedelta64])
assert_type(AR_LIKE_O // AR_u, Any)

assert_type(AR_i // AR_LIKE_b, npt.NDArray[np.int64])
assert_type(AR_i // AR_LIKE_u, npt.NDArray[np.signedinteger[Any]])
assert_type(AR_i // AR_LIKE_i, npt.NDArray[np.signedinteger[Any]])
assert_type(AR_i // AR_LIKE_f, npt.NDArray[np.floating[Any]])
assert_type(AR_i // AR_LIKE_O, Any)

assert_type(AR_LIKE_b // AR_i, npt.NDArray[np.int64])
assert_type(AR_LIKE_u // AR_i, npt.NDArray[np.signedinteger[Any]])
assert_type(AR_LIKE_i // AR_i, npt.NDArray[np.signedinteger[Any]])
assert_type(AR_LIKE_f // AR_i, npt.NDArray[np.floating[Any]])
assert_type(AR_LIKE_m // AR_i, npt.NDArray[np.timedelta64])
assert_type(AR_LIKE_O // AR_i, Any)

assert_type(AR_f // AR_LIKE_b, npt.NDArray[np.float64])
assert_type(AR_f // AR_LIKE_u, npt.NDArray[np.float64])
assert_type(AR_f // AR_LIKE_i, npt.NDArray[np.float64])
assert_type(AR_f // AR_LIKE_f, npt.NDArray[np.float64])
assert_type(AR_f // AR_LIKE_O, Any)

assert_type(AR_LIKE_b // AR_f, npt.NDArray[np.float64])
assert_type(AR_LIKE_u // AR_f, npt.NDArray[np.float64])
assert_type(AR_LIKE_i // AR_f, npt.NDArray[np.float64])
assert_type(AR_LIKE_f // AR_f, npt.NDArray[np.float64])
assert_type(AR_LIKE_m // AR_f, npt.NDArray[np.timedelta64])
assert_type(AR_LIKE_O // AR_f, Any)

assert_type(AR_m // AR_LIKE_u, npt.NDArray[np.timedelta64])
assert_type(AR_m // AR_LIKE_i, npt.NDArray[np.timedelta64])
assert_type(AR_m // AR_LIKE_f, npt.NDArray[np.timedelta64])
assert_type(AR_m // AR_LIKE_m, npt.NDArray[np.int64])
assert_type(AR_m // AR_LIKE_O, Any)

assert_type(AR_LIKE_m // AR_m, npt.NDArray[np.int64])
assert_type(AR_LIKE_O // AR_m, Any)

assert_type(AR_O // AR_LIKE_b, Any)
assert_type(AR_O // AR_LIKE_u, Any)
assert_type(AR_O // AR_LIKE_i, Any)
assert_type(AR_O // AR_LIKE_f, Any)
assert_type(AR_O // AR_LIKE_m, Any)
assert_type(AR_O // AR_LIKE_M, Any)
assert_type(AR_O // AR_LIKE_O, Any)

assert_type(AR_LIKE_b // AR_O, Any)
assert_type(AR_LIKE_u // AR_O, Any)
assert_type(AR_LIKE_i // AR_O, Any)
assert_type(AR_LIKE_f // AR_O, Any)
assert_type(AR_LIKE_m // AR_O, Any)
assert_type(AR_LIKE_M // AR_O, Any)
assert_type(AR_LIKE_O // AR_O, Any)

# unary ops

assert_type(-f16, np.floating[_128Bit])
assert_type(-c16, np.complex128)
assert_type(-c8, np.complex64)
assert_type(-f8, np.float64)
assert_type(-f4, np.float32)
assert_type(-i8, np.int64)
assert_type(-i4, np.int32)
assert_type(-u8, np.uint64)
assert_type(-u4, np.uint32)
assert_type(-m8, np.timedelta64)
assert_type(-m8_none, np.timedelta64[None])
assert_type(-m8_int, np.timedelta64[int])
assert_type(-m8_delta, np.timedelta64[dt.timedelta])
assert_type(-AR_f, npt.NDArray[np.float64])

assert_type(+f16, np.floating[_128Bit])
assert_type(+c16, np.complex128)
assert_type(+c8, np.complex64)
assert_type(+f8, np.float64)
assert_type(+f4, np.float32)
assert_type(+i8, np.int64)
assert_type(+i4, np.int32)
assert_type(+u8, np.uint64)
assert_type(+u4, np.uint32)
assert_type(+m8_none, np.timedelta64[None])
assert_type(+m8_int, np.timedelta64[int])
assert_type(+m8_delta, np.timedelta64[dt.timedelta])
assert_type(+AR_f, npt.NDArray[np.float64])

assert_type(abs(f16), np.floating[_128Bit])
assert_type(abs(c16), np.float64)
assert_type(abs(c8), np.float32)
assert_type(abs(f8), np.float64)
assert_type(abs(f4), np.float32)
assert_type(abs(i8), np.int64)
assert_type(abs(i4), np.int32)
assert_type(abs(u8), np.uint64)
assert_type(abs(u4), np.uint32)
assert_type(abs(m8), np.timedelta64)
assert_type(abs(m8_none), np.timedelta64[None])
assert_type(abs(m8_int), np.timedelta64[int])
assert_type(abs(m8_delta), np.timedelta64[dt.timedelta])
assert_type(abs(b_), np.bool)
assert_type(abs(AR_O), npt.NDArray[np.object_])

# Time structures

assert_type(M8 + m8, np.datetime64)
assert_type(M8 + i, np.datetime64)
assert_type(M8 + i8, np.datetime64)
assert_type(M8 - M8, np.timedelta64)
assert_type(M8 - i, np.datetime64)
assert_type(M8 - i8, np.datetime64)

assert_type(M8_none + m8, np.datetime64[None])
assert_type(M8_none + i, np.datetime64[None])
assert_type(M8_none + i8, np.datetime64[None])
assert_type(M8_none - M8, np.timedelta64[None])
assert_type(M8_none - m8, np.datetime64[None])
assert_type(M8_none - i, np.datetime64[None])
assert_type(M8_none - i8, np.datetime64[None])

assert_type(m8 + m8, np.timedelta64)
assert_type(m8 + i, np.timedelta64)
assert_type(m8 + i8, np.timedelta64)
assert_type(m8 - m8, np.timedelta64)
assert_type(m8 - i, np.timedelta64)
assert_type(m8 - i8, np.timedelta64)
assert_type(m8 * f, np.timedelta64)
assert_type(m8 * f4, np.timedelta64)
assert_type(m8 * np.True_, np.timedelta64)
assert_type(m8 / f, np.timedelta64)
assert_type(m8 / f4, np.timedelta64)
assert_type(m8 / m8, np.float64)
assert_type(m8 // m8, np.int64)
assert_type(m8 % m8, np.timedelta64)
assert_type(divmod(m8, m8), tuple[np.int64, np.timedelta64])

assert_type(m8_none + m8, np.timedelta64[None])
assert_type(m8_none + i, np.timedelta64[None])
assert_type(m8_none + i8, np.timedelta64[None])
assert_type(m8_none - i, np.timedelta64[None])
assert_type(m8_none - i8, np.timedelta64[None])

assert_type(m8_int + i, np.timedelta64[int])
assert_type(m8_int + m8_delta, np.timedelta64[int])
assert_type(m8_int + m8, np.timedelta64[int | None])
assert_type(m8_int - i, np.timedelta64[int])
assert_type(m8_int - m8_delta, np.timedelta64[int])
assert_type(m8_int - m8, np.timedelta64[int | None])

assert_type(m8_delta + date, dt.date)
assert_type(m8_delta + time, dt.datetime)
assert_type(m8_delta + delta, dt.timedelta)
assert_type(m8_delta - delta, dt.timedelta)
assert_type(m8_delta / delta, float)
assert_type(m8_delta // delta, int)
assert_type(m8_delta % delta, dt.timedelta)
assert_type(divmod(m8_delta, delta), tuple[int, dt.timedelta])

# boolean

assert_type(b_ / b, np.float64)
assert_type(b_ / b_, np.float64)
assert_type(b_ / i, np.float64)
assert_type(b_ / i8, np.float64)
assert_type(b_ / i4, np.float64)
assert_type(b_ / u8, np.float64)
assert_type(b_ / u4, np.float64)
assert_type(b_ / f, np.float64)
assert_type(b_ / f16, np.floating[_128Bit])
assert_type(b_ / f8, np.float64)
assert_type(b_ / f4, np.float32)
assert_type(b_ / c, np.complex128)
assert_type(b_ / c16, np.complex128)
assert_type(b_ / c8, np.complex64)

assert_type(b / b_, np.float64)
assert_type(b_ / b_, np.float64)
assert_type(i / b_, np.float64)
assert_type(i8 / b_, np.float64)
assert_type(i4 / b_, np.float64)
assert_type(u8 / b_, np.float64)
assert_type(u4 / b_, np.float64)
assert_type(f / b_, np.float64)
assert_type(f16 / b_, np.floating[_128Bit])
assert_type(f8 / b_, np.float64)
assert_type(f4 / b_, np.float32)
assert_type(c / b_, np.complex128)
assert_type(c16 / b_, np.complex128)
assert_type(c8 / b_, np.complex64)

# Complex

assert_type(c16 + f16, np.complex128 | np.complexfloating[_128Bit, _128Bit])
assert_type(c16 + c16, np.complex128)
assert_type(c16 + f8, np.complex128)
assert_type(c16 + i8, np.complex128)
assert_type(c16 + c8, np.complex128)
assert_type(c16 + f4, np.complex128)
assert_type(c16 + i4, np.complex128)
assert_type(c16 + b_, np.complex128)
assert_type(c16 + b, np.complex128)
assert_type(c16 + c, np.complex128)
assert_type(c16 + f, np.complex128)
assert_type(c16 + AR_f, npt.NDArray[np.complex128])

assert_type(f16 + c16, np.complex128 | np.complexfloating[_128Bit, _128Bit])
assert_type(c16 + c16, np.complex128)
assert_type(f8 + c16, np.complex128)
assert_type(i8 + c16, np.complex128)
assert_type(c8 + c16, np.complex128 | np.complex64)
assert_type(f4 + c16, np.complex128 | np.complex64)
assert_type(i4 + c16, np.complex128)
assert_type(b_ + c16, np.complex128)
assert_type(b + c16, np.complex128)
assert_type(c + c16, np.complex128)
assert_type(f + c16, np.complex128)
assert_type(AR_f + c16, npt.NDArray[np.complex128])

assert_type(c8 + f16, np.complexfloating[_32Bit, _32Bit] | np.complexfloating[_128Bit, _128Bit])
assert_type(c8 + c16, np.complex64 | np.complex128)
assert_type(c8 + f8, np.complex64 | np.complex128)
assert_type(c8 + i8, np.complexfloating[_32Bit, _32Bit] | np.complexfloating[_64Bit, _64Bit])
assert_type(c8 + c8, np.complex64)
assert_type(c8 + f4, np.complex64)
assert_type(c8 + i4, np.complex64)
assert_type(c8 + b_, np.complex64)
assert_type(c8 + b, np.complex64)
assert_type(c8 + c, np.complex64 | np.complex128)
assert_type(c8 + f, np.complex64 | np.complex128)
assert_type(c8 + AR_f, npt.NDArray[np.complexfloating])

assert_type(f16 + c8, np.complexfloating[_128Bit, _128Bit] | np.complex64)
assert_type(c16 + c8, np.complex128)
assert_type(f8 + c8, np.complexfloating[_64Bit, _64Bit])
assert_type(i8 + c8, np.complexfloating[_64Bit, _64Bit] | np.complex64)
assert_type(c8 + c8, np.complex64)
assert_type(f4 + c8, np.complex64)
assert_type(i4 + c8, np.complex64)
assert_type(b_ + c8, np.complex64)
assert_type(b + c8, np.complex64)
assert_type(c + c8, np.complex64 | np.complex128)
assert_type(f + c8, np.complex64 | np.complex128)
assert_type(AR_f + c8, npt.NDArray[np.complexfloating])

# Float

assert_type(f8 + f16, np.float64| np.floating[_128Bit])
assert_type(f8 + f8, np.float64)
assert_type(f8 + i8, np.float64)
assert_type(f8 + f4, np.float64)
assert_type(f8 + i4, np.float64)
assert_type(f8 + b_, np.float64)
assert_type(f8 + b, np.float64)
assert_type(f8 + c, np.float64 | np.complex128)
assert_type(f8 + f, np.float64)
assert_type(f8 + AR_f, npt.NDArray[np.float64])

assert_type(f16 + f8, np.floating[_128Bit] | np.float64)
assert_type(f8 + f8, np.float64)
assert_type(i8 + f8, np.float64)
assert_type(f4 + f8, np.float32 | np.float64)
assert_type(i4 + f8,np.float64)
assert_type(b_ + f8, np.float64)
assert_type(b + f8, np.float64)
assert_type(c + f8, np.complex128 | np.float64)
assert_type(f + f8, np.float64)
assert_type(AR_f + f8, npt.NDArray[np.float64])

assert_type(f4 + f16, np.float32 | np.floating[_128Bit])
assert_type(f4 + f8, np.float32 | np.float64)
assert_type(f4 + i8, np.float32 | np.floating[_64Bit])
assert_type(f4 + f4, np.float32)
assert_type(f4 + i4, np.float32)
assert_type(f4 + b_, np.float32)
assert_type(f4 + b, np.float32)
assert_type(f4 + c, np.complex64 | np.complex128)
assert_type(f4 + f, np.float32 | np.float64)
assert_type(f4 + AR_f, npt.NDArray[np.float64])

assert_type(f16 + f4, np.floating[_128Bit] | np.float32)
assert_type(f8 + f4, np.float64)
assert_type(i8 + f4, np.floating[_32Bit] | np.floating[_64Bit])
assert_type(f4 + f4, np.float32)
assert_type(i4 + f4, np.float32)
assert_type(b_ + f4, np.float32)
assert_type(b + f4, np.float32)
assert_type(c + f4, np.complex64 | np.complex128)
assert_type(f + f4, np.float64 | np.float32)
assert_type(AR_f + f4, npt.NDArray[np.float64])

# Int

assert_type(i8 + i8, np.int64)
assert_type(i8 + u8, Any)
assert_type(i8 + i4, np.signedinteger[_32Bit] | np.signedinteger[_64Bit])
assert_type(i8 + u4, Any)
assert_type(i8 + b_, np.int64)
assert_type(i8 + b, np.int64)
assert_type(i8 + c, np.complex128)
assert_type(i8 + f, np.float64)
assert_type(i8 + AR_f, npt.NDArray[np.float64])

assert_type(u8 + u8, np.uint64)
assert_type(u8 + i4, Any)
assert_type(u8 + u4, np.unsignedinteger[_32Bit] | np.unsignedinteger[_64Bit])
assert_type(u8 + b_, np.uint64)
assert_type(u8 + b, np.uint64)
assert_type(u8 + c, np.complex128)
assert_type(u8 + f, np.float64)
assert_type(u8 + AR_f, npt.NDArray[np.float64])

assert_type(i8 + i8, np.int64)
assert_type(u8 + i8, Any)
assert_type(i4 + i8, np.signedinteger[_32Bit] | np.signedinteger[_64Bit])
assert_type(u4 + i8, Any)
assert_type(b_ + i8, np.int64)
assert_type(b + i8, np.int64)
assert_type(c + i8, np.complex128)
assert_type(f + i8, np.float64)
assert_type(AR_f + i8, npt.NDArray[np.float64])

assert_type(u8 + u8, np.uint64)
assert_type(i4 + u8, Any)
assert_type(u4 + u8, np.unsignedinteger[_32Bit] | np.unsignedinteger[_64Bit])
assert_type(b_ + u8, np.uint64)
assert_type(b + u8, np.uint64)
assert_type(c + u8, np.complex128)
assert_type(f + u8, np.float64)
assert_type(AR_f + u8, npt.NDArray[np.float64])

assert_type(i4 + i8, np.signedinteger[_32Bit] | np.signedinteger[_64Bit])
assert_type(i4 + i4, np.int32)
assert_type(i4 + b_, np.int32)
assert_type(i4 + b, np.int32)
assert_type(i4 + AR_f, npt.NDArray[np.float64])

assert_type(u4 + i8, Any)
assert_type(u4 + i4, Any)
assert_type(u4 + u8, np.unsignedinteger[_32Bit] | np.unsignedinteger[_64Bit])
assert_type(u4 + u4, np.uint32)
assert_type(u4 + b_, np.uint32)
assert_type(u4 + b, np.uint32)
assert_type(u4 + AR_f, npt.NDArray[np.float64])

assert_type(i8 + i4, np.signedinteger[_32Bit] | np.signedinteger[_64Bit])
assert_type(i4 + i4, np.int32)
assert_type(b_ + i4, np.int32)
assert_type(b + i4, np.int32)
assert_type(AR_f + i4, npt.NDArray[np.float64])

assert_type(i8 + u4, Any)
assert_type(i4 + u4, Any)
assert_type(u8 + u4, np.unsignedinteger[_32Bit] | np.unsignedinteger[_64Bit])
assert_type(u4 + u4, np.uint32)
assert_type(b_ + u4, np.uint32)
assert_type(b + u4, np.uint32)
assert_type(AR_f + u4, npt.NDArray[np.float64])

# Any

assert_type(AR_Any + 2, npt.NDArray[Any])

# regression tests for https://github.com/numpy/numpy/issues/28805

assert_type(AR_floating + f, npt.NDArray[np.floating])
assert_type(AR_floating - f, npt.NDArray[np.floating])
assert_type(AR_floating * f, npt.NDArray[np.floating])
assert_type(AR_floating ** f, npt.NDArray[np.floating])
assert_type(AR_floating / f, npt.NDArray[np.floating])
assert_type(AR_floating // f, npt.NDArray[np.floating])
assert_type(AR_floating % f, npt.NDArray[np.floating])
assert_type(divmod(AR_floating, f), tuple[npt.NDArray[np.floating], npt.NDArray[np.floating]])

assert_type(f + AR_floating, npt.NDArray[np.floating])
assert_type(f - AR_floating, npt.NDArray[np.floating])
assert_type(f * AR_floating, npt.NDArray[np.floating])
assert_type(f ** AR_floating, npt.NDArray[np.floating])
assert_type(f / AR_floating, npt.NDArray[np.floating])
assert_type(f // AR_floating, npt.NDArray[np.floating])
assert_type(f % AR_floating, npt.NDArray[np.floating])
assert_type(divmod(f, AR_floating), tuple[npt.NDArray[np.floating], npt.NDArray[np.floating]])
