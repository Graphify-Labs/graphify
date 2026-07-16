import ctypes as ct
import datetime as dt
from decimal import Decimal
from fractions import Fraction
from typing import Any, Literal, TypeAlias

import numpy as np
from numpy.dtypes import StringDType

from typing_extensions import LiteralString, assert_type

# a combination of likely `object` dtype-like candidates (no `_co`)
_PyObjectLike: TypeAlias = Decimal | Fraction | dt.datetime | dt.timedelta

dtype_U: np.dtype[np.str_]
dtype_V: np.dtype[np.void]
dtype_i8: np.dtype[np.int64]

py_int_co: type[int | bool]
py_float_co: type[float | int | bool]
py_complex_co: type[complex | float | int | bool]
py_object: type[_PyObjectLike]
py_character: type[str | bytes]
py_flexible: type[str | bytes | memoryview]

ct_floating: type[ct.c_float | ct.c_double | ct.c_longdouble]
ct_number: type[ct.c_uint8 | ct.c_float]
ct_generic: type[ct.c_bool | ct.c_char]

cs_integer: Literal["u1", "<i2", "L"]
cs_number: Literal["=L" ,"i", "c16"]
cs_flex: Literal[">V", "S"]
cs_generic: Literal["H", "U", "h", "|M8[Y]", "?"]

dt_inexact: np.dtype[np.inexact[Any]]
dt_string: StringDType


assert_type(np.dtype(np.float64), np.dtype[np.float64])
assert_type(np.dtype(np.float64, metadata={"test": "test"}), np.dtype[np.float64])
assert_type(np.dtype(np.int64), np.dtype[np.int64])

# String aliases
assert_type(np.dtype("float64"), np.dtype[np.float64])
assert_type(np.dtype("float32"), np.dtype[np.float32])
assert_type(np.dtype("int64"), np.dtype[np.int64])
assert_type(np.dtype("int32"), np.dtype[np.int32])
assert_type(np.dtype("bool"), np.dtype[np.bool])
assert_type(np.dtype("bytes"), np.dtype[np.bytes_])
assert_type(np.dtype("str"), np.dtype[np.str_])

# Python types
assert_type(np.dtype(bool), np.dtype[np.bool])
assert_type(np.dtype(py_int_co), np.dtype[np.int_ | np.bool])
assert_type(np.dtype(int), np.dtype[np.int_ | np.bool])
assert_type(np.dtype(py_float_co), np.dtype[np.float64 | np.int_ | np.bool])
assert_type(np.dtype(float), np.dtype[np.float64 | np.int_ | np.bool])
assert_type(np.dtype(py_complex_co), np.dtype[np.complex128 | np.float64 | np.int_ | np.bool])
assert_type(np.dtype(complex), np.dtype[np.complex128 | np.float64 | np.int_ | np.bool])
assert_type(np.dtype(py_object), np.dtype[np.object_])
assert_type(np.dtype(str), np.dtype[np.str_])
assert_type(np.dtype(bytes), np.dtype[np.bytes_])
assert_type(np.dtype(py_character), np.dtype[np.character])
assert_type(np.dtype(memoryview), np.dtype[np.void])
assert_type(np.dtype(py_flexible), np.dtype[np.flexible])

assert_type(np.dtype(list), np.dtype[np.object_])
assert_type(np.dtype(dt.datetime), np.dtype[np.object_])
assert_type(np.dtype(dt.timedelta), np.dtype[np.object_])
assert_type(np.dtype(Decimal), np.dtype[np.object_])
assert_type(np.dtype(Fraction), np.dtype[np.object_])

# char-codes
assert_type(np.dtype("?"), np.dtype[np.bool])
assert_type(np.dtype("|b1"), np.dtype[np.bool])
assert_type(np.dtype("u1"), np.dtype[np.uint8])
assert_type(np.dtype("l"), np.dtype[np.long])
assert_type(np.dtype("longlong"), np.dtype[np.longlong])
assert_type(np.dtype(">g"), np.dtype[np.longdouble])
assert_type(np.dtype(cs_integer), np.dtype[np.integer[Any]])
assert_type(np.dtype(cs_number), np.dtype[np.number[Any]])
assert_type(np.dtype(cs_flex), np.dtype[np.flexible])
assert_type(np.dtype(cs_generic), np.dtype[np.generic])

# ctypes
assert_type(np.dtype(ct.c_double), np.dtype[np.double])
assert_type(np.dtype(ct.c_longlong), np.dtype[np.longlong])
assert_type(np.dtype(ct.c_uint32), np.dtype[np.uint32])
assert_type(np.dtype(ct.c_bool), np.dtype[np.bool])
assert_type(np.dtype(ct.c_char), np.dtype[np.bytes_])
assert_type(np.dtype(ct.py_object), np.dtype[np.object_])

# Special case for None
assert_type(np.dtype(None), np.dtype[np.float64])

# Dypes of dtypes
assert_type(np.dtype(np.dtype(np.float64)), np.dtype[np.float64])
assert_type(np.dtype(dt_inexact), np.dtype[np.inexact[Any]])

# Parameterized dtypes
assert_type(np.dtype("S8"), np.dtype[Any])

# Void
assert_type(np.dtype(("U", 10)), np.dtype[np.void])

# StringDType
assert_type(np.dtype(dt_string), StringDType)
assert_type(np.dtype("T"), StringDType)
assert_type(np.dtype("=T"), StringDType)
assert_type(np.dtype("|T"), StringDType)


# Methods and attributes
assert_type(dtype_U.base, np.dtype[Any])
assert_type(dtype_U.subdtype, None | tuple[np.dtype[Any], tuple[int, ...]])
assert_type(dtype_U.newbyteorder(), np.dtype[np.str_])
assert_type(dtype_U.type, type[np.str_])
assert_type(dtype_U.name, LiteralString)
assert_type(dtype_U.names, None | tuple[str, ...])

assert_type(dtype_U * 0, np.dtype[np.str_])
assert_type(dtype_U * 1, np.dtype[np.str_])
assert_type(dtype_U * 2, np.dtype[np.str_])

assert_type(dtype_i8 * 0, np.dtype[np.void])
assert_type(dtype_i8 * 1, np.dtype[np.int64])
assert_type(dtype_i8 * 2, np.dtype[np.void])

assert_type(0 * dtype_U, np.dtype[np.str_])
assert_type(1 * dtype_U, np.dtype[np.str_])
assert_type(2 * dtype_U, np.dtype[np.str_])

assert_type(0 * dtype_i8, np.dtype[Any])
assert_type(1 * dtype_i8, np.dtype[Any])
assert_type(2 * dtype_i8, np.dtype[Any])

assert_type(dtype_V["f0"], np.dtype[Any])
assert_type(dtype_V[0], np.dtype[Any])
assert_type(dtype_V[["f0", "f1"]], np.dtype[np.void])
assert_type(dtype_V[["f0"]], np.dtype[np.void])
