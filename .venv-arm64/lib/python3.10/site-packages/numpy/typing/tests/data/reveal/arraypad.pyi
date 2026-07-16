from collections.abc import Mapping
from typing import Any, SupportsIndex

import numpy as np
import numpy.typing as npt

from typing_extensions import assert_type

def mode_func(
    ar: npt.NDArray[np.number[Any]],
    width: tuple[int, int],
    iaxis: SupportsIndex,
    kwargs: Mapping[str, Any],
) -> None: ...

AR_i8: npt.NDArray[np.int64]
AR_f8: npt.NDArray[np.float64]
AR_LIKE: list[int]

assert_type(np.pad(AR_i8, (2, 3), "constant"), npt.NDArray[np.int64])
assert_type(np.pad(AR_LIKE, (2, 3), "constant"), npt.NDArray[Any])

assert_type(np.pad(AR_f8, (2, 3), mode_func), npt.NDArray[np.float64])
assert_type(np.pad(AR_f8, (2, 3), mode_func, a=1, b=2), npt.NDArray[np.float64])
