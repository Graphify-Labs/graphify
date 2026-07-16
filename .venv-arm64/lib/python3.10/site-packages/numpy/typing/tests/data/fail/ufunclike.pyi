import numpy as np
import numpy.typing as npt

AR_c: npt.NDArray[np.complex128]
AR_m: npt.NDArray[np.timedelta64]
AR_M: npt.NDArray[np.datetime64]
AR_O: npt.NDArray[np.object_]

np.fix(AR_c)  # E: incompatible type
np.fix(AR_m)  # E: incompatible type
np.fix(AR_M)  # E: incompatible type

np.isposinf(AR_c)  # E: incompatible type
np.isposinf(AR_m)  # E: incompatible type
np.isposinf(AR_M)  # E: incompatible type
np.isposinf(AR_O)  # E: incompatible type

np.isneginf(AR_c)  # E: incompatible type
np.isneginf(AR_m)  # E: incompatible type
np.isneginf(AR_M)  # E: incompatible type
np.isneginf(AR_O)  # E: incompatible type
