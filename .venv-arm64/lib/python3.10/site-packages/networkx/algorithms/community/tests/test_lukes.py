from itertools import product

import pytest

import networkx as nx

EWL = "e_weight"
NWL = "n_weight"


# first test from the Lukes original paper
def paper_1_case(float_edge_wt=False, explicit_node_wt=True, directed=False):
    # problem-specific constants
    limit = 3

    # configuration
    if float_edge_wt:
        shift = 0.001
    else:
        shift = 0

    if directed:
        example_1 = nx.DiGraph()
    else:
        example_1 = nx.Graph()

    # graph creation
    example_1.add_edge(1, 2, **{EWL: 3 + shift})
    example_1.add_edge(1, 4, **{EWL: 2 + shift})
    example_1.add_edge(2, 3, **{EWL: 4 + shift})
    example_1.add_edge(2, 5, **{EWL: 6 + shift})

    # node weights
    if explicit_node_wt:
        nx.set_node_attributes(example_1, 1, NWL)
        wtu = NWL
    else:
        wtu = None

    # partitioning
    clusters_1 = {
        frozenset(x)
        for x in nx.community.lukes_partitioning(
            example_1, limit, node_weight=wtu, edge_weight=EWL
        )
    }

    return clusters_1


# second test from the Lukes original paper
def paper_2_case(explicit_edge_wt=True, directed=False):
    # problem specific constants
    byte_block_size = 32

    # configuration
    if directed:
        example_2 = nx.DiGraph()
    else:
        example_2 = nx.Graph()

    if explicit_edge_wt:
        edic = {EWL: 1}
        wtu = EWL
    else:
        edic = {}
        wtu = None

    # graph creation
    example_2.add_edge("name", "home_address", **edic)
    example_2.add_edge("name", "education", **edic)
    example_2.add_edge("education", "bs", **edic)
    example_2.add_edge("education", "ms", **edic)
    example_2.add_edge("education", "phd", **edic)
    example_2.add_edge("name", "telephone", **edic)
    example_2.add_edge("telephone", "home", **edic)
    example_2.add_edge("telephone", "office", **edic)
    example_2.add_edge("office", "no1", **edic)
    example_2.add_edge("office", "no2", **edic)

    example_2.nodes["name"][NWL] = 20
    example_2.nodes["education"][NWL] = 10
    example_2.nodes["bs"][NWL] = 1
    example_2.nodes["ms"][NWL] = 1
    example_2.nodes["phd"][NWL] = 1
    example_2.nodes["home_address"][NWL] = 8
    example_2.nodes["telephone"][NWL] = 8
    example_2.nodes["home"][NWL] = 8
    example_2.nodes["office"][NWL] = 4
    example_2.nodes["no1"][NWL] = 1
    example_2.nodes["no2"][NWL] = 1

    # partitioning
    clusters_2 = {
        frozenset(x)
        for x in nx.community.lukes_partitioning(
            example_2, byte_block_size, node_weight=NWL, edge_weight=wtu
        )
    }

    return clusters_2


def test_paper_1_case():
    ground_truth = {frozenset([1, 4]), frozenset([2, 3, 5])}

    tf = (True, False)
    for flt, nwt, drc in product(tf, tf, tf):
        part = paper_1_case(flt, nwt, drc)
        assert part == ground_truth


def test_paper_2_case():
    ground_truth = {
        frozenset(["education", "bs", "ms", "phd"]),
        frozenset(["name", "home_address"]),
        frozenset(["telephone", "home", "office", "no1", "no2"]),
    }

    tf = (True, False)
    for ewt, drc in product(tf, tf):
        part = paper_2_case(ewt, drc)
        assert part == ground_truth


def test_mandatory_tree():
    not_a_tree = nx.complete_graph(4)

    with pytest.raises(nx.NotATree):
        nx.community.lukes_partitioning(not_a_tree, 5)


def test_mandatory_integrality():
    byte_block_size = 32

    ex_1_broken = nx.DiGraph()

    ex_1_broken.add_edge(1, 2, **{EWL: 3.2})
    ex_1_broken.add_edge(1, 4, **{EWL: 2.4})
    ex_1_broken.add_edge(2, 3, **{EWL: 4.0})
    ex_1_broken.add_edge(2, 5, **{EWL: 6.3})

    ex_1_broken.nodes[1][NWL] = 1.2  # !
    ex_1_broken.nodes[2][NWL] = 1
    ex_1_broken.nodes[3][NWL] = 1
    ex_1_broken.nodes[4][NWL] = 1
    ex_1_broken.nodes[5][NWL] = 2

    with pytest.raises(TypeError):
        nx.community.lukes_partitioning(
            ex_1_broken, byte_block_size, node_weight=NWL, edge_weight=EWL
        )
