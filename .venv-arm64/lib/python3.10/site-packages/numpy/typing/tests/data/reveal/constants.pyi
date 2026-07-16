from typing import Literal
from typing_extensions import assert_type

import numpy as np

assert_type(np.e, float)
assert_type(np.euler_gamma, float)
assert_type(np.inf, float)
assert_type(np.nan, float)
assert_type(np.pi, float)

assert_type(np.little_endian, bool)

assert_type(np.True_, np.bool[Literal[True]])
assert_type(np.False_, np.bool[Literal[False]])
