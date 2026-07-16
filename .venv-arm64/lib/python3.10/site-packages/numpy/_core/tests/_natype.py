# Vendored implementation of pandas.NA, adapted from pandas/_libs/missing.pyx
#
# This is vendored to avoid adding pandas as a test dependency.

__all__ = ["pd_NA"]

import numbers

import numpy as np

def _create_binary_propagating_op(name, is_divmod=False):
    is_cmp = name.strip("_") in ["eq", "ne", "le", "lt", "ge", "gt"]

    def method(self, other):
        if (
            other is pd_NA
            or isinstance(other, (str, bytes))
            or isinstance(other, (numbers.Number, np.bool))
            or isinstance(other, np.ndarray)
            and not other.shape
        ):
            # Need the other.shape clause to handle NumPy scalars,
            # since we do a setitem on `out` below, which
            # won't work for NumPy scalars.
            if is_divmod:
                return pd_NA, pd_NA
            else:
                return pd_NA

        elif isinstance(other, np.ndarray):
            out = np.empty(other.shape, dtype=object)
            out[:] = pd_NA

            if is_divmod:
                return out, out.copy()
            else:
                return out

        elif is_cmp and isinstance(other, (np.datetime64, np.timedelta64)):
            return pd_NA

        elif isinstance(other, np.datetime64):
            if name in ["__sub__", "__rsub__"]:
                return pd_NA

        elif isinstance(other, np.timedelta64):
            if name in ["__sub__", "__rsub__", "__add__", "__radd__"]:
                return pd_NA

        return NotImplemented

    method.__name__ = name
    return method


def _create_unary_propagating_op(name: str):
    def method(self):
        return pd_NA

    method.__name__ = name
    return method


class NAType:
    def __repr__(self) -> str:
        return "<NA>"

    def __format__(self, format_spec) -> str:
        try:
            return self.__repr__().__format__(format_spec)
        except ValueError:
            return self.__repr__()

    def __bool__(self):
        raise TypeError("boolean value of NA is ambiguous")

    def __hash__(self):
        exponent = 31 if is_32bit else 61
        return 2**exponent - 1

    def __reduce__(self):
        return "pd_NA"

    # Binary arithmetic and comparison ops -> propagate

    __add__ = _create_binary_propagating_op("__add__")
    __radd__ = _create_binary_propagating_op("__radd__")
    __sub__ = _create_binary_propagating_op("__sub__")
    __rsub__ = _create_binary_propagating_op("__rsub__")
    __mul__ = _create_binary_propagating_op("__mul__")
    __rmul__ = _create_binary_propagating_op("__rmul__")
    __matmul__ = _create_binary_propagating_op("__matmul__")
    __rmatmul__ = _create_binary_propagating_op("__rmatmul__")
    __truediv__ = _create_binary_propagating_op("__truediv__")
    __rtruediv__ = _create_binary_propagating_op("__rtruediv__")
    __floordiv__ = _create_binary_propagating_op("__floordiv__")
    __rfloordiv__ = _create_binary_propagating_op("__rfloordiv__")
    __mod__ = _create_binary_propagating_op("__mod__")
    __rmod__ = _create_binary_propagating_op("__rmod__")
    __divmod__ = _create_binary_propagating_op("__divmod__", is_divmod=True)
    __rdivmod__ = _create_binary_propagating_op("__rdivmod__", is_divmod=True)
    # __lshift__ and __rshift__ are not implemented

    __eq__ = _create_binary_propagating_op("__eq__")
    __ne__ = _create_binary_propagating_op("__ne__")
    __le__ = _create_binary_propagating_op("__le__")
    __lt__ = _create_binary_propagating_op("__lt__")
    __gt__ = _create_binary_propagating_op("__gt__")
    __ge__ = _create_binary_propagating_op("__ge__")

    # Unary ops

    __neg__ = _create_unary_propagating_op("__neg__")
    __pos__ = _create_unary_propagating_op("__pos__")
    __abs__ = _create_unary_propagating_op("__abs__")
    __invert__ = _create_unary_propagating_op("__invert__")

    # pow has special
    def __pow__(self, other):
        if other is pd_NA:
            return pd_NA
        elif isinstance(other, (numbers.Number, np.bool)):
            if other == 0:
                # returning positive is correct for +/- 0.
                return type(other)(1)
            else:
                return pd_NA
        elif util.is_array(other):
            return np.where(other == 0, other.dtype.type(1), pd_NA)

        return NotImplemented

    def __rpow__(self, other):
        if other is pd_NA:
            return pd_NA
        elif isinstance(other, (numbers.Number, np.bool)):
            if other == 1:
                return other
            else:
                return pd_NA
        elif util.is_array(other):
            return np.where(other == 1, other, pd_NA)
        return NotImplemented

    # Logical ops using Kleene logic

    def __and__(self, other):
        if other is False:
            return False
        elif other is True or other is pd_NA:
            return pd_NA
        return NotImplemented

    __rand__ = __and__

    def __or__(self, other):
        if other is True:
            return True
        elif other is False or other is pd_NA:
            return pd_NA
        return NotImplemented

    __ror__ = __or__

    def __xor__(self, other):
        if other is False or other is True or other is pd_NA:
            return pd_NA
        return NotImplemented

    __rxor__ = __xor__

    __array_priority__ = 1000
    _HANDLED_TYPES = (np.ndarray, numbers.Number, str, np.bool)

    def __array_ufunc__(self, ufunc, method, *inputs, **kwargs):
        types = self._HANDLED_TYPES + (NAType,)
        for x in inputs:
            if not isinstance(x, types):
                return NotImplemented

        if method != "__call__":
            raise ValueError(f"ufunc method '{method}' not supported for NA")
        result = maybe_dispatch_ufunc_to_dunder_op(
            self, ufunc, method, *inputs, **kwargs
        )
        if result is NotImplemented:
            # For a NumPy ufunc that's not a binop, like np.logaddexp
            index = [i for i, x in enumerate(inputs) if x is pd_NA][0]
            result = np.broadcast_arrays(*inputs)[index]
            if result.ndim == 0:
                result = result.item()
            if ufunc.nout > 1:
                result = (pd_NA,) * ufunc.nout

        return result


pd_NA = NAType()
