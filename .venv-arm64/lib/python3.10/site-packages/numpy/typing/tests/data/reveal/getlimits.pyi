from typing import Any

import numpy as np
from numpy._typing import _64Bit

from typing_extensions import assert_type, LiteralString

f: float
f8: np.float64
c8: np.complex64

i: int
i8: np.int64
u4: np.uint32

finfo_f8: np.finfo[np.float64]
iinfo_i8: np.iinfo[np.int64]

assert_type(np.finfo(f), np.finfo[np.float64])
assert_type(np.finfo(f8), np.finfo[np.floating[_64Bit]])
assert_type(np.finfo(c8), np.finfo[np.float32])
assert_type(np.finfo('f2'), np.finfo[np.floating[Any]])

assert_type(finfo_f8.dtype, np.dtype[np.float64])
assert_type(finfo_f8.bits, int)
assert_type(finfo_f8.eps, np.float64)
assert_type(finfo_f8.epsneg, np.float64)
assert_type(finfo_f8.iexp, int)
assert_type(finfo_f8.machep, int)
assert_type(finfo_f8.max, np.float64)
assert_type(finfo_f8.maxexp, int)
assert_type(finfo_f8.min, np.float64)
assert_type(finfo_f8.minexp, int)
assert_type(finfo_f8.negep, int)
assert_type(finfo_f8.nexp, int)
assert_type(finfo_f8.nmant, int)
assert_type(finfo_f8.precision, int)
assert_type(finfo_f8.resolution, np.float64)
assert_type(finfo_f8.tiny, np.float64)
assert_type(finfo_f8.smallest_normal, np.float64)
assert_type(finfo_f8.smallest_subnormal, np.float64)

assert_type(np.iinfo(i), np.iinfo[np.int_])
assert_type(np.iinfo(i8), np.iinfo[np.int64])
assert_type(np.iinfo(u4), np.iinfo[np.uint32])
assert_type(np.iinfo('i2'), np.iinfo[Any])

assert_type(iinfo_i8.dtype, np.dtype[np.int64])
assert_type(iinfo_i8.kind, LiteralString)
assert_type(iinfo_i8.bits, int)
assert_type(iinfo_i8.key, LiteralString)
assert_type(iinfo_i8.min, int)
assert_type(iinfo_i8.max, int)
