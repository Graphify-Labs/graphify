def __getattr__(attr_name):
    from numpy._core import umath
    from ._utils import _raise_warning
    ret = getattr(umath, attr_name, None)
    if ret is None:
        raise AttributeError(
            f"module 'numpy.core.umath' has no attribute {attr_name}")
    _raise_warning(attr_name, "umath")
    return ret
