import numpy as np
import numpy.typing as npt

AR_f8: npt.NDArray[np.float64]

np.sin.nin + "foo"  # E: Unsupported operand types
np.sin(1, foo="bar")  # E: No overload variant

np.abs(None)  # E: No overload variant

np.add(1, 1, 1)  # E: No overload variant
np.add(1, 1, axis=0)  # E: No overload variant

np.matmul(AR_f8, AR_f8, where=True)  # E: No overload variant

np.frexp(AR_f8, out=None)  # E: No overload variant
np.frexp(AR_f8, out=AR_f8)  # E: No overload variant
