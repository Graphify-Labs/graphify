"""Tests for :mod:`_core.fromnumeric`."""

from typing import Any, Literal as L

import numpy as np
import numpy.typing as npt

from typing_extensions import assert_type

class NDArraySubclass(npt.NDArray[np.complex128]):
    ...

AR_b: npt.NDArray[np.bool]
AR_f4: npt.NDArray[np.float32]
AR_c16: npt.NDArray[np.complex128]
AR_u8: npt.NDArray[np.uint64]
AR_i8: npt.NDArray[np.int64]
AR_O: npt.NDArray[np.object_]
AR_subclass: NDArraySubclass
AR_m: npt.NDArray[np.timedelta64]
AR_0d: np.ndarray[tuple[()], np.dtype[Any]]
AR_1d: np.ndarray[tuple[int], np.dtype[Any]]
AR_nd: np.ndarray[tuple[int, ...], np.dtype[Any]]

b: np.bool
f4: np.float32
i8: np.int64
f: float

assert_type(np.take(b, 0), np.bool)
assert_type(np.take(f4, 0), np.float32)
assert_type(np.take(f, 0), Any)
assert_type(np.take(AR_b, 0), np.bool)
assert_type(np.take(AR_f4, 0), np.float32)
assert_type(np.take(AR_b, [0]), npt.NDArray[np.bool])
assert_type(np.take(AR_f4, [0]), npt.NDArray[np.float32])
assert_type(np.take([1], [0]), npt.NDArray[Any])
assert_type(np.take(AR_f4, [0], out=AR_subclass), NDArraySubclass)

assert_type(np.reshape(b, 1), np.ndarray[tuple[int], np.dtype[np.bool]])
assert_type(np.reshape(f4, 1), np.ndarray[tuple[int], np.dtype[np.float32]])
assert_type(np.reshape(f, 1), np.ndarray[tuple[int], np.dtype[Any]])
assert_type(np.reshape(AR_b, 1), np.ndarray[tuple[int], np.dtype[np.bool]])
assert_type(np.reshape(AR_f4, 1), np.ndarray[tuple[int], np.dtype[np.float32]])

assert_type(np.choose(1, [True, True]), Any)
assert_type(np.choose([1], [True, True]), npt.NDArray[Any])
assert_type(np.choose([1], AR_b), npt.NDArray[np.bool])
assert_type(np.choose([1], AR_b, out=AR_f4), npt.NDArray[np.float32])

assert_type(np.repeat(b, 1), npt.NDArray[np.bool])
assert_type(np.repeat(f4, 1), npt.NDArray[np.float32])
assert_type(np.repeat(f, 1), npt.NDArray[Any])
assert_type(np.repeat(AR_b, 1), npt.NDArray[np.bool])
assert_type(np.repeat(AR_f4, 1), npt.NDArray[np.float32])

# TODO: array_bdd tests for np.put()

assert_type(np.swapaxes([[0, 1]], 0, 0), npt.NDArray[Any])
assert_type(np.swapaxes(AR_b, 0, 0), npt.NDArray[np.bool])
assert_type(np.swapaxes(AR_f4, 0, 0), npt.NDArray[np.float32])

assert_type(np.transpose(b), npt.NDArray[np.bool])
assert_type(np.transpose(f4), npt.NDArray[np.float32])
assert_type(np.transpose(f), npt.NDArray[Any])
assert_type(np.transpose(AR_b), npt.NDArray[np.bool])
assert_type(np.transpose(AR_f4), npt.NDArray[np.float32])

assert_type(np.partition(b, 0, axis=None), npt.NDArray[np.bool])
assert_type(np.partition(f4, 0, axis=None), npt.NDArray[np.float32])
assert_type(np.partition(f, 0, axis=None), npt.NDArray[Any])
assert_type(np.partition(AR_b, 0), npt.NDArray[np.bool])
assert_type(np.partition(AR_f4, 0), npt.NDArray[np.float32])

assert_type(np.argpartition(b, 0), npt.NDArray[np.intp])
assert_type(np.argpartition(f4, 0), npt.NDArray[np.intp])
assert_type(np.argpartition(f, 0), npt.NDArray[np.intp])
assert_type(np.argpartition(AR_b, 0), npt.NDArray[np.intp])
assert_type(np.argpartition(AR_f4, 0), npt.NDArray[np.intp])

assert_type(np.sort([2, 1], 0), npt.NDArray[Any])
assert_type(np.sort(AR_b, 0), npt.NDArray[np.bool])
assert_type(np.sort(AR_f4, 0), npt.NDArray[np.float32])

assert_type(np.argsort(AR_b, 0), npt.NDArray[np.intp])
assert_type(np.argsort(AR_f4, 0), npt.NDArray[np.intp])

assert_type(np.argmax(AR_b), np.intp)
assert_type(np.argmax(AR_f4), np.intp)
assert_type(np.argmax(AR_b, axis=0), Any)
assert_type(np.argmax(AR_f4, axis=0), Any)
assert_type(np.argmax(AR_f4, out=AR_subclass), NDArraySubclass)

assert_type(np.argmin(AR_b), np.intp)
assert_type(np.argmin(AR_f4), np.intp)
assert_type(np.argmin(AR_b, axis=0), Any)
assert_type(np.argmin(AR_f4, axis=0), Any)
assert_type(np.argmin(AR_f4, out=AR_subclass), NDArraySubclass)

assert_type(np.searchsorted(AR_b[0], 0), np.intp)
assert_type(np.searchsorted(AR_f4[0], 0), np.intp)
assert_type(np.searchsorted(AR_b[0], [0]), npt.NDArray[np.intp])
assert_type(np.searchsorted(AR_f4[0], [0]), npt.NDArray[np.intp])

assert_type(np.resize(b, (5, 5)), np.ndarray[tuple[int, int], np.dtype[np.bool]])
assert_type(np.resize(f4, (5, 5)), np.ndarray[tuple[int, int], np.dtype[np.float32]])
assert_type(np.resize(f, (5, 5)), np.ndarray[tuple[int, int], np.dtype[Any]])
assert_type(np.resize(AR_b, (5, 5)), np.ndarray[tuple[int, int], np.dtype[np.bool]])
assert_type(np.resize(AR_f4, (5, 5)), np.ndarray[tuple[int, int], np.dtype[np.float32]])

assert_type(np.squeeze(b), np.bool)
assert_type(np.squeeze(f4), np.float32)
assert_type(np.squeeze(f), npt.NDArray[Any])
assert_type(np.squeeze(AR_b), npt.NDArray[np.bool])
assert_type(np.squeeze(AR_f4), npt.NDArray[np.float32])

assert_type(np.diagonal(AR_b), npt.NDArray[np.bool])
assert_type(np.diagonal(AR_f4), npt.NDArray[np.float32])

assert_type(np.trace(AR_b), Any)
assert_type(np.trace(AR_f4), Any)
assert_type(np.trace(AR_f4, out=AR_subclass), NDArraySubclass)

assert_type(np.ravel(b), np.ndarray[tuple[int], np.dtype[np.bool]])
assert_type(np.ravel(f4), np.ndarray[tuple[int], np.dtype[np.float32]])
assert_type(np.ravel(f), np.ndarray[tuple[int], np.dtype[np.float64 | np.int_ | np.bool]])
assert_type(np.ravel(AR_b), np.ndarray[tuple[int], np.dtype[np.bool]])
assert_type(np.ravel(AR_f4), np.ndarray[tuple[int], np.dtype[np.float32]])

assert_type(np.nonzero(AR_b), tuple[npt.NDArray[np.intp], ...])
assert_type(np.nonzero(AR_f4), tuple[npt.NDArray[np.intp], ...])
assert_type(np.nonzero(AR_1d), tuple[npt.NDArray[np.intp], ...])
assert_type(np.nonzero(AR_nd), tuple[npt.NDArray[np.intp], ...])

assert_type(np.shape(b), tuple[()])
assert_type(np.shape(f), tuple[()])
assert_type(np.shape([1]), tuple[int])
assert_type(np.shape([[2]]), tuple[int, int])
assert_type(np.shape([[[3]]]), tuple[int, ...])
assert_type(np.shape(AR_b), tuple[int, ...])
assert_type(np.shape(AR_nd), tuple[int, ...])
# these fail on mypy, but it works as expected with pyright/pylance
# assert_type(np.shape(AR_0d), tuple[()])
# assert_type(np.shape(AR_1d), tuple[int])
# assert_type(np.shape(AR_2d), tuple[int, int])

assert_type(np.compress([True], b), npt.NDArray[np.bool])
assert_type(np.compress([True], f4), npt.NDArray[np.float32])
assert_type(np.compress([True], f), npt.NDArray[Any])
assert_type(np.compress([True], AR_b), npt.NDArray[np.bool])
assert_type(np.compress([True], AR_f4), npt.NDArray[np.float32])

assert_type(np.clip(b, 0, 1.0), np.bool)
assert_type(np.clip(f4, -1, 1), np.float32)
assert_type(np.clip(f, 0, 1), Any)
assert_type(np.clip(AR_b, 0, 1), npt.NDArray[np.bool])
assert_type(np.clip(AR_f4, 0, 1), npt.NDArray[np.float32])
assert_type(np.clip([0], 0, 1), npt.NDArray[Any])
assert_type(np.clip(AR_b, 0, 1, out=AR_subclass), NDArraySubclass)

assert_type(np.sum(b), np.bool)
assert_type(np.sum(f4), np.float32)
assert_type(np.sum(f), Any)
assert_type(np.sum(AR_b), np.bool)
assert_type(np.sum(AR_f4), np.float32)
assert_type(np.sum(AR_b, axis=0), Any)
assert_type(np.sum(AR_f4, axis=0), Any)
assert_type(np.sum(AR_f4, out=AR_subclass), NDArraySubclass)
assert_type(np.sum(AR_f4, dtype=np.float64), np.float64)
assert_type(np.sum(AR_f4, None, np.float64), np.float64)
assert_type(np.sum(AR_f4, dtype=np.float64, keepdims=False), np.float64)
assert_type(np.sum(AR_f4, None, np.float64, keepdims=False), np.float64)
assert_type(np.sum(AR_f4, dtype=np.float64, keepdims=True), np.float64 | npt.NDArray[np.float64])
assert_type(np.sum(AR_f4, None, np.float64, keepdims=True), np.float64 | npt.NDArray[np.float64])

assert_type(np.all(b), np.bool)
assert_type(np.all(f4), np.bool)
assert_type(np.all(f), np.bool)
assert_type(np.all(AR_b), np.bool)
assert_type(np.all(AR_f4), np.bool)
assert_type(np.all(AR_b, axis=0), Any)
assert_type(np.all(AR_f4, axis=0), Any)
assert_type(np.all(AR_b, keepdims=True), Any)
assert_type(np.all(AR_f4, keepdims=True), Any)
assert_type(np.all(AR_f4, out=AR_subclass), NDArraySubclass)

assert_type(np.any(b), np.bool)
assert_type(np.any(f4), np.bool)
assert_type(np.any(f), np.bool)
assert_type(np.any(AR_b), np.bool)
assert_type(np.any(AR_f4), np.bool)
assert_type(np.any(AR_b, axis=0), Any)
assert_type(np.any(AR_f4, axis=0), Any)
assert_type(np.any(AR_b, keepdims=True), Any)
assert_type(np.any(AR_f4, keepdims=True), Any)
assert_type(np.any(AR_f4, out=AR_subclass), NDArraySubclass)

assert_type(np.cumsum(b), npt.NDArray[np.bool])
assert_type(np.cumsum(f4), npt.NDArray[np.float32])
assert_type(np.cumsum(f), npt.NDArray[Any])
assert_type(np.cumsum(AR_b), npt.NDArray[np.bool])
assert_type(np.cumsum(AR_f4), npt.NDArray[np.float32])
assert_type(np.cumsum(f, dtype=float), npt.NDArray[Any])
assert_type(np.cumsum(f, dtype=np.float64), npt.NDArray[np.float64])
assert_type(np.cumsum(AR_f4, out=AR_subclass), NDArraySubclass)

assert_type(np.cumulative_sum(b), npt.NDArray[np.bool])
assert_type(np.cumulative_sum(f4), npt.NDArray[np.float32])
assert_type(np.cumulative_sum(f), npt.NDArray[Any])
assert_type(np.cumulative_sum(AR_b), npt.NDArray[np.bool])
assert_type(np.cumulative_sum(AR_f4), npt.NDArray[np.float32])
assert_type(np.cumulative_sum(f, dtype=float), npt.NDArray[Any])
assert_type(np.cumulative_sum(f, dtype=np.float64), npt.NDArray[np.float64])
assert_type(np.cumulative_sum(AR_f4, out=AR_subclass), NDArraySubclass)

assert_type(np.ptp(b), np.bool)
assert_type(np.ptp(f4), np.float32)
assert_type(np.ptp(f), Any)
assert_type(np.ptp(AR_b), np.bool)
assert_type(np.ptp(AR_f4), np.float32)
assert_type(np.ptp(AR_b, axis=0), Any)
assert_type(np.ptp(AR_f4, axis=0), Any)
assert_type(np.ptp(AR_b, keepdims=True), Any)
assert_type(np.ptp(AR_f4, keepdims=True), Any)
assert_type(np.ptp(AR_f4, out=AR_subclass), NDArraySubclass)

assert_type(np.amax(b), np.bool)
assert_type(np.amax(f4), np.float32)
assert_type(np.amax(f), Any)
assert_type(np.amax(AR_b), np.bool)
assert_type(np.amax(AR_f4), np.float32)
assert_type(np.amax(AR_b, axis=0), Any)
assert_type(np.amax(AR_f4, axis=0), Any)
assert_type(np.amax(AR_b, keepdims=True), Any)
assert_type(np.amax(AR_f4, keepdims=True), Any)
assert_type(np.amax(AR_f4, out=AR_subclass), NDArraySubclass)

assert_type(np.amin(b), np.bool)
assert_type(np.amin(f4), np.float32)
assert_type(np.amin(f), Any)
assert_type(np.amin(AR_b), np.bool)
assert_type(np.amin(AR_f4), np.float32)
assert_type(np.amin(AR_b, axis=0), Any)
assert_type(np.amin(AR_f4, axis=0), Any)
assert_type(np.amin(AR_b, keepdims=True), Any)
assert_type(np.amin(AR_f4, keepdims=True), Any)
assert_type(np.amin(AR_f4, out=AR_subclass), NDArraySubclass)

assert_type(np.prod(AR_b), np.int_)
assert_type(np.prod(AR_u8), np.uint64)
assert_type(np.prod(AR_i8), np.int64)
assert_type(np.prod(AR_f4), np.floating[Any])
assert_type(np.prod(AR_c16), np.complexfloating[Any, Any])
assert_type(np.prod(AR_O), Any)
assert_type(np.prod(AR_f4, axis=0), Any)
assert_type(np.prod(AR_f4, keepdims=True), Any)
assert_type(np.prod(AR_f4, dtype=np.float64), np.float64)
assert_type(np.prod(AR_f4, dtype=float), Any)
assert_type(np.prod(AR_f4, out=AR_subclass), NDArraySubclass)

assert_type(np.cumprod(AR_b), npt.NDArray[np.int_])
assert_type(np.cumprod(AR_u8), npt.NDArray[np.uint64])
assert_type(np.cumprod(AR_i8), npt.NDArray[np.int64])
assert_type(np.cumprod(AR_f4), npt.NDArray[np.floating[Any]])
assert_type(np.cumprod(AR_c16), npt.NDArray[np.complexfloating[Any, Any]])
assert_type(np.cumprod(AR_O), npt.NDArray[np.object_])
assert_type(np.cumprod(AR_f4, axis=0), npt.NDArray[np.floating[Any]])
assert_type(np.cumprod(AR_f4, dtype=np.float64), npt.NDArray[np.float64])
assert_type(np.cumprod(AR_f4, dtype=float), npt.NDArray[Any])
assert_type(np.cumprod(AR_f4, out=AR_subclass), NDArraySubclass)

assert_type(np.cumulative_prod(AR_b), npt.NDArray[np.int_])
assert_type(np.cumulative_prod(AR_u8), npt.NDArray[np.uint64])
assert_type(np.cumulative_prod(AR_i8), npt.NDArray[np.int64])
assert_type(np.cumulative_prod(AR_f4), npt.NDArray[np.floating[Any]])
assert_type(np.cumulative_prod(AR_c16), npt.NDArray[np.complexfloating[Any, Any]])
assert_type(np.cumulative_prod(AR_O), npt.NDArray[np.object_])
assert_type(np.cumulative_prod(AR_f4, axis=0), npt.NDArray[np.floating[Any]])
assert_type(np.cumulative_prod(AR_f4, dtype=np.float64), npt.NDArray[np.float64])
assert_type(np.cumulative_prod(AR_f4, dtype=float), npt.NDArray[Any])
assert_type(np.cumulative_prod(AR_f4, out=AR_subclass), NDArraySubclass)

assert_type(np.ndim(b), int)
assert_type(np.ndim(f4), int)
assert_type(np.ndim(f), int)
assert_type(np.ndim(AR_b), int)
assert_type(np.ndim(AR_f4), int)

assert_type(np.size(b), int)
assert_type(np.size(f4), int)
assert_type(np.size(f), int)
assert_type(np.size(AR_b), int)
assert_type(np.size(AR_f4), int)

assert_type(np.around(b), np.float16)
assert_type(np.around(f), Any)
assert_type(np.around(i8), np.int64)
assert_type(np.around(f4), np.float32)
assert_type(np.around(AR_b), npt.NDArray[np.float16])
assert_type(np.around(AR_i8), npt.NDArray[np.int64])
assert_type(np.around(AR_f4), npt.NDArray[np.float32])
assert_type(np.around([1.5]), npt.NDArray[Any])
assert_type(np.around(AR_f4, out=AR_subclass), NDArraySubclass)

assert_type(np.mean(AR_b), np.floating[Any])
assert_type(np.mean(AR_i8), np.floating[Any])
assert_type(np.mean(AR_f4), np.floating[Any])
assert_type(np.mean(AR_m), np.timedelta64)
assert_type(np.mean(AR_c16), np.complexfloating[Any, Any])
assert_type(np.mean(AR_O), Any)
assert_type(np.mean(AR_f4, axis=0), Any)
assert_type(np.mean(AR_f4, keepdims=True), Any)
assert_type(np.mean(AR_f4, dtype=float), Any)
assert_type(np.mean(AR_f4, dtype=np.float64), np.float64)
assert_type(np.mean(AR_f4, out=AR_subclass), NDArraySubclass)
assert_type(np.mean(AR_f4, dtype=np.float64), np.float64)
assert_type(np.mean(AR_f4, None, np.float64), np.float64)
assert_type(np.mean(AR_f4, dtype=np.float64, keepdims=False), np.float64)
assert_type(np.mean(AR_f4, None, np.float64, keepdims=False), np.float64)
assert_type(np.mean(AR_f4, dtype=np.float64, keepdims=True), np.float64 | npt.NDArray[np.float64])
assert_type(np.mean(AR_f4, None, np.float64, keepdims=True), np.float64 | npt.NDArray[np.float64])

assert_type(np.std(AR_b), np.floating[Any])
assert_type(np.std(AR_i8), np.floating[Any])
assert_type(np.std(AR_f4), np.floating[Any])
assert_type(np.std(AR_c16), np.floating[Any])
assert_type(np.std(AR_O), Any)
assert_type(np.std(AR_f4, axis=0), Any)
assert_type(np.std(AR_f4, keepdims=True), Any)
assert_type(np.std(AR_f4, dtype=float), Any)
assert_type(np.std(AR_f4, dtype=np.float64), np.float64)
assert_type(np.std(AR_f4, out=AR_subclass), NDArraySubclass)

assert_type(np.var(AR_b), np.floating[Any])
assert_type(np.var(AR_i8), np.floating[Any])
assert_type(np.var(AR_f4), np.floating[Any])
assert_type(np.var(AR_c16), np.floating[Any])
assert_type(np.var(AR_O), Any)
assert_type(np.var(AR_f4, axis=0), Any)
assert_type(np.var(AR_f4, keepdims=True), Any)
assert_type(np.var(AR_f4, dtype=float), Any)
assert_type(np.var(AR_f4, dtype=np.float64), np.float64)
assert_type(np.var(AR_f4, out=AR_subclass), NDArraySubclass)
