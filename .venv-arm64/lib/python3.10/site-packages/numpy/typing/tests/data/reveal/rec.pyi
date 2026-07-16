import io
from typing import Any

import numpy as np
import numpy.typing as npt

from typing_extensions import assert_type

AR_i8: npt.NDArray[np.int64]
REC_AR_V: np.recarray[tuple[int, ...], np.dtype[np.record]]
AR_LIST: list[npt.NDArray[np.int64]]

record: np.record
file_obj: io.BufferedIOBase

assert_type(np.rec.format_parser(
    formats=[np.float64, np.int64, np.bool],
    names=["f8", "i8", "?"],
    titles=None,
    aligned=True,
), np.rec.format_parser)
assert_type(np.rec.format_parser.dtype, np.dtype[np.void])

assert_type(record.field_a, Any)
assert_type(record.field_b, Any)
assert_type(record["field_a"], Any)
assert_type(record["field_b"], Any)
assert_type(record.pprint(), str)
record.field_c = 5

assert_type(REC_AR_V.field(0), Any)
assert_type(REC_AR_V.field("field_a"), Any)
assert_type(REC_AR_V.field(0, AR_i8), None)
assert_type(REC_AR_V.field("field_a", AR_i8), None)
assert_type(REC_AR_V["field_a"], npt.NDArray[Any])
assert_type(REC_AR_V.field_a, Any)
assert_type(REC_AR_V.__array_finalize__(object()), None)

assert_type(
    np.recarray(
        shape=(10, 5),
        formats=[np.float64, np.int64, np.bool],
        order="K",
        byteorder="|",
    ),
    np.recarray[Any, np.dtype[np.record]],
)

assert_type(
    np.recarray(
        shape=(10, 5),
        dtype=[("f8", np.float64), ("i8", np.int64)],
        strides=(5, 5),
    ),
    np.recarray[Any, np.dtype[Any]],
)

assert_type(np.rec.fromarrays(AR_LIST), np.recarray[Any, np.dtype[Any]])
assert_type(
    np.rec.fromarrays(AR_LIST, dtype=np.int64),
    np.recarray[Any, np.dtype[Any]],
)
assert_type(
    np.rec.fromarrays(
        AR_LIST,
        formats=[np.int64, np.float64],
        names=["i8", "f8"]
    ),
    np.recarray[Any, np.dtype[np.record]],
)

assert_type(
    np.rec.fromrecords((1, 1.5)),
    np.recarray[Any, np.dtype[np.record]]
)

assert_type(
    np.rec.fromrecords(
        [(1, 1.5)],
        dtype=[("i8", np.int64), ("f8", np.float64)],
    ),
    np.recarray[Any, np.dtype[np.record]],
)

assert_type(
    np.rec.fromrecords(
        REC_AR_V,
        formats=[np.int64, np.float64],
        names=["i8", "f8"]
    ),
    np.recarray[Any, np.dtype[np.record]],
)

assert_type(
    np.rec.fromstring(
        b"(1, 1.5)",
        dtype=[("i8", np.int64), ("f8", np.float64)],
    ),
    np.recarray[Any, np.dtype[np.record]],
)

assert_type(
    np.rec.fromstring(
        REC_AR_V,
        formats=[np.int64, np.float64],
        names=["i8", "f8"]
    ),
    np.recarray[Any, np.dtype[np.record]],
)

assert_type(np.rec.fromfile(
    "test_file.txt",
    dtype=[("i8", np.int64), ("f8", np.float64)],
), np.recarray[Any, np.dtype[Any]])

assert_type(
    np.rec.fromfile(
        file_obj,
        formats=[np.int64, np.float64],
        names=["i8", "f8"]
    ),
    np.recarray[Any, np.dtype[np.record]],
)

assert_type(np.rec.array(AR_i8), np.recarray[Any, np.dtype[np.int64]])

assert_type(
    np.rec.array([(1, 1.5)], dtype=[("i8", np.int64), ("f8", np.float64)]),
    np.recarray[Any, np.dtype[Any]],
)

assert_type(
    np.rec.array(
        [(1, 1.5)],
        formats=[np.int64, np.float64],
        names=["i8", "f8"]
    ),
    np.recarray[Any, np.dtype[np.record]],
)

assert_type(
    np.rec.array(
        None,
        dtype=np.float64,
        shape=(10, 3),
    ),
    np.recarray[Any, np.dtype[Any]],
)

assert_type(
    np.rec.array(
        None,
        formats=[np.int64, np.float64],
        names=["i8", "f8"],
        shape=(10, 3),
    ),
    np.recarray[Any, np.dtype[np.record]],
)

assert_type(
    np.rec.array(file_obj, dtype=np.float64),
    np.recarray[Any, np.dtype[Any]],
)

assert_type(
    np.rec.array(file_obj, formats=[np.int64, np.float64], names=["i8", "f8"]),
    np.recarray[Any, np.dtype[np.record]],
)
