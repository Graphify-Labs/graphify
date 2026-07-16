import types

import numpy as np
from numpy import f2py

from typing_extensions import assert_type

assert_type(np, types.ModuleType)

assert_type(np.char, types.ModuleType)
assert_type(np.ctypeslib, types.ModuleType)
assert_type(np.emath, types.ModuleType)
assert_type(np.fft, types.ModuleType)
assert_type(np.lib, types.ModuleType)
assert_type(np.linalg, types.ModuleType)
assert_type(np.ma, types.ModuleType)
assert_type(np.matrixlib, types.ModuleType)
assert_type(np.polynomial, types.ModuleType)
assert_type(np.random, types.ModuleType)
assert_type(np.rec, types.ModuleType)
assert_type(np.testing, types.ModuleType)
assert_type(np.version, types.ModuleType)
assert_type(np.exceptions, types.ModuleType)
assert_type(np.dtypes, types.ModuleType)

assert_type(np.lib.format, types.ModuleType)
assert_type(np.lib.mixins, types.ModuleType)
assert_type(np.lib.scimath, types.ModuleType)
assert_type(np.lib.stride_tricks, types.ModuleType)
assert_type(np.ma.extras, types.ModuleType)
assert_type(np.polynomial.chebyshev, types.ModuleType)
assert_type(np.polynomial.hermite, types.ModuleType)
assert_type(np.polynomial.hermite_e, types.ModuleType)
assert_type(np.polynomial.laguerre, types.ModuleType)
assert_type(np.polynomial.legendre, types.ModuleType)
assert_type(np.polynomial.polynomial, types.ModuleType)

assert_type(np.__path__, list[str])
assert_type(np.__version__, str)
assert_type(np.test, np._pytesttester.PytestTester)
assert_type(np.test.module_name, str)

assert_type(np.__all__, list[str])
assert_type(np.char.__all__, list[str])
assert_type(np.ctypeslib.__all__, list[str])
assert_type(np.emath.__all__, list[str])
assert_type(np.lib.__all__, list[str])
assert_type(np.ma.__all__, list[str])
assert_type(np.random.__all__, list[str])
assert_type(np.rec.__all__, list[str])
assert_type(np.testing.__all__, list[str])
assert_type(f2py.__all__, list[str])
