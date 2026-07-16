import numpy.exceptions as ex

ex.AxisError("test")
ex.AxisError(1, ndim=2)
ex.AxisError(1, ndim=2, msg_prefix="error")
ex.AxisError(1, ndim=2, msg_prefix=None)
