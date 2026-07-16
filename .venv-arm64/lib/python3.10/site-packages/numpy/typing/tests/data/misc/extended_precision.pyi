import sys

import numpy as np
from numpy._typing import _80Bit, _96Bit, _128Bit, _256Bit

if sys.version_info >= (3, 11):
    from typing import assert_type
else:
    from typing_extensions import assert_type

assert_type(np.uint128(), np.unsignedinteger[_128Bit])
assert_type(np.uint256(), np.unsignedinteger[_256Bit])

assert_type(np.int128(), np.signedinteger[_128Bit])
assert_type(np.int256(), np.signedinteger[_256Bit])

assert_type(np.float80(), np.floating[_80Bit])
assert_type(np.float96(), np.floating[_96Bit])
assert_type(np.float128(), np.floating[_128Bit])
assert_type(np.float256(), np.floating[_256Bit])

assert_type(np.complex160(), np.complexfloating[_80Bit, _80Bit])
assert_type(np.complex192(), np.complexfloating[_96Bit, _96Bit])
assert_type(np.complex256(), np.complexfloating[_128Bit, _128Bit])
assert_type(np.complex512(), np.complexfloating[_256Bit, _256Bit])
