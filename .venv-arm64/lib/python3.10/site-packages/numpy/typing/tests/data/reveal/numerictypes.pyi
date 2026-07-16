from typing import Literal
from typing_extensions import assert_type

import numpy as np


assert_type(
    np.ScalarType,
    tuple[
        type[int],
        type[float],
        type[complex],
        type[bool],
        type[bytes],
        type[str],
        type[memoryview],
        type[np.bool],
        type[np.csingle],
        type[np.cdouble],
        type[np.clongdouble],
        type[np.half],
        type[np.single],
        type[np.double],
        type[np.longdouble],
        type[np.byte],
        type[np.short],
        type[np.intc],
        type[np.long],
        type[np.longlong],
        type[np.timedelta64],
        type[np.datetime64],
        type[np.object_],
        type[np.bytes_],
        type[np.str_],
        type[np.ubyte],
        type[np.ushort],
        type[np.uintc],
        type[np.ulong],
        type[np.ulonglong],
        type[np.void],
    ],
)
assert_type(np.ScalarType[0], type[int])
assert_type(np.ScalarType[3], type[bool])
assert_type(np.ScalarType[8], type[np.csingle])
assert_type(np.ScalarType[10], type[np.clongdouble])
assert_type(np.bool_(object()), np.bool)

assert_type(np.typecodes["Character"], Literal["c"])
assert_type(np.typecodes["Complex"], Literal["FDG"])
assert_type(np.typecodes["All"], Literal["?bhilqnpBHILQNPefdgFDGSUVOMm"])

assert_type(np.sctypeDict['uint8'], type[np.generic])
