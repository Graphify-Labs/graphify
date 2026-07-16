from typing import Any

import numpy as np
import numpy.typing as npt

from typing_extensions import assert_type

AR_i8: npt.NDArray[np.int64]
AR_f8: npt.NDArray[np.float64]

assert_type(np.histogram_bin_edges(AR_i8, bins="auto"), npt.NDArray[Any])
assert_type(np.histogram_bin_edges(AR_i8, bins="rice", range=(0, 3)), npt.NDArray[Any])
assert_type(np.histogram_bin_edges(AR_i8, bins="scott", weights=AR_f8), npt.NDArray[Any])

assert_type(np.histogram(AR_i8, bins="auto"), tuple[npt.NDArray[Any], npt.NDArray[Any]])
assert_type(np.histogram(AR_i8, bins="rice", range=(0, 3)), tuple[npt.NDArray[Any], npt.NDArray[Any]])
assert_type(np.histogram(AR_i8, bins="scott", weights=AR_f8), tuple[npt.NDArray[Any], npt.NDArray[Any]])
assert_type(np.histogram(AR_f8, bins=1, density=True), tuple[npt.NDArray[Any], npt.NDArray[Any]])

assert_type(np.histogramdd(AR_i8, bins=[1]),
            tuple[npt.NDArray[Any], tuple[npt.NDArray[Any], ...]])
assert_type(np.histogramdd(AR_i8, range=[(0, 3)]),
            tuple[npt.NDArray[Any], tuple[npt.NDArray[Any], ...]])
assert_type(np.histogramdd(AR_i8, weights=AR_f8),
            tuple[npt.NDArray[Any], tuple[npt.NDArray[Any], ...]])
assert_type(np.histogramdd(AR_f8, density=True),
            tuple[npt.NDArray[Any], tuple[npt.NDArray[Any], ...]])
