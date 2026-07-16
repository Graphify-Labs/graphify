import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("scipy")

import networkx as nx
from networkx.generators.degree_seq import havel_hakimi_graph
from networkx.generators.expanders import margulis_gabber_galil_graph


class TestLaplacian:
    @classmethod
    def setup_class(cls):
        deg = [3, 2, 2, 1, 0]
        cls.G = havel_hakimi_graph(deg)
        cls.WG = nx.Graph(
            (u, v, {"weight": 0.5, "other": 0.3}) for (u, v) in cls.G.edges()
        )
        cls.WG.add_node(4)
        cls.MG = nx.MultiGraph(cls.G)

        # Graph with clsloops
        cls.Gsl = cls.G.copy()
        for node in cls.Gsl.nodes():
            cls.Gsl.add_edge(node, node)

        # Graph used as an example in Sec. 4.1 of Langville and Meyer,
        # "Google's PageRank and Beyond".
        cls.DiG = nx.DiGraph()
        cls.DiG.add_edges_from(
            (
                (1, 2),
                (1, 3),
                (3, 1),
                (3, 2),
                (3, 5),
                (4, 5),
                (4, 6),
                (5, 4),
                (5, 6),
                (6, 4),
            )
        )
        cls.DiMG = nx.MultiDiGraph(cls.DiG)
        cls.DiWG = nx.DiGraph(
            (u, v, {"weight": 0.5, "other": 0.3}) for (u, v) in cls.DiG.edges()
        )
        cls.DiGsl = cls.DiG.copy()
        for node in cls.DiGsl.nodes():
            cls.DiGsl.add_edge(node, node)

    def test_laplacian(self):
        "Graph Laplacian"
        # fmt: off
        NL = np.array([[ 3, -1, -1, -1,  0],
                       [-1,  2, -1,  0,  0],
                       [-1, -1,  2,  0,  0],
                       [-1,  0,  0,  1,  0],
                       [ 0,  0,  0,  0,  0]])
        # fmt: on
        WL = 0.5 * NL
        OL = 0.3 * NL
        # fmt: off
        DiNL = np.array([[ 2, -1, -1,  0,  0,  0],
                         [ 0,  0,  0,  0,  0,  0],
                         [-1, -1,  3, -1,  0,  0],
                         [ 0,  0,  0,  2, -1, -1],
                         [ 0,  0,  0, -1,  2, -1],
                         [ 0,  0,  0,  0, -1,  1]])
        # fmt: on
        DiWL = 0.5 * DiNL
        DiOL = 0.3 * DiNL
        np.testing.assert_equal(nx.laplacian_matrix(self.G).todense(), NL)
        np.testing.assert_equal(nx.laplacian_matrix(self.MG).todense(), NL)
        np.testing.assert_equal(
            nx.laplacian_matrix(self.G, nodelist=[0, 1]).todense(),
            np.array([[1, -1], [-1, 1]]),
        )
        np.testing.assert_equal(nx.laplacian_matrix(self.WG).todense(), WL)
        np.testing.assert_equal(nx.laplacian_matrix(self.WG, weight=None).todense(), NL)
        np.testing.assert_equal(
            nx.laplacian_matrix(self.WG, weight="other").todense(), OL
        )

        np.testing.assert_equal(nx.laplacian_matrix(self.DiG).todense(), DiNL)
        np.testing.assert_equal(nx.laplacian_matrix(self.DiMG).todense(), DiNL)
        np.testing.assert_equal(
            nx.laplacian_matrix(self.DiG, nodelist=[1, 2]).todense(),
            np.array([[1, -1], [0, 0]]),
        )
        np.testing.assert_equal(nx.laplacian_matrix(self.DiWG).todense(), DiWL)
        np.testing.assert_equal(
            nx.laplacian_matrix(self.DiWG, weight=None).todense(), DiNL
        )
        np.testing.assert_equal(
            nx.laplacian_matrix(self.DiWG, weight="other").todense(), DiOL
        )

    def test_normalized_laplacian(self):
        "Generalized Graph Laplacian"
        # fmt: off
        G = np.array([[ 1.   , -0.408, -0.408, -0.577,  0.],
                      [-0.408,  1.   , -0.5  ,  0.   ,  0.],
                      [-0.408, -0.5  ,  1.   ,  0.   ,  0.],
                      [-0.577,  0.   ,  0.   ,  1.   ,  0.],
                      [ 0.   ,  0.   ,  0.   ,  0.   ,  0.]])
        GL = np.array([[ 1.   , -0.408, -0.408, -0.577,  0.   ],
                       [-0.408,  1.   , -0.5  ,  0.   ,  0.   ],
                       [-0.408, -0.5  ,  1.   ,  0.   ,  0.   ],
                       [-0.577,  0.   ,  0.   ,  1.   ,  0.   ],
                       [ 0.   ,  0.   ,  0.   ,  0.   ,  0.   ]])
        Lsl = np.array([[ 0.75  , -0.2887, -0.2887, -0.3536,  0.    ],
                        [-0.2887,  0.6667, -0.3333,  0.    ,  0.    ],
                        [-0.2887, -0.3333,  0.6667,  0.    ,  0.    ],
                        [-0.3536,  0.    ,  0.    ,  0.5   ,  0.    ],
                        [ 0.    ,  0.    ,  0.    ,  0.    ,  0.    ]])

        DiG = np.array([[ 1.    ,  0.    , -0.4082,  0.    ,  0.    ,  0.    ],
                        [ 0.    ,  0.    ,  0.    ,  0.    ,  0.    ,  0.    ],
                        [-0.4082,  0.    ,  1.    ,  0.    , -0.4082,  0.    ],
                        [ 0.    ,  0.    ,  0.    ,  1.    , -0.5   , -0.7071],
                        [ 0.    ,  0.    ,  0.    , -0.5   ,  1.    , -0.7071],
                        [ 0.    ,  0.    ,  0.    , -0.7071,  0.     , 1.    ]])
        DiGL = np.array([[ 1.    ,  0.    , -0.4082,  0.    ,  0.    ,  0.    ],
                         [ 0.    ,  0.    ,  0.    ,  0.    ,  0.    ,  0.    ],
                         [-0.4082,  0.    ,  1.    , -0.4082,  0.    ,  0.    ],
                         [ 0.    ,  0.    ,  0.    ,  1.    , -0.5   , -0.7071],
                         [ 0.    ,  0.    ,  0.    , -0.5   ,  1.    , -0.7071],
                         [ 0.    ,  0.    ,  0.    ,  0.    , -0.7071,  1.    ]])
        DiLsl = np.array([[ 0.6667, -0.5774, -0.2887,  0.    ,  0.    ,  0.    ],
                          [ 0.    ,  0.    ,  0.    ,  0.    ,  0.    ,  0.    ],
                          [-0.2887, -0.5   ,  0.75  , -0.2887,  0.    ,  0.    ],
                          [ 0.    ,  0.    ,  0.    ,  0.6667, -0.3333, -0.4082],
                          [ 0.    ,  0.    ,  0.    , -0.3333,  0.6667, -0.4082],
                          [ 0.    ,  0.    ,  0.    ,  0.    , -0.4082,  0.5   ]])
        # fmt: on

        np.testing.assert_almost_equal(
            nx.normalized_laplacian_matrix(self.G, nodelist=range(5)).todense(),
            G,
            decimal=3,
        )
        np.testing.assert_almost_equal(
            nx.normalized_laplacian_matrix(self.G).todense(), GL, decimal=3
        )
        np.testing.assert_almost_equal(
            nx.normalized_laplacian_matrix(self.MG).todense(), GL, decimal=3
        )
        np.testing.assert_almost_equal(
            nx.normalized_laplacian_matrix(self.WG).todense(), GL, decimal=3
        )
        np.testing.assert_almost_equal(
            nx.normalized_laplacian_matrix(self.WG, weight="other").todense(),
            GL,
            decimal=3,
        )
        np.testing.assert_almost_equal(
            nx.normalized_laplacian_matrix(self.Gsl).todense(), Lsl, decimal=3
        )

        np.testing.assert_almost_equal(
            nx.normalized_laplacian_matrix(
                self.DiG,
                nodelist=range(1, 1 + 6),
            ).todense(),
            DiG,
            decimal=3,
        )
        np.testing.assert_almost_equal(
            nx.normalized_laplacian_matrix(self.DiG).todense(), DiGL, decimal=3
        )
        np.testing.assert_almost_equal(
            nx.normalized_laplacian_matrix(self.DiMG).todense(), DiGL, decimal=3
        )
        np.testing.assert_almost_equal(
            nx.normalized_laplacian_matrix(self.DiWG).todense(), DiGL, decimal=3
        )
        np.testing.assert_almost_equal(
            nx.normalized_laplacian_matrix(self.DiWG, weight="other").todense(),
            DiGL,
            decimal=3,
        )
        np.testing.assert_almost_equal(
            nx.normalized_laplacian_matrix(self.DiGsl).todense(), DiLsl, decimal=3
        )


def test_directed_laplacian():
    "Directed Laplacian"
    # Graph used as an example in Sec. 4.1 of Langville and Meyer,
    # "Google's PageRank and Beyond". The graph contains dangling nodes, so
    # the pagerank random walk is selected by directed_laplacian
    G = nx.DiGraph()
    G.add_edges_from(
        (
            (1, 2),
            (1, 3),
            (3, 1),
            (3, 2),
            (3, 5),
            (4, 5),
            (4, 6),
            (5, 4),
            (5, 6),
            (6, 4),
        )
    )
    # fmt: off
    GL = np.array([[ 0.9833, -0.2941, -0.3882, -0.0291, -0.0231, -0.0261],
                   [-0.2941,  0.8333, -0.2339, -0.0536, -0.0589, -0.0554],
                   [-0.3882, -0.2339,  0.9833, -0.0278, -0.0896, -0.0251],
                   [-0.0291, -0.0536, -0.0278,  0.9833, -0.4878, -0.6675],
                   [-0.0231, -0.0589, -0.0896, -0.4878,  0.9833, -0.2078],
                   [-0.0261, -0.0554, -0.0251, -0.6675, -0.2078,  0.9833]])
    # fmt: on
    L = nx.directed_laplacian_matrix(G, alpha=0.9, nodelist=sorted(G))
    np.testing.assert_almost_equal(L, GL, decimal=3)

    # Make the graph strongly connected, so we can use a random and lazy walk
    G.add_edges_from(((2, 5), (6, 1)))
    # fmt: off
    GL = np.array([[ 1.    , -0.3062, -0.4714,  0.    ,  0.    , -0.3227],
                   [-0.3062,  1.    , -0.1443,  0.    , -0.3162,  0.    ],
                   [-0.4714, -0.1443,  1.    ,  0.    , -0.0913,  0.    ],
                   [ 0.    ,  0.    ,  0.    ,  1.    , -0.5   , -0.5   ],
                   [ 0.    , -0.3162, -0.0913, -0.5   ,  1.    , -0.25  ],
                   [-0.3227,  0.    ,  0.    , -0.5   , -0.25  ,  1.    ]])
    # fmt: on
    L = nx.directed_laplacian_matrix(
        G, alpha=0.9, nodelist=sorted(G), walk_type="random"
    )
    np.testing.assert_almost_equal(L, GL, decimal=3)

    # fmt: off
    GL = np.array([[ 0.5   , -0.1531, -0.2357,  0.    ,  0.    , -0.1614],
                   [-0.1531,  0.5   , -0.0722,  0.    , -0.1581,  0.    ],
                   [-0.2357, -0.0722,  0.5   ,  0.    , -0.0456,  0.    ],
                   [ 0.    ,  0.    ,  0.    ,  0.5   , -0.25  , -0.25  ],
                   [ 0.    , -0.1581, -0.0456, -0.25  ,  0.5   , -0.125 ],
                   [-0.1614,  0.    ,  0.    , -0.25  , -0.125 ,  0.5   ]])  
    # fmt: on
    L = nx.directed_laplacian_matrix(G, alpha=0.9, nodelist=sorted(G), walk_type="lazy")
    np.testing.assert_almost_equal(L, GL, decimal=3)

    # Make a strongly connected periodic graph
    G = nx.DiGraph()
    G.add_edges_from(((1, 2), (2, 4), (4, 1), (1, 3), (3, 4)))
    # fmt: off
    GL = np.array([[ 0.5  , -0.176, -0.176, -0.25 ],
                   [-0.176,  0.5  ,  0.   , -0.176],
                   [-0.176,  0.   ,  0.5  , -0.176],
                   [-0.25 , -0.176, -0.176,  0.5  ]])
    # fmt: on
    L = nx.directed_laplacian_matrix(G, alpha=0.9, nodelist=sorted(G))
    np.testing.assert_almost_equal(L, GL, decimal=3)


def test_directed_combinatorial_laplacian():
    "Directed combinatorial Laplacian"
    # Graph used as an example in Sec. 4.1 of Langville and Meyer,
    # "Google's PageRank and Beyond". The graph contains dangling nodes, so
    # the pagerank random walk is selected by directed_laplacian
    G = nx.DiGraph()
    G.add_edges_from(
        (
            (1, 2),
            (1, 3),
            (3, 1),
            (3, 2),
            (3, 5),
            (4, 5),
            (4, 6),
            (5, 4),
            (5, 6),
            (6, 4),
        )
    )
    # fmt: off
    GL = np.array([[ 0.0366, -0.0132, -0.0153, -0.0034, -0.0020, -0.0027],
                   [-0.0132,  0.0450, -0.0111, -0.0076, -0.0062, -0.0069],
                   [-0.0153, -0.0111,  0.0408, -0.0035, -0.0083, -0.0027],
                   [-0.0034, -0.0076, -0.0035,  0.3688, -0.1356, -0.2187],
                   [-0.0020, -0.0062, -0.0083, -0.1356,  0.2026, -0.0505],
                   [-0.0027, -0.0069, -0.0027, -0.2187, -0.0505,  0.2815]])
    # fmt: on

    L = nx.directed_combinatorial_laplacian_matrix(G, alpha=0.9, nodelist=sorted(G))
    np.testing.assert_almost_equal(L, GL, decimal=3)

    # Make the graph strongly connected, so we can use a random and lazy walk
    G.add_edges_from(((2, 5), (6, 1)))

    # fmt: off
    GL = np.array([[ 0.1395, -0.0349, -0.0465,  0.    ,  0.    , -0.0581],
                   [-0.0349,  0.093 , -0.0116,  0.    , -0.0465,  0.    ],
                   [-0.0465, -0.0116,  0.0698,  0.    , -0.0116,  0.    ],
                   [ 0.    ,  0.    ,  0.    ,  0.2326, -0.1163, -0.1163],
                   [ 0.    , -0.0465, -0.0116, -0.1163,  0.2326, -0.0581],
                   [-0.0581,  0.    ,  0.    , -0.1163, -0.0581,  0.2326]])
    # fmt: on

    L = nx.directed_combinatorial_laplacian_matrix(
        G, alpha=0.9, nodelist=sorted(G), walk_type="random"
    )
    np.testing.assert_almost_equal(L, GL, decimal=3)

    # fmt: off
    GL = np.array([[ 0.0698, -0.0174, -0.0233,  0.    ,  0.    , -0.0291],
                   [-0.0174,  0.0465, -0.0058,  0.    , -0.0233,  0.    ],
                   [-0.0233, -0.0058,  0.0349,  0.    , -0.0058,  0.    ],
                   [ 0.    ,  0.    ,  0.    ,  0.1163, -0.0581, -0.0581],
                   [ 0.    , -0.0233, -0.0058, -0.0581,  0.1163, -0.0291],
                   [-0.0291,  0.    ,  0.    , -0.0581, -0.0291,  0.1163]])
    # fmt: on

    L = nx.directed_combinatorial_laplacian_matrix(
        G, alpha=0.9, nodelist=sorted(G), walk_type="lazy"
    )
    np.testing.assert_almost_equal(L, GL, decimal=3)

    E = nx.DiGraph(margulis_gabber_galil_graph(2))
    L = nx.directed_combinatorial_laplacian_matrix(E)
    # fmt: off
    expected = np.array(
        [[ 0.16666667, -0.08333333, -0.08333333,  0.        ],
         [-0.08333333,  0.16666667,  0.        , -0.08333333],
         [-0.08333333,  0.        ,  0.16666667, -0.08333333],
         [ 0.        , -0.08333333, -0.08333333,  0.16666667]]
    )
    # fmt: on
    np.testing.assert_almost_equal(L, expected, decimal=6)

    with pytest.raises(nx.NetworkXError):
        nx.directed_combinatorial_laplacian_matrix(G, walk_type="pagerank", alpha=100)
    with pytest.raises(nx.NetworkXError):
        nx.directed_combinatorial_laplacian_matrix(G, walk_type="silly")
