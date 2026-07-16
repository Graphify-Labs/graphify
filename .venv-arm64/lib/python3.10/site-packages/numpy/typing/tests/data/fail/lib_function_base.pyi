from typing import Any

import numpy as np
import numpy.typing as npt

AR_f8: npt.NDArray[np.float64]
AR_c16: npt.NDArray[np.complex128]
AR_m: npt.NDArray[np.timedelta64]
AR_M: npt.NDArray[np.datetime64]
AR_O: npt.NDArray[np.object_]
AR_b_list: list[npt.NDArray[np.bool]]

def fn_none_i(a: None, /) -> npt.NDArray[Any]: ...
def fn_ar_i(a: npt.NDArray[np.float64], posarg: int, /) -> npt.NDArray[Any]: ...

np.average(AR_m)  # E: incompatible type
np.select(1, [AR_f8])  # E: incompatible type
np.angle(AR_m)  # E: incompatible type
np.unwrap(AR_m)  # E: incompatible type
np.unwrap(AR_c16)  # E: incompatible type
np.trim_zeros(1)  # E: incompatible type
np.place(1, [True], 1.5)  # E: incompatible type
np.vectorize(1)  # E: incompatible type
np.place(AR_f8, slice(None), 5)  # E: incompatible type

np.piecewise(AR_f8, True, [fn_ar_i], 42)  # E: No overload variants
# TODO: enable these once mypy actually supports ParamSpec (released in 2021)
# NOTE: pyright correctly reports errors for these (`reportCallIssue`)
# np.piecewise(AR_f8, AR_b_list, [fn_none_i])  # E: No overload variants
# np.piecewise(AR_f8, AR_b_list, [fn_ar_i])  # E: No overload variant
# np.piecewise(AR_f8, AR_b_list, [fn_ar_i], 3.14)  # E: No overload variant
# np.piecewise(AR_f8, AR_b_list, [fn_ar_i], 42, None)  # E: No overload variant
# np.piecewise(AR_f8, AR_b_list, [fn_ar_i], 42, _=None)  # E: No overload variant

np.interp(AR_f8, AR_c16, AR_f8)  # E: incompatible type
np.interp(AR_c16, AR_f8, AR_f8)  # E: incompatible type
np.interp(AR_f8, AR_f8, AR_f8, period=AR_c16)  # E: No overload variant
np.interp(AR_f8, AR_f8, AR_O)  # E: incompatible type

np.cov(AR_m)  # E: incompatible type
np.cov(AR_O)  # E: incompatible type
np.corrcoef(AR_m)  # E: incompatible type
np.corrcoef(AR_O)  # E: incompatible type
np.corrcoef(AR_f8, bias=True)  # E: No overload variant
np.corrcoef(AR_f8, ddof=2)  # E: No overload variant
np.blackman(1j)  # E: incompatible type
np.bartlett(1j)  # E: incompatible type
np.hanning(1j)  # E: incompatible type
np.hamming(1j)  # E: incompatible type
np.hamming(AR_c16)  # E: incompatible type
np.kaiser(1j, 1)  # E: incompatible type
np.sinc(AR_O)  # E: incompatible type
np.median(AR_M)  # E: incompatible type

np.percentile(AR_f8, 50j)  # E: No overload variant
np.percentile(AR_f8, 50, interpolation="bob")  # E: No overload variant
np.quantile(AR_f8, 0.5j)  # E: No overload variant
np.quantile(AR_f8, 0.5, interpolation="bob")  # E: No overload variant
np.meshgrid(AR_f8, AR_f8, indexing="bob")  # E: incompatible type
np.delete(AR_f8, AR_f8)  # E: incompatible type
np.insert(AR_f8, AR_f8, 1.5)  # E: incompatible type
np.digitize(AR_f8, 1j)  # E: No overload variant
