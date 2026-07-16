from itertools import chain, islice, tee
from math import inf
from random import shuffle

import pytest

import networkx as nx
from networkx.algorithms.traversal.edgedfs import FORWARD, REVERSE


def check_independent(basis):
    if len(basis) == 0:
        return

    np = pytest.importorskip("numpy")
    sp = pytest.importorskip("scipy")  # Required by incidence_matrix

    H = nx.Graph()
    for b in basis:
        nx.add_cycle(H, b)
    inc = nx.incidence_matrix(H, oriented=True)
    rank = np.linalg.matrix_rank(inc.toarray(), tol=None, hermitian=False)
    assert inc.shape[1] - rank == len(basis)


class TestCycles:
    @classmethod
    def setup_class(cls):
        G = nx.Graph()
        nx.add_cycle(G, [0, 1, 2, 3])
        nx.add_cycle(G, [0, 3, 4, 5])
        nx.add_cycle(G, [0, 1, 6, 7, 8])
        G.add_edge(8, 9)
        cls.G = G

    def is_cyclic_permutation(self, a, b):
        n = len(a)
        if len(b) != n:
            return False
        l = a + a
        return any(l[i : i + n] == b for i in range(n))

    def test_cycle_basis(self):
        G = self.G
        cy = nx.cycle_basis(G, 0)
        sort_cy = sorted(sorted(c) for c in cy)
        assert sort_cy == [[0, 1, 2, 3], [0, 1, 6, 7, 8], [0, 3, 4, 5]]
        cy = nx.cycle_basis(G, 1)
        sort_cy = sorted(sorted(c) for c in cy)
        assert sort_cy == [[0, 1, 2, 3], [0, 1, 6, 7, 8], [0, 3, 4, 5]]
        cy = nx.cycle_basis(G, 9)
        sort_cy = sorted(sorted(c) for c in cy)
        assert sort_cy == [[0, 1, 2, 3], [0, 1, 6, 7, 8], [0, 3, 4, 5]]
        # test disconnected graphs
        nx.add_cycle(G, "ABC")
        cy = nx.cycle_basis(G, 9)
        sort_cy = sorted(sorted(c) for c in cy[:-1]) + [sorted(cy[-1])]
        assert sort_cy == [[0, 1, 2, 3], [0, 1, 6, 7, 8], [0, 3, 4, 5], ["A", "B", "C"]]

    def test_cycle_basis2(self):
        with pytest.raises(nx.NetworkXNotImplemented):
            G = nx.DiGraph()
            cy = nx.cycle_basis(G, 0)

    def test_cycle_basis3(self):
        with pytest.raises(nx.NetworkXNotImplemented):
            G = nx.MultiGraph()
            cy = nx.cycle_basis(G, 0)

    def test_cycle_basis_ordered(self):
        # see gh-6654 replace sets with (ordered) dicts
        G = nx.cycle_graph(5)
        G.update(nx.cycle_graph(range(3, 8)))
        cbG = nx.cycle_basis(G)

        perm = {1: 0, 0: 1}  # switch 0 and 1
        H = nx.relabel_nodes(G, perm)
        cbH = [[perm.get(n, n) for n in cyc] for cyc in nx.cycle_basis(H)]
        assert cbG == cbH

    def test_cycle_basis_self_loop(self):
        """Tests the function for graphs with self loops"""
        G = nx.Graph()
        nx.add_cycle(G, [0, 1, 2, 3])
        nx.add_cycle(G, [0, 0, 6, 2])
        cy = nx.cycle_basis(G)
        sort_cy = sorted(sorted(c) for c in cy)
        assert sort_cy == [[0], [0, 1, 2], [0, 2, 3], [0, 2, 6]]

    def test_simple_cycles(self):
        edges = [(0, 0), (0, 1), (0, 2), (1, 2), (2, 0), (2, 1), (2, 2)]
        G = nx.DiGraph(edges)
        cc = sorted(nx.simple_cycles(G))
        ca = [[0], [0, 1, 2], [0, 2], [1, 2], [2]]
        assert len(cc) == len(ca)
        for c in cc:
            assert any(self.is_cyclic_permutation(c, rc) for rc in ca)

    def test_simple_cycles_singleton(self):
        G = nx.Graph([(0, 0)])  # self-loop
        assert list(nx.simple_cycles(G)) == [[0]]

    def test_unsortable(self):
        # this test ensures that graphs whose nodes without an intrinsic
        # ordering do not cause issues
        G = nx.DiGraph()
        nx.add_cycle(G, ["a", 1])
        c = list(nx.simple_cycles(G))
        assert len(c) == 1

    def test_simple_cycles_small(self):
        G = nx.DiGraph()
        nx.add_cycle(G, [1, 2, 3])
        c = sorted(nx.simple_cycles(G))
        assert len(c) == 1
        assert self.is_cyclic_permutation(c[0], [1, 2, 3])
        nx.add_cycle(G, [10, 20, 30])
        cc = sorted(nx.simple_cycles(G))
        assert len(cc) == 2
        ca = [[1, 2, 3], [10, 20, 30]]
        for c in cc:
            assert any(self.is_cyclic_permutation(c, rc) for rc in ca)

    def test_simple_cycles_empty(self):
        G = nx.DiGraph()
        assert list(nx.simple_cycles(G)) == []

    def worst_case_graph(self, k):
        # see figure 1 in Johnson's paper
        # this graph has exactly 3k simple cycles
        G = nx.DiGraph()
        for n in range(2, k + 2):
            G.add_edge(1, n)
            G.add_edge(n, k + 2)
        G.add_edge(2 * k + 1, 1)
        for n in range(k + 2, 2 * k + 2):
            G.add_edge(n, 2 * k + 2)
            G.add_edge(n, n + 1)
        G.add_edge(2 * k + 3, k + 2)
        for n in range(2 * k + 3, 3 * k + 3):
            G.add_edge(2 * k + 2, n)
            G.add_edge(n, 3 * k + 3)
        G.add_edge(3 * k + 3, 2 * k + 2)
        return G

    def test_worst_case_graph(self):
        # see figure 1 in Johnson's paper
        for k in range(3, 10):
            G = self.worst_case_graph(k)
            l = len(list(nx.simple_cycles(G)))
            assert l == 3 * k

    def test_recursive_simple_and_not(self):
        for k in range(2, 10):
            G = self.worst_case_graph(k)
            cc = sorted(nx.simple_cycles(G))
            rcc = sorted(nx.recursive_simple_cycles(G))
            assert len(cc) == len(rcc)
            for c in cc:
                assert any(self.is_cyclic_permutation(c, r) for r in rcc)
            for rc in rcc:
                assert any(self.is_cyclic_permutation(rc, c) for c in cc)

    def test_simple_graph_with_reported_bug(self):
        G = nx.DiGraph()
        edges = [
            (0, 2),
            (0, 3),
            (1, 0),
            (1, 3),
            (2, 1),
            (2, 4),
            (3, 2),
            (3, 4),
            (4, 0),
            (4, 1),
            (4, 5),
            (5, 0),
            (5, 1),
            (5, 2),
            (5, 3),
        ]
        G.add_edges_from(edges)
        cc = sorted(nx.simple_cycles(G))
        assert len(cc) == 26
        rcc = sorted(nx.recursive_simple_cycles(G))
        assert len(cc) == len(rcc)
        for c in cc:
            assert any(self.is_cyclic_permutation(c, rc) for rc in rcc)
        for rc in rcc:
            assert any(self.is_cyclic_permutation(rc, c) for c in cc)


def pairwise(iterable):
    a, b = tee(iterable)
    next(b, None)
    return zip(a, b)


def cycle_edges(c):
    return pairwise(chain(c, islice(c, 1)))


def directed_cycle_edgeset(c):
    return frozenset(cycle_edges(c))


def undirected_cycle_edgeset(c):
    if len(c) == 1:
        return frozenset(cycle_edges(c))
    return frozenset(map(frozenset, cycle_edges(c)))


def multigraph_cycle_edgeset(c):
    if len(c) <= 2:
        return frozenset(cycle_edges(c))
    else:
        return frozenset(map(frozenset, cycle_edges(c)))


class TestCycleEnumeration:
    @staticmethod
    def K(n):
        return nx.complete_graph(n)

    @staticmethod
    def D(n):
        return nx.complete_graph(n).to_directed()

    @staticmethod
    def edgeset_function(g):
        if g.is_directed():
            return directed_cycle_edgeset
        elif g.is_multigraph():
            return multigraph_cycle_edgeset
        else:
            return undirected_cycle_edgeset

    def check_cycle(self, g, c, es, cache, source, original_c, length_bound, chordless):
        if length_bound is not None and len(c) > length_bound:
            raise RuntimeError(
                f"computed cycle {original_c} exceeds length bound {length_bound}"
            )
        if source == "computed":
            if es in cache:
                raise RuntimeError(
                    f"computed cycle {original_c} has already been found!"
                )
            else:
                cache[es] = tuple(original_c)
        else:
            if es in cache:
                cache.pop(es)
            else:
                raise RuntimeError(f"expected cycle {original_c} was not computed")

        if not all(g.has_edge(*e) for e in es):
            raise RuntimeError(
                f"{source} claimed cycle {original_c} is not a cycle of g"
            )
        if chordless and len(g.subgraph(c).edges) > len(c):
            raise RuntimeError(f"{source} cycle {original_c} is not chordless")

    def check_cycle_algorithm(
        self,
        g,
        expected_cycles,
        length_bound=None,
        chordless=False,
        algorithm=None,
    ):
        if algorithm is None:
            algorithm = nx.chordless_cycles if chordless else nx.simple_cycles

        # note: we shuffle the labels of g to rule out accidentally-correct
        # behavior which occurred during the development of chordless cycle
        # enumeration algorithms

        relabel = list(range(len(g)))
        shuffle(relabel)
        label = dict(zip(g, relabel))
        unlabel = dict(zip(relabel, g))
        h = nx.relabel_nodes(g, label, copy=True)

        edgeset = self.edgeset_function(h)

        params = {}
        if length_bound is not None:
            params["length_bound"] = length_bound

        cycle_cache = {}
        for c in algorithm(h, **params):
            original_c = [unlabel[x] for x in c]
            es = edgeset(c)
            self.check_cycle(
                h, c, es, cycle_cache, "computed", original_c, length_bound, chordless
            )

        if isinstance(expected_cycles, int):
            if len(cycle_cache) != expected_cycles:
                raise RuntimeError(
                    f"expected {expected_cycles} cycles, got {len(cycle_cache)}"
                )
            return
        for original_c in expected_cycles:
            c = [label[x] for x in original_c]
            es = edgeset(c)
            self.check_cycle(
                h, c, es, cycle_cache, "expected", original_c, length_bound, chordless
            )

        if len(cycle_cache):
            for c in cycle_cache.values():
                raise RuntimeError(
                    f"computed cycle {c} is valid but not in the expected cycle set!"
                )

    def check_cycle_enumeration_integer_sequence(
        self,
        g_family,
        cycle_counts,
        length_bound=None,
        chordless=False,
        algorithm=None,
    ):
        for g, num_cycles in zip(g_family, cycle_counts):
            self.check_cycle_algorithm(
                g,
                num_cycles,
                length_bound=length_bound,
                chordless=chordless,
                algorithm=algorithm,
            )

    def test_directed_chordless_cycle_digons(self):
        g = nx.DiGraph()
        nx.add_cycle(g, range(5))
        nx.add_cycle(g, range(5)[::-1])
        g.add_edge(0, 0)
        expected_cycles = [(0,), (1, 2), (2, 3), (3, 4)]
        self.check_cycle_algorithm(g, expected_cycles, chordless=True)

        self.check_cycle_algorithm(g, expected_cycles, chordless=True, length_bound=2)

        expected_cycles = [c for c in expected_cycles if len(c) < 2]
        self.check_cycle_algorithm(g, expected_cycles, chordless=True, length_bound=1)

    def test_directed_chordless_cycle_undirected(self):
        g = nx.DiGraph([(1, 2), (2, 3), (3, 4), (4, 5), (5, 0), (5, 1), (0, 2)])
        expected_cycles = [(0, 2, 3, 4, 5), (1, 2, 3, 4, 5)]
        self.check_cycle_algorithm(g, expected_cycles, chordless=True)

        g = nx.DiGraph()
        nx.add_cycle(g, range(5))
        nx.add_cycle(g, range(4, 9))
        g.add_edge(7, 3)
        expected_cycles = [(0, 1, 2, 3, 4), (3, 4, 5, 6, 7), (4, 5, 6, 7, 8)]
        self.check_cycle_algorithm(g, expected_cycles, chordless=True)

        g.add_edge(3, 7)
        expected_cycles = [(0, 1, 2, 3, 4), (3, 7), (4, 5, 6, 7, 8)]
        self.check_cycle_algorithm(g, expected_cycles, chordless=True)

        expected_cycles = [(3, 7)]
        self.check_cycle_algorithm(g, expected_cycles, chordless=True, length_bound=4)

        g.remove_edge(7, 3)
        expected_cycles = [(0, 1, 2, 3, 4), (4, 5, 6, 7, 8)]
        self.check_cycle_algorithm(g, expected_cycles, chordless=True)

        g = nx.DiGraph((i, j) for i in range(10) for j in range(i))
        expected_cycles = []
        self.check_cycle_algorithm(g, expected_cycles, chordless=True)

    def test_chordless_cycles_directed(self):
        G = nx.DiGraph()
        nx.add_cycle(G, range(5))
        nx.add_cycle(G, range(4, 12))
        expected = [[*range(5)], [*range(4, 12)]]
        self.check_cycle_algorithm(G, expected, chordless=True)
        self.check_cycle_algorithm(
            G, [c for c in expected if len(c) <= 5], length_bound=5, chordless=True
        )

        G.add_edge(7, 3)
        expected.append([*range(3, 8)])
        self.check_cycle_algorithm(G, expected, chordless=True)
        self.check_cycle_algorithm(
            G, [c for c in expected if len(c) <= 5], length_bound=5, chordless=True
        )

        G.add_edge(3, 7)
        expected[-1] = [7, 3]
        self.check_cycle_algorithm(G, expected, chordless=True)
        self.check_cycle_algorithm(
            G, [c for c in expected if len(c) <= 5], length_bound=5, chordless=True
        )

        expected.pop()
        G.remove_edge(7, 3)
        self.check_cycle_algorithm(G, expected, chordless=True)
        self.check_cycle_algorithm(
            G, [c for c in expected if len(c) <= 5], length_bound=5, chordless=True
        )

    def test_directed_chordless_cycle_diclique(self):
        g_family = [self.D(n) for n in range(10)]
        expected_cycles = [(n * n - n) // 2 for n in range(10)]
        self.check_cycle_enumeration_integer_sequence(
            g_family, expected_cycles, chordless=True
        )

        expected_cycles = [(n * n - n) // 2 for n in range(10)]
        self.check_cycle_enumeration_integer_sequence(
            g_family, expected_cycles, length_bound=2
        )

    def test_directed_chordless_loop_blockade(self):
        g = nx.DiGraph((i, i) for i in range(10))
        nx.add_cycle(g, range(10))
        expected_cycles = [(i,) for i in range(10)]
        self.check_cycle_algorithm(g, expected_cycles, chordless=True)

        self.check_cycle_algorithm(g, expected_cycles, length_bound=1)

        g = nx.MultiDiGraph(g)
        g.add_edges_from((i, i) for i in range(0, 10, 2))
        expected_cycles = [(i,) for i in range(1, 10, 2)]
        self.check_cycle_algorithm(g, expected_cycles, chordless=True)

    def test_simple_cycles_notable_clique_sequences(self):
        # A000292: Number of labeled graphs on n+3 nodes that are triangles.
        g_family = [self.K(n) for n in range(2, 12)]
        expected = [0, 1, 4, 10, 20, 35, 56, 84, 120, 165, 220]
        self.check_cycle_enumeration_integer_sequence(
            g_family, expected, length_bound=3
        )

        def triangles(g, **kwargs):
            yield from (c for c in nx.simple_cycles(g, **kwargs) if len(c) == 3)

        # directed complete graphs have twice as many triangles thanks to reversal
        g_family = [self.D(n) for n in range(2, 12)]
        expected = [2 * e for e in expected]
        self.check_cycle_enumeration_integer_sequence(
            g_family, expected, length_bound=3, algorithm=triangles
        )

        def four_cycles(g, **kwargs):
            yield from (c for c in nx.simple_cycles(g, **kwargs) if len(c) == 4)

        # A050534: the number of 4-cycles in the complete graph K_{n+1}
        expected = [0, 0, 0, 3, 15, 45, 105, 210, 378, 630, 990]
        g_family = [self.K(n) for n in range(1, 12)]
        self.check_cycle_enumeration_integer_sequence(
            g_family, expected, length_bound=4, algorithm=four_cycles
        )

        # directed complete graphs have twice as many 4-cycles thanks to reversal
        expected = [2 * e for e in expected]
        g_family = [self.D(n) for n in range(1, 15)]
        self.check_cycle_enumeration_integer_sequence(
            g_family, expected, length_bound=4, algorithm=four_cycles
        )

        # A006231: the number of elementary circuits in a complete directed graph with n nodes
        expected = [0, 1, 5, 20, 84, 409, 2365]
        g_family = [self.D(n) for n in range(1, 8)]
        self.check_cycle_enumeration_integer_sequence(g_family, expected)

        # A002807: Number of cycles in the complete graph on n nodes K_{n}.
        expected = [0, 0, 0, 1, 7, 37, 197, 1172]
        g_family = [self.K(n) for n in range(8)]
        self.check_cycle_enumeration_integer_sequence(g_family, expected)

    def test_directed_chordless_cycle_parallel_multiedges(self):
        g = nx.MultiGraph()

        nx.add_cycle(g, range(5))
        expected = [[*range(5)]]
        self.check_cycle_algorithm(g, expected, chordless=True)

        nx.add_cycle(g, range(5))
        expected = [*cycle_edges(range(5))]
        self.check_cycle_algorithm(g, expected, chordless=True)

        nx.add_cycle(g, range(5))
        expected = []
        self.check_cycle_algorithm(g, expected, chordless=True)

        g = nx.MultiDiGraph()

        nx.add_cycle(g, range(5))
        expected = [[*range(5)]]
        self.check_cycle_algorithm(g, expected, chordless=True)

        nx.add_cycle(g, range(5))
        self.check_cycle_algorithm(g, [], chordless=True)

        nx.add_cycle(g, range(5))
        self.check_cycle_algorithm(g, [], chordless=True)

        g = nx.MultiDiGraph()

        nx.add_cycle(g, range(5))
        nx.add_cycle(g, range(5)[::-1])
        expected = [*cycle_edges(range(5))]
        self.check_cycle_algorithm(g, expected, chordless=True)

        nx.add_cycle(g, range(5))
        self.check_cycle_algorithm(g, [], chordless=True)

    def test_chordless_cycles_graph(self):
        G = nx.Graph()
        nx.add_cycle(G, range(5))
        nx.add_cycle(G, range(4, 12))
        expected = [[*range(5)], [*range(4, 12)]]
        self.check_cycle_algorithm(G, expected, chordless=True)
        self.check_cycle_algorithm(
            G, [c for c in expected if len(c) <= 5], length_bound=5, chordless=True
        )

        G.add_edge(7, 3)
        expected.append([*range(3, 8)])
        expected.append([4, 3, 7, 8, 9, 10, 11])
        self.check_cycle_algorithm(G, expected, chordless=True)
        self.check_cycle_algorithm(
            G, [c for c in expected if len(c) <= 5], length_bound=5, chordless=True
        )

    def test_chordless_cycles_giant_hamiltonian(self):
        # ... o - e - o - e - o ... # o = odd, e = even
        # ... ---/ \-----/ \--- ... # <-- "long" edges
        #
        # each long edge belongs to exactly one triangle, and one giant cycle
        # of length n/2.  The remaining edges each belong to a triangle

        n = 1000
        assert n % 2 == 0
        G = nx.Graph()
        for v in range(n):
            if not v % 2:
                G.add_edge(v, (v + 2) % n)
            G.add_edge(v, (v + 1) % n)

        expected = [[*range(0, n, 2)]] + [
            [x % n for x in range(i, i + 3)] for i in range(0, n, 2)
        ]
        self.check_cycle_algorithm(G, expected, chordless=True)
        self.check_cycle_algorithm(
            G, [c for c in expected if len(c) <= 3], length_bound=3, chordless=True
        )

        # ... o -> e -> o -> e -> o ... # o = odd, e = even
        # ... <---/ \---<---/ \---< ... # <-- "long" edges
        #
        # this time, we orient the short and long edges in opposition
        # the cycle structure of this graph is the same, but we need to reverse
        # the long one in our representation.  Also, we need to drop the size
        # because our partitioning algorithm uses strongly connected components
        # instead of separating graphs by their strong articulation points

        n = 100
        assert n % 2 == 0
        G = nx.DiGraph()
        for v in range(n):
            G.add_edge(v, (v + 1) % n)
            if not v % 2:
                G.add_edge((v + 2) % n, v)

        expected = [[*range(n - 2, -2, -2)]] + [
            [x % n for x in range(i, i + 3)] for i in range(0, n, 2)
        ]
        self.check_cycle_algorithm(G, expected, chordless=True)
        self.check_cycle_algorithm(
            G, [c for c in expected if len(c) <= 3], length_bound=3, chordless=True
        )

    def test_simple_cycles_acyclic_tournament(self):
        n = 10
        G = nx.DiGraph((x, y) for x in range(n) for y in range(x))
        self.check_cycle_algorithm(G, [])
        self.check_cycle_algorithm(G, [], chordless=True)

        for k in range(n + 1):
            self.check_cycle_algorithm(G, [], length_bound=k)
            self.check_cycle_algorithm(G, [], length_bound=k, chordless=True)

    def test_simple_cycles_graph(self):
        testG = nx.cycle_graph(8)
        cyc1 = tuple(range(8))
        self.check_cycle_algorithm(testG, [cyc1])

        testG.add_edge(4, -1)
        nx.add_path(testG, [3, -2, -3, -4])
        self.check_cycle_algorithm(testG, [cyc1])

        testG.update(nx.cycle_graph(range(8, 16)))
        cyc2 = tuple(range(8, 16))
        self.check_cycle_algorithm(testG, [cyc1, cyc2])

        testG.update(nx.cycle_graph(range(4, 12)))
        cyc3 = tuple(range(4, 12))
        expected = {
            (0, 1, 2, 3, 4, 5, 6, 7),  # cyc1
            (8, 9, 10, 11, 12, 13, 14, 15),  # cyc2
            (4, 5, 6, 7, 8, 9, 10, 11),  # cyc3
            (4, 5, 6, 7, 8, 15, 14, 13, 12, 11),  # cyc2 + cyc3
            (0, 1, 2, 3, 4, 11, 10, 9, 8, 7),  # cyc1 + cyc3
            (0, 1, 2, 3, 4, 11, 12, 13, 14, 15, 8, 7),  # cyc1 + cyc2 + cyc3
        }
        self.check_cycle_algorithm(testG, expected)
        assert len(expected) == (2**3 - 1) - 1  # 1 disjoint comb: cyc1 + cyc2

        # Basis size = 5 (2 loops overlapping gives 5 small loops
        #        E
        #       / \         Note: A-F = 10-15
        #    1-2-3-4-5
        #    / |   |  \   cyc1=012DAB -- left
        #   0  D   F  6   cyc2=234E   -- top
        #   \  |   |  /   cyc3=45678F -- right
        #    B-A-9-8-7    cyc4=89AC   -- bottom
        #       \ /       cyc5=234F89AD -- middle
        #        C
        #
        # combinations of 5 basis elements: 2^5 - 1  (one includes no cycles)
        #
        # disjoint combs: (11 total) not simple cycles
        #   Any pair not including cyc5 => choose(4, 2) = 6
        #   Any triple not including cyc5 => choose(4, 3) = 4
        #   Any quad not including cyc5 => choose(4, 4) = 1
        #
        # we expect 31 - 11 = 20 simple cycles
        #
        testG = nx.cycle_graph(12)
        testG.update(nx.cycle_graph([12, 10, 13, 2, 14, 4, 15, 8]).edges)
        expected = (2**5 - 1) - 11  # 11 disjoint combinations
        self.check_cycle_algorithm(testG, expected)

    def test_simple_cycles_bounded(self):
        # iteratively construct a cluster of nested cycles running in the same direction
        # there should be one cycle of every length
        d = nx.DiGraph()
        expected = []
        for n in range(10):
            nx.add_cycle(d, range(n))
            expected.append(n)
            for k, e in enumerate(expected):
                self.check_cycle_algorithm(d, e, length_bound=k)

        # iteratively construct a path of undirected cycles, connected at articulation
        # points.  there should be one cycle of every length except 2: no digons
        g = nx.Graph()
        top = 0
        expected = []
        for n in range(10):
            expected.append(n if n < 2 else n - 1)
            if n == 2:
                # no digons in undirected graphs
                continue
            nx.add_cycle(g, range(top, top + n))
            top += n
            for k, e in enumerate(expected):
                self.check_cycle_algorithm(g, e, length_bound=k)

    def test_simple_cycles_bound_corner_cases(self):
        G = nx.cycle_graph(4)
        DG = nx.cycle_graph(4, create_using=nx.DiGraph)
        assert list(nx.simple_cycles(G, length_bound=0)) == []
        assert list(nx.simple_cycles(DG, length_bound=0)) == []
        assert list(nx.chordless_cycles(G, length_bound=0)) == []
        assert list(nx.chordless_cycles(DG, length_bound=0)) == []

    def test_simple_cycles_bound_error(self):
        with pytest.raises(ValueError):
            G = nx.DiGraph()
            for c in nx.simple_cycles(G, -1):
                assert False

        with pytest.raises(ValueError):
            G = nx.Graph()
            for c in nx.simple_cycles(G, -1):
                assert False

        with pytest.raises(ValueError):
            G = nx.Graph()
            for c in nx.chordless_cycles(G, -1):
                assert False

        with pytest.raises(ValueError):
            G = nx.DiGraph()
            for c in nx.chordless_cycles(G, -1):
                assert False

    def test_chordless_cycles_clique(self):
        g_family = [self.K(n) for n in range(2, 15)]
        expected = [0, 1, 4, 10, 20, 35, 56, 84, 120, 165, 220, 286, 364]
        self.check_cycle_enumeration_integer_sequence(
            g_family, expected, chordless=True
        )

        # directed cliques have as many digons as undirected graphs have edges
        expected = [(n * n - n) // 2 for n in range(15)]
        g_family = [self.D(n) for n in range(15)]
        self.check_cycle_enumeration_integer_sequence(
            g_family, expected, chordless=True
        )


# These tests might fail with hash randomization since they depend on
# edge_dfs. For more information, see the comments in:
#    networkx/algorithms/traversal/tests/test_edgedfs.py


class TestFindCycle:
    @classmethod
    def setup_class(cls):
        cls.nodes = [0, 1, 2, 3]
        cls.edges = [(-1, 0), (0, 1), (1, 0), (1, 0), (2, 1), (3, 1)]

    def test_graph_nocycle(self):
        G = nx.Graph(self.edges)
        pytest.raises(nx.exception.NetworkXNoCycle, nx.find_cycle, G, self.nodes)

    def test_graph_cycle(self):
        G = nx.Graph(self.edges)
        G.add_edge(2, 0)
        x = list(nx.find_cycle(G, self.nodes))
        x_ = [(0, 1), (1, 2), (2, 0)]
        assert x == x_

    def test_graph_orientation_none(self):
        G = nx.Graph(self.edges)
        G.add_edge(2, 0)
        x = list(nx.find_cycle(G, self.nodes, orientation=None))
        x_ = [(0, 1), (1, 2), (2, 0)]
        assert x == x_

    def test_graph_orientation_original(self):
        G = nx.Graph(self.edges)
        G.add_edge(2, 0)
        x = list(nx.find_cycle(G, self.nodes, orientation="original"))
        x_ = [(0, 1, FORWARD), (1, 2, FORWARD), (2, 0, FORWARD)]
        assert x == x_

    def test_digraph(self):
        G = nx.DiGraph(self.edges)
        x = list(nx.find_cycle(G, self.nodes))
        x_ = [(0, 1), (1, 0)]
        assert x == x_

    def test_digraph_orientation_none(self):
        G = nx.DiGraph(self.edges)
        x = list(nx.find_cycle(G, self.nodes, orientation=None))
        x_ = [(0, 1), (1, 0)]
        assert x == x_

    def test_digraph_orientation_original(self):
        G = nx.DiGraph(self.edges)
        x = list(nx.find_cycle(G, self.nodes, orientation="original"))
        x_ = [(0, 1, FORWARD), (1, 0, FORWARD)]
        assert x == x_

    def test_multigraph(self):
        G = nx.MultiGraph(self.edges)
        x = list(nx.find_cycle(G, self.nodes))
        x_ = [(0, 1, 0), (1, 0, 1)]  # or (1, 0, 2)
        # Hash randomization...could be any edge.
        assert x[0] == x_[0]
        assert x[1][:2] == x_[1][:2]

    def test_multidigraph(self):
        G = nx.MultiDiGraph(self.edges)
        x = list(nx.find_cycle(G, self.nodes))
        x_ = [(0, 1, 0), (1, 0, 0)]  # (1, 0, 1)
        assert x[0] == x_[0]
        assert x[1][:2] == x_[1][:2]

    def test_digraph_ignore(self):
        G = nx.DiGraph(self.edges)
        x = list(nx.find_cycle(G, self.nodes, orientation="ignore"))
        x_ = [(0, 1, FORWARD), (1, 0, FORWARD)]
        assert x == x_

    def test_digraph_reverse(self):
        G = nx.DiGraph(self.edges)
        x = list(nx.find_cycle(G, self.nodes, orientation="reverse"))
        x_ = [(1, 0, REVERSE), (0, 1, REVERSE)]
        assert x == x_

    def test_multidigraph_ignore(self):
        G = nx.MultiDiGraph(self.edges)
        x = list(nx.find_cycle(G, self.nodes, orientation="ignore"))
        x_ = [(0, 1, 0, FORWARD), (1, 0, 0, FORWARD)]  # or (1, 0, 1, 1)
        assert x[0] == x_[0]
        assert x[1][:2] == x_[1][:2]
        assert x[1][3] == x_[1][3]

    def test_multidigraph_ignore2(self):
        # Loop traversed an edge while ignoring its orientation.
        G = nx.MultiDiGraph([(0, 1), (1, 2), (1, 2)])
        x = list(nx.find_cycle(G, [0, 1, 2], orientation="ignore"))
        x_ = [(1, 2, 0, FORWARD), (1, 2, 1, REVERSE)]
        assert x == x_

    def test_multidigraph_original(self):
        # Node 2 doesn't need to be searched again from visited from 4.
        # The goal here is to cover the case when 2 to be researched from 4,
        # when 4 is visited from the first time (so we must make sure that 4
        # is not visited from 2, and hence, we respect the edge orientation).
        G = nx.MultiDiGraph([(0, 1), (1, 2), (2, 3), (4, 2)])
        pytest.raises(
            nx.exception.NetworkXNoCycle,
            nx.find_cycle,
            G,
            [0, 1, 2, 3, 4],
            orientation="original",
        )

    def test_dag(self):
        G = nx.DiGraph([(0, 1), (0, 2), (1, 2)])
        pytest.raises(
            nx.exception.NetworkXNoCycle, nx.find_cycle, G, orientation="original"
        )
        x = list(nx.find_cycle(G, orientation="ignore"))
        assert x == [(0, 1, FORWARD), (1, 2, FORWARD), (0, 2, REVERSE)]

    def test_prev_explored(self):
        # https://github.com/networkx/networkx/issues/2323

        G = nx.DiGraph()
        G.add_edges_from([(1, 0), (2, 0), (1, 2), (2, 1)])
        pytest.raises(nx.NetworkXNoCycle, nx.find_cycle, G, source=0)
        x = list(nx.find_cycle(G, 1))
        x_ = [(1, 2), (2, 1)]
        assert x == x_

        x = list(nx.find_cycle(G, 2))
        x_ = [(2, 1), (1, 2)]
        assert x == x_

        x = list(nx.find_cycle(G))
        x_ = [(1, 2), (2, 1)]
        assert x == x_

    def test_no_cycle(self):
        # https://github.com/networkx/networkx/issues/2439

        G = nx.DiGraph()
        G.add_edges_from([(1, 2), (2, 0), (3, 1), (3, 2)])
        pytest.raises(nx.NetworkXNoCycle, nx.find_cycle, G, source=0)
        pytest.raises(nx.NetworkXNoCycle, nx.find_cycle, G)


def assert_basis_equal(a, b):
    assert sorted(a) == sorted(b)


class TestMinimumCycleBasis:
    @classmethod
    def setup_class(cls):
        T = nx.Graph()
        nx.add_cycle(T, [1, 2, 3, 4], weight=1)
        T.add_edge(2, 4, weight=5)
        cls.diamond_graph = T

    def test_unweighted_diamond(self):
        mcb = nx.minimum_cycle_basis(self.diamond_graph)
        assert_basis_equal(mcb, [[2, 4, 1], [3, 4, 2]])

    def test_weighted_diamond(self):
        mcb = nx.minimum_cycle_basis(self.diamond_graph, weight="weight")
        assert_basis_equal(mcb, [[2, 4, 1], [4, 3, 2, 1]])

    def test_dimensionality(self):
        # checks |MCB|=|E|-|V|+|NC|
        ntrial = 10
        for seed in range(1234, 1234 + ntrial):
            rg = nx.erdos_renyi_graph(10, 0.3, seed=seed)
            nnodes = rg.number_of_nodes()
            nedges = rg.number_of_edges()
            ncomp = nx.number_connected_components(rg)

            mcb = nx.minimum_cycle_basis(rg)
            assert len(mcb) == nedges - nnodes + ncomp
            check_independent(mcb)

    def test_complete_graph(self):
        cg = nx.complete_graph(5)
        mcb = nx.minimum_cycle_basis(cg)
        assert all(len(cycle) == 3 for cycle in mcb)
        check_independent(mcb)

    def test_tree_graph(self):
        tg = nx.balanced_tree(3, 3)
        assert not nx.minimum_cycle_basis(tg)

    def test_petersen_graph(self):
        G = nx.petersen_graph()
        mcb = list(nx.minimum_cycle_basis(G))
        expected = [
            [4, 9, 7, 5, 0],
            [1, 2, 3, 4, 0],
            [1, 6, 8, 5, 0],
            [4, 3, 8, 5, 0],
            [1, 6, 9, 4, 0],
            [1, 2, 7, 5, 0],
        ]
        assert len(mcb) == len(expected)
        assert all(c in expected for c in mcb)

        # check that order of the nodes is a path
        for c in mcb:
            assert all(G.has_edge(u, v) for u, v in nx.utils.pairwise(c, cyclic=True))
        # check independence of the basis
        check_independent(mcb)

    def test_gh6787_variable_weighted_complete_graph(self):
        N = 8
        cg = nx.complete_graph(N)
        cg.add_weighted_edges_from([(u, v, 9) for u, v in cg.edges])
        cg.add_weighted_edges_from([(u, v, 1) for u, v in nx.cycle_graph(N).edges])
        mcb = nx.minimum_cycle_basis(cg, weight="weight")
        check_independent(mcb)

    def test_gh6787_and_edge_attribute_names(self):
        G = nx.cycle_graph(4)
        G.add_weighted_edges_from([(0, 2, 10), (1, 3, 10)], weight="dist")
        expected = [[1, 3, 0], [3, 2, 1, 0], [1, 2, 0]]
        mcb = list(nx.minimum_cycle_basis(G, weight="dist"))
        assert len(mcb) == len(expected)
        assert all(c in expected for c in mcb)

        # test not using a weight with weight attributes
        expected = [[1, 3, 0], [1, 2, 0], [3, 2, 0]]
        mcb = list(nx.minimum_cycle_basis(G))
        assert len(mcb) == len(expected)
        assert all(c in expected for c in mcb)


class TestGirth:
    @pytest.mark.parametrize(
        ("G", "expected"),
        (
            (nx.chvatal_graph(), 4),
            (nx.tutte_graph(), 4),
            (nx.petersen_graph(), 5),
            (nx.heawood_graph(), 6),
            (nx.pappus_graph(), 6),
            (nx.random_labeled_tree(10, seed=42), inf),
            (nx.empty_graph(10), inf),
            (nx.Graph(chain(cycle_edges(range(5)), cycle_edges(range(6, 10)))), 4),
            (
                nx.Graph(
                    [
                        (0, 6),
                        (0, 8),
                        (0, 9),
                        (1, 8),
                        (2, 8),
                        (2, 9),
                        (4, 9),
                        (5, 9),
                        (6, 8),
                        (6, 9),
                        (7, 8),
                    ]
                ),
                3,
            ),
        ),
    )
    def test_girth(self, G, expected):
        assert nx.girth(G) == expected
