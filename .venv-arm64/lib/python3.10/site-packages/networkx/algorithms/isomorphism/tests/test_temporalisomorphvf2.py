"""
Tests for the temporal aspect of the Temporal VF2 isomorphism algorithm.
"""

from datetime import date, datetime, timedelta

import networkx as nx
from networkx.algorithms import isomorphism as iso


def provide_g1_edgelist():
    return [(0, 1), (0, 2), (1, 2), (2, 4), (1, 3), (3, 4), (4, 5)]


def put_same_time(G, att_name):
    for e in G.edges(data=True):
        e[2][att_name] = date(2015, 1, 1)
    return G


def put_same_datetime(G, att_name):
    for e in G.edges(data=True):
        e[2][att_name] = datetime(2015, 1, 1)
    return G


def put_sequence_time(G, att_name):
    current_date = date(2015, 1, 1)
    for e in G.edges(data=True):
        current_date += timedelta(days=1)
        e[2][att_name] = current_date
    return G


def put_time_config_0(G, att_name):
    G[0][1][att_name] = date(2015, 1, 2)
    G[0][2][att_name] = date(2015, 1, 2)
    G[1][2][att_name] = date(2015, 1, 3)
    G[1][3][att_name] = date(2015, 1, 1)
    G[2][4][att_name] = date(2015, 1, 1)
    G[3][4][att_name] = date(2015, 1, 3)
    G[4][5][att_name] = date(2015, 1, 3)
    return G


def put_time_config_1(G, att_name):
    G[0][1][att_name] = date(2015, 1, 2)
    G[0][2][att_name] = date(2015, 1, 1)
    G[1][2][att_name] = date(2015, 1, 3)
    G[1][3][att_name] = date(2015, 1, 1)
    G[2][4][att_name] = date(2015, 1, 2)
    G[3][4][att_name] = date(2015, 1, 4)
    G[4][5][att_name] = date(2015, 1, 3)
    return G


def put_time_config_2(G, att_name):
    G[0][1][att_name] = date(2015, 1, 1)
    G[0][2][att_name] = date(2015, 1, 1)
    G[1][2][att_name] = date(2015, 1, 3)
    G[1][3][att_name] = date(2015, 1, 2)
    G[2][4][att_name] = date(2015, 1, 2)
    G[3][4][att_name] = date(2015, 1, 3)
    G[4][5][att_name] = date(2015, 1, 2)
    return G


class TestTimeRespectingGraphMatcher:
    """
    A test class for the undirected temporal graph matcher.
    """

    def provide_g1_topology(self):
        G1 = nx.Graph()
        G1.add_edges_from(provide_g1_edgelist())
        return G1

    def provide_g2_path_3edges(self):
        G2 = nx.Graph()
        G2.add_edges_from([(0, 1), (1, 2), (2, 3)])
        return G2

    def test_timdelta_zero_timeRespecting_returnsTrue(self):
        G1 = self.provide_g1_topology()
        temporal_name = "date"
        G1 = put_same_time(G1, temporal_name)
        G2 = self.provide_g2_path_3edges()
        d = timedelta()
        gm = iso.TimeRespectingGraphMatcher(G1, G2, temporal_name, d)
        assert gm.subgraph_is_isomorphic()

    def test_timdelta_zero_datetime_timeRespecting_returnsTrue(self):
        G1 = self.provide_g1_topology()
        temporal_name = "date"
        G1 = put_same_datetime(G1, temporal_name)
        G2 = self.provide_g2_path_3edges()
        d = timedelta()
        gm = iso.TimeRespectingGraphMatcher(G1, G2, temporal_name, d)
        assert gm.subgraph_is_isomorphic()

    def test_attNameStrange_timdelta_zero_timeRespecting_returnsTrue(self):
        G1 = self.provide_g1_topology()
        temporal_name = "strange_name"
        G1 = put_same_time(G1, temporal_name)
        G2 = self.provide_g2_path_3edges()
        d = timedelta()
        gm = iso.TimeRespectingGraphMatcher(G1, G2, temporal_name, d)
        assert gm.subgraph_is_isomorphic()

    def test_notTimeRespecting_returnsFalse(self):
        G1 = self.provide_g1_topology()
        temporal_name = "date"
        G1 = put_sequence_time(G1, temporal_name)
        G2 = self.provide_g2_path_3edges()
        d = timedelta()
        gm = iso.TimeRespectingGraphMatcher(G1, G2, temporal_name, d)
        assert not gm.subgraph_is_isomorphic()

    def test_timdelta_one_config0_returns_no_embeddings(self):
        G1 = self.provide_g1_topology()
        temporal_name = "date"
        G1 = put_time_config_0(G1, temporal_name)
        G2 = self.provide_g2_path_3edges()
        d = timedelta(days=1)
        gm = iso.TimeRespectingGraphMatcher(G1, G2, temporal_name, d)
        count_match = len(list(gm.subgraph_isomorphisms_iter()))
        assert count_match == 0

    def test_timdelta_one_config1_returns_four_embedding(self):
        G1 = self.provide_g1_topology()
        temporal_name = "date"
        G1 = put_time_config_1(G1, temporal_name)
        G2 = self.provide_g2_path_3edges()
        d = timedelta(days=1)
        gm = iso.TimeRespectingGraphMatcher(G1, G2, temporal_name, d)
        count_match = len(list(gm.subgraph_isomorphisms_iter()))
        assert count_match == 4

    def test_timdelta_one_config2_returns_ten_embeddings(self):
        G1 = self.provide_g1_topology()
        temporal_name = "date"
        G1 = put_time_config_2(G1, temporal_name)
        G2 = self.provide_g2_path_3edges()
        d = timedelta(days=1)
        gm = iso.TimeRespectingGraphMatcher(G1, G2, temporal_name, d)
        L = list(gm.subgraph_isomorphisms_iter())
        count_match = len(list(gm.subgraph_isomorphisms_iter()))
        assert count_match == 10


class TestDiTimeRespectingGraphMatcher:
    """
    A test class for the directed time-respecting graph matcher.
    """

    def provide_g1_topology(self):
        G1 = nx.DiGraph()
        G1.add_edges_from(provide_g1_edgelist())
        return G1

    def provide_g2_path_3edges(self):
        G2 = nx.DiGraph()
        G2.add_edges_from([(0, 1), (1, 2), (2, 3)])
        return G2

    def test_timdelta_zero_same_dates_returns_true(self):
        G1 = self.provide_g1_topology()
        temporal_name = "date"
        G1 = put_same_time(G1, temporal_name)
        G2 = self.provide_g2_path_3edges()
        d = timedelta()
        gm = iso.TimeRespectingDiGraphMatcher(G1, G2, temporal_name, d)
        assert gm.subgraph_is_isomorphic()

    def test_attNameStrange_timdelta_zero_same_dates_returns_true(self):
        G1 = self.provide_g1_topology()
        temporal_name = "strange"
        G1 = put_same_time(G1, temporal_name)
        G2 = self.provide_g2_path_3edges()
        d = timedelta()
        gm = iso.TimeRespectingDiGraphMatcher(G1, G2, temporal_name, d)
        assert gm.subgraph_is_isomorphic()

    def test_timdelta_one_config0_returns_no_embeddings(self):
        G1 = self.provide_g1_topology()
        temporal_name = "date"
        G1 = put_time_config_0(G1, temporal_name)
        G2 = self.provide_g2_path_3edges()
        d = timedelta(days=1)
        gm = iso.TimeRespectingDiGraphMatcher(G1, G2, temporal_name, d)
        count_match = len(list(gm.subgraph_isomorphisms_iter()))
        assert count_match == 0

    def test_timdelta_one_config1_returns_one_embedding(self):
        G1 = self.provide_g1_topology()
        temporal_name = "date"
        G1 = put_time_config_1(G1, temporal_name)
        G2 = self.provide_g2_path_3edges()
        d = timedelta(days=1)
        gm = iso.TimeRespectingDiGraphMatcher(G1, G2, temporal_name, d)
        count_match = len(list(gm.subgraph_isomorphisms_iter()))
        assert count_match == 1

    def test_timdelta_one_config2_returns_two_embeddings(self):
        G1 = self.provide_g1_topology()
        temporal_name = "date"
        G1 = put_time_config_2(G1, temporal_name)
        G2 = self.provide_g2_path_3edges()
        d = timedelta(days=1)
        gm = iso.TimeRespectingDiGraphMatcher(G1, G2, temporal_name, d)
        count_match = len(list(gm.subgraph_isomorphisms_iter()))
        assert count_match == 2
