import itertools as it

import pytest

import networkx as nx
from networkx import vf2pp_is_isomorphic, vf2pp_isomorphism
from networkx.algorithms.isomorphism.vf2pp import (
    _consistent_PT,
    _cut_PT,
    _feasibility,
    _find_candidates,
    _find_candidates_Di,
    _GraphParameters,
    _initialize_parameters,
    _matching_order,
    _restore_Tinout,
    _restore_Tinout_Di,
    _StateParameters,
    _update_Tinout,
)

labels_same = ["blue"]

labels_many = [
    "white",
    "red",
    "blue",
    "green",
    "orange",
    "black",
    "purple",
    "yellow",
    "brown",
    "cyan",
    "solarized",
    "pink",
    "none",
]


class TestNodeOrdering:
    def test_empty_graph(self):
        G1 = nx.Graph()
        G2 = nx.Graph()
        gparams = _GraphParameters(G1, G2, None, None, None, None, None)
        assert len(set(_matching_order(gparams))) == 0

    def test_single_node(self):
        G1 = nx.Graph()
        G2 = nx.Graph()
        G1.add_node(1)
        G2.add_node(1)

        nx.set_node_attributes(G1, dict(zip(G1, it.cycle(labels_many))), "label")
        nx.set_node_attributes(
            G2,
            dict(zip(G2, it.cycle(labels_many))),
            "label",
        )
        l1, l2 = (
            nx.get_node_attributes(G1, "label"),
            nx.get_node_attributes(G2, "label"),
        )

        gparams = _GraphParameters(
            G1,
            G2,
            l1,
            l2,
            nx.utils.groups(l1),
            nx.utils.groups(l2),
            nx.utils.groups(dict(G2.degree())),
        )
        m = _matching_order(gparams)
        assert m == [1]

    def test_matching_order(self):
        labels = [
            "blue",
            "blue",
            "red",
            "red",
            "red",
            "red",
            "green",
            "green",
            "green",
            "yellow",
            "purple",
            "purple",
            "blue",
            "blue",
        ]
        G1 = nx.Graph(
            [
                (0, 1),
                (0, 2),
                (1, 2),
                (2, 5),
                (2, 4),
                (1, 3),
                (1, 4),
                (3, 6),
                (4, 6),
                (6, 7),
                (7, 8),
                (9, 10),
                (9, 11),
                (11, 12),
                (11, 13),
                (12, 13),
                (10, 13),
            ]
        )
        G2 = G1.copy()
        nx.set_node_attributes(G1, dict(zip(G1, it.cycle(labels))), "label")
        nx.set_node_attributes(
            G2,
            dict(zip(G2, it.cycle(labels))),
            "label",
        )
        l1, l2 = (
            nx.get_node_attributes(G1, "label"),
            nx.get_node_attributes(G2, "label"),
        )
        gparams = _GraphParameters(
            G1,
            G2,
            l1,
            l2,
            nx.utils.groups(l1),
            nx.utils.groups(l2),
            nx.utils.groups(dict(G2.degree())),
        )

        expected = [9, 11, 10, 13, 12, 1, 2, 4, 0, 3, 6, 5, 7, 8]
        assert _matching_order(gparams) == expected

    def test_matching_order_all_branches(self):
        G1 = nx.Graph(
            [(0, 1), (0, 2), (0, 3), (0, 4), (1, 2), (1, 3), (1, 4), (2, 4), (3, 4)]
        )
        G1.add_node(5)
        G2 = G1.copy()

        G1.nodes[0]["label"] = "black"
        G1.nodes[1]["label"] = "blue"
        G1.nodes[2]["label"] = "blue"
        G1.nodes[3]["label"] = "red"
        G1.nodes[4]["label"] = "red"
        G1.nodes[5]["label"] = "blue"

        G2.nodes[0]["label"] = "black"
        G2.nodes[1]["label"] = "blue"
        G2.nodes[2]["label"] = "blue"
        G2.nodes[3]["label"] = "red"
        G2.nodes[4]["label"] = "red"
        G2.nodes[5]["label"] = "blue"

        l1, l2 = (
            nx.get_node_attributes(G1, "label"),
            nx.get_node_attributes(G2, "label"),
        )
        gparams = _GraphParameters(
            G1,
            G2,
            l1,
            l2,
            nx.utils.groups(l1),
            nx.utils.groups(l2),
            nx.utils.groups(dict(G2.degree())),
        )

        expected = [0, 4, 1, 3, 2, 5]
        assert _matching_order(gparams) == expected


class TestGraphCandidateSelection:
    G1_edges = [
        (1, 2),
        (1, 4),
        (1, 5),
        (2, 3),
        (2, 4),
        (3, 4),
        (4, 5),
        (1, 6),
        (6, 7),
        (6, 8),
        (8, 9),
        (7, 9),
    ]
    mapped = {
        0: "x",
        1: "a",
        2: "b",
        3: "c",
        4: "d",
        5: "e",
        6: "f",
        7: "g",
        8: "h",
        9: "i",
    }

    def test_no_covered_neighbors_no_labels(self):
        G1 = nx.Graph()
        G1.add_edges_from(self.G1_edges)
        G1.add_node(0)
        G2 = nx.relabel_nodes(G1, self.mapped)

        G1_degree = dict(G1.degree)
        l1 = dict(G1.nodes(data="label", default=-1))
        l2 = dict(G2.nodes(data="label", default=-1))
        gparams = _GraphParameters(
            G1,
            G2,
            l1,
            l2,
            nx.utils.groups(l1),
            nx.utils.groups(l2),
            nx.utils.groups(dict(G2.degree())),
        )

        m = {9: self.mapped[9], 1: self.mapped[1]}
        m_rev = {self.mapped[9]: 9, self.mapped[1]: 1}

        T1 = {7, 8, 2, 4, 5}
        T1_tilde = {0, 3, 6}
        T2 = {"g", "h", "b", "d", "e"}
        T2_tilde = {"x", "c", "f"}

        sparams = _StateParameters(
            m, m_rev, T1, None, T1_tilde, None, T2, None, T2_tilde, None
        )

        u = 3
        candidates = _find_candidates(u, gparams, sparams, G1_degree)
        assert candidates == {self.mapped[u]}

        u = 0
        candidates = _find_candidates(u, gparams, sparams, G1_degree)
        assert candidates == {self.mapped[u]}

        m.pop(9)
        m_rev.pop(self.mapped[9])

        T1 = {2, 4, 5, 6}
        T1_tilde = {0, 3, 7, 8, 9}
        T2 = {"g", "h", "b", "d", "e", "f"}
        T2_tilde = {"x", "c", "g", "h", "i"}

        sparams = _StateParameters(
            m, m_rev, T1, None, T1_tilde, None, T2, None, T2_tilde, None
        )

        u = 7
        candidates = _find_candidates(u, gparams, sparams, G1_degree)
        assert candidates == {
            self.mapped[u],
            self.mapped[8],
            self.mapped[3],
            self.mapped[9],
        }

    def test_no_covered_neighbors_with_labels(self):
        G1 = nx.Graph()
        G1.add_edges_from(self.G1_edges)
        G1.add_node(0)
        G2 = nx.relabel_nodes(G1, self.mapped)

        G1_degree = dict(G1.degree)
        nx.set_node_attributes(
            G1,
            dict(zip(G1, it.cycle(labels_many))),
            "label",
        )
        nx.set_node_attributes(
            G2,
            dict(
                zip(
                    [self.mapped[n] for n in G1],
                    it.cycle(labels_many),
                )
            ),
            "label",
        )
        l1 = dict(G1.nodes(data="label", default=-1))
        l2 = dict(G2.nodes(data="label", default=-1))
        gparams = _GraphParameters(
            G1,
            G2,
            l1,
            l2,
            nx.utils.groups(l1),
            nx.utils.groups(l2),
            nx.utils.groups(dict(G2.degree())),
        )

        m = {9: self.mapped[9], 1: self.mapped[1]}
        m_rev = {self.mapped[9]: 9, self.mapped[1]: 1}

        T1 = {7, 8, 2, 4, 5, 6}
        T1_tilde = {0, 3}
        T2 = {"g", "h", "b", "d", "e", "f"}
        T2_tilde = {"x", "c"}

        sparams = _StateParameters(
            m, m_rev, T1, None, T1_tilde, None, T2, None, T2_tilde, None
        )

        u = 3
        candidates = _find_candidates(u, gparams, sparams, G1_degree)
        assert candidates == {self.mapped[u]}

        u = 0
        candidates = _find_candidates(u, gparams, sparams, G1_degree)
        assert candidates == {self.mapped[u]}

        # Change label of disconnected node
        G1.nodes[u]["label"] = "blue"
        l1 = dict(G1.nodes(data="label", default=-1))
        l2 = dict(G2.nodes(data="label", default=-1))
        gparams = _GraphParameters(
            G1,
            G2,
            l1,
            l2,
            nx.utils.groups(l1),
            nx.utils.groups(l2),
            nx.utils.groups(dict(G2.degree())),
        )

        # No candidate
        candidates = _find_candidates(u, gparams, sparams, G1_degree)
        assert candidates == set()

        m.pop(9)
        m_rev.pop(self.mapped[9])

        T1 = {2, 4, 5, 6}
        T1_tilde = {0, 3, 7, 8, 9}
        T2 = {"b", "d", "e", "f"}
        T2_tilde = {"x", "c", "g", "h", "i"}

        sparams = _StateParameters(
            m, m_rev, T1, None, T1_tilde, None, T2, None, T2_tilde, None
        )

        u = 7
        candidates = _find_candidates(u, gparams, sparams, G1_degree)
        assert candidates == {self.mapped[u]}

        G1.nodes[8]["label"] = G1.nodes[7]["label"]
        G2.nodes[self.mapped[8]]["label"] = G1.nodes[7]["label"]
        l1 = dict(G1.nodes(data="label", default=-1))
        l2 = dict(G2.nodes(data="label", default=-1))
        gparams = _GraphParameters(
            G1,
            G2,
            l1,
            l2,
            nx.utils.groups(l1),
            nx.utils.groups(l2),
            nx.utils.groups(dict(G2.degree())),
        )

        candidates = _find_candidates(u, gparams, sparams, G1_degree)
        assert candidates == {self.mapped[u], self.mapped[8]}

    def test_covered_neighbors_no_labels(self):
        G1 = nx.Graph()
        G1.add_edges_from(self.G1_edges)
        G1.add_node(0)
        G2 = nx.relabel_nodes(G1, self.mapped)

        G1_degree = dict(G1.degree)
        l1 = dict(G1.nodes(data=None, default=-1))
        l2 = dict(G2.nodes(data=None, default=-1))
        gparams = _GraphParameters(
            G1,
            G2,
            l1,
            l2,
            nx.utils.groups(l1),
            nx.utils.groups(l2),
            nx.utils.groups(dict(G2.degree())),
        )

        m = {9: self.mapped[9], 1: self.mapped[1]}
        m_rev = {self.mapped[9]: 9, self.mapped[1]: 1}

        T1 = {7, 8, 2, 4, 5, 6}
        T1_tilde = {0, 3}
        T2 = {"g", "h", "b", "d", "e", "f"}
        T2_tilde = {"x", "c"}

        sparams = _StateParameters(
            m, m_rev, T1, None, T1_tilde, None, T2, None, T2_tilde, None
        )

        u = 5
        candidates = _find_candidates(u, gparams, sparams, G1_degree)
        assert candidates == {self.mapped[u]}

        u = 6
        candidates = _find_candidates(u, gparams, sparams, G1_degree)
        assert candidates == {self.mapped[u], self.mapped[2]}

    def test_covered_neighbors_with_labels(self):
        G1 = nx.Graph()
        G1.add_edges_from(self.G1_edges)
        G1.add_node(0)
        G2 = nx.relabel_nodes(G1, self.mapped)

        G1_degree = dict(G1.degree)
        nx.set_node_attributes(
            G1,
            dict(zip(G1, it.cycle(labels_many))),
            "label",
        )
        nx.set_node_attributes(
            G2,
            dict(
                zip(
                    [self.mapped[n] for n in G1],
                    it.cycle(labels_many),
                )
            ),
            "label",
        )
        l1 = dict(G1.nodes(data="label", default=-1))
        l2 = dict(G2.nodes(data="label", default=-1))
        gparams = _GraphParameters(
            G1,
            G2,
            l1,
            l2,
            nx.utils.groups(l1),
            nx.utils.groups(l2),
            nx.utils.groups(dict(G2.degree())),
        )

        m = {9: self.mapped[9], 1: self.mapped[1]}
        m_rev = {self.mapped[9]: 9, self.mapped[1]: 1}

        T1 = {7, 8, 2, 4, 5, 6}
        T1_tilde = {0, 3}
        T2 = {"g", "h", "b", "d", "e", "f"}
        T2_tilde = {"x", "c"}

        sparams = _StateParameters(
            m, m_rev, T1, None, T1_tilde, None, T2, None, T2_tilde, None
        )

        u = 5
        candidates = _find_candidates(u, gparams, sparams, G1_degree)
        assert candidates == {self.mapped[u]}

        u = 6
        candidates = _find_candidates(u, gparams, sparams, G1_degree)
        assert candidates == {self.mapped[u]}

        # Assign to 2, the same label as 6
        G1.nodes[2]["label"] = G1.nodes[u]["label"]
        G2.nodes[self.mapped[2]]["label"] = G1.nodes[u]["label"]
        l1 = dict(G1.nodes(data="label", default=-1))
        l2 = dict(G2.nodes(data="label", default=-1))
        gparams = _GraphParameters(
            G1,
            G2,
            l1,
            l2,
            nx.utils.groups(l1),
            nx.utils.groups(l2),
            nx.utils.groups(dict(G2.degree())),
        )

        candidates = _find_candidates(u, gparams, sparams, G1_degree)
        assert candidates == {self.mapped[u], self.mapped[2]}


class TestDiGraphCandidateSelection:
    G1_edges = [
        (1, 2),
        (1, 4),
        (5, 1),
        (2, 3),
        (4, 2),
        (3, 4),
        (4, 5),
        (1, 6),
        (6, 7),
        (6, 8),
        (8, 9),
        (7, 9),
    ]
    mapped = {
        0: "x",
        1: "a",
        2: "b",
        3: "c",
        4: "d",
        5: "e",
        6: "f",
        7: "g",
        8: "h",
        9: "i",
    }

    def test_no_covered_neighbors_no_labels(self):
        G1 = nx.DiGraph()
        G1.add_edges_from(self.G1_edges)
        G1.add_node(0)
        G2 = nx.relabel_nodes(G1, self.mapped)

        G1_degree = {
            n: (in_degree, out_degree)
            for (n, in_degree), (_, out_degree) in zip(G1.in_degree, G1.out_degree)
        }

        l1 = dict(G1.nodes(data="label", default=-1))
        l2 = dict(G2.nodes(data="label", default=-1))
        gparams = _GraphParameters(
            G1,
            G2,
            l1,
            l2,
            nx.utils.groups(l1),
            nx.utils.groups(l2),
            nx.utils.groups(
                {
                    node: (in_degree, out_degree)
                    for (node, in_degree), (_, out_degree) in zip(
                        G2.in_degree(), G2.out_degree()
                    )
                }
            ),
        )

        m = {9: self.mapped[9], 1: self.mapped[1]}
        m_rev = {self.mapped[9]: 9, self.mapped[1]: 1}

        T1_out = {2, 4, 6}
        T1_in = {5, 7, 8}
        T1_tilde = {0, 3}
        T2_out = {"b", "d", "f"}
        T2_in = {"e", "g", "h"}
        T2_tilde = {"x", "c"}

        sparams = _StateParameters(
            m, m_rev, T1_out, T1_in, T1_tilde, None, T2_out, T2_in, T2_tilde, None
        )

        u = 3
        candidates = _find_candidates_Di(u, gparams, sparams, G1_degree)
        assert candidates == {self.mapped[u]}

        u = 0
        candidates = _find_candidates_Di(u, gparams, sparams, G1_degree)
        assert candidates == {self.mapped[u]}

        m.pop(9)
        m_rev.pop(self.mapped[9])

        T1_out = {2, 4, 6}
        T1_in = {5}
        T1_tilde = {0, 3, 7, 8, 9}
        T2_out = {"b", "d", "f"}
        T2_in = {"e"}
        T2_tilde = {"x", "c", "g", "h", "i"}

        sparams = _StateParameters(
            m, m_rev, T1_out, T1_in, T1_tilde, None, T2_out, T2_in, T2_tilde, None
        )

        u = 7
        candidates = _find_candidates_Di(u, gparams, sparams, G1_degree)
        assert candidates == {self.mapped[u], self.mapped[8], self.mapped[3]}

    def test_no_covered_neighbors_with_labels(self):
        G1 = nx.DiGraph()
        G1.add_edges_from(self.G1_edges)
        G1.add_node(0)
        G2 = nx.relabel_nodes(G1, self.mapped)

        G1_degree = {
            n: (in_degree, out_degree)
            for (n, in_degree), (_, out_degree) in zip(G1.in_degree, G1.out_degree)
        }
        nx.set_node_attributes(
            G1,
            dict(zip(G1, it.cycle(labels_many))),
            "label",
        )
        nx.set_node_attributes(
            G2,
            dict(
                zip(
                    [self.mapped[n] for n in G1],
                    it.cycle(labels_many),
                )
            ),
            "label",
        )
        l1 = dict(G1.nodes(data="label", default=-1))
        l2 = dict(G2.nodes(data="label", default=-1))
        gparams = _GraphParameters(
            G1,
            G2,
            l1,
            l2,
            nx.utils.groups(l1),
            nx.utils.groups(l2),
            nx.utils.groups(
                {
                    node: (in_degree, out_degree)
                    for (node, in_degree), (_, out_degree) in zip(
                        G2.in_degree(), G2.out_degree()
                    )
                }
            ),
        )

        m = {9: self.mapped[9], 1: self.mapped[1]}
        m_rev = {self.mapped[9]: 9, self.mapped[1]: 1}

        T1_out = {2, 4, 6}
        T1_in = {5, 7, 8}
        T1_tilde = {0, 3}
        T2_out = {"b", "d", "f"}
        T2_in = {"e", "g", "h"}
        T2_tilde = {"x", "c"}

        sparams = _StateParameters(
            m, m_rev, T1_out, T1_in, T1_tilde, None, T2_out, T2_in, T2_tilde, None
        )

        u = 3
        candidates = _find_candidates_Di(u, gparams, sparams, G1_degree)
        assert candidates == {self.mapped[u]}

        u = 0
        candidates = _find_candidates_Di(u, gparams, sparams, G1_degree)
        assert candidates == {self.mapped[u]}

        # Change label of disconnected node
        G1.nodes[u]["label"] = "blue"
        l1 = dict(G1.nodes(data="label", default=-1))
        l2 = dict(G2.nodes(data="label", default=-1))
        gparams = _GraphParameters(
            G1,
            G2,
            l1,
            l2,
            nx.utils.groups(l1),
            nx.utils.groups(l2),
            nx.utils.groups(
                {
                    node: (in_degree, out_degree)
                    for (node, in_degree), (_, out_degree) in zip(
                        G2.in_degree(), G2.out_degree()
                    )
                }
            ),
        )

        # No candidate
        candidates = _find_candidates_Di(u, gparams, sparams, G1_degree)
        assert candidates == set()

        m.pop(9)
        m_rev.pop(self.mapped[9])

        T1_out = {2, 4, 6}
        T1_in = {5}
        T1_tilde = {0, 3, 7, 8, 9}
        T2_out = {"b", "d", "f"}
        T2_in = {"e"}
        T2_tilde = {"x", "c", "g", "h", "i"}

        sparams = _StateParameters(
            m, m_rev, T1_out, T1_in, T1_tilde, None, T2_out, T2_in, T2_tilde, None
        )

        u = 7
        candidates = _find_candidates_Di(u, gparams, sparams, G1_degree)
        assert candidates == {self.mapped[u]}

        G1.nodes[8]["label"] = G1.nodes[7]["label"]
        G2.nodes[self.mapped[8]]["label"] = G1.nodes[7]["label"]
        l1 = dict(G1.nodes(data="label", default=-1))
        l2 = dict(G2.nodes(data="label", default=-1))
        gparams = _GraphParameters(
            G1,
            G2,
            l1,
            l2,
            nx.utils.groups(l1),
            nx.utils.groups(l2),
            nx.utils.groups(
                {
                    node: (in_degree, out_degree)
                    for (node, in_degree), (_, out_degree) in zip(
                        G2.in_degree(), G2.out_degree()
                    )
                }
            ),
        )

        candidates = _find_candidates_Di(u, gparams, sparams, G1_degree)
        assert candidates == {self.mapped[u], self.mapped[8]}

    def test_covered_neighbors_no_labels(self):
        G1 = nx.DiGraph()
        G1.add_edges_from(self.G1_edges)
        G1.add_node(0)
        G2 = nx.relabel_nodes(G1, self.mapped)

        G1_degree = {
            n: (in_degree, out_degree)
            for (n, in_degree), (_, out_degree) in zip(G1.in_degree, G1.out_degree)
        }

        l1 = dict(G1.nodes(data=None, default=-1))
        l2 = dict(G2.nodes(data=None, default=-1))
        gparams = _GraphParameters(
            G1,
            G2,
            l1,
            l2,
            nx.utils.groups(l1),
            nx.utils.groups(l2),
            nx.utils.groups(
                {
                    node: (in_degree, out_degree)
                    for (node, in_degree), (_, out_degree) in zip(
                        G2.in_degree(), G2.out_degree()
                    )
                }
            ),
        )

        m = {9: self.mapped[9], 1: self.mapped[1]}
        m_rev = {self.mapped[9]: 9, self.mapped[1]: 1}

        T1_out = {2, 4, 6}
        T1_in = {5, 7, 8}
        T1_tilde = {0, 3}
        T2_out = {"b", "d", "f"}
        T2_in = {"e", "g", "h"}
        T2_tilde = {"x", "c"}

        sparams = _StateParameters(
            m, m_rev, T1_out, T1_in, T1_tilde, None, T2_out, T2_in, T2_tilde, None
        )

        u = 5
        candidates = _find_candidates_Di(u, gparams, sparams, G1_degree)
        assert candidates == {self.mapped[u]}

        u = 6
        candidates = _find_candidates_Di(u, gparams, sparams, G1_degree)
        assert candidates == {self.mapped[u]}

        # Change the direction of an edge to make the degree orientation same as first candidate of u.
        G1.remove_edge(4, 2)
        G1.add_edge(2, 4)
        G2.remove_edge("d", "b")
        G2.add_edge("b", "d")

        gparams = _GraphParameters(
            G1,
            G2,
            l1,
            l2,
            nx.utils.groups(l1),
            nx.utils.groups(l2),
            nx.utils.groups(
                {
                    node: (in_degree, out_degree)
                    for (node, in_degree), (_, out_degree) in zip(
                        G2.in_degree(), G2.out_degree()
                    )
                }
            ),
        )

        candidates = _find_candidates_Di(u, gparams, sparams, G1_degree)
        assert candidates == {self.mapped[u], self.mapped[2]}

    def test_covered_neighbors_with_labels(self):
        G1 = nx.DiGraph()
        G1.add_edges_from(self.G1_edges)
        G1.add_node(0)
        G2 = nx.relabel_nodes(G1, self.mapped)

        G1.remove_edge(4, 2)
        G1.add_edge(2, 4)
        G2.remove_edge("d", "b")
        G2.add_edge("b", "d")

        G1_degree = {
            n: (in_degree, out_degree)
            for (n, in_degree), (_, out_degree) in zip(G1.in_degree, G1.out_degree)
        }

        nx.set_node_attributes(
            G1,
            dict(zip(G1, it.cycle(labels_many))),
            "label",
        )
        nx.set_node_attributes(
            G2,
            dict(
                zip(
                    [self.mapped[n] for n in G1],
                    it.cycle(labels_many),
                )
            ),
            "label",
        )
        l1 = dict(G1.nodes(data="label", default=-1))
        l2 = dict(G2.nodes(data="label", default=-1))
        gparams = _GraphParameters(
            G1,
            G2,
            l1,
            l2,
            nx.utils.groups(l1),
            nx.utils.groups(l2),
            nx.utils.groups(
                {
                    node: (in_degree, out_degree)
                    for (node, in_degree), (_, out_degree) in zip(
                        G2.in_degree(), G2.out_degree()
                    )
                }
            ),
        )

        m = {9: self.mapped[9], 1: self.mapped[1]}
        m_rev = {self.mapped[9]: 9, self.mapped[1]: 1}

        T1_out = {2, 4, 6}
        T1_in = {5, 7, 8}
        T1_tilde = {0, 3}
        T2_out = {"b", "d", "f"}
        T2_in = {"e", "g", "h"}
        T2_tilde = {"x", "c"}

        sparams = _StateParameters(
            m, m_rev, T1_out, T1_in, T1_tilde, None, T2_out, T2_in, T2_tilde, None
        )

        u = 5
        candidates = _find_candidates_Di(u, gparams, sparams, G1_degree)
        assert candidates == {self.mapped[u]}

        u = 6
        candidates = _find_candidates_Di(u, gparams, sparams, G1_degree)
        assert candidates == {self.mapped[u]}

        # Assign to 2, the same label as 6
        G1.nodes[2]["label"] = G1.nodes[u]["label"]
        G2.nodes[self.mapped[2]]["label"] = G1.nodes[u]["label"]
        l1 = dict(G1.nodes(data="label", default=-1))
        l2 = dict(G2.nodes(data="label", default=-1))
        gparams = _GraphParameters(
            G1,
            G2,
            l1,
            l2,
            nx.utils.groups(l1),
            nx.utils.groups(l2),
            nx.utils.groups(
                {
                    node: (in_degree, out_degree)
                    for (node, in_degree), (_, out_degree) in zip(
                        G2.in_degree(), G2.out_degree()
                    )
                }
            ),
        )

        candidates = _find_candidates_Di(u, gparams, sparams, G1_degree)
        assert candidates == {self.mapped[u], self.mapped[2]}

        # Change the direction of an edge to make the degree orientation same as first candidate of u.
        G1.remove_edge(2, 4)
        G1.add_edge(4, 2)
        G2.remove_edge("b", "d")
        G2.add_edge("d", "b")

        gparams = _GraphParameters(
            G1,
            G2,
            l1,
            l2,
            nx.utils.groups(l1),
            nx.utils.groups(l2),
            nx.utils.groups(
                {
                    node: (in_degree, out_degree)
                    for (node, in_degree), (_, out_degree) in zip(
                        G2.in_degree(), G2.out_degree()
                    )
                }
            ),
        )

        candidates = _find_candidates_Di(u, gparams, sparams, G1_degree)
        assert candidates == {self.mapped[u]}

    def test_same_in_out_degrees_no_candidate(self):
        g1 = nx.DiGraph([(4, 1), (4, 2), (3, 4), (5, 4), (6, 4)])
        g2 = nx.DiGraph([(1, 4), (2, 4), (3, 4), (4, 5), (4, 6)])

        l1 = dict(g1.nodes(data=None, default=-1))
        l2 = dict(g2.nodes(data=None, default=-1))
        gparams = _GraphParameters(
            g1,
            g2,
            l1,
            l2,
            nx.utils.groups(l1),
            nx.utils.groups(l2),
            nx.utils.groups(
                {
                    node: (in_degree, out_degree)
                    for (node, in_degree), (_, out_degree) in zip(
                        g2.in_degree(), g2.out_degree()
                    )
                }
            ),
        )

        g1_degree = {
            n: (in_degree, out_degree)
            for (n, in_degree), (_, out_degree) in zip(g1.in_degree, g1.out_degree)
        }

        m = {1: 1, 2: 2, 3: 3}
        m_rev = m.copy()

        T1_out = {4}
        T1_in = {4}
        T1_tilde = {5, 6}
        T2_out = {4}
        T2_in = {4}
        T2_tilde = {5, 6}

        sparams = _StateParameters(
            m, m_rev, T1_out, T1_in, T1_tilde, None, T2_out, T2_in, T2_tilde, None
        )

        u = 4
        # despite the same in and out degree, there's no candidate for u=4
        candidates = _find_candidates_Di(u, gparams, sparams, g1_degree)
        assert candidates == set()
        # Notice how the regular candidate selection method returns wrong result.
        assert _find_candidates(u, gparams, sparams, g1_degree) == {4}


class TestGraphISOFeasibility:
    def test_const_covered_neighbors(self):
        G1 = nx.Graph([(0, 1), (1, 2), (3, 0), (3, 2)])
        G2 = nx.Graph([("a", "b"), ("b", "c"), ("k", "a"), ("k", "c")])
        gparams = _GraphParameters(G1, G2, None, None, None, None, None)
        sparams = _StateParameters(
            {0: "a", 1: "b", 2: "c"},
            {"a": 0, "b": 1, "c": 2},
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        )
        u, v = 3, "k"
        assert _consistent_PT(u, v, gparams, sparams)

    def test_const_no_covered_neighbors(self):
        G1 = nx.Graph([(0, 1), (1, 2), (3, 4), (3, 5)])
        G2 = nx.Graph([("a", "b"), ("b", "c"), ("k", "w"), ("k", "z")])
        gparams = _GraphParameters(G1, G2, None, None, None, None, None)
        sparams = _StateParameters(
            {0: "a", 1: "b", 2: "c"},
            {"a": 0, "b": 1, "c": 2},
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        )
        u, v = 3, "k"
        assert _consistent_PT(u, v, gparams, sparams)

    def test_const_mixed_covered_uncovered_neighbors(self):
        G1 = nx.Graph([(0, 1), (1, 2), (3, 0), (3, 2), (3, 4), (3, 5)])
        G2 = nx.Graph(
            [("a", "b"), ("b", "c"), ("k", "a"), ("k", "c"), ("k", "w"), ("k", "z")]
        )
        gparams = _GraphParameters(G1, G2, None, None, None, None, None)
        sparams = _StateParameters(
            {0: "a", 1: "b", 2: "c"},
            {"a": 0, "b": 1, "c": 2},
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        )
        u, v = 3, "k"
        assert _consistent_PT(u, v, gparams, sparams)

    def test_const_fail_cases(self):
        G1 = nx.Graph(
            [
                (0, 1),
                (1, 2),
                (10, 0),
                (10, 3),
                (10, 4),
                (10, 5),
                (10, 6),
                (4, 1),
                (5, 3),
            ]
        )
        G2 = nx.Graph(
            [
                ("a", "b"),
                ("b", "c"),
                ("k", "a"),
                ("k", "d"),
                ("k", "e"),
                ("k", "f"),
                ("k", "g"),
                ("e", "b"),
                ("f", "d"),
            ]
        )
        gparams = _GraphParameters(G1, G2, None, None, None, None, None)
        sparams = _StateParameters(
            {0: "a", 1: "b", 2: "c", 3: "d"},
            {"a": 0, "b": 1, "c": 2, "d": 3},
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        )
        u, v = 10, "k"
        assert _consistent_PT(u, v, gparams, sparams)

        # Delete one uncovered neighbor of u. Notice how it still passes the test.
        # Two reasons for this:
        #   1. If u, v had different degrees from the beginning, they wouldn't
        #      be selected as candidates in the first place.
        #   2. Even if they are selected, consistency is basically 1-look-ahead,
        #      meaning that we take into consideration the relation of the
        #      candidates with their mapped neighbors. The node we deleted is
        #      not a covered neighbor.
        #      Such nodes will be checked by the cut_PT function, which is
        #      basically the 2-look-ahead, checking the relation of the
        #      candidates with T1, T2 (in which belongs the node we just deleted).
        G1.remove_node(6)
        assert _consistent_PT(u, v, gparams, sparams)

        # Add one more covered neighbor of u in G1
        G1.add_edge(u, 2)
        assert not _consistent_PT(u, v, gparams, sparams)

        # Compensate in G2
        G2.add_edge(v, "c")
        assert _consistent_PT(u, v, gparams, sparams)

        # Add one more covered neighbor of v in G2
        G2.add_edge(v, "x")
        G1.add_node(7)
        sparams.mapping.update({7: "x"})
        sparams.reverse_mapping.update({"x": 7})
        assert not _consistent_PT(u, v, gparams, sparams)

        # Compendate in G1
        G1.add_edge(u, 7)
        assert _consistent_PT(u, v, gparams, sparams)

    @pytest.mark.parametrize("graph_type", (nx.Graph, nx.DiGraph))
    def test_cut_inconsistent_labels(self, graph_type):
        G1 = graph_type(
            [
                (0, 1),
                (1, 2),
                (10, 0),
                (10, 3),
                (10, 4),
                (10, 5),
                (10, 6),
                (4, 1),
                (5, 3),
            ]
        )
        G2 = graph_type(
            [
                ("a", "b"),
                ("b", "c"),
                ("k", "a"),
                ("k", "d"),
                ("k", "e"),
                ("k", "f"),
                ("k", "g"),
                ("e", "b"),
                ("f", "d"),
            ]
        )

        l1 = {n: "blue" for n in G1.nodes()}
        l2 = {n: "blue" for n in G2.nodes()}
        l1.update({6: "green"})  # Change the label of one neighbor of u

        gparams = _GraphParameters(
            G1, G2, l1, l2, nx.utils.groups(l1), nx.utils.groups(l2), None
        )
        sparams = _StateParameters(
            {0: "a", 1: "b", 2: "c", 3: "d"},
            {"a": 0, "b": 1, "c": 2, "d": 3},
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        )

        u, v = 10, "k"
        assert _cut_PT(u, v, gparams, sparams)

    def test_cut_consistent_labels(self):
        G1 = nx.Graph(
            [
                (0, 1),
                (1, 2),
                (10, 0),
                (10, 3),
                (10, 4),
                (10, 5),
                (10, 6),
                (4, 1),
                (5, 3),
            ]
        )
        G2 = nx.Graph(
            [
                ("a", "b"),
                ("b", "c"),
                ("k", "a"),
                ("k", "d"),
                ("k", "e"),
                ("k", "f"),
                ("k", "g"),
                ("e", "b"),
                ("f", "d"),
            ]
        )

        l1 = {n: "blue" for n in G1.nodes()}
        l2 = {n: "blue" for n in G2.nodes()}

        gparams = _GraphParameters(
            G1, G2, l1, l2, nx.utils.groups(l1), nx.utils.groups(l2), None
        )
        sparams = _StateParameters(
            {0: "a", 1: "b", 2: "c", 3: "d"},
            {"a": 0, "b": 1, "c": 2, "d": 3},
            {4, 5},
            None,
            {6},
            None,
            {"e", "f"},
            None,
            {"g"},
            None,
        )

        u, v = 10, "k"
        assert not _cut_PT(u, v, gparams, sparams)

    def test_cut_same_labels(self):
        G1 = nx.Graph(
            [
                (0, 1),
                (1, 2),
                (10, 0),
                (10, 3),
                (10, 4),
                (10, 5),
                (10, 6),
                (4, 1),
                (5, 3),
            ]
        )
        mapped = {0: "a", 1: "b", 2: "c", 3: "d", 4: "e", 5: "f", 6: "g", 10: "k"}
        G2 = nx.relabel_nodes(G1, mapped)
        l1 = {n: "blue" for n in G1.nodes()}
        l2 = {n: "blue" for n in G2.nodes()}

        gparams = _GraphParameters(
            G1, G2, l1, l2, nx.utils.groups(l1), nx.utils.groups(l2), None
        )
        sparams = _StateParameters(
            {0: "a", 1: "b", 2: "c", 3: "d"},
            {"a": 0, "b": 1, "c": 2, "d": 3},
            {4, 5},
            None,
            {6},
            None,
            {"e", "f"},
            None,
            {"g"},
            None,
        )

        u, v = 10, "k"
        assert not _cut_PT(u, v, gparams, sparams)

        # Change intersection between G1[u] and T1, so it's not the same as the one between G2[v] and T2
        G1.remove_edge(u, 4)
        assert _cut_PT(u, v, gparams, sparams)

        # Compensate in G2
        G2.remove_edge(v, mapped[4])
        assert not _cut_PT(u, v, gparams, sparams)

        # Change intersection between G2[v] and T2_tilde, so it's not the same as the one between G1[u] and T1_tilde
        G2.remove_edge(v, mapped[6])
        assert _cut_PT(u, v, gparams, sparams)

        # Compensate in G1
        G1.remove_edge(u, 6)
        assert not _cut_PT(u, v, gparams, sparams)

        # Add disconnected nodes, which will form the new Ti_out
        G1.add_nodes_from([6, 7, 8])
        G2.add_nodes_from(["g", "y", "z"])
        sparams.T1_tilde.update({6, 7, 8})
        sparams.T2_tilde.update({"g", "y", "z"})

        l1 = {n: "blue" for n in G1.nodes()}
        l2 = {n: "blue" for n in G2.nodes()}
        gparams = _GraphParameters(
            G1, G2, l1, l2, nx.utils.groups(l1), nx.utils.groups(l2), None
        )

        assert not _cut_PT(u, v, gparams, sparams)

        # Add some new nodes to the mapping
        sparams.mapping.update({6: "g", 7: "y"})
        sparams.reverse_mapping.update({"g": 6, "y": 7})

        # Add more nodes to T1, T2.
        G1.add_edges_from([(6, 20), (7, 20), (6, 21)])
        G2.add_edges_from([("g", "i"), ("g", "j"), ("y", "j")])

        sparams.mapping.update({20: "j", 21: "i"})
        sparams.reverse_mapping.update({"j": 20, "i": 21})
        sparams.T1.update({20, 21})
        sparams.T2.update({"i", "j"})
        sparams.T1_tilde.difference_update({6, 7})
        sparams.T2_tilde.difference_update({"g", "y"})

        assert not _cut_PT(u, v, gparams, sparams)

        # Add nodes from the new T1 and T2, as neighbors of u and v respectively
        G1.add_edges_from([(u, 20), (u, 21)])
        G2.add_edges_from([(v, "i"), (v, "j")])
        l1 = {n: "blue" for n in G1.nodes()}
        l2 = {n: "blue" for n in G2.nodes()}
        gparams = _GraphParameters(
            G1, G2, l1, l2, nx.utils.groups(l1), nx.utils.groups(l2), None
        )

        assert not _cut_PT(u, v, gparams, sparams)

        # Change the edges, maintaining the G1[u]-T1 intersection
        G1.remove_edge(u, 20)
        G1.add_edge(u, 4)
        assert not _cut_PT(u, v, gparams, sparams)

        # Connect u to 8 which is still in T1_tilde
        G1.add_edge(u, 8)
        assert _cut_PT(u, v, gparams, sparams)

        # Same for v and z, so that inters(G1[u], T1out) == inters(G2[v], T2out)
        G2.add_edge(v, "z")
        assert not _cut_PT(u, v, gparams, sparams)

    def test_cut_different_labels(self):
        G1 = nx.Graph(
            [
                (0, 1),
                (1, 2),
                (1, 14),
                (0, 4),
                (1, 5),
                (2, 6),
                (3, 7),
                (3, 6),
                (4, 10),
                (4, 9),
                (6, 10),
                (20, 9),
                (20, 15),
                (20, 12),
                (20, 11),
                (12, 13),
                (11, 13),
                (20, 8),
                (20, 3),
                (20, 5),
                (20, 0),
            ]
        )
        mapped = {
            0: "a",
            1: "b",
            2: "c",
            3: "d",
            4: "e",
            5: "f",
            6: "g",
            7: "h",
            8: "i",
            9: "j",
            10: "k",
            11: "l",
            12: "m",
            13: "n",
            14: "o",
            15: "p",
            20: "x",
        }
        G2 = nx.relabel_nodes(G1, mapped)

        l1 = {n: "none" for n in G1.nodes()}
        l2 = {}

        l1.update(
            {
                9: "blue",
                15: "blue",
                12: "blue",
                11: "green",
                3: "green",
                8: "red",
                0: "red",
                5: "yellow",
            }
        )
        l2.update({mapped[n]: l for n, l in l1.items()})

        gparams = _GraphParameters(
            G1, G2, l1, l2, nx.utils.groups(l1), nx.utils.groups(l2), None
        )
        sparams = _StateParameters(
            {0: "a", 1: "b", 2: "c", 3: "d"},
            {"a": 0, "b": 1, "c": 2, "d": 3},
            {4, 5, 6, 7, 14},
            None,
            {9, 10, 15, 12, 11, 13, 8},
            None,
            {"e", "f", "g", "h", "o"},
            None,
            {"j", "k", "l", "m", "n", "i", "p"},
            None,
        )

        u, v = 20, "x"
        assert not _cut_PT(u, v, gparams, sparams)

        # Change the orientation of the labels on neighbors of u compared to neighbors of v. Leave the structure intact
        l1.update({9: "red"})
        assert _cut_PT(u, v, gparams, sparams)

        # compensate in G2
        l2.update({mapped[9]: "red"})
        assert not _cut_PT(u, v, gparams, sparams)

        # Change the intersection of G1[u] and T1
        G1.add_edge(u, 4)
        assert _cut_PT(u, v, gparams, sparams)

        # Same for G2[v] and T2
        G2.add_edge(v, mapped[4])
        assert not _cut_PT(u, v, gparams, sparams)

        # Change the intersection of G2[v] and T2_tilde
        G2.remove_edge(v, mapped[8])
        assert _cut_PT(u, v, gparams, sparams)

        # Same for G1[u] and T1_tilde
        G1.remove_edge(u, 8)
        assert not _cut_PT(u, v, gparams, sparams)

        # Place 8 and mapped[8] in T1 and T2 respectively, by connecting it to covered nodes
        G1.add_edge(8, 3)
        G2.add_edge(mapped[8], mapped[3])
        sparams.T1.add(8)
        sparams.T2.add(mapped[8])
        sparams.T1_tilde.remove(8)
        sparams.T2_tilde.remove(mapped[8])

        assert not _cut_PT(u, v, gparams, sparams)

        # Remove neighbor of u from T1
        G1.remove_node(5)
        l1.pop(5)
        sparams.T1.remove(5)
        assert _cut_PT(u, v, gparams, sparams)

        # Same in G2
        G2.remove_node(mapped[5])
        l2.pop(mapped[5])
        sparams.T2.remove(mapped[5])
        assert not _cut_PT(u, v, gparams, sparams)

    def test_feasibility_same_labels(self):
        G1 = nx.Graph(
            [
                (0, 1),
                (1, 2),
                (1, 14),
                (0, 4),
                (1, 5),
                (2, 6),
                (3, 7),
                (3, 6),
                (4, 10),
                (4, 9),
                (6, 10),
                (20, 9),
                (20, 15),
                (20, 12),
                (20, 11),
                (12, 13),
                (11, 13),
                (20, 8),
                (20, 2),
                (20, 5),
                (20, 0),
            ]
        )
        mapped = {
            0: "a",
            1: "b",
            2: "c",
            3: "d",
            4: "e",
            5: "f",
            6: "g",
            7: "h",
            8: "i",
            9: "j",
            10: "k",
            11: "l",
            12: "m",
            13: "n",
            14: "o",
            15: "p",
            20: "x",
        }
        G2 = nx.relabel_nodes(G1, mapped)

        l1 = {n: "blue" for n in G1.nodes()}
        l2 = {mapped[n]: "blue" for n in G1.nodes()}

        gparams = _GraphParameters(
            G1, G2, l1, l2, nx.utils.groups(l1), nx.utils.groups(l2), None
        )
        sparams = _StateParameters(
            {0: "a", 1: "b", 2: "c", 3: "d"},
            {"a": 0, "b": 1, "c": 2, "d": 3},
            {4, 5, 6, 7, 14},
            None,
            {9, 10, 15, 12, 11, 13, 8},
            None,
            {"e", "f", "g", "h", "o"},
            None,
            {"j", "k", "l", "m", "n", "i", "p"},
            None,
        )

        u, v = 20, "x"
        assert not _cut_PT(u, v, gparams, sparams)

        # Change structure in G2 such that, ONLY consistency is harmed
        G2.remove_edge(mapped[20], mapped[2])
        G2.add_edge(mapped[20], mapped[3])

        # Consistency check fails, while the cutting rules are satisfied!
        assert not _cut_PT(u, v, gparams, sparams)
        assert not _consistent_PT(u, v, gparams, sparams)

        # Compensate in G1 and make it consistent
        G1.remove_edge(20, 2)
        G1.add_edge(20, 3)
        assert not _cut_PT(u, v, gparams, sparams)
        assert _consistent_PT(u, v, gparams, sparams)

        # ONLY fail the cutting check
        G2.add_edge(v, mapped[10])
        assert _cut_PT(u, v, gparams, sparams)
        assert _consistent_PT(u, v, gparams, sparams)

    def test_feasibility_different_labels(self):
        G1 = nx.Graph(
            [
                (0, 1),
                (1, 2),
                (1, 14),
                (0, 4),
                (1, 5),
                (2, 6),
                (3, 7),
                (3, 6),
                (4, 10),
                (4, 9),
                (6, 10),
                (20, 9),
                (20, 15),
                (20, 12),
                (20, 11),
                (12, 13),
                (11, 13),
                (20, 8),
                (20, 2),
                (20, 5),
                (20, 0),
            ]
        )
        mapped = {
            0: "a",
            1: "b",
            2: "c",
            3: "d",
            4: "e",
            5: "f",
            6: "g",
            7: "h",
            8: "i",
            9: "j",
            10: "k",
            11: "l",
            12: "m",
            13: "n",
            14: "o",
            15: "p",
            20: "x",
        }
        G2 = nx.relabel_nodes(G1, mapped)

        l1 = {n: "none" for n in G1.nodes()}
        l2 = {}

        l1.update(
            {
                9: "blue",
                15: "blue",
                12: "blue",
                11: "green",
                2: "green",
                8: "red",
                0: "red",
                5: "yellow",
            }
        )
        l2.update({mapped[n]: l for n, l in l1.items()})

        gparams = _GraphParameters(
            G1, G2, l1, l2, nx.utils.groups(l1), nx.utils.groups(l2), None
        )
        sparams = _StateParameters(
            {0: "a", 1: "b", 2: "c", 3: "d"},
            {"a": 0, "b": 1, "c": 2, "d": 3},
            {4, 5, 6, 7, 14},
            None,
            {9, 10, 15, 12, 11, 13, 8},
            None,
            {"e", "f", "g", "h", "o"},
            None,
            {"j", "k", "l", "m", "n", "i", "p"},
            None,
        )

        u, v = 20, "x"
        assert not _cut_PT(u, v, gparams, sparams)

        # Change structure in G2 such that, ONLY consistency is harmed
        G2.remove_edge(mapped[20], mapped[2])
        G2.add_edge(mapped[20], mapped[3])
        l2.update({mapped[3]: "green"})

        # Consistency check fails, while the cutting rules are satisfied!
        assert not _cut_PT(u, v, gparams, sparams)
        assert not _consistent_PT(u, v, gparams, sparams)

        # Compensate in G1 and make it consistent
        G1.remove_edge(20, 2)
        G1.add_edge(20, 3)
        l1.update({3: "green"})
        assert not _cut_PT(u, v, gparams, sparams)
        assert _consistent_PT(u, v, gparams, sparams)

        # ONLY fail the cutting check
        l1.update({5: "red"})
        assert _cut_PT(u, v, gparams, sparams)
        assert _consistent_PT(u, v, gparams, sparams)


class TestMultiGraphISOFeasibility:
    def test_const_covered_neighbors(self):
        G1 = nx.MultiGraph(
            [(0, 1), (0, 1), (1, 2), (3, 0), (3, 0), (3, 0), (3, 2), (3, 2)]
        )
        G2 = nx.MultiGraph(
            [
                ("a", "b"),
                ("a", "b"),
                ("b", "c"),
                ("k", "a"),
                ("k", "a"),
                ("k", "a"),
                ("k", "c"),
                ("k", "c"),
            ]
        )
        gparams = _GraphParameters(G1, G2, None, None, None, None, None)
        sparams = _StateParameters(
            {0: "a", 1: "b", 2: "c"},
            {"a": 0, "b": 1, "c": 2},
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        )
        u, v = 3, "k"
        assert _consistent_PT(u, v, gparams, sparams)

    def test_const_no_covered_neighbors(self):
        G1 = nx.MultiGraph([(0, 1), (0, 1), (1, 2), (3, 4), (3, 4), (3, 5)])
        G2 = nx.MultiGraph([("a", "b"), ("b", "c"), ("k", "w"), ("k", "w"), ("k", "z")])
        gparams = _GraphParameters(G1, G2, None, None, None, None, None)
        sparams = _StateParameters(
            {0: "a", 1: "b", 2: "c"},
            {"a": 0, "b": 1, "c": 2},
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        )
        u, v = 3, "k"
        assert _consistent_PT(u, v, gparams, sparams)

    def test_const_mixed_covered_uncovered_neighbors(self):
        G1 = nx.MultiGraph(
            [(0, 1), (1, 2), (3, 0), (3, 0), (3, 0), (3, 2), (3, 2), (3, 4), (3, 5)]
        )
        G2 = nx.MultiGraph(
            [
                ("a", "b"),
                ("b", "c"),
                ("k", "a"),
                ("k", "a"),
                ("k", "a"),
                ("k", "c"),
                ("k", "c"),
                ("k", "w"),
                ("k", "z"),
            ]
        )
        gparams = _GraphParameters(G1, G2, None, None, None, None, None)
        sparams = _StateParameters(
            {0: "a", 1: "b", 2: "c"},
            {"a": 0, "b": 1, "c": 2},
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        )
        u, v = 3, "k"
        assert _consistent_PT(u, v, gparams, sparams)

    def test_const_fail_cases(self):
        G1 = nx.MultiGraph(
            [
                (0, 1),
                (1, 2),
                (10, 0),
                (10, 0),
                (10, 0),
                (10, 3),
                (10, 3),
                (10, 4),
                (10, 5),
                (10, 6),
                (10, 6),
                (4, 1),
                (5, 3),
            ]
        )
        mapped = {0: "a", 1: "b", 2: "c", 3: "d", 4: "e", 5: "f", 6: "g", 10: "k"}
        G2 = nx.relabel_nodes(G1, mapped)

        gparams = _GraphParameters(G1, G2, None, None, None, None, None)
        sparams = _StateParameters(
            {0: "a", 1: "b", 2: "c", 3: "d"},
            {"a": 0, "b": 1, "c": 2, "d": 3},
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        )
        u, v = 10, "k"
        assert _consistent_PT(u, v, gparams, sparams)

        # Delete one uncovered neighbor of u. Notice how it still passes the test. Two reasons for this:
        # 1. If u, v had different degrees from the beginning, they wouldn't be selected as candidates in the first
        #    place.
        # 2. Even if they are selected, consistency is basically 1-look-ahead, meaning that we take into consideration
        #    the relation of the candidates with their mapped neighbors. The node we deleted is not a covered neighbor.
        #    Such nodes will be checked by the cut_PT function, which is basically the 2-look-ahead, checking the
        #    relation of the candidates with T1, T2 (in which belongs the node we just deleted).
        G1.remove_node(6)
        assert _consistent_PT(u, v, gparams, sparams)

        # Add one more covered neighbor of u in G1
        G1.add_edge(u, 2)
        assert not _consistent_PT(u, v, gparams, sparams)

        # Compensate in G2
        G2.add_edge(v, "c")
        assert _consistent_PT(u, v, gparams, sparams)

        # Add one more covered neighbor of v in G2
        G2.add_edge(v, "x")
        G1.add_node(7)
        sparams.mapping.update({7: "x"})
        sparams.reverse_mapping.update({"x": 7})
        assert not _consistent_PT(u, v, gparams, sparams)

        # Compendate in G1
        G1.add_edge(u, 7)
        assert _consistent_PT(u, v, gparams, sparams)

        # Delete an edge between u and a covered neighbor
        G1.remove_edges_from([(u, 0), (u, 0)])
        assert not _consistent_PT(u, v, gparams, sparams)

        # Compensate in G2
        G2.remove_edges_from([(v, mapped[0]), (v, mapped[0])])
        assert _consistent_PT(u, v, gparams, sparams)

        # Remove an edge between v and a covered neighbor
        G2.remove_edge(v, mapped[3])
        assert not _consistent_PT(u, v, gparams, sparams)

        # Compensate in G1
        G1.remove_edge(u, 3)
        assert _consistent_PT(u, v, gparams, sparams)

    def test_cut_same_labels(self):
        G1 = nx.MultiGraph(
            [
                (0, 1),
                (1, 2),
                (10, 0),
                (10, 0),
                (10, 0),
                (10, 3),
                (10, 3),
                (10, 4),
                (10, 4),
                (10, 5),
                (10, 5),
                (10, 5),
                (10, 5),
                (10, 6),
                (10, 6),
                (4, 1),
                (5, 3),
            ]
        )
        mapped = {0: "a", 1: "b", 2: "c", 3: "d", 4: "e", 5: "f", 6: "g", 10: "k"}
        G2 = nx.relabel_nodes(G1, mapped)
        l1 = {n: "blue" for n in G1.nodes()}
        l2 = {n: "blue" for n in G2.nodes()}

        gparams = _GraphParameters(
            G1, G2, l1, l2, nx.utils.groups(l1), nx.utils.groups(l2), None
        )
        sparams = _StateParameters(
            {0: "a", 1: "b", 2: "c", 3: "d"},
            {"a": 0, "b": 1, "c": 2, "d": 3},
            {4, 5},
            None,
            {6},
            None,
            {"e", "f"},
            None,
            {"g"},
            None,
        )

        u, v = 10, "k"
        assert not _cut_PT(u, v, gparams, sparams)

        # Remove one of the multiple edges between u and a neighbor
        G1.remove_edge(u, 4)
        assert _cut_PT(u, v, gparams, sparams)

        # Compensate in G2
        G1.remove_edge(u, 4)
        G2.remove_edges_from([(v, mapped[4]), (v, mapped[4])])
        assert not _cut_PT(u, v, gparams, sparams)

        # Change intersection between G2[v] and T2_tilde, so it's not the same as the one between G1[u] and T1_tilde
        G2.remove_edge(v, mapped[6])
        assert _cut_PT(u, v, gparams, sparams)

        # Compensate in G1
        G1.remove_edge(u, 6)
        assert not _cut_PT(u, v, gparams, sparams)

        # Add more edges between u and neighbor which belongs in T1_tilde
        G1.add_edges_from([(u, 5), (u, 5), (u, 5)])
        assert _cut_PT(u, v, gparams, sparams)

        # Compensate in G2
        G2.add_edges_from([(v, mapped[5]), (v, mapped[5]), (v, mapped[5])])
        assert not _cut_PT(u, v, gparams, sparams)

        # Add disconnected nodes, which will form the new Ti_out
        G1.add_nodes_from([6, 7, 8])
        G2.add_nodes_from(["g", "y", "z"])
        G1.add_edges_from([(u, 6), (u, 6), (u, 6), (u, 8)])
        G2.add_edges_from([(v, "g"), (v, "g"), (v, "g"), (v, "z")])

        sparams.T1_tilde.update({6, 7, 8})
        sparams.T2_tilde.update({"g", "y", "z"})

        l1 = {n: "blue" for n in G1.nodes()}
        l2 = {n: "blue" for n in G2.nodes()}
        gparams = _GraphParameters(
            G1, G2, l1, l2, nx.utils.groups(l1), nx.utils.groups(l2), None
        )

        assert not _cut_PT(u, v, gparams, sparams)

        # Add some new nodes to the mapping
        sparams.mapping.update({6: "g", 7: "y"})
        sparams.reverse_mapping.update({"g": 6, "y": 7})

        # Add more nodes to T1, T2.
        G1.add_edges_from([(6, 20), (7, 20), (6, 21)])
        G2.add_edges_from([("g", "i"), ("g", "j"), ("y", "j")])

        sparams.T1.update({20, 21})
        sparams.T2.update({"i", "j"})
        sparams.T1_tilde.difference_update({6, 7})
        sparams.T2_tilde.difference_update({"g", "y"})

        assert not _cut_PT(u, v, gparams, sparams)

        # Remove some edges
        G2.remove_edge(v, "g")
        assert _cut_PT(u, v, gparams, sparams)

        G1.remove_edge(u, 6)
        G1.add_edge(u, 8)
        G2.add_edge(v, "z")
        assert not _cut_PT(u, v, gparams, sparams)

        # Add nodes from the new T1 and T2, as neighbors of u and v respectively
        G1.add_edges_from([(u, 20), (u, 20), (u, 20), (u, 21)])
        G2.add_edges_from([(v, "i"), (v, "i"), (v, "i"), (v, "j")])
        l1 = {n: "blue" for n in G1.nodes()}
        l2 = {n: "blue" for n in G2.nodes()}
        gparams = _GraphParameters(
            G1, G2, l1, l2, nx.utils.groups(l1), nx.utils.groups(l2), None
        )

        assert not _cut_PT(u, v, gparams, sparams)

        # Change the edges
        G1.remove_edge(u, 20)
        G1.add_edge(u, 4)
        assert _cut_PT(u, v, gparams, sparams)

        G2.remove_edge(v, "i")
        G2.add_edge(v, mapped[4])
        assert not _cut_PT(u, v, gparams, sparams)

    def test_cut_different_labels(self):
        G1 = nx.MultiGraph(
            [
                (0, 1),
                (0, 1),
                (1, 2),
                (1, 2),
                (1, 14),
                (0, 4),
                (1, 5),
                (2, 6),
                (3, 7),
                (3, 6),
                (4, 10),
                (4, 9),
                (6, 10),
                (20, 9),
                (20, 9),
                (20, 9),
                (20, 15),
                (20, 15),
                (20, 12),
                (20, 11),
                (20, 11),
                (20, 11),
                (12, 13),
                (11, 13),
                (20, 8),
                (20, 8),
                (20, 3),
                (20, 3),
                (20, 5),
                (20, 5),
                (20, 5),
                (20, 0),
                (20, 0),
                (20, 0),
            ]
        )
        mapped = {
            0: "a",
            1: "b",
            2: "c",
            3: "d",
            4: "e",
            5: "f",
            6: "g",
            7: "h",
            8: "i",
            9: "j",
            10: "k",
            11: "l",
            12: "m",
            13: "n",
            14: "o",
            15: "p",
            20: "x",
        }
        G2 = nx.relabel_nodes(G1, mapped)

        l1 = {n: "none" for n in G1.nodes()}
        l2 = {}

        l1.update(
            {
                9: "blue",
                15: "blue",
                12: "blue",
                11: "green",
                3: "green",
                8: "red",
                0: "red",
                5: "yellow",
            }
        )
        l2.update({mapped[n]: l for n, l in l1.items()})

        gparams = _GraphParameters(
            G1, G2, l1, l2, nx.utils.groups(l1), nx.utils.groups(l2), None
        )
        sparams = _StateParameters(
            {0: "a", 1: "b", 2: "c", 3: "d"},
            {"a": 0, "b": 1, "c": 2, "d": 3},
            {4, 5, 6, 7, 14},
            None,
            {9, 10, 15, 12, 11, 13, 8},
            None,
            {"e", "f", "g", "h", "o"},
            None,
            {"j", "k", "l", "m", "n", "i", "p"},
            None,
        )

        u, v = 20, "x"
        assert not _cut_PT(u, v, gparams, sparams)

        # Change the orientation of the labels on neighbors of u compared to neighbors of v. Leave the structure intact
        l1.update({9: "red"})
        assert _cut_PT(u, v, gparams, sparams)

        # compensate in G2
        l2.update({mapped[9]: "red"})
        assert not _cut_PT(u, v, gparams, sparams)

        # Change the intersection of G1[u] and T1
        G1.add_edge(u, 4)
        assert _cut_PT(u, v, gparams, sparams)

        # Same for G2[v] and T2
        G2.add_edge(v, mapped[4])
        assert not _cut_PT(u, v, gparams, sparams)

        # Delete one from the multiple edges
        G2.remove_edge(v, mapped[8])
        assert _cut_PT(u, v, gparams, sparams)

        # Same for G1[u] and T1_tilde
        G1.remove_edge(u, 8)
        assert not _cut_PT(u, v, gparams, sparams)

        # Place 8 and mapped[8] in T1 and T2 respectively, by connecting it to covered nodes
        G1.add_edges_from([(8, 3), (8, 3), (8, u)])
        G2.add_edges_from([(mapped[8], mapped[3]), (mapped[8], mapped[3])])
        sparams.T1.add(8)
        sparams.T2.add(mapped[8])
        sparams.T1_tilde.remove(8)
        sparams.T2_tilde.remove(mapped[8])

        assert _cut_PT(u, v, gparams, sparams)

        # Fix uneven edges
        G1.remove_edge(8, u)
        assert not _cut_PT(u, v, gparams, sparams)

        # Remove neighbor of u from T1
        G1.remove_node(5)
        l1.pop(5)
        sparams.T1.remove(5)
        assert _cut_PT(u, v, gparams, sparams)

        # Same in G2
        G2.remove_node(mapped[5])
        l2.pop(mapped[5])
        sparams.T2.remove(mapped[5])
        assert not _cut_PT(u, v, gparams, sparams)

    def test_feasibility_same_labels(self):
        G1 = nx.MultiGraph(
            [
                (0, 1),
                (0, 1),
                (1, 2),
                (1, 2),
                (1, 14),
                (0, 4),
                (1, 5),
                (2, 6),
                (3, 7),
                (3, 6),
                (4, 10),
                (4, 9),
                (6, 10),
                (20, 9),
                (20, 9),
                (20, 9),
                (20, 15),
                (20, 15),
                (20, 12),
                (20, 11),
                (20, 11),
                (20, 11),
                (12, 13),
                (11, 13),
                (20, 8),
                (20, 8),
                (20, 3),
                (20, 3),
                (20, 5),
                (20, 5),
                (20, 5),
                (20, 0),
                (20, 0),
                (20, 0),
            ]
        )
        mapped = {
            0: "a",
            1: "b",
            2: "c",
            3: "d",
            4: "e",
            5: "f",
            6: "g",
            7: "h",
            8: "i",
            9: "j",
            10: "k",
            11: "l",
            12: "m",
            13: "n",
            14: "o",
            15: "p",
            20: "x",
        }
        G2 = nx.relabel_nodes(G1, mapped)
        l1 = {n: "blue" for n in G1.nodes()}
        l2 = {mapped[n]: "blue" for n in G1.nodes()}

        gparams = _GraphParameters(
            G1, G2, l1, l2, nx.utils.groups(l1), nx.utils.groups(l2), None
        )
        sparams = _StateParameters(
            {0: "a", 1: "b", 2: "c", 3: "d"},
            {"a": 0, "b": 1, "c": 2, "d": 3},
            {4, 5, 6, 7, 14},
            None,
            {9, 10, 15, 12, 11, 13, 8},
            None,
            {"e", "f", "g", "h", "o"},
            None,
            {"j", "k", "l", "m", "n", "i", "p"},
            None,
        )

        u, v = 20, "x"
        assert not _cut_PT(u, v, gparams, sparams)

        # Change structure in G2 such that, ONLY consistency is harmed
        G2.remove_edges_from([(mapped[20], mapped[3]), (mapped[20], mapped[3])])
        G2.add_edges_from([(mapped[20], mapped[2]), (mapped[20], mapped[2])])

        # Consistency check fails, while the cutting rules are satisfied!
        assert not _cut_PT(u, v, gparams, sparams)
        assert not _consistent_PT(u, v, gparams, sparams)

        # Compensate in G1 and make it consistent
        G1.remove_edges_from([(20, 3), (20, 3)])
        G1.add_edges_from([(20, 2), (20, 2)])
        assert not _cut_PT(u, v, gparams, sparams)
        assert _consistent_PT(u, v, gparams, sparams)

        # ONLY fail the cutting check
        G2.add_edges_from([(v, mapped[10])] * 5)
        assert _cut_PT(u, v, gparams, sparams)
        assert _consistent_PT(u, v, gparams, sparams)

        # Pass all tests
        G1.add_edges_from([(u, 10)] * 5)
        assert not _cut_PT(u, v, gparams, sparams)
        assert _consistent_PT(u, v, gparams, sparams)

    def test_feasibility_different_labels(self):
        G1 = nx.MultiGraph(
            [
                (0, 1),
                (0, 1),
                (1, 2),
                (1, 2),
                (1, 14),
                (0, 4),
                (1, 5),
                (2, 6),
                (3, 7),
                (3, 6),
                (4, 10),
                (4, 9),
                (6, 10),
                (20, 9),
                (20, 9),
                (20, 9),
                (20, 15),
                (20, 15),
                (20, 12),
                (20, 11),
                (20, 11),
                (20, 11),
                (12, 13),
                (11, 13),
                (20, 8),
                (20, 8),
                (20, 2),
                (20, 2),
                (20, 5),
                (20, 5),
                (20, 5),
                (20, 0),
                (20, 0),
                (20, 0),
            ]
        )
        mapped = {
            0: "a",
            1: "b",
            2: "c",
            3: "d",
            4: "e",
            5: "f",
            6: "g",
            7: "h",
            8: "i",
            9: "j",
            10: "k",
            11: "l",
            12: "m",
            13: "n",
            14: "o",
            15: "p",
            20: "x",
        }
        G2 = nx.relabel_nodes(G1, mapped)
        l1 = {n: "none" for n in G1.nodes()}
        l2 = {}

        l1.update(
            {
                9: "blue",
                15: "blue",
                12: "blue",
                11: "green",
                2: "green",
                8: "red",
                0: "red",
                5: "yellow",
            }
        )
        l2.update({mapped[n]: l for n, l in l1.items()})

        gparams = _GraphParameters(
            G1, G2, l1, l2, nx.utils.groups(l1), nx.utils.groups(l2), None
        )
        sparams = _StateParameters(
            {0: "a", 1: "b", 2: "c", 3: "d"},
            {"a": 0, "b": 1, "c": 2, "d": 3},
            {4, 5, 6, 7, 14},
            None,
            {9, 10, 15, 12, 11, 13, 8},
            None,
            {"e", "f", "g", "h", "o"},
            None,
            {"j", "k", "l", "m", "n", "i", "p"},
            None,
        )

        u, v = 20, "x"
        assert not _cut_PT(u, v, gparams, sparams)

        # Change structure in G2 such that, ONLY consistency is harmed
        G2.remove_edges_from([(mapped[20], mapped[2]), (mapped[20], mapped[2])])
        G2.add_edges_from([(mapped[20], mapped[3]), (mapped[20], mapped[3])])
        l2.update({mapped[3]: "green"})

        # Consistency check fails, while the cutting rules are satisfied!
        assert not _cut_PT(u, v, gparams, sparams)
        assert not _consistent_PT(u, v, gparams, sparams)

        # Compensate in G1 and make it consistent
        G1.remove_edges_from([(20, 2), (20, 2)])
        G1.add_edges_from([(20, 3), (20, 3)])
        l1.update({3: "green"})
        assert not _cut_PT(u, v, gparams, sparams)
        assert _consistent_PT(u, v, gparams, sparams)

        # ONLY fail the cutting check
        l1.update({5: "red"})
        assert _cut_PT(u, v, gparams, sparams)
        assert _consistent_PT(u, v, gparams, sparams)


class TestDiGraphISOFeasibility:
    def test_const_covered_neighbors(self):
        G1 = nx.DiGraph([(0, 1), (1, 2), (0, 3), (2, 3)])
        G2 = nx.DiGraph([("a", "b"), ("b", "c"), ("a", "k"), ("c", "k")])
        gparams = _GraphParameters(G1, G2, None, None, None, None, None)
        sparams = _StateParameters(
            {0: "a", 1: "b", 2: "c"},
            {"a": 0, "b": 1, "c": 2},
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        )
        u, v = 3, "k"
        assert _consistent_PT(u, v, gparams, sparams)

    def test_const_no_covered_neighbors(self):
        G1 = nx.DiGraph([(0, 1), (1, 2), (3, 4), (3, 5)])
        G2 = nx.DiGraph([("a", "b"), ("b", "c"), ("k", "w"), ("k", "z")])
        gparams = _GraphParameters(G1, G2, None, None, None, None, None)
        sparams = _StateParameters(
            {0: "a", 1: "b", 2: "c"},
            {"a": 0, "b": 1, "c": 2},
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        )
        u, v = 3, "k"
        assert _consistent_PT(u, v, gparams, sparams)

    def test_const_mixed_covered_uncovered_neighbors(self):
        G1 = nx.DiGraph([(0, 1), (1, 2), (3, 0), (3, 2), (3, 4), (3, 5)])
        G2 = nx.DiGraph(
            [("a", "b"), ("b", "c"), ("k", "a"), ("k", "c"), ("k", "w"), ("k", "z")]
        )
        gparams = _GraphParameters(G1, G2, None, None, None, None, None)
        sparams = _StateParameters(
            {0: "a", 1: "b", 2: "c"},
            {"a": 0, "b": 1, "c": 2},
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        )
        u, v = 3, "k"
        assert _consistent_PT(u, v, gparams, sparams)

    def test_const_fail_cases(self):
        G1 = nx.DiGraph(
            [
                (0, 1),
                (2, 1),
                (10, 0),
                (10, 3),
                (10, 4),
                (5, 10),
                (10, 6),
                (1, 4),
                (5, 3),
            ]
        )
        G2 = nx.DiGraph(
            [
                ("a", "b"),
                ("c", "b"),
                ("k", "a"),
                ("k", "d"),
                ("k", "e"),
                ("f", "k"),
                ("k", "g"),
                ("b", "e"),
                ("f", "d"),
            ]
        )
        gparams = _GraphParameters(G1, G2, None, None, None, None, None)
        sparams = _StateParameters(
            {0: "a", 1: "b", 2: "c", 3: "d"},
            {"a": 0, "b": 1, "c": 2, "d": 3},
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        )
        u, v = 10, "k"
        assert _consistent_PT(u, v, gparams, sparams)

        # Delete one uncovered neighbor of u. Notice how it still passes the
        # test. Two reasons for this:
        #   1. If u, v had different degrees from the beginning, they wouldn't
        #      be selected as candidates in the first place.
        #   2. Even if they are selected, consistency is basically
        #      1-look-ahead, meaning that we take into consideration the
        #      relation of the candidates with their mapped neighbors.
        #      The node we deleted is not a covered neighbor.
        #      Such nodes will be checked by the cut_PT function, which is
        #      basically the 2-look-ahead, checking the relation of the
        #      candidates with T1, T2 (in which belongs the node we just deleted).
        G1.remove_node(6)
        assert _consistent_PT(u, v, gparams, sparams)

        # Add one more covered neighbor of u in G1
        G1.add_edge(u, 2)
        assert not _consistent_PT(u, v, gparams, sparams)

        # Compensate in G2
        G2.add_edge(v, "c")
        assert _consistent_PT(u, v, gparams, sparams)

        # Add one more covered neighbor of v in G2
        G2.add_edge(v, "x")
        G1.add_node(7)
        sparams.mapping.update({7: "x"})
        sparams.reverse_mapping.update({"x": 7})
        assert not _consistent_PT(u, v, gparams, sparams)

        # Compensate in G1
        G1.add_edge(u, 7)
        assert _consistent_PT(u, v, gparams, sparams)

    def test_cut_inconsistent_labels(self):
        G1 = nx.DiGraph(
            [
                (0, 1),
                (2, 1),
                (10, 0),
                (10, 3),
                (10, 4),
                (5, 10),
                (10, 6),
                (1, 4),
                (5, 3),
            ]
        )
        G2 = nx.DiGraph(
            [
                ("a", "b"),
                ("c", "b"),
                ("k", "a"),
                ("k", "d"),
                ("k", "e"),
                ("f", "k"),
                ("k", "g"),
                ("b", "e"),
                ("f", "d"),
            ]
        )

        l1 = {n: "blue" for n in G1.nodes()}
        l2 = {n: "blue" for n in G2.nodes()}
        l1.update({5: "green"})  # Change the label of one neighbor of u

        gparams = _GraphParameters(
            G1, G2, l1, l2, nx.utils.groups(l1), nx.utils.groups(l2), None
        )
        sparams = _StateParameters(
            {0: "a", 1: "b", 2: "c", 3: "d"},
            {"a": 0, "b": 1, "c": 2, "d": 3},
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        )

        u, v = 10, "k"
        assert _cut_PT(u, v, gparams, sparams)

    def test_cut_consistent_labels(self):
        G1 = nx.DiGraph(
            [
                (0, 1),
                (2, 1),
                (10, 0),
                (10, 3),
                (10, 4),
                (5, 10),
                (10, 6),
                (1, 4),
                (5, 3),
            ]
        )
        G2 = nx.DiGraph(
            [
                ("a", "b"),
                ("c", "b"),
                ("k", "a"),
                ("k", "d"),
                ("k", "e"),
                ("f", "k"),
                ("k", "g"),
                ("b", "e"),
                ("f", "d"),
            ]
        )

        l1 = {n: "blue" for n in G1.nodes()}
        l2 = {n: "blue" for n in G2.nodes()}

        gparams = _GraphParameters(
            G1, G2, l1, l2, nx.utils.groups(l1), nx.utils.groups(l2), None
        )
        sparams = _StateParameters(
            {0: "a", 1: "b", 2: "c", 3: "d"},
            {"a": 0, "b": 1, "c": 2, "d": 3},
            {4},
            {5, 10},
            {6},
            None,
            {"e"},
            {"f", "k"},
            {"g"},
            None,
        )

        u, v = 10, "k"
        assert not _cut_PT(u, v, gparams, sparams)

    def test_cut_same_labels(self):
        G1 = nx.DiGraph(
            [
                (0, 1),
                (2, 1),
                (10, 0),
                (10, 3),
                (10, 4),
                (5, 10),
                (10, 6),
                (1, 4),
                (5, 3),
            ]
        )
        mapped = {0: "a", 1: "b", 2: "c", 3: "d", 4: "e", 5: "f", 6: "g", 10: "k"}
        G2 = nx.relabel_nodes(G1, mapped)
        l1 = {n: "blue" for n in G1.nodes()}
        l2 = {n: "blue" for n in G2.nodes()}

        gparams = _GraphParameters(
            G1, G2, l1, l2, nx.utils.groups(l1), nx.utils.groups(l2), None
        )
        sparams = _StateParameters(
            {0: "a", 1: "b", 2: "c", 3: "d"},
            {"a": 0, "b": 1, "c": 2, "d": 3},
            {4},
            {5, 10},
            {6},
            None,
            {"e"},
            {"f", "k"},
            {"g"},
            None,
        )

        u, v = 10, "k"
        assert not _cut_PT(u, v, gparams, sparams)

        # Change intersection between G1[u] and T1_out, so it's not the same as the one between G2[v] and T2_out
        G1.remove_edge(u, 4)
        assert _cut_PT(u, v, gparams, sparams)

        # Compensate in G2
        G2.remove_edge(v, mapped[4])
        assert not _cut_PT(u, v, gparams, sparams)

        # Change intersection between G1[u] and T1_in, so it's not the same as the one between G2[v] and T2_in
        G1.remove_edge(5, u)
        assert _cut_PT(u, v, gparams, sparams)

        # Compensate in G2
        G2.remove_edge(mapped[5], v)
        assert not _cut_PT(u, v, gparams, sparams)

        # Change intersection between G2[v] and T2_tilde, so it's not the same as the one between G1[u] and T1_tilde
        G2.remove_edge(v, mapped[6])
        assert _cut_PT(u, v, gparams, sparams)

        # Compensate in G1
        G1.remove_edge(u, 6)
        assert not _cut_PT(u, v, gparams, sparams)

        # Add disconnected nodes, which will form the new Ti_tilde
        G1.add_nodes_from([6, 7, 8])
        G2.add_nodes_from(["g", "y", "z"])
        sparams.T1_tilde.update({6, 7, 8})
        sparams.T2_tilde.update({"g", "y", "z"})

        l1 = {n: "blue" for n in G1.nodes()}
        l2 = {n: "blue" for n in G2.nodes()}
        gparams = _GraphParameters(
            G1, G2, l1, l2, nx.utils.groups(l1), nx.utils.groups(l2), None
        )

        assert not _cut_PT(u, v, gparams, sparams)

    def test_cut_different_labels(self):
        G1 = nx.DiGraph(
            [
                (0, 1),
                (1, 2),
                (14, 1),
                (0, 4),
                (1, 5),
                (2, 6),
                (3, 7),
                (3, 6),
                (10, 4),
                (4, 9),
                (6, 10),
                (20, 9),
                (20, 15),
                (20, 12),
                (20, 11),
                (12, 13),
                (11, 13),
                (20, 8),
                (20, 3),
                (20, 5),
                (0, 20),
            ]
        )
        mapped = {
            0: "a",
            1: "b",
            2: "c",
            3: "d",
            4: "e",
            5: "f",
            6: "g",
            7: "h",
            8: "i",
            9: "j",
            10: "k",
            11: "l",
            12: "m",
            13: "n",
            14: "o",
            15: "p",
            20: "x",
        }
        G2 = nx.relabel_nodes(G1, mapped)

        l1 = {n: "none" for n in G1.nodes()}
        l2 = {}

        l1.update(
            {
                9: "blue",
                15: "blue",
                12: "blue",
                11: "green",
                3: "green",
                8: "red",
                0: "red",
                5: "yellow",
            }
        )
        l2.update({mapped[n]: l for n, l in l1.items()})

        gparams = _GraphParameters(
            G1, G2, l1, l2, nx.utils.groups(l1), nx.utils.groups(l2), None
        )
        sparams = _StateParameters(
            {0: "a", 1: "b", 2: "c", 3: "d"},
            {"a": 0, "b": 1, "c": 2, "d": 3},
            {4, 5, 6, 7, 20},
            {14, 20},
            {9, 10, 15, 12, 11, 13, 8},
            None,
            {"e", "f", "g", "x"},
            {"o", "x"},
            {"j", "k", "l", "m", "n", "i", "p"},
            None,
        )

        u, v = 20, "x"
        assert not _cut_PT(u, v, gparams, sparams)

        # Change the orientation of the labels on neighbors of u compared to neighbors of v. Leave the structure intact
        l1.update({9: "red"})
        assert _cut_PT(u, v, gparams, sparams)

        # compensate in G2
        l2.update({mapped[9]: "red"})
        assert not _cut_PT(u, v, gparams, sparams)

        # Change the intersection of G1[u] and T1_out
        G1.add_edge(u, 4)
        assert _cut_PT(u, v, gparams, sparams)

        # Same for G2[v] and T2_out
        G2.add_edge(v, mapped[4])
        assert not _cut_PT(u, v, gparams, sparams)

        # Change the intersection of G1[u] and T1_in
        G1.add_edge(u, 14)
        assert _cut_PT(u, v, gparams, sparams)

        # Same for G2[v] and T2_in
        G2.add_edge(v, mapped[14])
        assert not _cut_PT(u, v, gparams, sparams)

        # Change the intersection of G2[v] and T2_tilde
        G2.remove_edge(v, mapped[8])
        assert _cut_PT(u, v, gparams, sparams)

        # Same for G1[u] and T1_tilde
        G1.remove_edge(u, 8)
        assert not _cut_PT(u, v, gparams, sparams)

        # Place 8 and mapped[8] in T1 and T2 respectively, by connecting it to covered nodes
        G1.add_edge(8, 3)
        G2.add_edge(mapped[8], mapped[3])
        sparams.T1.add(8)
        sparams.T2.add(mapped[8])
        sparams.T1_tilde.remove(8)
        sparams.T2_tilde.remove(mapped[8])

        assert not _cut_PT(u, v, gparams, sparams)

        # Remove neighbor of u from T1
        G1.remove_node(5)
        l1.pop(5)
        sparams.T1.remove(5)
        assert _cut_PT(u, v, gparams, sparams)

        # Same in G2
        G2.remove_node(mapped[5])
        l2.pop(mapped[5])
        sparams.T2.remove(mapped[5])
        assert not _cut_PT(u, v, gparams, sparams)

    def test_predecessor_T1_in_fail(self):
        G1 = nx.DiGraph(
            [(0, 1), (0, 3), (4, 0), (1, 5), (5, 2), (3, 6), (4, 6), (6, 5)]
        )
        mapped = {0: "a", 1: "b", 2: "c", 3: "d", 4: "e", 5: "f", 6: "g"}
        G2 = nx.relabel_nodes(G1, mapped)
        l1 = {n: "blue" for n in G1.nodes()}
        l2 = {n: "blue" for n in G2.nodes()}

        gparams = _GraphParameters(
            G1, G2, l1, l2, nx.utils.groups(l1), nx.utils.groups(l2), None
        )
        sparams = _StateParameters(
            {0: "a", 1: "b", 2: "c"},
            {"a": 0, "b": 1, "c": 2},
            {3, 5},
            {4, 5},
            {6},
            None,
            {"d", "f"},
            {"f"},  # mapped[4] is missing from T2_in
            {"g"},
            None,
        )

        u, v = 6, "g"
        assert _cut_PT(u, v, gparams, sparams)

        sparams.T2_in.add("e")
        assert not _cut_PT(u, v, gparams, sparams)


class TestGraphTinoutUpdating:
    edges = [
        (1, 3),
        (2, 3),
        (3, 4),
        (4, 9),
        (4, 5),
        (3, 9),
        (5, 8),
        (5, 7),
        (8, 7),
        (6, 7),
    ]
    mapped = {
        0: "x",
        1: "a",
        2: "b",
        3: "c",
        4: "d",
        5: "e",
        6: "f",
        7: "g",
        8: "h",
        9: "i",
    }
    G1 = nx.Graph()
    G1.add_edges_from(edges)
    G1.add_node(0)
    G2 = nx.relabel_nodes(G1, mapping=mapped)

    def test_updating(self):
        G2_degree = dict(self.G2.degree)
        gparams, sparams = _initialize_parameters(self.G1, self.G2, G2_degree)
        m, m_rev, T1, _, T1_tilde, _, T2, _, T2_tilde, _ = sparams

        # Add node to the mapping
        m[4] = self.mapped[4]
        m_rev[self.mapped[4]] = 4
        _update_Tinout(4, self.mapped[4], gparams, sparams)

        assert T1 == {3, 5, 9}
        assert T2 == {"c", "i", "e"}
        assert T1_tilde == {0, 1, 2, 6, 7, 8}
        assert T2_tilde == {"x", "a", "b", "f", "g", "h"}

        # Add node to the mapping
        m[5] = self.mapped[5]
        m_rev.update({self.mapped[5]: 5})
        _update_Tinout(5, self.mapped[5], gparams, sparams)

        assert T1 == {3, 9, 8, 7}
        assert T2 == {"c", "i", "h", "g"}
        assert T1_tilde == {0, 1, 2, 6}
        assert T2_tilde == {"x", "a", "b", "f"}

        # Add node to the mapping
        m[6] = self.mapped[6]
        m_rev.update({self.mapped[6]: 6})
        _update_Tinout(6, self.mapped[6], gparams, sparams)

        assert T1 == {3, 9, 8, 7}
        assert T2 == {"c", "i", "h", "g"}
        assert T1_tilde == {0, 1, 2}
        assert T2_tilde == {"x", "a", "b"}

        # Add node to the mapping
        m[3] = self.mapped[3]
        m_rev.update({self.mapped[3]: 3})
        _update_Tinout(3, self.mapped[3], gparams, sparams)

        assert T1 == {1, 2, 9, 8, 7}
        assert T2 == {"a", "b", "i", "h", "g"}
        assert T1_tilde == {0}
        assert T2_tilde == {"x"}

        # Add node to the mapping
        m[0] = self.mapped[0]
        m_rev.update({self.mapped[0]: 0})
        _update_Tinout(0, self.mapped[0], gparams, sparams)

        assert T1 == {1, 2, 9, 8, 7}
        assert T2 == {"a", "b", "i", "h", "g"}
        assert T1_tilde == set()
        assert T2_tilde == set()

    def test_restoring(self):
        m = {0: "x", 3: "c", 4: "d", 5: "e", 6: "f"}
        m_rev = {"x": 0, "c": 3, "d": 4, "e": 5, "f": 6}

        T1 = {1, 2, 7, 9, 8}
        T2 = {"a", "b", "g", "i", "h"}
        T1_tilde = set()
        T2_tilde = set()

        gparams = _GraphParameters(self.G1, self.G2, {}, {}, {}, {}, {})
        sparams = _StateParameters(
            m, m_rev, T1, None, T1_tilde, None, T2, None, T2_tilde, None
        )

        # Remove a node from the mapping
        m.pop(0)
        m_rev.pop("x")
        _restore_Tinout(0, self.mapped[0], gparams, sparams)

        assert T1 == {1, 2, 7, 9, 8}
        assert T2 == {"a", "b", "g", "i", "h"}
        assert T1_tilde == {0}
        assert T2_tilde == {"x"}

        # Remove a node from the mapping
        m.pop(6)
        m_rev.pop("f")
        _restore_Tinout(6, self.mapped[6], gparams, sparams)

        assert T1 == {1, 2, 7, 9, 8}
        assert T2 == {"a", "b", "g", "i", "h"}
        assert T1_tilde == {0, 6}
        assert T2_tilde == {"x", "f"}

        # Remove a node from the mapping
        m.pop(3)
        m_rev.pop("c")
        _restore_Tinout(3, self.mapped[3], gparams, sparams)

        assert T1 == {7, 9, 8, 3}
        assert T2 == {"g", "i", "h", "c"}
        assert T1_tilde == {0, 6, 1, 2}
        assert T2_tilde == {"x", "f", "a", "b"}

        # Remove a node from the mapping
        m.pop(5)
        m_rev.pop("e")
        _restore_Tinout(5, self.mapped[5], gparams, sparams)

        assert T1 == {9, 3, 5}
        assert T2 == {"i", "c", "e"}
        assert T1_tilde == {0, 6, 1, 2, 7, 8}
        assert T2_tilde == {"x", "f", "a", "b", "g", "h"}

        # Remove a node from the mapping
        m.pop(4)
        m_rev.pop("d")
        _restore_Tinout(4, self.mapped[4], gparams, sparams)

        assert T1 == set()
        assert T2 == set()
        assert T1_tilde == set(self.G1.nodes())
        assert T2_tilde == set(self.G2.nodes())


class TestDiGraphTinoutUpdating:
    edges = [
        (1, 3),
        (3, 2),
        (3, 4),
        (4, 9),
        (4, 5),
        (3, 9),
        (5, 8),
        (5, 7),
        (8, 7),
        (7, 6),
    ]
    mapped = {
        0: "x",
        1: "a",
        2: "b",
        3: "c",
        4: "d",
        5: "e",
        6: "f",
        7: "g",
        8: "h",
        9: "i",
    }
    G1 = nx.DiGraph(edges)
    G1.add_node(0)
    G2 = nx.relabel_nodes(G1, mapping=mapped)

    def test_updating(self):
        G2_degree = {
            n: (in_degree, out_degree)
            for (n, in_degree), (_, out_degree) in zip(
                self.G2.in_degree, self.G2.out_degree
            )
        }
        gparams, sparams = _initialize_parameters(self.G1, self.G2, G2_degree)
        m, m_rev, T1_out, T1_in, T1_tilde, _, T2_out, T2_in, T2_tilde, _ = sparams

        # Add node to the mapping
        m[4] = self.mapped[4]
        m_rev[self.mapped[4]] = 4
        _update_Tinout(4, self.mapped[4], gparams, sparams)

        assert T1_out == {5, 9}
        assert T1_in == {3}
        assert T2_out == {"i", "e"}
        assert T2_in == {"c"}
        assert T1_tilde == {0, 1, 2, 6, 7, 8}
        assert T2_tilde == {"x", "a", "b", "f", "g", "h"}

        # Add node to the mapping
        m[5] = self.mapped[5]
        m_rev[self.mapped[5]] = 5
        _update_Tinout(5, self.mapped[5], gparams, sparams)

        assert T1_out == {9, 8, 7}
        assert T1_in == {3}
        assert T2_out == {"i", "g", "h"}
        assert T2_in == {"c"}
        assert T1_tilde == {0, 1, 2, 6}
        assert T2_tilde == {"x", "a", "b", "f"}

        # Add node to the mapping
        m[6] = self.mapped[6]
        m_rev[self.mapped[6]] = 6
        _update_Tinout(6, self.mapped[6], gparams, sparams)

        assert T1_out == {9, 8, 7}
        assert T1_in == {3, 7}
        assert T2_out == {"i", "g", "h"}
        assert T2_in == {"c", "g"}
        assert T1_tilde == {0, 1, 2}
        assert T2_tilde == {"x", "a", "b"}

        # Add node to the mapping
        m[3] = self.mapped[3]
        m_rev[self.mapped[3]] = 3
        _update_Tinout(3, self.mapped[3], gparams, sparams)

        assert T1_out == {9, 8, 7, 2}
        assert T1_in == {7, 1}
        assert T2_out == {"i", "g", "h", "b"}
        assert T2_in == {"g", "a"}
        assert T1_tilde == {0}
        assert T2_tilde == {"x"}

        # Add node to the mapping
        m[0] = self.mapped[0]
        m_rev[self.mapped[0]] = 0
        _update_Tinout(0, self.mapped[0], gparams, sparams)

        assert T1_out == {9, 8, 7, 2}
        assert T1_in == {7, 1}
        assert T2_out == {"i", "g", "h", "b"}
        assert T2_in == {"g", "a"}
        assert T1_tilde == set()
        assert T2_tilde == set()

    def test_restoring(self):
        m = {0: "x", 3: "c", 4: "d", 5: "e", 6: "f"}
        m_rev = {"x": 0, "c": 3, "d": 4, "e": 5, "f": 6}

        T1_out = {2, 7, 9, 8}
        T1_in = {1, 7}
        T2_out = {"b", "g", "i", "h"}
        T2_in = {"a", "g"}
        T1_tilde = set()
        T2_tilde = set()

        gparams = _GraphParameters(self.G1, self.G2, {}, {}, {}, {}, {})
        sparams = _StateParameters(
            m, m_rev, T1_out, T1_in, T1_tilde, None, T2_out, T2_in, T2_tilde, None
        )

        # Remove a node from the mapping
        m.pop(0)
        m_rev.pop("x")
        _restore_Tinout_Di(0, self.mapped[0], gparams, sparams)

        assert T1_out == {2, 7, 9, 8}
        assert T1_in == {1, 7}
        assert T2_out == {"b", "g", "i", "h"}
        assert T2_in == {"a", "g"}
        assert T1_tilde == {0}
        assert T2_tilde == {"x"}

        # Remove a node from the mapping
        m.pop(6)
        m_rev.pop("f")
        _restore_Tinout_Di(6, self.mapped[6], gparams, sparams)

        assert T1_out == {2, 9, 8, 7}
        assert T1_in == {1}
        assert T2_out == {"b", "i", "h", "g"}
        assert T2_in == {"a"}
        assert T1_tilde == {0, 6}
        assert T2_tilde == {"x", "f"}

        # Remove a node from the mapping
        m.pop(3)
        m_rev.pop("c")
        _restore_Tinout_Di(3, self.mapped[3], gparams, sparams)

        assert T1_out == {9, 8, 7}
        assert T1_in == {3}
        assert T2_out == {"i", "h", "g"}
        assert T2_in == {"c"}
        assert T1_tilde == {0, 6, 1, 2}
        assert T2_tilde == {"x", "f", "a", "b"}

        # Remove a node from the mapping
        m.pop(5)
        m_rev.pop("e")
        _restore_Tinout_Di(5, self.mapped[5], gparams, sparams)

        assert T1_out == {9, 5}
        assert T1_in == {3}
        assert T2_out == {"i", "e"}
        assert T2_in == {"c"}
        assert T1_tilde == {0, 6, 1, 2, 8, 7}
        assert T2_tilde == {"x", "f", "a", "b", "h", "g"}

        # Remove a node from the mapping
        m.pop(4)
        m_rev.pop("d")
        _restore_Tinout_Di(4, self.mapped[4], gparams, sparams)

        assert T1_out == set()
        assert T1_in == set()
        assert T2_out == set()
        assert T2_in == set()
        assert T1_tilde == set(self.G1.nodes())
        assert T2_tilde == set(self.G2.nodes())
