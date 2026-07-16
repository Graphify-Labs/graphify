from typing import Any

import numpy as np
import numpy.typing as npt

from typing_extensions import assert_type

nditer_obj: np.nditer

assert_type(np.nditer([0, 1], flags=["c_index"]), np.nditer)
assert_type(np.nditer([0, 1], op_flags=[["readonly", "readonly"]]), np.nditer)
assert_type(np.nditer([0, 1], op_dtypes=np.int_), np.nditer)
assert_type(np.nditer([0, 1], order="C", casting="no"), np.nditer)

assert_type(nditer_obj.dtypes, tuple[np.dtype[Any], ...])
assert_type(nditer_obj.finished, bool)
assert_type(nditer_obj.has_delayed_bufalloc, bool)
assert_type(nditer_obj.has_index, bool)
assert_type(nditer_obj.has_multi_index, bool)
assert_type(nditer_obj.index, int)
assert_type(nditer_obj.iterationneedsapi, bool)
assert_type(nditer_obj.iterindex, int)
assert_type(nditer_obj.iterrange, tuple[int, ...])
assert_type(nditer_obj.itersize, int)
assert_type(nditer_obj.itviews, tuple[npt.NDArray[Any], ...])
assert_type(nditer_obj.multi_index, tuple[int, ...])
assert_type(nditer_obj.ndim, int)
assert_type(nditer_obj.nop, int)
assert_type(nditer_obj.operands, tuple[npt.NDArray[Any], ...])
assert_type(nditer_obj.shape, tuple[int, ...])
assert_type(nditer_obj.value, tuple[npt.NDArray[Any], ...])

assert_type(nditer_obj.close(), None)
assert_type(nditer_obj.copy(), np.nditer)
assert_type(nditer_obj.debug_print(), None)
assert_type(nditer_obj.enable_external_loop(), None)
assert_type(nditer_obj.iternext(), bool)
assert_type(nditer_obj.remove_axis(0), None)
assert_type(nditer_obj.remove_multi_index(), None)
assert_type(nditer_obj.reset(), None)

assert_type(len(nditer_obj), int)
assert_type(iter(nditer_obj), np.nditer)
assert_type(next(nditer_obj), tuple[npt.NDArray[Any], ...])
assert_type(nditer_obj.__copy__(), np.nditer)
with nditer_obj as f:
    assert_type(f, np.nditer)
assert_type(nditer_obj[0], npt.NDArray[Any])
assert_type(nditer_obj[:], tuple[npt.NDArray[Any], ...])
nditer_obj[0] = 0
nditer_obj[:] = [0, 1]
