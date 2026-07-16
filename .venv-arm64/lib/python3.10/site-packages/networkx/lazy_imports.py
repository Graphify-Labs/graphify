import importlib
import importlib.util
import inspect
import os
import sys
import types

__all__ = ["attach", "_lazy_import"]


def attach(module_name, submodules=None, submod_attrs=None):
    """Attach lazily loaded submodules, and functions or other attributes.

    Typically, modules import submodules and attributes as follows::

      import mysubmodule
      import anothersubmodule

      from .foo import someattr

    The idea of  this function is to replace the `__init__.py`
    module's `__getattr__`, `__dir__`, and `__all__` attributes such that
    all imports work exactly the way they normally would, except that the
    actual import is delayed until the resulting module object is first used.

    The typical way to call this function, replacing the above imports, is::

      __getattr__, __lazy_dir__, __all__ = lazy.attach(
          __name__, ["mysubmodule", "anothersubmodule"], {"foo": "someattr"}
      )

    This functionality requires Python 3.7 or higher.

    Parameters
    ----------
    module_name : str
        Typically use __name__.
    submodules : set
        List of submodules to lazily import.
    submod_attrs : dict
        Dictionary of submodule -> list of attributes / functions.
        These attributes are imported as they are used.

    Returns
    -------
    __getattr__, __dir__, __all__

    """
    if submod_attrs is None:
        submod_attrs = {}

    if submodules is None:
        submodules = set()
    else:
        submodules = set(submodules)

    attr_to_modules = {
        attr: mod for mod, attrs in submod_attrs.items() for attr in attrs
    }

    __all__ = list(submodules | attr_to_modules.keys())

    def __getattr__(name):
        if name in submodules:
            return importlib.import_module(f"{module_name}.{name}")
        elif name in attr_to_modules:
            submod = importlib.import_module(f"{module_name}.{attr_to_modules[name]}")
            return getattr(submod, name)
        else:
            raise AttributeError(f"No {module_name} attribute {name}")

    def __dir__():
        return __all__

    if os.environ.get("EAGER_IMPORT", ""):
        for attr in set(attr_to_modules.keys()) | submodules:
            __getattr__(attr)

    return __getattr__, __dir__, list(__all__)


class DelayedImportErrorModule(types.ModuleType):
    def __init__(self, frame_data, *args, **kwargs):
        self.__frame_data = frame_data
        super().__init__(*args, **kwargs)

    def __getattr__(self, x):
        if x in ("__class__", "__file__", "__frame_data"):
            super().__getattr__(x)
        else:
            fd = self.__frame_data
            raise ModuleNotFoundError(
                f"No module named '{fd['spec']}'\n\n"
                "This error is lazily reported, having originally occurred in\n"
                f'  File {fd["filename"]}, line {fd["lineno"]}, in {fd["function"]}\n\n'
                f'----> {"".join(fd["code_context"] or "").strip()}'
            )


def _lazy_import(fullname):
    """Return a lazily imported proxy for a module or library.

    Warning
    -------
    Importing using this function can currently cause trouble
    when the user tries to import from a subpackage of a module before
    the package is fully imported. In particular, this idiom may not work:

      np = lazy_import("numpy")
      from numpy.lib import recfunctions

    This is due to a difference in the way Python's LazyLoader handles
    subpackage imports compared to the normal import process. Hopefully
    we will get Python's LazyLoader to fix this, or find a workaround.
    In the meantime, this is a potential problem.

    The workaround is to import numpy before importing from the subpackage.

    Notes
    -----
    We often see the following pattern::

      def myfunc():
          import scipy as sp
          sp.argmin(...)
          ....

    This is to prevent a library, in this case `scipy`, from being
    imported at function definition time, since that can be slow.

    This function provides a proxy module that, upon access, imports
    the actual module.  So the idiom equivalent to the above example is::

      sp = lazy.load("scipy")

      def myfunc():
          sp.argmin(...)
          ....

    The initial import time is fast because the actual import is delayed
    until the first attribute is requested. The overall import time may
    decrease as well for users that don't make use of large portions
    of the library.

    Parameters
    ----------
    fullname : str
        The full name of the package or subpackage to import.  For example::

          sp = lazy.load("scipy")  # import scipy as sp
          spla = lazy.load("scipy.linalg")  # import scipy.linalg as spla

    Returns
    -------
    pm : importlib.util._LazyModule
        Proxy module. Can be used like any regularly imported module.
        Actual loading of the module occurs upon first attribute request.

    """
    try:
        return sys.modules[fullname]
    except:
        pass

    # Not previously loaded -- look it up
    spec = importlib.util.find_spec(fullname)

    if spec is None:
        try:
            parent = inspect.stack()[1]
            frame_data = {
                "spec": fullname,
                "filename": parent.filename,
                "lineno": parent.lineno,
                "function": parent.function,
                "code_context": parent.code_context,
            }
            return DelayedImportErrorModule(frame_data, "DelayedImportErrorModule")
        finally:
            del parent

    module = importlib.util.module_from_spec(spec)
    sys.modules[fullname] = module

    loader = importlib.util.LazyLoader(spec.loader)
    loader.exec_module(module)

    return module
