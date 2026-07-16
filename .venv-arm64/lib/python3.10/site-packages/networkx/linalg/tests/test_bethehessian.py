import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("scipy")

import networkx as nx
from networkx.generators.degree_seq import havel_hakimi_graph


class TestBetheHessian:
    @classmethod
    def setup_class(cls):
        deg = [3, 2, 2, 1, 0]
        cls.G = havel_hakimi_graph(deg)
        cls.P = nx.path_graph(3)

    def test_bethe_hessian(self):
        "Bethe Hessian matrix"
        # fmt: off
        H = np.array([[4, -2, 0],
                      [-2, 5, -2],
                      [0, -2, 4]])
        # fmt: on
        permutation = [2, 0, 1]
        # Bethe Hessian gives expected form
        np.testing.assert_equal(nx.bethe_hessian_matrix(self.P, r=2).todense(), H)
        # nodelist is correctly implemented
        np.testing.assert_equal(
            nx.bethe_hessian_matrix(self.P, r=2, nodelist=permutation).todense(),
            H[np.ix_(permutation, permutation)],
        )
        # Equal to Laplacian matrix when r=1
        np.testing.assert_equal(
            nx.bethe_hessian_matrix(self.G, r=1).todense(),
            nx.laplacian_matrix(self.G).todense(),
        )
        # Correct default for the regularizer r
        np.testing.assert_equal(
            nx.bethe_hessian_matrix(self.G).todense(),
            nx.bethe_hessian_matrix(self.G, r=1.25).todense(),
        )
