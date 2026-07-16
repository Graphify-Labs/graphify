import pytest

import numpy as np
from numpy.ma import masked_array
from numpy.testing import assert_array_equal


def test_matrix_transpose_raises_error_for_1d():
    msg = "matrix transpose with ndim < 2 is undefined"
    ma_arr = masked_array(data=[1, 2, 3, 4, 5, 6],
                          mask=[1, 0, 1, 1, 1, 0])
    with pytest.raises(ValueError, match=msg):
        ma_arr.mT


def test_matrix_transpose_equals_transpose_2d():
    ma_arr = masked_array(data=[[1, 2, 3], [4, 5, 6]],
                          mask=[[1, 0, 1], [1, 1, 0]])
    assert_array_equal(ma_arr.T, ma_arr.mT)


ARRAY_SHAPES_TO_TEST = (
    (5, 2),
    (5, 2, 3),
    (5, 2, 3, 4),
)


@pytest.mark.parametrize("shape", ARRAY_SHAPES_TO_TEST)
def test_matrix_transpose_equals_swapaxes(shape):
    num_of_axes = len(shape)
    vec = np.arange(shape[-1])
    arr = np.broadcast_to(vec, shape)

    rng = np.random.default_rng(42)
    mask = rng.choice([0, 1], size=shape)
    ma_arr = masked_array(data=arr, mask=mask)

    tgt = np.swapaxes(arr, num_of_axes - 2, num_of_axes - 1)
    assert_array_equal(tgt, ma_arr.mT)
