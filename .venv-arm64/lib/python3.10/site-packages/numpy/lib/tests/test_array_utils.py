import numpy as np

from numpy.lib import array_utils
from numpy.testing import assert_equal


class TestByteBounds:
    def test_byte_bounds(self):
        # pointer difference matches size * itemsize
        # due to contiguity
        a = np.arange(12).reshape(3, 4)
        low, high = array_utils.byte_bounds(a)
        assert_equal(high - low, a.size * a.itemsize)

    def test_unusual_order_positive_stride(self):
        a = np.arange(12).reshape(3, 4)
        b = a.T
        low, high = array_utils.byte_bounds(b)
        assert_equal(high - low, b.size * b.itemsize)

    def test_unusual_order_negative_stride(self):
        a = np.arange(12).reshape(3, 4)
        b = a.T[::-1]
        low, high = array_utils.byte_bounds(b)
        assert_equal(high - low, b.size * b.itemsize)

    def test_strided(self):
        a = np.arange(12)
        b = a[::2]
        low, high = array_utils.byte_bounds(b)
        # the largest pointer address is lost (even numbers only in the
        # stride), and compensate addresses for striding by 2
        assert_equal(high - low, b.size * 2 * b.itemsize - b.itemsize)
