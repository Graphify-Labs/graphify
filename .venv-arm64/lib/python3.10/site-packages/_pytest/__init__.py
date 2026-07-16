from __future__ import annotations


__all__ = ["__version__", "version_tuple"]

try:
    from ._version import version as __version__
    from ._version import version_tuple
except ImportError:  # pragma: no cover
    # broken installation, we don't even try
    # unknown only works because we do poor mans version compare
    __version__ = "unknown"
    version_tuple = (0, 0, "unknown")
