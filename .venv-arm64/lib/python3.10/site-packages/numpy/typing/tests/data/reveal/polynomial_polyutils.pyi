from collections.abc import Sequence
from decimal import Decimal
from fractions import Fraction
from typing import Any, Literal as L, TypeAlias

import numpy as np
import numpy.typing as npt
import numpy.polynomial.polyutils as pu
from numpy.polynomial._polytypes import _Tuple2

from typing_extensions import assert_type

_ArrFloat1D: TypeAlias = np.ndarray[tuple[int], np.dtype[np.floating[Any]]]
_ArrComplex1D: TypeAlias = np.ndarray[tuple[int], np.dtype[np.complexfloating[Any, Any]]]
_ArrObject1D: TypeAlias = np.ndarray[tuple[int], np.dtype[np.object_]]

_ArrFloat1D_2: TypeAlias = np.ndarray[tuple[L[2]], np.dtype[np.float64]]
_ArrComplex1D_2: TypeAlias = np.ndarray[tuple[L[2]], np.dtype[np.complex128]]
_ArrObject1D_2: TypeAlias = np.ndarray[tuple[L[2]], np.dtype[np.object_]]

num_int: int
num_float: float
num_complex: complex
# will result in an `object_` dtype
num_object: Decimal | Fraction

sct_int: np.int_
sct_float: np.float64
sct_complex: np.complex128
sct_object: np.object_  # doesn't exist at runtime

arr_int: npt.NDArray[np.int_]
arr_float: npt.NDArray[np.float64]
arr_complex: npt.NDArray[np.complex128]
arr_object: npt.NDArray[np.object_]

seq_num_int: Sequence[int]
seq_num_float: Sequence[float]
seq_num_complex: Sequence[complex]
seq_num_object: Sequence[Decimal | Fraction]

seq_sct_int: Sequence[np.int_]
seq_sct_float: Sequence[np.float64]
seq_sct_complex: Sequence[np.complex128]
seq_sct_object: Sequence[np.object_]

seq_arr_int: Sequence[npt.NDArray[np.int_]]
seq_arr_float: Sequence[npt.NDArray[np.float64]]
seq_arr_complex: Sequence[npt.NDArray[np.complex128]]
seq_arr_object: Sequence[npt.NDArray[np.object_]]

seq_seq_num_int: Sequence[Sequence[int]]
seq_seq_num_float: Sequence[Sequence[float]]
seq_seq_num_complex: Sequence[Sequence[complex]]
seq_seq_num_object: Sequence[Sequence[Decimal | Fraction]]

seq_seq_sct_int: Sequence[Sequence[np.int_]]
seq_seq_sct_float: Sequence[Sequence[np.float64]]
seq_seq_sct_complex: Sequence[Sequence[np.complex128]]
seq_seq_sct_object: Sequence[Sequence[np.object_]]  # doesn't exist at runtime

# as_series

assert_type(pu.as_series(arr_int), list[_ArrFloat1D])
assert_type(pu.as_series(arr_float), list[_ArrFloat1D])
assert_type(pu.as_series(arr_complex), list[_ArrComplex1D])
assert_type(pu.as_series(arr_object), list[_ArrObject1D])

assert_type(pu.as_series(seq_num_int), list[_ArrFloat1D])
assert_type(pu.as_series(seq_num_float), list[_ArrFloat1D])
assert_type(pu.as_series(seq_num_complex), list[_ArrComplex1D])
assert_type(pu.as_series(seq_num_object), list[_ArrObject1D])

assert_type(pu.as_series(seq_sct_int), list[_ArrFloat1D])
assert_type(pu.as_series(seq_sct_float), list[_ArrFloat1D])
assert_type(pu.as_series(seq_sct_complex), list[_ArrComplex1D])
assert_type(pu.as_series(seq_sct_object), list[_ArrObject1D])

assert_type(pu.as_series(seq_arr_int), list[_ArrFloat1D])
assert_type(pu.as_series(seq_arr_float), list[_ArrFloat1D])
assert_type(pu.as_series(seq_arr_complex), list[_ArrComplex1D])
assert_type(pu.as_series(seq_arr_object), list[_ArrObject1D])

assert_type(pu.as_series(seq_seq_num_int), list[_ArrFloat1D])
assert_type(pu.as_series(seq_seq_num_float), list[_ArrFloat1D])
assert_type(pu.as_series(seq_seq_num_complex), list[_ArrComplex1D])
assert_type(pu.as_series(seq_seq_num_object), list[_ArrObject1D])

assert_type(pu.as_series(seq_seq_sct_int), list[_ArrFloat1D])
assert_type(pu.as_series(seq_seq_sct_float), list[_ArrFloat1D])
assert_type(pu.as_series(seq_seq_sct_complex), list[_ArrComplex1D])
assert_type(pu.as_series(seq_seq_sct_object), list[_ArrObject1D])

# trimcoef

assert_type(pu.trimcoef(num_int), _ArrFloat1D)
assert_type(pu.trimcoef(num_float), _ArrFloat1D)
assert_type(pu.trimcoef(num_complex), _ArrComplex1D)
assert_type(pu.trimcoef(num_object), _ArrObject1D)
assert_type(pu.trimcoef(num_object), _ArrObject1D)

assert_type(pu.trimcoef(sct_int), _ArrFloat1D)
assert_type(pu.trimcoef(sct_float), _ArrFloat1D)
assert_type(pu.trimcoef(sct_complex), _ArrComplex1D)
assert_type(pu.trimcoef(sct_object), _ArrObject1D)

assert_type(pu.trimcoef(arr_int), _ArrFloat1D)
assert_type(pu.trimcoef(arr_float), _ArrFloat1D)
assert_type(pu.trimcoef(arr_complex), _ArrComplex1D)
assert_type(pu.trimcoef(arr_object), _ArrObject1D)

assert_type(pu.trimcoef(seq_num_int), _ArrFloat1D)
assert_type(pu.trimcoef(seq_num_float), _ArrFloat1D)
assert_type(pu.trimcoef(seq_num_complex), _ArrComplex1D)
assert_type(pu.trimcoef(seq_num_object), _ArrObject1D)

assert_type(pu.trimcoef(seq_sct_int), _ArrFloat1D)
assert_type(pu.trimcoef(seq_sct_float), _ArrFloat1D)
assert_type(pu.trimcoef(seq_sct_complex), _ArrComplex1D)
assert_type(pu.trimcoef(seq_sct_object), _ArrObject1D)

# getdomain

assert_type(pu.getdomain(num_int), _ArrFloat1D_2)
assert_type(pu.getdomain(num_float), _ArrFloat1D_2)
assert_type(pu.getdomain(num_complex), _ArrComplex1D_2)
assert_type(pu.getdomain(num_object), _ArrObject1D_2)
assert_type(pu.getdomain(num_object), _ArrObject1D_2)

assert_type(pu.getdomain(sct_int), _ArrFloat1D_2)
assert_type(pu.getdomain(sct_float), _ArrFloat1D_2)
assert_type(pu.getdomain(sct_complex), _ArrComplex1D_2)
assert_type(pu.getdomain(sct_object), _ArrObject1D_2)

assert_type(pu.getdomain(arr_int), _ArrFloat1D_2)
assert_type(pu.getdomain(arr_float), _ArrFloat1D_2)
assert_type(pu.getdomain(arr_complex), _ArrComplex1D_2)
assert_type(pu.getdomain(arr_object), _ArrObject1D_2)

assert_type(pu.getdomain(seq_num_int), _ArrFloat1D_2)
assert_type(pu.getdomain(seq_num_float), _ArrFloat1D_2)
assert_type(pu.getdomain(seq_num_complex), _ArrComplex1D_2)
assert_type(pu.getdomain(seq_num_object), _ArrObject1D_2)

assert_type(pu.getdomain(seq_sct_int), _ArrFloat1D_2)
assert_type(pu.getdomain(seq_sct_float), _ArrFloat1D_2)
assert_type(pu.getdomain(seq_sct_complex), _ArrComplex1D_2)
assert_type(pu.getdomain(seq_sct_object), _ArrObject1D_2)

# mapparms

assert_type(pu.mapparms(seq_num_int, seq_num_int), _Tuple2[float])
assert_type(pu.mapparms(seq_num_int, seq_num_float), _Tuple2[float])
assert_type(pu.mapparms(seq_num_float, seq_num_float), _Tuple2[float])
assert_type(pu.mapparms(seq_num_float, seq_num_complex), _Tuple2[complex])
assert_type(pu.mapparms(seq_num_complex, seq_num_complex), _Tuple2[complex])
assert_type(pu.mapparms(seq_num_complex, seq_num_object), _Tuple2[object])
assert_type(pu.mapparms(seq_num_object, seq_num_object), _Tuple2[object])

assert_type(pu.mapparms(seq_sct_int, seq_sct_int), _Tuple2[np.floating[Any]])
assert_type(pu.mapparms(seq_sct_int, seq_sct_float), _Tuple2[np.floating[Any]])
assert_type(pu.mapparms(seq_sct_float, seq_sct_float), _Tuple2[float])
assert_type(pu.mapparms(seq_sct_float, seq_sct_complex), _Tuple2[complex])
assert_type(pu.mapparms(seq_sct_complex, seq_sct_complex), _Tuple2[complex])
assert_type(pu.mapparms(seq_sct_complex, seq_sct_object), _Tuple2[object])
assert_type(pu.mapparms(seq_sct_object, seq_sct_object), _Tuple2[object])

assert_type(pu.mapparms(arr_int, arr_int), _Tuple2[np.floating[Any]])
assert_type(pu.mapparms(arr_int, arr_float), _Tuple2[np.floating[Any]])
assert_type(pu.mapparms(arr_float, arr_float), _Tuple2[np.floating[Any]])
assert_type(pu.mapparms(arr_float, arr_complex), _Tuple2[np.complexfloating[Any, Any]])
assert_type(pu.mapparms(arr_complex, arr_complex), _Tuple2[np.complexfloating[Any, Any]])
assert_type(pu.mapparms(arr_complex, arr_object), _Tuple2[object])
assert_type(pu.mapparms(arr_object, arr_object), _Tuple2[object])

# mapdomain

assert_type(pu.mapdomain(num_int, seq_num_int, seq_num_int), np.floating[Any])
assert_type(pu.mapdomain(num_int, seq_num_int, seq_num_float), np.floating[Any])
assert_type(pu.mapdomain(num_int, seq_num_float, seq_num_float), np.floating[Any])
assert_type(pu.mapdomain(num_float, seq_num_float, seq_num_float), np.floating[Any])
assert_type(pu.mapdomain(num_float, seq_num_float, seq_num_complex), np.complexfloating[Any, Any])
assert_type(pu.mapdomain(num_float, seq_num_complex, seq_num_complex), np.complexfloating[Any, Any])
assert_type(pu.mapdomain(num_complex, seq_num_complex, seq_num_complex), np.complexfloating[Any, Any])
assert_type(pu.mapdomain(num_complex, seq_num_complex, seq_num_object), object)
assert_type(pu.mapdomain(num_complex, seq_num_object, seq_num_object), object)
assert_type(pu.mapdomain(num_object, seq_num_object, seq_num_object), object)

assert_type(pu.mapdomain(seq_num_int, seq_num_int, seq_num_int), _ArrFloat1D)
assert_type(pu.mapdomain(seq_num_int, seq_num_int, seq_num_float), _ArrFloat1D)
assert_type(pu.mapdomain(seq_num_int, seq_num_float, seq_num_float), _ArrFloat1D)
assert_type(pu.mapdomain(seq_num_float, seq_num_float, seq_num_float), _ArrFloat1D)
assert_type(pu.mapdomain(seq_num_float, seq_num_float, seq_num_complex), _ArrComplex1D)
assert_type(pu.mapdomain(seq_num_float, seq_num_complex, seq_num_complex), _ArrComplex1D)
assert_type(pu.mapdomain(seq_num_complex, seq_num_complex, seq_num_complex), _ArrComplex1D)
assert_type(pu.mapdomain(seq_num_complex, seq_num_complex, seq_num_object), _ArrObject1D)
assert_type(pu.mapdomain(seq_num_complex, seq_num_object, seq_num_object), _ArrObject1D)
assert_type(pu.mapdomain(seq_num_object, seq_num_object, seq_num_object), _ArrObject1D)

assert_type(pu.mapdomain(seq_sct_int, seq_sct_int, seq_sct_int), _ArrFloat1D)
assert_type(pu.mapdomain(seq_sct_int, seq_sct_int, seq_sct_float), _ArrFloat1D)
assert_type(pu.mapdomain(seq_sct_int, seq_sct_float, seq_sct_float), _ArrFloat1D)
assert_type(pu.mapdomain(seq_sct_float, seq_sct_float, seq_sct_float), _ArrFloat1D)
assert_type(pu.mapdomain(seq_sct_float, seq_sct_float, seq_sct_complex), _ArrComplex1D)
assert_type(pu.mapdomain(seq_sct_float, seq_sct_complex, seq_sct_complex), _ArrComplex1D)
assert_type(pu.mapdomain(seq_sct_complex, seq_sct_complex, seq_sct_complex), _ArrComplex1D)
assert_type(pu.mapdomain(seq_sct_complex, seq_sct_complex, seq_sct_object), _ArrObject1D)
assert_type(pu.mapdomain(seq_sct_complex, seq_sct_object, seq_sct_object), _ArrObject1D)
assert_type(pu.mapdomain(seq_sct_object, seq_sct_object, seq_sct_object), _ArrObject1D)

assert_type(pu.mapdomain(arr_int, arr_int, arr_int), _ArrFloat1D)
assert_type(pu.mapdomain(arr_int, arr_int, arr_float), _ArrFloat1D)
assert_type(pu.mapdomain(arr_int, arr_float, arr_float), _ArrFloat1D)
assert_type(pu.mapdomain(arr_float, arr_float, arr_float), _ArrFloat1D)
assert_type(pu.mapdomain(arr_float, arr_float, arr_complex), _ArrComplex1D)
assert_type(pu.mapdomain(arr_float, arr_complex, arr_complex), _ArrComplex1D)
assert_type(pu.mapdomain(arr_complex, arr_complex, arr_complex), _ArrComplex1D)
assert_type(pu.mapdomain(arr_complex, arr_complex, arr_object), _ArrObject1D)
assert_type(pu.mapdomain(arr_complex, arr_object, arr_object), _ArrObject1D)
assert_type(pu.mapdomain(arr_object, arr_object, arr_object), _ArrObject1D)
