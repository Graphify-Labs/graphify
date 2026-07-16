from typing import Any, Literal as L, TypeAlias

import numpy as np
import numpy.typing as npt
from numpy._typing import _64Bit, _32Bit

from typing_extensions import assert_type

FalseType: TypeAlias = L[False]
TrueType: TypeAlias = L[True]

i4: np.int32
i8: np.int64

u4: np.uint32
u8: np.uint64

b_: np.bool[bool]
b0_: np.bool[FalseType]
b1_: np.bool[TrueType]

b: bool
b0: FalseType
b1: TrueType

i: int

AR: npt.NDArray[np.int32]


assert_type(i8 << i8, np.int64)
assert_type(i8 >> i8, np.int64)
assert_type(i8 | i8, np.int64)
assert_type(i8 ^ i8, np.int64)
assert_type(i8 & i8, np.int64)

assert_type(i8 << AR, npt.NDArray[np.signedinteger[Any]])
assert_type(i8 >> AR, npt.NDArray[np.signedinteger[Any]])
assert_type(i8 | AR, npt.NDArray[np.signedinteger[Any]])
assert_type(i8 ^ AR, npt.NDArray[np.signedinteger[Any]])
assert_type(i8 & AR, npt.NDArray[np.signedinteger[Any]])

assert_type(i4 << i4, np.int32)
assert_type(i4 >> i4, np.int32)
assert_type(i4 | i4, np.int32)
assert_type(i4 ^ i4, np.int32)
assert_type(i4 & i4, np.int32)

assert_type(i8 << i4, np.signedinteger[_32Bit] | np.signedinteger[_64Bit])
assert_type(i8 >> i4, np.signedinteger[_32Bit] | np.signedinteger[_64Bit])
assert_type(i8 | i4, np.signedinteger[_32Bit] | np.signedinteger[_64Bit])
assert_type(i8 ^ i4, np.signedinteger[_32Bit] | np.signedinteger[_64Bit])
assert_type(i8 & i4, np.signedinteger[_32Bit] | np.signedinteger[_64Bit])

assert_type(i8 << b_, np.int64)
assert_type(i8 >> b_, np.int64)
assert_type(i8 | b_, np.int64)
assert_type(i8 ^ b_, np.int64)
assert_type(i8 & b_, np.int64)

assert_type(i8 << b, np.int64)
assert_type(i8 >> b, np.int64)
assert_type(i8 | b, np.int64)
assert_type(i8 ^ b, np.int64)
assert_type(i8 & b, np.int64)

assert_type(u8 << u8, np.uint64)
assert_type(u8 >> u8, np.uint64)
assert_type(u8 | u8, np.uint64)
assert_type(u8 ^ u8, np.uint64)
assert_type(u8 & u8, np.uint64)

assert_type(u8 << AR, npt.NDArray[np.signedinteger[Any]])
assert_type(u8 >> AR, npt.NDArray[np.signedinteger[Any]])
assert_type(u8 | AR, npt.NDArray[np.signedinteger[Any]])
assert_type(u8 ^ AR, npt.NDArray[np.signedinteger[Any]])
assert_type(u8 & AR, npt.NDArray[np.signedinteger[Any]])

assert_type(u4 << u4, np.uint32)
assert_type(u4 >> u4, np.uint32)
assert_type(u4 | u4, np.uint32)
assert_type(u4 ^ u4, np.uint32)
assert_type(u4 & u4, np.uint32)

assert_type(u4 << i4, np.signedinteger[Any])
assert_type(u4 >> i4, np.signedinteger[Any])
assert_type(u4 | i4, np.signedinteger[Any])
assert_type(u4 ^ i4, np.signedinteger[Any])
assert_type(u4 & i4, np.signedinteger[Any])

assert_type(u4 << i, np.signedinteger[Any])
assert_type(u4 >> i, np.signedinteger[Any])
assert_type(u4 | i, np.signedinteger[Any])
assert_type(u4 ^ i, np.signedinteger[Any])
assert_type(u4 & i, np.signedinteger[Any])

assert_type(u8 << b_, np.uint64)
assert_type(u8 >> b_, np.uint64)
assert_type(u8 | b_, np.uint64)
assert_type(u8 ^ b_, np.uint64)
assert_type(u8 & b_, np.uint64)

assert_type(u8 << b, np.uint64)
assert_type(u8 >> b, np.uint64)
assert_type(u8 | b, np.uint64)
assert_type(u8 ^ b, np.uint64)
assert_type(u8 & b, np.uint64)

assert_type(b_ << b_, np.int8)
assert_type(b_ >> b_, np.int8)
assert_type(b_ | b_, np.bool)
assert_type(b_ ^ b_, np.bool)
assert_type(b_ & b_, np.bool)

assert_type(b_ << AR, npt.NDArray[np.signedinteger[Any]])
assert_type(b_ >> AR, npt.NDArray[np.signedinteger[Any]])
assert_type(b_ | AR, npt.NDArray[np.signedinteger[Any]])
assert_type(b_ ^ AR, npt.NDArray[np.signedinteger[Any]])
assert_type(b_ & AR, npt.NDArray[np.signedinteger[Any]])

assert_type(b_ << b, np.int8)
assert_type(b_ >> b, np.int8)
assert_type(b_ | b, np.bool)
assert_type(b_ ^ b, np.bool)
assert_type(b_ & b, np.bool)

assert_type(b_ << i, np.int_)
assert_type(b_ >> i, np.int_)
assert_type(b_ | i, np.bool | np.int_)
assert_type(b_ ^ i, np.bool | np.int_)
assert_type(b_ & i, np.bool | np.int_)

assert_type(~i8, np.int64)
assert_type(~i4, np.int32)
assert_type(~u8, np.uint64)
assert_type(~u4, np.uint32)
assert_type(~b_, np.bool)
assert_type(~b0_, np.bool[TrueType])
assert_type(~b1_, np.bool[FalseType])
assert_type(~AR, npt.NDArray[np.int32])

assert_type(b_ | b0_, np.bool)
assert_type(b0_ | b_, np.bool)
assert_type(b_ | b1_, np.bool[TrueType])
assert_type(b1_ | b_, np.bool[TrueType])

assert_type(b_ ^ b0_, np.bool)
assert_type(b0_ ^ b_, np.bool)
assert_type(b_ ^ b1_, np.bool)
assert_type(b1_ ^ b_, np.bool)

assert_type(b_ & b0_, np.bool[FalseType])
assert_type(b0_ & b_, np.bool[FalseType])
assert_type(b_ & b1_, np.bool)
assert_type(b1_ & b_, np.bool)

assert_type(b0_ | b0_, np.bool[FalseType])
assert_type(b0_ | b1_, np.bool[TrueType])
assert_type(b1_ | b0_, np.bool[TrueType])
assert_type(b1_ | b1_, np.bool[TrueType])

assert_type(b0_ ^ b0_, np.bool[FalseType])
assert_type(b0_ ^ b1_, np.bool[TrueType])
assert_type(b1_ ^ b0_, np.bool[TrueType])
assert_type(b1_ ^ b1_, np.bool[FalseType])

assert_type(b0_ & b0_, np.bool[FalseType])
assert_type(b0_ & b1_, np.bool[FalseType])
assert_type(b1_ & b0_, np.bool[FalseType])
assert_type(b1_ & b1_, np.bool[TrueType])
