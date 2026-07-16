from importlib.metadata import PackageNotFoundError, version

from .decorator import cross_origin
from .extension import CORS

try:
    __version__ = version("flask-cors")
except PackageNotFoundError:  # pragma: no cover - package is not installed
    __version__ = "unknown"

__all__ = ["CORS", "__version__", "cross_origin"]

# Set default logging handler to avoid "No handler found" warnings.
import logging
from logging import NullHandler

# Set initial level to WARN. Users must manually enable logging for
# flask_cors to see our logging.
rootlogger = logging.getLogger(__name__)
rootlogger.addHandler(NullHandler())

if rootlogger.level == logging.NOTSET:
    rootlogger.setLevel(logging.WARN)
