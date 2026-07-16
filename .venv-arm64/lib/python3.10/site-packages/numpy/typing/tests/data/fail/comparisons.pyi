import numpy as np
import numpy.typing as npt

AR_i: npt.NDArray[np.int64]
AR_f: npt.NDArray[np.float64]
AR_c: npt.NDArray[np.complex128]
AR_m: npt.NDArray[np.timedelta64]
AR_M: npt.NDArray[np.datetime64]

AR_f > AR_m  # E: Unsupported operand types
AR_c > AR_m  # E: Unsupported operand types

AR_m > AR_f  # E: Unsupported operand types
AR_m > AR_c  # E: Unsupported operand types

AR_i > AR_M  # E: Unsupported operand types
AR_f > AR_M  # E: Unsupported operand types
AR_m > AR_M  # E: Unsupported operand types

AR_M > AR_i  # E: Unsupported operand types
AR_M > AR_f  # E: Unsupported operand types
AR_M > AR_m  # E: Unsupported operand types

AR_i > str()  # E: No overload variant
AR_i > bytes()  # E: No overload variant
str() > AR_M  # E: Unsupported operand types
bytes() > AR_M  # E: Unsupported operand types
