def __getattr__(attr_name):
    from numpy._core import shape_base
    from ._utils import _raise_warning
    ret = getattr(shape_base, attr_name, None)
    if ret is None:
        raise AttributeError(
            f"module 'numpy.core.shape_base' has no attribute {attr_name}")
    _raise_warning(attr_name, "shape_base")
    return ret
