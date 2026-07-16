import numpy.exceptions as ex

ex.AxisError(1.0)  # E: No overload variant
ex.AxisError(1, ndim=2.0)  # E: No overload variant
ex.AxisError(2, msg_prefix=404)  # E: No overload variant
