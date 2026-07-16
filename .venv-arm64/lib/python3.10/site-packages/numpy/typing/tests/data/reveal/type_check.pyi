from typing import Any, Literal

import numpy as np
import numpy.typing as npt
from numpy._typing import _16Bit, _32Bit, _64Bit, _128Bit

from typing_extensions import assert_type

f8: np.float64
f: float

# NOTE: Avoid importing the platform specific `np.float128` type
AR_i8: npt.NDArray[np.int64]
AR_i4: npt.NDArray[np.int32]
AR_f2: npt.NDArray[np.float16]
AR_f8: npt.NDArray[np.float64]
AR_f16: npt.NDArray[np.floating[_128Bit]]
AR_c8: npt.NDArray[np.complex64]
AR_c16: npt.NDArray[np.complex128]

AR_LIKE_f: list[float]

class ComplexObj:
    real: slice
    imag: slice

assert_type(np.mintypecode(["f8"], typeset="qfQF"), str)

assert_type(np.real(ComplexObj()), slice)
assert_type(np.real(AR_f8), npt.NDArray[np.float64])
assert_type(np.real(AR_c16), npt.NDArray[np.float64])
assert_type(np.real(AR_LIKE_f), npt.NDArray[Any])

assert_type(np.imag(ComplexObj()), slice)
assert_type(np.imag(AR_f8), npt.NDArray[np.float64])
assert_type(np.imag(AR_c16), npt.NDArray[np.float64])
assert_type(np.imag(AR_LIKE_f), npt.NDArray[Any])

assert_type(np.iscomplex(f8), np.bool)
assert_type(np.iscomplex(AR_f8), npt.NDArray[np.bool])
assert_type(np.iscomplex(AR_LIKE_f), npt.NDArray[np.bool])

assert_type(np.isreal(f8), np.bool)
assert_type(np.isreal(AR_f8), npt.NDArray[np.bool])
assert_type(np.isreal(AR_LIKE_f), npt.NDArray[np.bool])

assert_type(np.iscomplexobj(f8), bool)
assert_type(np.isrealobj(f8), bool)

assert_type(np.nan_to_num(f8), np.float64)
assert_type(np.nan_to_num(f, copy=True), Any)
assert_type(np.nan_to_num(AR_f8, nan=1.5), npt.NDArray[np.float64])
assert_type(np.nan_to_num(AR_LIKE_f, posinf=9999), npt.NDArray[Any])

assert_type(np.real_if_close(AR_f8), npt.NDArray[np.float64])
assert_type(
    np.real_if_close(AR_c16),
    npt.NDArray[np.floating[_64Bit]] | npt.NDArray[np.complexfloating[_64Bit, _64Bit]],
)
assert_type(np.real_if_close(AR_c8), npt.NDArray[np.float32] | npt.NDArray[np.complex64])
assert_type(np.real_if_close(AR_LIKE_f), npt.NDArray[Any])

assert_type(np.typename("h"), Literal["short"])
assert_type(np.typename("B"), Literal["unsigned char"])
assert_type(np.typename("V"), Literal["void"])
assert_type(np.typename("S1"), Literal["character"])

assert_type(np.common_type(AR_i4), type[np.floating[_64Bit]])
assert_type(np.common_type(AR_f2), type[np.float16])
assert_type(np.common_type(AR_f2, AR_i4), type[np.floating[_16Bit | _64Bit]])
assert_type(np.common_type(AR_f16, AR_i4), type[np.floating[_64Bit | _128Bit]])
assert_type(
    np.common_type(AR_c8, AR_f2),
    type[np.complexfloating[_16Bit | _32Bit, _16Bit | _32Bit]],
)
assert_type(
    np.common_type(AR_f2, AR_c8, AR_i4),
    type[np.complexfloating[_16Bit | _32Bit | _64Bit, _16Bit | _32Bit | _64Bit]],
)
