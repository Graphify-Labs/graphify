"""Based on the `if __name__ == "__main__"` test code in `lib/_user_array_impl.py`."""

from __future__ import annotations

import numpy as np
from numpy.lib.user_array import container

N = 10_000
W = H = int(N**0.5)

a: np.ndarray[tuple[int, int], np.dtype[np.int32]]
ua: container[tuple[int, int], np.dtype[np.int32]]

a = np.arange(N, dtype=np.int32).reshape(W, H)
ua = container(a)

ua_small: container[tuple[int, int], np.dtype[np.int32]] = ua[:3, :5]
ua_small[0, 0] = 10

ua_bool: container[tuple[int, int], np.dtype[np.bool]] = ua_small > 1

# shape: tuple[int, int] = np.shape(ua)
