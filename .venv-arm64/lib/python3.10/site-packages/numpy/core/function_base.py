def __getattr__(attr_name):
    from numpy._core import function_base
    from ._utils import _raise_warning
    ret = getattr(function_base, attr_name, None)
    if ret is None:
        raise AttributeError(
            f"module 'numpy.core.function_base' has no attribute {attr_name}")
    _raise_warning(attr_name, "function_base")
    return ret
