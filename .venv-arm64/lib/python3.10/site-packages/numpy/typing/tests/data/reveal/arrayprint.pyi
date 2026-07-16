import contextlib
from collections.abc import Callable
from typing import Any

import numpy as np
import numpy.typing as npt
from numpy._core.arrayprint import _FormatOptions

from typing_extensions import assert_type

AR: npt.NDArray[np.int64]
func_float: Callable[[np.floating[Any]], str]
func_int: Callable[[np.integer[Any]], str]

assert_type(np.get_printoptions(), _FormatOptions)
assert_type(
    np.array2string(AR, formatter={'float_kind': func_float, 'int_kind': func_int}),
    str,
)
assert_type(np.format_float_scientific(1.0), str)
assert_type(np.format_float_positional(1), str)
assert_type(np.array_repr(AR), str)
assert_type(np.array_str(AR), str)

assert_type(np.printoptions(), contextlib._GeneratorContextManager[_FormatOptions])
with np.printoptions() as dct:
    assert_type(dct, _FormatOptions)
