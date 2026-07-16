"""Unit tests for the :mod:`networkx.generators.harary_graph` module."""

import pytest

import networkx as nx
from networkx.algorithms.isomorphism.isomorph import is_isomorphic
from networkx.generators.harary_graph import hkn_harary_graph, hnm_harary_graph


class TestHararyGraph:
    """
    Suppose n nodes, m >= n-1 edges, d = 2m // n, r = 2m % n
    """

    def test_hnm_harary_graph(self):
        # When d is even and r = 0, the hnm_harary_graph(n,m) is
        # the circulant_graph(n, list(range(1,d/2+1)))
        for n, m in [(5, 5), (6, 12), (7, 14)]:
            G1 = hnm_harary_graph(n, m)
            d = 2 * m // n
            G2 = nx.circulant_graph(n, list(range(1, d // 2 + 1)))
            assert is_isomorphic(G1, G2)

        # When d is even and r > 0, the hnm_harary_graph(n,m) is
        # the circulant_graph(n, list(range(1,d/2+1)))
        # with r edges added arbitrarily
        for n, m in [(5, 7), (6, 13), (7, 16)]:
            G1 = hnm_harary_graph(n, m)
            d = 2 * m // n
            G2 = nx.circulant_graph(n, list(range(1, d // 2 + 1)))
            assert set(G2.edges) < set(G1.edges)
            assert G1.number_of_edges() == m

        # When d is odd and n is even and r = 0, the hnm_harary_graph(n,m)
        # is the circulant_graph(n, list(range(1,(d+1)/2) plus [n//2])
        for n, m in [(6, 9), (8, 12), (10, 15)]:
            G1 = hnm_harary_graph(n, m)
            d = 2 * m // n
            L = list(range(1, (d + 1) // 2))
            L.append(n // 2)
            G2 = nx.circulant_graph(n, L)
            assert is_isomorphic(G1, G2)

        # When d is odd and n is even and r > 0, the hnm_harary_graph(n,m)
        # is the circulant_graph(n, list(range(1,(d+1)/2) plus [n//2])
        # with r edges added arbitrarily
        for n, m in [(6, 10), (8, 13), (10, 17)]:
            G1 = hnm_harary_graph(n, m)
            d = 2 * m // n
            L = list(range(1, (d + 1) // 2))
            L.append(n // 2)
            G2 = nx.circulant_graph(n, L)
            assert set(G2.edges) < set(G1.edges)
            assert G1.number_of_edges() == m

        # When d is odd and n is odd, the hnm_harary_graph(n,m) is
        # the circulant_graph(n, list(range(1,(d+1)/2))
        # with m - n*(d-1)/2 edges added arbitrarily
        for n, m in [(5, 4), (7, 12), (9, 14)]:
            G1 = hnm_harary_graph(n, m)
            d = 2 * m // n
            L = list(range(1, (d + 1) // 2))
            G2 = nx.circulant_graph(n, L)
            assert set(G2.edges) < set(G1.edges)
            assert G1.number_of_edges() == m

        # Raise NetworkXError if n<1
        n = 0
        m = 0
        pytest.raises(nx.NetworkXError, hnm_harary_graph, n, m)

        # Raise NetworkXError if m < n-1
        n = 6
        m = 4
        pytest.raises(nx.NetworkXError, hnm_harary_graph, n, m)

        # Raise NetworkXError if m > n(n-1)/2
        n = 6
        m = 16
        pytest.raises(nx.NetworkXError, hnm_harary_graph, n, m)

    """
        Suppose connectivity k, number of nodes n
    """

    def test_hkn_harary_graph(self):
        # When k == 1, the hkn_harary_graph(k,n) is
        # the path_graph(n)
        for k, n in [(1, 6), (1, 7)]:
            G1 = hkn_harary_graph(k, n)
            G2 = nx.path_graph(n)
            assert is_isomorphic(G1, G2)

        # When k is even, the hkn_harary_graph(k,n) is
        # the circulant_graph(n, list(range(1,k/2+1)))
        for k, n in [(2, 6), (2, 7), (4, 6), (4, 7)]:
            G1 = hkn_harary_graph(k, n)
            G2 = nx.circulant_graph(n, list(range(1, k // 2 + 1)))
            assert is_isomorphic(G1, G2)

        # When k is odd and n is even, the hkn_harary_graph(k,n) is
        # the circulant_graph(n, list(range(1,(k+1)/2)) plus [n/2])
        for k, n in [(3, 6), (5, 8), (7, 10)]:
            G1 = hkn_harary_graph(k, n)
            L = list(range(1, (k + 1) // 2))
            L.append(n // 2)
            G2 = nx.circulant_graph(n, L)
            assert is_isomorphic(G1, G2)

        # When k is odd and n is odd, the hkn_harary_graph(k,n) is
        # the circulant_graph(n, list(range(1,(k+1)/2))) with
        # n//2+1 edges added between node i and node i+n//2+1
        for k, n in [(3, 5), (5, 9), (7, 11)]:
            G1 = hkn_harary_graph(k, n)
            G2 = nx.circulant_graph(n, list(range(1, (k + 1) // 2)))
            eSet1 = set(G1.edges)
            eSet2 = set(G2.edges)
            eSet3 = set()
            half = n // 2
            for i in range(half + 1):
                # add half+1 edges between i and i+half
                eSet3.add((i, (i + half) % n))
            assert eSet1 == eSet2 | eSet3

        # Raise NetworkXError if k<1
        k = 0
        n = 0
        pytest.raises(nx.NetworkXError, hkn_harary_graph, k, n)

        # Raise NetworkXError if n<k+1
        k = 6
        n = 6
        pytest.raises(nx.NetworkXError, hkn_harary_graph, k, n)
