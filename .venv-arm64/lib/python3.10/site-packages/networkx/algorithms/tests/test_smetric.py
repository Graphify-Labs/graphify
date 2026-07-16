import pytest

import networkx as nx


def test_smetric():
    G = nx.Graph([(1, 2), (2, 3), (2, 4), (1, 4)])
    assert nx.s_metric(G) == 19.0
