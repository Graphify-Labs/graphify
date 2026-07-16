from typing import Any, TypeVar

import numpy as np
import numpy.typing as npt

from typing_extensions import assert_type

_SCT = TypeVar("_SCT", bound=np.generic)


def func1(ar: npt.NDArray[_SCT], a: int) -> npt.NDArray[_SCT]:
    pass


def func2(ar: npt.NDArray[np.number[Any]], a: str) -> npt.NDArray[np.float64]:
    pass


AR_b: npt.NDArray[np.bool]
AR_u: npt.NDArray[np.uint64]
AR_i: npt.NDArray[np.int64]
AR_f: npt.NDArray[np.float64]
AR_c: npt.NDArray[np.complex128]
AR_O: npt.NDArray[np.object_]

AR_LIKE_b: list[bool]
AR_LIKE_c: list[complex]

assert_type(np.fliplr(AR_b), npt.NDArray[np.bool])
assert_type(np.fliplr(AR_LIKE_b), npt.NDArray[Any])

assert_type(np.flipud(AR_b), npt.NDArray[np.bool])
assert_type(np.flipud(AR_LIKE_b), npt.NDArray[Any])

assert_type(np.eye(10), npt.NDArray[np.float64])
assert_type(np.eye(10, M=20, dtype=np.int64), npt.NDArray[np.int64])
assert_type(np.eye(10, k=2, dtype=int), npt.NDArray[Any])

assert_type(np.diag(AR_b), npt.NDArray[np.bool])
assert_type(np.diag(AR_LIKE_b, k=0), npt.NDArray[Any])

assert_type(np.diagflat(AR_b), npt.NDArray[np.bool])
assert_type(np.diagflat(AR_LIKE_b, k=0), npt.NDArray[Any])

assert_type(np.tri(10), npt.NDArray[np.float64])
assert_type(np.tri(10, M=20, dtype=np.int64), npt.NDArray[np.int64])
assert_type(np.tri(10, k=2, dtype=int), npt.NDArray[Any])

assert_type(np.tril(AR_b), npt.NDArray[np.bool])
assert_type(np.tril(AR_LIKE_b, k=0), npt.NDArray[Any])

assert_type(np.triu(AR_b), npt.NDArray[np.bool])
assert_type(np.triu(AR_LIKE_b, k=0), npt.NDArray[Any])

assert_type(np.vander(AR_b), npt.NDArray[np.signedinteger[Any]])
assert_type(np.vander(AR_u), npt.NDArray[np.signedinteger[Any]])
assert_type(np.vander(AR_i, N=2), npt.NDArray[np.signedinteger[Any]])
assert_type(np.vander(AR_f, increasing=True), npt.NDArray[np.floating[Any]])
assert_type(np.vander(AR_c), npt.NDArray[np.complexfloating[Any, Any]])
assert_type(np.vander(AR_O), npt.NDArray[np.object_])

assert_type(
    np.histogram2d(AR_LIKE_c, AR_LIKE_c),
    tuple[
        npt.NDArray[np.float64],
        npt.NDArray[np.complex128 | np.float64],
        npt.NDArray[np.complex128 | np.float64],
    ],
)
assert_type(
    np.histogram2d(AR_i, AR_b),
    tuple[
        npt.NDArray[np.float64],
        npt.NDArray[np.float64],
        npt.NDArray[np.float64],
    ],
)
assert_type(
    np.histogram2d(AR_f, AR_i),
    tuple[
        npt.NDArray[np.float64],
        npt.NDArray[np.float64],
        npt.NDArray[np.float64],
    ],
)
assert_type(
    np.histogram2d(AR_i, AR_f),
    tuple[
        npt.NDArray[np.float64],
        npt.NDArray[np.float64],
        npt.NDArray[np.float64],
    ],
)
assert_type(
    np.histogram2d(AR_f, AR_c, weights=AR_LIKE_b),
    tuple[
        npt.NDArray[np.float64],
        npt.NDArray[np.complex128],
        npt.NDArray[np.complex128],
    ],
)
assert_type(
    np.histogram2d(AR_f, AR_c, bins=8),
    tuple[
        npt.NDArray[np.float64],
        npt.NDArray[np.complex128],
        npt.NDArray[np.complex128],
    ],
)
assert_type(
    np.histogram2d(AR_c, AR_f, bins=(8, 5)),
    tuple[
        npt.NDArray[np.float64],
        npt.NDArray[np.complex128],
        npt.NDArray[np.complex128],
    ],
)
assert_type(
    np.histogram2d(AR_c, AR_i, bins=AR_u),
    tuple[
        npt.NDArray[np.float64],
        npt.NDArray[np.uint64],
        npt.NDArray[np.uint64],
    ],
)
assert_type(
    np.histogram2d(AR_c, AR_c, bins=(AR_u, AR_u)),
    tuple[
        npt.NDArray[np.float64],
        npt.NDArray[np.uint64],
        npt.NDArray[np.uint64],
    ],
)
assert_type(
    np.histogram2d(AR_c, AR_c, bins=(AR_b, 8)),
    tuple[
        npt.NDArray[np.float64],
        npt.NDArray[np.bool | np.complex128],
        npt.NDArray[np.bool | np.complex128],
    ],
)

assert_type(np.mask_indices(10, func1), tuple[npt.NDArray[np.intp], npt.NDArray[np.intp]])
assert_type(np.mask_indices(8, func2, "0"), tuple[npt.NDArray[np.intp], npt.NDArray[np.intp]])

assert_type(np.tril_indices(10), tuple[npt.NDArray[np.int_], npt.NDArray[np.int_]])

assert_type(np.tril_indices_from(AR_b), tuple[npt.NDArray[np.int_], npt.NDArray[np.int_]])

assert_type(np.triu_indices(10), tuple[npt.NDArray[np.int_], npt.NDArray[np.int_]])

assert_type(np.triu_indices_from(AR_b), tuple[npt.NDArray[np.int_], npt.NDArray[np.int_]])
