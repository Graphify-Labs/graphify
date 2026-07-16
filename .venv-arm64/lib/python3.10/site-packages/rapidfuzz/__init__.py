"""
rapid string matching library
"""

from __future__ import annotations

__author__: str = "Max Bachmann"
__license__: str = "MIT"
__version__: str = "3.14.5"

from rapidfuzz import distance, fuzz, process, utils

__all__ = ["distance", "fuzz", "get_include", "process", "utils"]


def get_include():
    """
    Return the directory that contains the RapidFuzz \\*.h header files.
    Extension modules that need to compile against RapidFuzz should use this
    function to locate the appropriate include directory.
    Notes
    -----
    When using ``distutils``, for example in ``setup.py``.
    ::
        import rapidfuzz_capi
        ...
        Extension('extension_name', ...
                include_dirs=[rapidfuzz_capi.get_include()])
        ...
    """
    from pathlib import Path

    return str(Path(__file__).parent)
