def __getattr__(attr_name):
    from numpy._core import einsumfunc
    from ._utils import _raise_warning
    ret = getattr(einsumfunc, attr_name, None)
    if ret is None:
        raise AttributeError(
            f"module 'numpy.core.einsumfunc' has no attribute {attr_name}")
    _raise_warning(attr_name, "einsumfunc")
    return ret
