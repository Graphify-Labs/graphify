from typing import Literal

import numpy as np

from typing_extensions import Never, assert_type

info = np.__array_namespace_info__()

assert_type(info.__module__, Literal["numpy"])

assert_type(info.default_device(), Literal["cpu"])
assert_type(info.devices()[0], Literal["cpu"])
assert_type(info.devices()[-1], Literal["cpu"])

assert_type(info.capabilities()["boolean indexing"], Literal[True])
assert_type(info.capabilities()["data-dependent shapes"], Literal[True])

assert_type(info.default_dtypes()["real floating"], np.dtype[np.float64])
assert_type(info.default_dtypes()["complex floating"], np.dtype[np.complex128])
assert_type(info.default_dtypes()["integral"], np.dtype[np.int_])
assert_type(info.default_dtypes()["indexing"], np.dtype[np.intp])

assert_type(info.dtypes()["bool"], np.dtype[np.bool])
assert_type(info.dtypes()["int8"], np.dtype[np.int8])
assert_type(info.dtypes()["uint8"], np.dtype[np.uint8])
assert_type(info.dtypes()["float32"], np.dtype[np.float32])
assert_type(info.dtypes()["complex64"], np.dtype[np.complex64])

assert_type(info.dtypes(kind="bool")["bool"], np.dtype[np.bool])
assert_type(info.dtypes(kind="signed integer")["int64"], np.dtype[np.int64])
assert_type(info.dtypes(kind="unsigned integer")["uint64"], np.dtype[np.uint64])
assert_type(info.dtypes(kind="integral")["int32"], np.dtype[np.int32])
assert_type(info.dtypes(kind="integral")["uint32"], np.dtype[np.uint32])
assert_type(info.dtypes(kind="real floating")["float64"], np.dtype[np.float64])
assert_type(info.dtypes(kind="complex floating")["complex128"], np.dtype[np.complex128])
assert_type(info.dtypes(kind="numeric")["int16"], np.dtype[np.int16])
assert_type(info.dtypes(kind="numeric")["uint16"], np.dtype[np.uint16])
assert_type(info.dtypes(kind="numeric")["float64"], np.dtype[np.float64])
assert_type(info.dtypes(kind="numeric")["complex128"], np.dtype[np.complex128])

assert_type(info.dtypes(kind=()), dict[Never, Never])

assert_type(info.dtypes(kind=("bool",))["bool"], np.dtype[np.bool])
assert_type(info.dtypes(kind=("signed integer",))["int64"], np.dtype[np.int64])
assert_type(info.dtypes(kind=("integral",))["uint32"], np.dtype[np.uint32])
assert_type(info.dtypes(kind=("complex floating",))["complex128"], np.dtype[np.complex128])
assert_type(info.dtypes(kind=("numeric",))["float64"], np.dtype[np.float64])

assert_type(
    info.dtypes(kind=("signed integer", "unsigned integer"))["int8"],
    np.dtype[np.int8],
)
assert_type(
    info.dtypes(kind=("signed integer", "unsigned integer"))["uint8"],
    np.dtype[np.uint8],
)
assert_type(
    info.dtypes(kind=("integral", "real floating", "complex floating"))["int16"],
    np.dtype[np.int16],
)
assert_type(
    info.dtypes(kind=("integral", "real floating", "complex floating"))["uint16"],
    np.dtype[np.uint16],
)
assert_type(
    info.dtypes(kind=("integral", "real floating", "complex floating"))["float32"],
    np.dtype[np.float32],
)
assert_type(
    info.dtypes(kind=("integral", "real floating", "complex floating"))["complex64"],
    np.dtype[np.complex64],
)
