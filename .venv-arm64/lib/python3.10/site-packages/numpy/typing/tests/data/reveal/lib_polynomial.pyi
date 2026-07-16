from typing import Any, NoReturn
from collections.abc import Iterator

import numpy as np
import numpy.typing as npt

from typing_extensions import assert_type

AR_b: npt.NDArray[np.bool]
AR_u4: npt.NDArray[np.uint32]
AR_i8: npt.NDArray[np.int64]
AR_f8: npt.NDArray[np.float64]
AR_c16: npt.NDArray[np.complex128]
AR_O: npt.NDArray[np.object_]

poly_obj: np.poly1d

assert_type(poly_obj.variable, str)
assert_type(poly_obj.order, int)
assert_type(poly_obj.o, int)
assert_type(poly_obj.roots, npt.NDArray[Any])
assert_type(poly_obj.r, npt.NDArray[Any])
assert_type(poly_obj.coeffs, npt.NDArray[Any])
assert_type(poly_obj.c, npt.NDArray[Any])
assert_type(poly_obj.coef, npt.NDArray[Any])
assert_type(poly_obj.coefficients, npt.NDArray[Any])
assert_type(poly_obj.__hash__, None)

assert_type(poly_obj(1), Any)
assert_type(poly_obj([1]), npt.NDArray[Any])
assert_type(poly_obj(poly_obj), np.poly1d)

assert_type(len(poly_obj), int)
assert_type(-poly_obj, np.poly1d)
assert_type(+poly_obj, np.poly1d)

assert_type(poly_obj * 5, np.poly1d)
assert_type(5 * poly_obj, np.poly1d)
assert_type(poly_obj + 5, np.poly1d)
assert_type(5 + poly_obj, np.poly1d)
assert_type(poly_obj - 5, np.poly1d)
assert_type(5 - poly_obj, np.poly1d)
assert_type(poly_obj**1, np.poly1d)
assert_type(poly_obj**1.0, np.poly1d)
assert_type(poly_obj / 5, np.poly1d)
assert_type(5 / poly_obj, np.poly1d)

assert_type(poly_obj[0], Any)
poly_obj[0] = 5
assert_type(iter(poly_obj), Iterator[Any])
assert_type(poly_obj.deriv(), np.poly1d)
assert_type(poly_obj.integ(), np.poly1d)

assert_type(np.poly(poly_obj), npt.NDArray[np.floating[Any]])
assert_type(np.poly(AR_f8), npt.NDArray[np.floating[Any]])
assert_type(np.poly(AR_c16), npt.NDArray[np.floating[Any]])

assert_type(np.polyint(poly_obj), np.poly1d)
assert_type(np.polyint(AR_f8), npt.NDArray[np.floating[Any]])
assert_type(np.polyint(AR_f8, k=AR_c16), npt.NDArray[np.complexfloating[Any, Any]])
assert_type(np.polyint(AR_O, m=2), npt.NDArray[np.object_])

assert_type(np.polyder(poly_obj), np.poly1d)
assert_type(np.polyder(AR_f8), npt.NDArray[np.floating[Any]])
assert_type(np.polyder(AR_c16), npt.NDArray[np.complexfloating[Any, Any]])
assert_type(np.polyder(AR_O, m=2), npt.NDArray[np.object_])

assert_type(np.polyfit(AR_f8, AR_f8, 2), npt.NDArray[np.float64])
assert_type(
    np.polyfit(AR_f8, AR_i8, 1, full=True),
    tuple[
        npt.NDArray[np.float64],
        npt.NDArray[np.float64],
        npt.NDArray[np.int32],
        npt.NDArray[np.float64],
        npt.NDArray[np.float64],
    ],
)
assert_type(
    np.polyfit(AR_u4, AR_f8, 1.0, cov="unscaled"),
    tuple[
        npt.NDArray[np.float64],
        npt.NDArray[np.float64],
    ],
)
assert_type(np.polyfit(AR_c16, AR_f8, 2), npt.NDArray[np.complex128])
assert_type(
    np.polyfit(AR_f8, AR_c16, 1, full=True),
    tuple[
        npt.NDArray[np.complex128],
        npt.NDArray[np.float64],
        npt.NDArray[np.int32],
        npt.NDArray[np.float64],
        npt.NDArray[np.float64],
    ],
)
assert_type(
    np.polyfit(AR_u4, AR_c16, 1.0, cov=True),
    tuple[
        npt.NDArray[np.complex128],
        npt.NDArray[np.complex128],
    ],
)

assert_type(np.polyval(AR_b, AR_b), npt.NDArray[np.int64])
assert_type(np.polyval(AR_u4, AR_b), npt.NDArray[np.unsignedinteger[Any]])
assert_type(np.polyval(AR_i8, AR_i8), npt.NDArray[np.signedinteger[Any]])
assert_type(np.polyval(AR_f8, AR_i8), npt.NDArray[np.floating[Any]])
assert_type(np.polyval(AR_i8, AR_c16), npt.NDArray[np.complexfloating[Any, Any]])
assert_type(np.polyval(AR_O, AR_O), npt.NDArray[np.object_])

assert_type(np.polyadd(poly_obj, AR_i8), np.poly1d)
assert_type(np.polyadd(AR_f8, poly_obj), np.poly1d)
assert_type(np.polyadd(AR_b, AR_b), npt.NDArray[np.bool])
assert_type(np.polyadd(AR_u4, AR_b), npt.NDArray[np.unsignedinteger[Any]])
assert_type(np.polyadd(AR_i8, AR_i8), npt.NDArray[np.signedinteger[Any]])
assert_type(np.polyadd(AR_f8, AR_i8), npt.NDArray[np.floating[Any]])
assert_type(np.polyadd(AR_i8, AR_c16), npt.NDArray[np.complexfloating[Any, Any]])
assert_type(np.polyadd(AR_O, AR_O), npt.NDArray[np.object_])

assert_type(np.polysub(poly_obj, AR_i8), np.poly1d)
assert_type(np.polysub(AR_f8, poly_obj), np.poly1d)
assert_type(np.polysub(AR_b, AR_b), NoReturn)
assert_type(np.polysub(AR_u4, AR_b), npt.NDArray[np.unsignedinteger[Any]])
assert_type(np.polysub(AR_i8, AR_i8), npt.NDArray[np.signedinteger[Any]])
assert_type(np.polysub(AR_f8, AR_i8), npt.NDArray[np.floating[Any]])
assert_type(np.polysub(AR_i8, AR_c16), npt.NDArray[np.complexfloating[Any, Any]])
assert_type(np.polysub(AR_O, AR_O), npt.NDArray[np.object_])

assert_type(np.polymul(poly_obj, AR_i8), np.poly1d)
assert_type(np.polymul(AR_f8, poly_obj), np.poly1d)
assert_type(np.polymul(AR_b, AR_b), npt.NDArray[np.bool])
assert_type(np.polymul(AR_u4, AR_b), npt.NDArray[np.unsignedinteger[Any]])
assert_type(np.polymul(AR_i8, AR_i8), npt.NDArray[np.signedinteger[Any]])
assert_type(np.polymul(AR_f8, AR_i8), npt.NDArray[np.floating[Any]])
assert_type(np.polymul(AR_i8, AR_c16), npt.NDArray[np.complexfloating[Any, Any]])
assert_type(np.polymul(AR_O, AR_O), npt.NDArray[np.object_])

assert_type(np.polydiv(poly_obj, AR_i8), tuple[np.poly1d, np.poly1d])
assert_type(np.polydiv(AR_f8, poly_obj), tuple[np.poly1d, np.poly1d])
assert_type(np.polydiv(AR_b, AR_b), tuple[npt.NDArray[np.floating[Any]], npt.NDArray[np.floating[Any]]])
assert_type(np.polydiv(AR_u4, AR_b), tuple[npt.NDArray[np.floating[Any]], npt.NDArray[np.floating[Any]]])
assert_type(np.polydiv(AR_i8, AR_i8), tuple[npt.NDArray[np.floating[Any]], npt.NDArray[np.floating[Any]]])
assert_type(np.polydiv(AR_f8, AR_i8), tuple[npt.NDArray[np.floating[Any]], npt.NDArray[np.floating[Any]]])
assert_type(np.polydiv(AR_i8, AR_c16), tuple[npt.NDArray[np.complexfloating[Any, Any]], npt.NDArray[np.complexfloating[Any, Any]]])
assert_type(np.polydiv(AR_O, AR_O), tuple[npt.NDArray[Any], npt.NDArray[Any]])
