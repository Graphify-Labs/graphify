import networkx as nx


class TestDFS:
    @classmethod
    def setup_class(cls):
        # simple graph
        G = nx.Graph()
        G.add_edges_from([(0, 1), (1, 2), (1, 3), (2, 4), (3, 0), (0, 4)])
        cls.G = G
        # simple graph, disconnected
        D = nx.Graph()
        D.add_edges_from([(0, 1), (2, 3)])
        cls.D = D

    def test_preorder_nodes(self):
        assert list(nx.dfs_preorder_nodes(self.G, source=0)) == [0, 1, 2, 4, 3]
        assert list(nx.dfs_preorder_nodes(self.D)) == [0, 1, 2, 3]
        assert list(nx.dfs_preorder_nodes(self.D, source=2)) == [2, 3]

    def test_postorder_nodes(self):
        assert list(nx.dfs_postorder_nodes(self.G, source=0)) == [4, 2, 3, 1, 0]
        assert list(nx.dfs_postorder_nodes(self.D)) == [1, 0, 3, 2]
        assert list(nx.dfs_postorder_nodes(self.D, source=0)) == [1, 0]

    def test_successor(self):
        assert nx.dfs_successors(self.G, source=0) == {0: [1], 1: [2, 3], 2: [4]}
        assert nx.dfs_successors(self.G, source=1) == {0: [3, 4], 1: [0], 4: [2]}
        assert nx.dfs_successors(self.D) == {0: [1], 2: [3]}
        assert nx.dfs_successors(self.D, source=1) == {1: [0]}

    def test_predecessor(self):
        assert nx.dfs_predecessors(self.G, source=0) == {1: 0, 2: 1, 3: 1, 4: 2}
        assert nx.dfs_predecessors(self.D) == {1: 0, 3: 2}

    def test_dfs_tree(self):
        exp_nodes = sorted(self.G.nodes())
        exp_edges = [(0, 1), (1, 2), (1, 3), (2, 4)]
        # Search from first node
        T = nx.dfs_tree(self.G, source=0)
        assert sorted(T.nodes()) == exp_nodes
        assert sorted(T.edges()) == exp_edges
        # Check source=None
        T = nx.dfs_tree(self.G, source=None)
        assert sorted(T.nodes()) == exp_nodes
        assert sorted(T.edges()) == exp_edges
        # Check source=None is the default
        T = nx.dfs_tree(self.G)
        assert sorted(T.nodes()) == exp_nodes
        assert sorted(T.edges()) == exp_edges

    def test_dfs_edges(self):
        edges = nx.dfs_edges(self.G, source=0)
        assert list(edges) == [(0, 1), (1, 2), (2, 4), (1, 3)]
        edges = nx.dfs_edges(self.D)
        assert list(edges) == [(0, 1), (2, 3)]

    def test_dfs_edges_sorting(self):
        G = nx.Graph([(0, 1), (1, 2), (1, 3), (2, 4), (3, 0), (0, 4)])
        edges_asc = nx.dfs_edges(G, source=0, sort_neighbors=sorted)
        sorted_desc = lambda x: sorted(x, reverse=True)
        edges_desc = nx.dfs_edges(G, source=0, sort_neighbors=sorted_desc)
        assert list(edges_asc) == [(0, 1), (1, 2), (2, 4), (1, 3)]
        assert list(edges_desc) == [(0, 4), (4, 2), (2, 1), (1, 3)]

    def test_dfs_labeled_edges(self):
        edges = list(nx.dfs_labeled_edges(self.G, source=0))
        forward = [(u, v) for (u, v, d) in edges if d == "forward"]
        assert forward == [(0, 0), (0, 1), (1, 2), (2, 4), (1, 3)]
        assert edges == [
            (0, 0, "forward"),
            (0, 1, "forward"),
            (1, 0, "nontree"),
            (1, 2, "forward"),
            (2, 1, "nontree"),
            (2, 4, "forward"),
            (4, 2, "nontree"),
            (4, 0, "nontree"),
            (2, 4, "reverse"),
            (1, 2, "reverse"),
            (1, 3, "forward"),
            (3, 1, "nontree"),
            (3, 0, "nontree"),
            (1, 3, "reverse"),
            (0, 1, "reverse"),
            (0, 3, "nontree"),
            (0, 4, "nontree"),
            (0, 0, "reverse"),
        ]

    def test_dfs_labeled_edges_sorting(self):
        G = nx.Graph([(0, 1), (1, 2), (1, 3), (2, 4), (3, 0), (0, 4)])
        edges_asc = nx.dfs_labeled_edges(G, source=0, sort_neighbors=sorted)
        sorted_desc = lambda x: sorted(x, reverse=True)
        edges_desc = nx.dfs_labeled_edges(G, source=0, sort_neighbors=sorted_desc)
        assert list(edges_asc) == [
            (0, 0, "forward"),
            (0, 1, "forward"),
            (1, 0, "nontree"),
            (1, 2, "forward"),
            (2, 1, "nontree"),
            (2, 4, "forward"),
            (4, 0, "nontree"),
            (4, 2, "nontree"),
            (2, 4, "reverse"),
            (1, 2, "reverse"),
            (1, 3, "forward"),
            (3, 0, "nontree"),
            (3, 1, "nontree"),
            (1, 3, "reverse"),
            (0, 1, "reverse"),
            (0, 3, "nontree"),
            (0, 4, "nontree"),
            (0, 0, "reverse"),
        ]
        assert list(edges_desc) == [
            (0, 0, "forward"),
            (0, 4, "forward"),
            (4, 2, "forward"),
            (2, 4, "nontree"),
            (2, 1, "forward"),
            (1, 3, "forward"),
            (3, 1, "nontree"),
            (3, 0, "nontree"),
            (1, 3, "reverse"),
            (1, 2, "nontree"),
            (1, 0, "nontree"),
            (2, 1, "reverse"),
            (4, 2, "reverse"),
            (4, 0, "nontree"),
            (0, 4, "reverse"),
            (0, 3, "nontree"),
            (0, 1, "nontree"),
            (0, 0, "reverse"),
        ]

    def test_dfs_labeled_disconnected_edges(self):
        edges = list(nx.dfs_labeled_edges(self.D))
        forward = [(u, v) for (u, v, d) in edges if d == "forward"]
        assert forward == [(0, 0), (0, 1), (2, 2), (2, 3)]
        assert edges == [
            (0, 0, "forward"),
            (0, 1, "forward"),
            (1, 0, "nontree"),
            (0, 1, "reverse"),
            (0, 0, "reverse"),
            (2, 2, "forward"),
            (2, 3, "forward"),
            (3, 2, "nontree"),
            (2, 3, "reverse"),
            (2, 2, "reverse"),
        ]

    def test_dfs_tree_isolates(self):
        G = nx.Graph()
        G.add_node(1)
        G.add_node(2)
        T = nx.dfs_tree(G, source=1)
        assert sorted(T.nodes()) == [1]
        assert sorted(T.edges()) == []
        T = nx.dfs_tree(G, source=None)
        assert sorted(T.nodes()) == [1, 2]
        assert sorted(T.edges()) == []


class TestDepthLimitedSearch:
    @classmethod
    def setup_class(cls):
        # a tree
        G = nx.Graph()
        nx.add_path(G, [0, 1, 2, 3, 4, 5, 6])
        nx.add_path(G, [2, 7, 8, 9, 10])
        cls.G = G
        # a disconnected graph
        D = nx.Graph()
        D.add_edges_from([(0, 1), (2, 3)])
        nx.add_path(D, [2, 7, 8, 9, 10])
        cls.D = D

    def test_dls_preorder_nodes(self):
        assert list(nx.dfs_preorder_nodes(self.G, source=0, depth_limit=2)) == [0, 1, 2]
        assert list(nx.dfs_preorder_nodes(self.D, source=1, depth_limit=2)) == ([1, 0])

    def test_dls_postorder_nodes(self):
        assert list(nx.dfs_postorder_nodes(self.G, source=3, depth_limit=3)) == [
            1,
            7,
            2,
            5,
            4,
            3,
        ]
        assert list(nx.dfs_postorder_nodes(self.D, source=2, depth_limit=2)) == (
            [3, 7, 2]
        )

    def test_dls_successor(self):
        result = nx.dfs_successors(self.G, source=4, depth_limit=3)
        assert {n: set(v) for n, v in result.items()} == {
            2: {1, 7},
            3: {2},
            4: {3, 5},
            5: {6},
        }
        result = nx.dfs_successors(self.D, source=7, depth_limit=2)
        assert {n: set(v) for n, v in result.items()} == {8: {9}, 2: {3}, 7: {8, 2}}

    def test_dls_predecessor(self):
        assert nx.dfs_predecessors(self.G, source=0, depth_limit=3) == {
            1: 0,
            2: 1,
            3: 2,
            7: 2,
        }
        assert nx.dfs_predecessors(self.D, source=2, depth_limit=3) == {
            8: 7,
            9: 8,
            3: 2,
            7: 2,
        }

    def test_dls_tree(self):
        T = nx.dfs_tree(self.G, source=3, depth_limit=1)
        assert sorted(T.edges()) == [(3, 2), (3, 4)]

    def test_dls_edges(self):
        edges = nx.dfs_edges(self.G, source=9, depth_limit=4)
        assert list(edges) == [(9, 8), (8, 7), (7, 2), (2, 1), (2, 3), (9, 10)]

    def test_dls_labeled_edges_depth_1(self):
        edges = list(nx.dfs_labeled_edges(self.G, source=5, depth_limit=1))
        forward = [(u, v) for (u, v, d) in edges if d == "forward"]
        assert forward == [(5, 5), (5, 4), (5, 6)]
        # Note: reverse-depth_limit edge types were not reported before gh-6240
        assert edges == [
            (5, 5, "forward"),
            (5, 4, "forward"),
            (5, 4, "reverse-depth_limit"),
            (5, 6, "forward"),
            (5, 6, "reverse-depth_limit"),
            (5, 5, "reverse"),
        ]

    def test_dls_labeled_edges_depth_2(self):
        edges = list(nx.dfs_labeled_edges(self.G, source=6, depth_limit=2))
        forward = [(u, v) for (u, v, d) in edges if d == "forward"]
        assert forward == [(6, 6), (6, 5), (5, 4)]
        assert edges == [
            (6, 6, "forward"),
            (6, 5, "forward"),
            (5, 4, "forward"),
            (5, 4, "reverse-depth_limit"),
            (5, 6, "nontree"),
            (6, 5, "reverse"),
            (6, 6, "reverse"),
        ]

    def test_dls_labeled_disconnected_edges(self):
        edges = list(nx.dfs_labeled_edges(self.D, depth_limit=1))
        assert edges == [
            (0, 0, "forward"),
            (0, 1, "forward"),
            (0, 1, "reverse-depth_limit"),
            (0, 0, "reverse"),
            (2, 2, "forward"),
            (2, 3, "forward"),
            (2, 3, "reverse-depth_limit"),
            (2, 7, "forward"),
            (2, 7, "reverse-depth_limit"),
            (2, 2, "reverse"),
            (8, 8, "forward"),
            (8, 7, "nontree"),
            (8, 9, "forward"),
            (8, 9, "reverse-depth_limit"),
            (8, 8, "reverse"),
            (10, 10, "forward"),
            (10, 9, "nontree"),
            (10, 10, "reverse"),
        ]
        # large depth_limit has no impact
        edges = list(nx.dfs_labeled_edges(self.D, depth_limit=19))
        assert edges == [
            (0, 0, "forward"),
            (0, 1, "forward"),
            (1, 0, "nontree"),
            (0, 1, "reverse"),
            (0, 0, "reverse"),
            (2, 2, "forward"),
            (2, 3, "forward"),
            (3, 2, "nontree"),
            (2, 3, "reverse"),
            (2, 7, "forward"),
            (7, 2, "nontree"),
            (7, 8, "forward"),
            (8, 7, "nontree"),
            (8, 9, "forward"),
            (9, 8, "nontree"),
            (9, 10, "forward"),
            (10, 9, "nontree"),
            (9, 10, "reverse"),
            (8, 9, "reverse"),
            (7, 8, "reverse"),
            (2, 7, "reverse"),
            (2, 2, "reverse"),
        ]
