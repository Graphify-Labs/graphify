"""
Automatically choose between `tqdm.notebook` and `tqdm.std`.

Usage:
>>> from tqdm.autonotebook import trange, tqdm
>>> for i in trange(10):
...     ...
"""
import os
import sys
from warnings import warn

try:
    if 'ipykernel.zmqshell' in sys.modules:
        if any(i == 'QT_API' or i.startswith('SPYDER') for i in os.environ):
            raise ImportError("console")  # jupyter-qtconsole/spyder
        ipy = sys.modules['IPython'].get_ipython().__class__.__name__.lower()
        if 'qt' in ipy or 'spyder' in ipy:
            raise ImportError("console")  # older jupyter-qtconsole/spyder
        # jupyter-notebook/jupyterlab/vscode/binder/colab
    elif 'IPython.utils._process_emscripten' in sys.modules:
        pass  # jupyterlite (pyodide)/jupyterlite-xeus
    else:
        raise ImportError("console")  # ipython/jupyter-console
    from .notebook import WARN_NOIPYW, IProgress
    if IProgress is None:
        from .std import TqdmWarning
        warn(WARN_NOIPYW, TqdmWarning, stacklevel=2)
        raise ImportError('ipywidgets')
except Exception:
    from .std import tqdm, trange
else:  # pragma: no cover
    from .notebook import tqdm, trange
    from .std import TqdmExperimentalWarning
    warn("Using `tqdm.autonotebook.tqdm` in notebook mode."
         " Use `tqdm.tqdm` instead to force console mode"
         " (e.g. in jupyter console)", TqdmExperimentalWarning, stacklevel=2)
__all__ = ["tqdm", "trange"]
