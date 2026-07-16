import numpy.exceptions as ex

from typing_extensions import assert_type

assert_type(ex.ModuleDeprecationWarning(), ex.ModuleDeprecationWarning)
assert_type(ex.VisibleDeprecationWarning(), ex.VisibleDeprecationWarning)
assert_type(ex.ComplexWarning(), ex.ComplexWarning)
assert_type(ex.RankWarning(), ex.RankWarning)
assert_type(ex.TooHardError(), ex.TooHardError)
assert_type(ex.AxisError("test"), ex.AxisError)
assert_type(ex.AxisError(5, 1), ex.AxisError)
