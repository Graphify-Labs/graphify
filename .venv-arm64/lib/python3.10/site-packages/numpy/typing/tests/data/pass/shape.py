from typing import Any, NamedTuple, cast

import numpy as np


# Subtype of tuple[int, int]
class XYGrid(NamedTuple):
    x_axis: int
    y_axis: int

# TODO: remove this cast after: https://github.com/numpy/numpy/pull/27171
arr: np.ndarray[XYGrid, Any] = cast(
    np.ndarray[XYGrid, Any],
    np.empty(XYGrid(2, 2)),
)

# Test variance of _ShapeType_co
def accepts_2d(a: np.ndarray[tuple[int, int], Any]) -> None:
    return None

accepts_2d(arr)
