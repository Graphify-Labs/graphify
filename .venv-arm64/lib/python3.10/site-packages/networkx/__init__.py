"""
NetworkX
========

NetworkX is a Python package for the creation, manipulation, and study of the
structure, dynamics, and functions of complex networks.

See https://networkx.org for complete documentation.
"""

__version__ = "3.4.2"


# These are imported in order as listed
from networkx.lazy_imports import _lazy_import

from networkx.exception import *

from networkx import utils
from networkx.utils import _clear_cache, _dispatchable

# load_and_call entry_points, set configs
config = utils.backends._set_configs_from_environment()
utils.config = utils.configs.config = config  # type: ignore[attr-defined]

from networkx import classes
from networkx.classes import filters
from networkx.classes import *

from networkx import convert
from networkx.convert import *

from networkx import convert_matrix
from networkx.convert_matrix import *

from networkx import relabel
from networkx.relabel import *

from networkx import generators
from networkx.generators import *

from networkx import readwrite
from networkx.readwrite import *

# Need to test with SciPy, when available
from networkx import algorithms
from networkx.algorithms import *

from networkx import linalg
from networkx.linalg import *

from networkx import drawing
from networkx.drawing import *
