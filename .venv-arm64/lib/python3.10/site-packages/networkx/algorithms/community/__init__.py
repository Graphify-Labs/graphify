"""Functions for computing and measuring community structure.

The ``community`` subpackage can be accessed by using :mod:`networkx.community`, then accessing the
functions as attributes of ``community``. For example::

    >>> import networkx as nx
    >>> G = nx.barbell_graph(5, 1)
    >>> communities_generator = nx.community.girvan_newman(G)
    >>> top_level_communities = next(communities_generator)
    >>> next_level_communities = next(communities_generator)
    >>> sorted(map(sorted, next_level_communities))
    [[0, 1, 2, 3, 4], [5], [6, 7, 8, 9, 10]]

"""

from networkx.algorithms.community.asyn_fluid import *
from networkx.algorithms.community.centrality import *
from networkx.algorithms.community.divisive import *
from networkx.algorithms.community.kclique import *
from networkx.algorithms.community.kernighan_lin import *
from networkx.algorithms.community.label_propagation import *
from networkx.algorithms.community.lukes import *
from networkx.algorithms.community.modularity_max import *
from networkx.algorithms.community.quality import *
from networkx.algorithms.community.community_utils import *
from networkx.algorithms.community.louvain import *
