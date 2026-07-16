import pytest

import numpy as np
from numpy.testing import assert_array_equal


def test_matrix_transpose_raises_error_for_1d():
    msg = "matrix transpose with ndim < 2 is undefined"
    arr = np.arange(48)
    with pytest.raises(ValueError, match=msg):
        arr.mT


def test_matrix_transpose_equals_transpose_2d():
    arr = np.arange(48).reshape((6, 8))
    assert_array_equal(arr.T, arr.mT)


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
    tgt = np.swapaxes(arr, num_of_axes - 2, num_of_axes - 1)
    mT = arr.mT
    assert_array_equal(tgt, mT)


class MyArr(np.ndarray):
    def __array_wrap__(self, arr, context=None, return_scalar=None):
        return super().__array_wrap__(arr, context, return_scalar)


class MyArrNoWrap(np.ndarray):
    pass


@pytest.mark.parametrize("subclass_self", [np.ndarray, MyArr, MyArrNoWrap])
@pytest.mark.parametrize("subclass_arr", [np.ndarray, MyArr, MyArrNoWrap])
def test_array_wrap(subclass_self, subclass_arr):
    # NumPy should allow `__array_wrap__` to be called on arrays, it's logic
    # is designed in a way that:
    #
    # * Subclasses never return scalars by default (to preserve their
    #   information).  They can choose to if they wish.
    # * NumPy returns scalars, if `return_scalar` is passed as True to allow
    #   manual calls to `arr.__array_wrap__` to do the right thing.
    # * The type of the input should be ignored (it should be a base-class
    #   array, but I am not sure this is guaranteed).

    arr = np.arange(3).view(subclass_self)

    arr0d = np.array(3, dtype=np.int8).view(subclass_arr)
    # With third argument True, ndarray allows "decay" to scalar.
    # (I don't think NumPy would pass `None`, but it seems clear to support)
    if subclass_self is np.ndarray:
        assert type(arr.__array_wrap__(arr0d, None, True)) is np.int8
    else:
        assert type(arr.__array_wrap__(arr0d, None, True)) is type(arr)

    # Otherwise, result should be viewed as the subclass
    assert type(arr.__array_wrap__(arr0d)) is type(arr)
    assert type(arr.__array_wrap__(arr0d, None, None)) is type(arr)
    assert type(arr.__array_wrap__(arr0d, None, False)) is type(arr)

    # Non 0-D array can't be converted to scalar, so we ignore that
    arr1d = np.array([3], dtype=np.int8).view(subclass_arr)
    assert type(arr.__array_wrap__(arr1d, None, True)) is type(arr)
