from collections.abc import Sequence
from typing import Any, TypeAlias

import numpy as np
import numpy.polynomial as npp
import numpy.typing as npt

from typing_extensions import assert_type

_ArrFloat1D: TypeAlias = np.ndarray[tuple[int], np.dtype[np.floating[Any]]]
_ArrFloat1D64: TypeAlias = np.ndarray[tuple[int], np.dtype[np.float64]]
_ArrComplex1D: TypeAlias = np.ndarray[tuple[int], np.dtype[np.complexfloating[Any, Any]]]
_ArrComplex1D128: TypeAlias = np.ndarray[tuple[int], np.dtype[np.complex128]]
_ArrObject1D: TypeAlias = np.ndarray[tuple[int], np.dtype[np.object_]]

AR_b: npt.NDArray[np.bool]
AR_u4: npt.NDArray[np.uint32]
AR_i8: npt.NDArray[np.int64]
AR_f8: npt.NDArray[np.float64]
AR_c16: npt.NDArray[np.complex128]
AR_O: npt.NDArray[np.object_]

PS_poly: npp.Polynomial
PS_cheb: npp.Chebyshev

assert_type(npp.polynomial.polyroots(AR_f8), _ArrFloat1D64)
assert_type(npp.polynomial.polyroots(AR_c16), _ArrComplex1D128)
assert_type(npp.polynomial.polyroots(AR_O), _ArrObject1D)

assert_type(npp.polynomial.polyfromroots(AR_f8), _ArrFloat1D)
assert_type(npp.polynomial.polyfromroots(AR_c16), _ArrComplex1D)
assert_type(npp.polynomial.polyfromroots(AR_O), _ArrObject1D)

# assert_type(npp.polynomial.polyadd(AR_b, AR_b), NoReturn)
assert_type(npp.polynomial.polyadd(AR_u4, AR_b), _ArrFloat1D)
assert_type(npp.polynomial.polyadd(AR_i8, AR_i8), _ArrFloat1D)
assert_type(npp.polynomial.polyadd(AR_f8, AR_i8), _ArrFloat1D)
assert_type(npp.polynomial.polyadd(AR_i8, AR_c16), _ArrComplex1D)
assert_type(npp.polynomial.polyadd(AR_O, AR_O), _ArrObject1D)

assert_type(npp.polynomial.polymulx(AR_u4), _ArrFloat1D)
assert_type(npp.polynomial.polymulx(AR_i8), _ArrFloat1D)
assert_type(npp.polynomial.polymulx(AR_f8), _ArrFloat1D)
assert_type(npp.polynomial.polymulx(AR_c16), _ArrComplex1D)
assert_type(npp.polynomial.polymulx(AR_O), _ArrObject1D)

assert_type(npp.polynomial.polypow(AR_u4, 2), _ArrFloat1D)
assert_type(npp.polynomial.polypow(AR_i8, 2), _ArrFloat1D)
assert_type(npp.polynomial.polypow(AR_f8, 2), _ArrFloat1D)
assert_type(npp.polynomial.polypow(AR_c16, 2), _ArrComplex1D)
assert_type(npp.polynomial.polypow(AR_O, 2), _ArrObject1D)

# assert_type(npp.polynomial.polyder(PS_poly), npt.NDArray[np.object_])
assert_type(npp.polynomial.polyder(AR_f8), npt.NDArray[np.floating[Any]])
assert_type(npp.polynomial.polyder(AR_c16), npt.NDArray[np.complexfloating[Any, Any]])
assert_type(npp.polynomial.polyder(AR_O, m=2), npt.NDArray[np.object_])

# assert_type(npp.polynomial.polyint(PS_poly), npt.NDArray[np.object_])
assert_type(npp.polynomial.polyint(AR_f8), npt.NDArray[np.floating[Any]])
assert_type(npp.polynomial.polyint(AR_f8, k=AR_c16), npt.NDArray[np.complexfloating[Any, Any]])
assert_type(npp.polynomial.polyint(AR_O, m=2), npt.NDArray[np.object_])

assert_type(npp.polynomial.polyval(AR_b, AR_b), npt.NDArray[np.floating[Any]])
assert_type(npp.polynomial.polyval(AR_u4, AR_b), npt.NDArray[np.floating[Any]])
assert_type(npp.polynomial.polyval(AR_i8, AR_i8), npt.NDArray[np.floating[Any]])
assert_type(npp.polynomial.polyval(AR_f8, AR_i8), npt.NDArray[np.floating[Any]])
assert_type(npp.polynomial.polyval(AR_i8, AR_c16), npt.NDArray[np.complexfloating[Any, Any]])
assert_type(npp.polynomial.polyval(AR_O, AR_O), npt.NDArray[np.object_])

assert_type(npp.polynomial.polyval2d(AR_b, AR_b, AR_b), npt.NDArray[np.floating[Any]])
assert_type(npp.polynomial.polyval2d(AR_u4, AR_u4, AR_b), npt.NDArray[np.floating[Any]])
assert_type(npp.polynomial.polyval2d(AR_i8, AR_i8, AR_i8), npt.NDArray[np.floating[Any]])
assert_type(npp.polynomial.polyval2d(AR_f8, AR_f8, AR_i8), npt.NDArray[np.floating[Any]])
assert_type(npp.polynomial.polyval2d(AR_i8, AR_i8, AR_c16), npt.NDArray[np.complexfloating[Any, Any]])
assert_type(npp.polynomial.polyval2d(AR_O, AR_O, AR_O), npt.NDArray[np.object_])

assert_type(npp.polynomial.polyval3d(AR_b, AR_b, AR_b, AR_b), npt.NDArray[np.floating[Any]])
assert_type(npp.polynomial.polyval3d(AR_u4, AR_u4, AR_u4, AR_b), npt.NDArray[np.floating[Any]])
assert_type(npp.polynomial.polyval3d(AR_i8, AR_i8, AR_i8, AR_i8), npt.NDArray[np.floating[Any]])
assert_type(npp.polynomial.polyval3d(AR_f8, AR_f8, AR_f8, AR_i8), npt.NDArray[np.floating[Any]])
assert_type(npp.polynomial.polyval3d(AR_i8, AR_i8, AR_i8, AR_c16), npt.NDArray[np.complexfloating[Any, Any]])
assert_type(npp.polynomial.polyval3d(AR_O, AR_O, AR_O, AR_O), npt.NDArray[np.object_])

assert_type(npp.polynomial.polyvalfromroots(AR_b, AR_b), npt.NDArray[np.floating[Any]])
assert_type(npp.polynomial.polyvalfromroots(AR_u4, AR_b), npt.NDArray[np.floating[Any]])
assert_type(npp.polynomial.polyvalfromroots(AR_i8, AR_i8), npt.NDArray[np.floating[Any]])
assert_type(npp.polynomial.polyvalfromroots(AR_f8, AR_i8), npt.NDArray[np.floating[Any]])
assert_type(npp.polynomial.polyvalfromroots(AR_i8, AR_c16), npt.NDArray[np.complexfloating[Any, Any]])
assert_type(npp.polynomial.polyvalfromroots(AR_O, AR_O), npt.NDArray[np.object_])

assert_type(npp.polynomial.polyvander(AR_f8, 3), npt.NDArray[np.floating[Any]])
assert_type(npp.polynomial.polyvander(AR_c16, 3), npt.NDArray[np.complexfloating[Any, Any]])
assert_type(npp.polynomial.polyvander(AR_O, 3), npt.NDArray[np.object_])

assert_type(npp.polynomial.polyvander2d(AR_f8, AR_f8, [4, 2]), npt.NDArray[np.floating[Any]])
assert_type(npp.polynomial.polyvander2d(AR_c16, AR_c16, [4, 2]), npt.NDArray[np.complexfloating[Any, Any]])
assert_type(npp.polynomial.polyvander2d(AR_O, AR_O, [4, 2]), npt.NDArray[np.object_])

assert_type(npp.polynomial.polyvander3d(AR_f8, AR_f8, AR_f8, [4, 3, 2]), npt.NDArray[np.floating[Any]])
assert_type(npp.polynomial.polyvander3d(AR_c16, AR_c16, AR_c16, [4, 3, 2]), npt.NDArray[np.complexfloating[Any, Any]])
assert_type(npp.polynomial.polyvander3d(AR_O, AR_O, AR_O, [4, 3, 2]), npt.NDArray[np.object_])

assert_type(
    npp.polynomial.polyfit(AR_f8, AR_f8, 2),
    npt.NDArray[np.floating[Any]],
)
assert_type(
    npp.polynomial.polyfit(AR_f8, AR_i8, 1, full=True),
    tuple[npt.NDArray[np.floating[Any]], Sequence[np.inexact[Any] | np.int32]],
)
assert_type(
    npp.polynomial.polyfit(AR_c16, AR_f8, 2),
    npt.NDArray[np.complexfloating[Any, Any]],
)
assert_type(
    npp.polynomial.polyfit(AR_f8, AR_c16, 1, full=True)[0],
    npt.NDArray[np.complexfloating[Any, Any]],
)

assert_type(npp.chebyshev.chebgauss(2), tuple[_ArrFloat1D64, _ArrFloat1D64])

assert_type(npp.chebyshev.chebweight(AR_f8), npt.NDArray[np.float64])
assert_type(npp.chebyshev.chebweight(AR_c16), npt.NDArray[np.complex128])
assert_type(npp.chebyshev.chebweight(AR_O), npt.NDArray[np.object_])

assert_type(npp.chebyshev.poly2cheb(AR_f8), _ArrFloat1D)
assert_type(npp.chebyshev.poly2cheb(AR_c16), _ArrComplex1D)
assert_type(npp.chebyshev.poly2cheb(AR_O), _ArrObject1D)

assert_type(npp.chebyshev.cheb2poly(AR_f8), _ArrFloat1D)
assert_type(npp.chebyshev.cheb2poly(AR_c16), _ArrComplex1D)
assert_type(npp.chebyshev.cheb2poly(AR_O), _ArrObject1D)

assert_type(npp.chebyshev.chebpts1(6), _ArrFloat1D64)
assert_type(npp.chebyshev.chebpts2(6), _ArrFloat1D64)

assert_type(
    npp.chebyshev.chebinterpolate(np.tanh, 3),
    npt.NDArray[np.float64 | np.complex128 | np.object_],
)
