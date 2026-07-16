"""Approximations of graph properties and Heuristic methods for optimization.

The functions in this class are not imported into the top-level ``networkx``
namespace so the easiest way to use them is with::

    >>> from networkx.algorithms import approximation

Another option is to import the specific function with
``from networkx.algorithms.approximation import function_name``.

"""

from networkx.algorithms.approximation.clustering_coefficient import *
from networkx.algorithms.approximation.clique import *
from networkx.algorithms.approximation.connectivity import *
from networkx.algorithms.approximation.distance_measures import *
from networkx.algorithms.approximation.dominating_set import *
from networkx.algorithms.approximation.kcomponents import *
from networkx.algorithms.approximation.matching import *
from networkx.algorithms.approximation.ramsey import *
from networkx.algorithms.approximation.steinertree import *
from networkx.algorithms.approximation.traveling_salesman import *
from networkx.algorithms.approximation.treewidth import *
from networkx.algorithms.approximation.vertex_cover import *
from networkx.algorithms.approximation.maxcut import *
