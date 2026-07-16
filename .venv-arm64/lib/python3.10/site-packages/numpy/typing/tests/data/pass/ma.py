from typing import Any

import numpy as np
import numpy.ma


m : np.ma.MaskedArray[Any, np.dtype[np.float64]] = np.ma.masked_array([1.5, 2, 3], mask=[True, False, True])

