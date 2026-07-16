from collections.abc import Callable
from typing import Any

import numpy as np
import numpy.typing as npt

AR: npt.NDArray[np.float64]
func1: Callable[[Any], str]
func2: Callable[[np.integer], str]

np.array2string(AR, style=None)  # E: No overload variant
np.array2string(AR, legacy="1.14")  # E: No overload variant
np.array2string(AR, sign="*")  # E: No overload variant
np.array2string(AR, floatmode="default")  # E: No overload variant
np.array2string(AR, formatter={"A": func1})  # E: No overload variant
np.array2string(AR, formatter={"float": func2})  # E: No overload variant
