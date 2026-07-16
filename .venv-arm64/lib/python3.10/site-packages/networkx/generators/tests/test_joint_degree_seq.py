import time

from networkx.algorithms.assortativity import degree_mixing_dict
from networkx.generators import gnm_random_graph, powerlaw_cluster_graph
from networkx.generators.joint_degree_seq import (
    directed_joint_degree_graph,
    is_valid_directed_joint_degree,
    is_valid_joint_degree,
    joint_degree_graph,
)


def test_is_valid_joint_degree():
    """Tests for conditions that invalidate a joint degree dict"""

    # valid joint degree that satisfies all five conditions
    joint_degrees = {
        1: {4: 1},
        2: {2: 2, 3: 2, 4: 2},
        3: {2: 2, 4: 1},
        4: {1: 1, 2: 2, 3: 1},
    }
    assert is_valid_joint_degree(joint_degrees)

    # test condition 1
    # joint_degrees_1[1][4] not integer
    joint_degrees_1 = {
        1: {4: 1.5},
        2: {2: 2, 3: 2, 4: 2},
        3: {2: 2, 4: 1},
        4: {1: 1.5, 2: 2, 3: 1},
    }
    assert not is_valid_joint_degree(joint_degrees_1)

    # test condition 2
    # degree_count[2] = sum(joint_degrees_2[2][j)/2, is not an int
    # degree_count[4] = sum(joint_degrees_2[4][j)/4, is not an int
    joint_degrees_2 = {
        1: {4: 1},
        2: {2: 2, 3: 2, 4: 3},
        3: {2: 2, 4: 1},
        4: {1: 1, 2: 3, 3: 1},
    }
    assert not is_valid_joint_degree(joint_degrees_2)

    # test conditions 3 and 4
    # joint_degrees_3[1][4]>degree_count[1]*degree_count[4]
    joint_degrees_3 = {
        1: {4: 2},
        2: {2: 2, 3: 2, 4: 2},
        3: {2: 2, 4: 1},
        4: {1: 2, 2: 2, 3: 1},
    }
    assert not is_valid_joint_degree(joint_degrees_3)

    # test condition 5
    # joint_degrees_5[1][1] not even
    joint_degrees_5 = {1: {1: 9}}
    assert not is_valid_joint_degree(joint_degrees_5)


def test_joint_degree_graph(ntimes=10):
    for _ in range(ntimes):
        seed = int(time.time())

        n, m, p = 20, 10, 1
        # generate random graph with model powerlaw_cluster and calculate
        # its joint degree
        g = powerlaw_cluster_graph(n, m, p, seed=seed)
        joint_degrees_g = degree_mixing_dict(g, normalized=False)

        # generate simple undirected graph with given joint degree
        # joint_degrees_g
        G = joint_degree_graph(joint_degrees_g)
        joint_degrees_G = degree_mixing_dict(G, normalized=False)

        # assert that the given joint degree is equal to the generated
        # graph's joint degree
        assert joint_degrees_g == joint_degrees_G


def test_is_valid_directed_joint_degree():
    in_degrees = [0, 1, 1, 2]
    out_degrees = [1, 1, 1, 1]
    nkk = {1: {1: 2, 2: 2}}
    assert is_valid_directed_joint_degree(in_degrees, out_degrees, nkk)

    # not realizable, values are not integers.
    nkk = {1: {1: 1.5, 2: 2.5}}
    assert not is_valid_directed_joint_degree(in_degrees, out_degrees, nkk)

    # not realizable, number of edges between 1-2 are insufficient.
    nkk = {1: {1: 2, 2: 1}}
    assert not is_valid_directed_joint_degree(in_degrees, out_degrees, nkk)

    # not realizable, in/out degree sequences have different number of nodes.
    out_degrees = [1, 1, 1]
    nkk = {1: {1: 2, 2: 2}}
    assert not is_valid_directed_joint_degree(in_degrees, out_degrees, nkk)

    # not realizable, degree sequences have fewer than required nodes.
    in_degrees = [0, 1, 2]
    assert not is_valid_directed_joint_degree(in_degrees, out_degrees, nkk)


def test_directed_joint_degree_graph(n=15, m=100, ntimes=1000):
    for _ in range(ntimes):
        # generate gnm random graph and calculate its joint degree.
        g = gnm_random_graph(n, m, None, directed=True)

        # in-degree sequence of g as a list of integers.
        in_degrees = list(dict(g.in_degree()).values())
        # out-degree sequence of g as a list of integers.
        out_degrees = list(dict(g.out_degree()).values())
        nkk = degree_mixing_dict(g)

        # generate simple directed graph with given degree sequence and joint
        # degree matrix.
        G = directed_joint_degree_graph(in_degrees, out_degrees, nkk)

        # assert degree sequence correctness.
        assert in_degrees == list(dict(G.in_degree()).values())
        assert out_degrees == list(dict(G.out_degree()).values())
        # assert joint degree matrix correctness.
        assert nkk == degree_mixing_dict(G)
