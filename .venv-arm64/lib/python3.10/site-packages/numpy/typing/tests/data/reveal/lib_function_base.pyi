from fractions import Fraction
from typing import Any
from collections.abc import Callable

import numpy as np
import numpy.typing as npt

from typing_extensions import assert_type

vectorized_func: np.vectorize

f8: np.float64
AR_LIKE_f8: list[float]
AR_LIKE_c16: list[complex]
AR_LIKE_O: list[Fraction]

AR_i8: npt.NDArray[np.int64]
AR_f8: npt.NDArray[np.float64]
AR_c16: npt.NDArray[np.complex128]
AR_m: npt.NDArray[np.timedelta64]
AR_M: npt.NDArray[np.datetime64]
AR_O: npt.NDArray[np.object_]
AR_b: npt.NDArray[np.bool]
AR_U: npt.NDArray[np.str_]
CHAR_AR_U: np.char.chararray[tuple[int, ...], np.dtype[np.str_]]

AR_b_list: list[npt.NDArray[np.bool]]

def func(
    a: npt.NDArray[Any],
    posarg: bool = ...,
    /,
    arg: int = ...,
    *,
    kwarg: str = ...,
) -> npt.NDArray[Any]: ...

assert_type(vectorized_func.pyfunc, Callable[..., Any])
assert_type(vectorized_func.cache, bool)
assert_type(vectorized_func.signature, None | str)
assert_type(vectorized_func.otypes, None | str)
assert_type(vectorized_func.excluded, set[int | str])
assert_type(vectorized_func.__doc__, None | str)
assert_type(vectorized_func([1]), Any)
assert_type(np.vectorize(int), np.vectorize)
assert_type(
    np.vectorize(int, otypes="i", doc="doc", excluded=(), cache=True, signature=None),
    np.vectorize,
)

assert_type(np.rot90(AR_f8, k=2), npt.NDArray[np.float64])
assert_type(np.rot90(AR_LIKE_f8, axes=(0, 1)), npt.NDArray[Any])

assert_type(np.flip(f8), np.float64)
assert_type(np.flip(1.0), Any)
assert_type(np.flip(AR_f8, axis=(0, 1)), npt.NDArray[np.float64])
assert_type(np.flip(AR_LIKE_f8, axis=0), npt.NDArray[Any])

assert_type(np.iterable(1), bool)
assert_type(np.iterable([1]), bool)

assert_type(np.average(AR_f8), np.floating[Any])
assert_type(np.average(AR_f8, weights=AR_c16), np.complexfloating[Any, Any])
assert_type(np.average(AR_O), Any)
assert_type(np.average(AR_f8, returned=True), tuple[np.floating[Any], np.floating[Any]])
assert_type(np.average(AR_f8, weights=AR_c16, returned=True), tuple[np.complexfloating[Any, Any], np.complexfloating[Any, Any]])
assert_type(np.average(AR_O, returned=True), tuple[Any, Any])
assert_type(np.average(AR_f8, axis=0), Any)
assert_type(np.average(AR_f8, axis=0, returned=True), tuple[Any, Any])

assert_type(np.asarray_chkfinite(AR_f8), npt.NDArray[np.float64])
assert_type(np.asarray_chkfinite(AR_LIKE_f8), npt.NDArray[Any])
assert_type(np.asarray_chkfinite(AR_f8, dtype=np.float64), npt.NDArray[np.float64])
assert_type(np.asarray_chkfinite(AR_f8, dtype=float), npt.NDArray[Any])

assert_type(np.piecewise(AR_f8, AR_b, [func]), npt.NDArray[np.float64])
assert_type(np.piecewise(AR_f8, AR_b_list, [func]), npt.NDArray[np.float64])
assert_type(np.piecewise(AR_f8, AR_b_list, [func], True, -1, kwarg=''), npt.NDArray[np.float64])
assert_type(np.piecewise(AR_f8, AR_b_list, [func], True, arg=-1, kwarg=''), npt.NDArray[np.float64])
assert_type(np.piecewise(AR_LIKE_f8, AR_b_list, [func]), npt.NDArray[Any])

assert_type(np.select([AR_f8], [AR_f8]), npt.NDArray[Any])

assert_type(np.copy(AR_LIKE_f8), npt.NDArray[Any])
assert_type(np.copy(AR_U), npt.NDArray[np.str_])
assert_type(np.copy(CHAR_AR_U), npt.NDArray[np.str_])
assert_type(np.copy(CHAR_AR_U, "K", subok=True), np.char.chararray[tuple[int, ...], np.dtype[np.str_]])
assert_type(np.copy(CHAR_AR_U, subok=True), np.char.chararray[tuple[int, ...], np.dtype[np.str_]])

assert_type(np.gradient(AR_f8, axis=None), Any)
assert_type(np.gradient(AR_LIKE_f8, edge_order=2), Any)

assert_type(np.diff("bob", n=0), str)
assert_type(np.diff(AR_f8, axis=0), npt.NDArray[Any])
assert_type(np.diff(AR_LIKE_f8, prepend=1.5), npt.NDArray[Any])

assert_type(np.interp(1, [1], AR_f8), np.float64)
assert_type(np.interp(1, [1], [1]), np.float64)
assert_type(np.interp(1, [1], AR_c16), np.complex128)
assert_type(np.interp(1, [1], [1j]), np.complex128)  # pyright correctly infers `complex128 | float64`
assert_type(np.interp([1], [1], AR_f8), npt.NDArray[np.float64])
assert_type(np.interp([1], [1], [1]), npt.NDArray[np.float64])
assert_type(np.interp([1], [1], AR_c16), npt.NDArray[np.complex128])
assert_type(np.interp([1], [1], [1j]), npt.NDArray[np.complex128])  # pyright correctly infers `NDArray[complex128 | float64]`

assert_type(np.angle(f8), np.floating[Any])
assert_type(np.angle(AR_f8), npt.NDArray[np.floating[Any]])
assert_type(np.angle(AR_c16, deg=True), npt.NDArray[np.floating[Any]])
assert_type(np.angle(AR_O), npt.NDArray[np.object_])

assert_type(np.unwrap(AR_f8), npt.NDArray[np.floating[Any]])
assert_type(np.unwrap(AR_O), npt.NDArray[np.object_])

assert_type(np.sort_complex(AR_f8), npt.NDArray[np.complexfloating[Any, Any]])

assert_type(np.trim_zeros(AR_f8), npt.NDArray[np.float64])
assert_type(np.trim_zeros(AR_LIKE_f8), list[float])

assert_type(np.extract(AR_i8, AR_f8), npt.NDArray[np.float64])
assert_type(np.extract(AR_i8, AR_LIKE_f8), npt.NDArray[Any])

assert_type(np.place(AR_f8, mask=AR_i8, vals=5.0), None)

assert_type(np.cov(AR_f8, bias=True), npt.NDArray[np.floating[Any]])
assert_type(np.cov(AR_f8, AR_c16, ddof=1), npt.NDArray[np.complexfloating[Any, Any]])
assert_type(np.cov(AR_f8, aweights=AR_f8, dtype=np.float32), npt.NDArray[np.float32])
assert_type(np.cov(AR_f8, fweights=AR_f8, dtype=float), npt.NDArray[Any])

assert_type(np.corrcoef(AR_f8, rowvar=True), npt.NDArray[np.floating[Any]])
assert_type(np.corrcoef(AR_f8, AR_c16), npt.NDArray[np.complexfloating[Any, Any]])
assert_type(np.corrcoef(AR_f8, dtype=np.float32), npt.NDArray[np.float32])
assert_type(np.corrcoef(AR_f8, dtype=float), npt.NDArray[Any])

assert_type(np.blackman(5), npt.NDArray[np.floating[Any]])
assert_type(np.bartlett(6), npt.NDArray[np.floating[Any]])
assert_type(np.hanning(4.5), npt.NDArray[np.floating[Any]])
assert_type(np.hamming(0), npt.NDArray[np.floating[Any]])
assert_type(np.i0(AR_i8), npt.NDArray[np.floating[Any]])
assert_type(np.kaiser(4, 5.9), npt.NDArray[np.floating[Any]])

assert_type(np.sinc(1.0), np.floating[Any])
assert_type(np.sinc(1j), np.complexfloating[Any, Any])
assert_type(np.sinc(AR_f8), npt.NDArray[np.floating[Any]])
assert_type(np.sinc(AR_c16), npt.NDArray[np.complexfloating[Any, Any]])

assert_type(np.median(AR_f8, keepdims=False), np.floating[Any])
assert_type(np.median(AR_c16, overwrite_input=True), np.complexfloating[Any, Any])
assert_type(np.median(AR_m), np.timedelta64)
assert_type(np.median(AR_O), Any)
assert_type(np.median(AR_f8, keepdims=True), Any)
assert_type(np.median(AR_c16, axis=0), Any)
assert_type(np.median(AR_LIKE_f8, out=AR_c16), npt.NDArray[np.complex128])

assert_type(np.percentile(AR_f8, 50), np.floating[Any])
assert_type(np.percentile(AR_c16, 50), np.complexfloating[Any, Any])
assert_type(np.percentile(AR_m, 50), np.timedelta64)
assert_type(np.percentile(AR_M, 50, overwrite_input=True), np.datetime64)
assert_type(np.percentile(AR_O, 50), Any)
assert_type(np.percentile(AR_f8, [50]), npt.NDArray[np.floating[Any]])
assert_type(np.percentile(AR_c16, [50]), npt.NDArray[np.complexfloating[Any, Any]])
assert_type(np.percentile(AR_m, [50]), npt.NDArray[np.timedelta64])
assert_type(np.percentile(AR_M, [50], method="nearest"), npt.NDArray[np.datetime64])
assert_type(np.percentile(AR_O, [50]), npt.NDArray[np.object_])
assert_type(np.percentile(AR_f8, [50], keepdims=True), Any)
assert_type(np.percentile(AR_f8, [50], axis=[1]), Any)
assert_type(np.percentile(AR_f8, [50], out=AR_c16), npt.NDArray[np.complex128])

assert_type(np.quantile(AR_f8, 0.5), np.floating[Any])
assert_type(np.quantile(AR_c16, 0.5), np.complexfloating[Any, Any])
assert_type(np.quantile(AR_m, 0.5), np.timedelta64)
assert_type(np.quantile(AR_M, 0.5, overwrite_input=True), np.datetime64)
assert_type(np.quantile(AR_O, 0.5), Any)
assert_type(np.quantile(AR_f8, [0.5]), npt.NDArray[np.floating[Any]])
assert_type(np.quantile(AR_c16, [0.5]), npt.NDArray[np.complexfloating[Any, Any]])
assert_type(np.quantile(AR_m, [0.5]), npt.NDArray[np.timedelta64])
assert_type(np.quantile(AR_M, [0.5], method="nearest"), npt.NDArray[np.datetime64])
assert_type(np.quantile(AR_O, [0.5]), npt.NDArray[np.object_])
assert_type(np.quantile(AR_f8, [0.5], keepdims=True), Any)
assert_type(np.quantile(AR_f8, [0.5], axis=[1]), Any)
assert_type(np.quantile(AR_f8, [0.5], out=AR_c16), npt.NDArray[np.complex128])

assert_type(np.trapezoid(AR_LIKE_f8), np.float64)
assert_type(np.trapezoid(AR_LIKE_f8, AR_LIKE_f8), np.float64)
assert_type(np.trapezoid(AR_LIKE_c16), np.complex128)
assert_type(np.trapezoid(AR_LIKE_c16, AR_LIKE_f8), np.complex128)
assert_type(np.trapezoid(AR_LIKE_f8, AR_LIKE_c16), np.complex128)
assert_type(np.trapezoid(AR_LIKE_O), float)
assert_type(np.trapezoid(AR_LIKE_O, AR_LIKE_f8), float)
assert_type(np.trapezoid(AR_f8), np.float64 | npt.NDArray[np.float64])
assert_type(np.trapezoid(AR_f8, AR_f8), np.float64 | npt.NDArray[np.float64])
assert_type(np.trapezoid(AR_c16), np.complex128 | npt.NDArray[np.complex128])
assert_type(np.trapezoid(AR_c16, AR_c16), np.complex128 | npt.NDArray[np.complex128])
assert_type(np.trapezoid(AR_m), np.timedelta64 | npt.NDArray[np.timedelta64])
assert_type(np.trapezoid(AR_O), float | npt.NDArray[np.object_])
assert_type(np.trapezoid(AR_O, AR_LIKE_f8), float | npt.NDArray[np.object_])

assert_type(np.meshgrid(AR_f8, AR_i8, copy=False), tuple[npt.NDArray[Any], ...])
assert_type(np.meshgrid(AR_f8, AR_i8, AR_c16, indexing="ij"), tuple[npt.NDArray[Any], ...])

assert_type(np.delete(AR_f8, np.s_[:5]), npt.NDArray[np.float64])
assert_type(np.delete(AR_LIKE_f8, [0, 4, 9], axis=0), npt.NDArray[Any])

assert_type(np.insert(AR_f8, np.s_[:5], 5), npt.NDArray[np.float64])
assert_type(np.insert(AR_LIKE_f8, [0, 4, 9], [0.5, 9.2, 7], axis=0), npt.NDArray[Any])

assert_type(np.append(AR_f8, 5), npt.NDArray[Any])
assert_type(np.append(AR_LIKE_f8, 1j, axis=0), npt.NDArray[Any])

assert_type(np.digitize(4.5, [1]), np.intp)
assert_type(np.digitize(AR_f8, [1, 2, 3]), npt.NDArray[np.intp])
