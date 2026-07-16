def __getattr__(attr_name):
    from numpy._core import defchararray
    from ._utils import _raise_warning
    ret = getattr(defchararray, attr_name, None)
    if ret is None:
        raise AttributeError(
            f"module 'numpy.core.defchararray' has no attribute {attr_name}")
    _raise_warning(attr_name, "defchararray")
    return ret
