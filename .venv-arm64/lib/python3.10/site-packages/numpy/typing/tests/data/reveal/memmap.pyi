from typing import Any

import numpy as np

from typing_extensions import assert_type

memmap_obj: np.memmap[Any, np.dtype[np.str_]]

assert_type(np.memmap.__array_priority__, float)
assert_type(memmap_obj.__array_priority__, float)
assert_type(memmap_obj.filename, str | None)
assert_type(memmap_obj.offset, int)
assert_type(memmap_obj.mode, str)
assert_type(memmap_obj.flush(), None)

assert_type(np.memmap("file.txt", offset=5), np.memmap[Any, np.dtype[np.uint8]])
assert_type(np.memmap(b"file.txt", dtype=np.float64, shape=(10, 3)), np.memmap[Any, np.dtype[np.float64]])
with open("file.txt", "rb") as f:
    assert_type(np.memmap(f, dtype=float, order="K"), np.memmap[Any, np.dtype[Any]])

assert_type(memmap_obj.__array_finalize__(object()), None)
