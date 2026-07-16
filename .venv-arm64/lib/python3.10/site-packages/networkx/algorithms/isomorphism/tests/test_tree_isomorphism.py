import random
import time

import pytest

import networkx as nx
from networkx.algorithms.isomorphism.tree_isomorphism import (
    rooted_tree_isomorphism,
    tree_isomorphism,
)
from networkx.classes.function import is_directed


@pytest.mark.parametrize("graph_constructor", (nx.DiGraph, nx.MultiGraph))
def test_tree_isomorphism_raises_on_directed_and_multigraphs(graph_constructor):
    t1 = graph_constructor([(0, 1)])
    t2 = graph_constructor([(1, 2)])
    with pytest.raises(nx.NetworkXNotImplemented):
        nx.isomorphism.tree_isomorphism(t1, t2)


# have this work for graph
# given two trees (either the directed or undirected)
# transform t2 according to the isomorphism
# and confirm it is identical to t1
# randomize the order of the edges when constructing
def check_isomorphism(t1, t2, isomorphism):
    # get the name of t1, given the name in t2
    mapping = {v2: v1 for (v1, v2) in isomorphism}

    # these should be the same
    d1 = is_directed(t1)
    d2 = is_directed(t2)
    assert d1 == d2

    edges_1 = []
    for u, v in t1.edges():
        if d1:
            edges_1.append((u, v))
        else:
            # if not directed, then need to
            # put the edge in a consistent direction
            if u < v:
                edges_1.append((u, v))
            else:
                edges_1.append((v, u))

    edges_2 = []
    for u, v in t2.edges():
        # translate to names for t1
        u = mapping[u]
        v = mapping[v]
        if d2:
            edges_2.append((u, v))
        else:
            if u < v:
                edges_2.append((u, v))
            else:
                edges_2.append((v, u))

    return sorted(edges_1) == sorted(edges_2)


def test_hardcoded():
    print("hardcoded test")

    # define a test problem
    edges_1 = [
        ("a", "b"),
        ("a", "c"),
        ("a", "d"),
        ("b", "e"),
        ("b", "f"),
        ("e", "j"),
        ("e", "k"),
        ("c", "g"),
        ("c", "h"),
        ("g", "m"),
        ("d", "i"),
        ("f", "l"),
    ]

    edges_2 = [
        ("v", "y"),
        ("v", "z"),
        ("u", "x"),
        ("q", "u"),
        ("q", "v"),
        ("p", "t"),
        ("n", "p"),
        ("n", "q"),
        ("n", "o"),
        ("o", "r"),
        ("o", "s"),
        ("s", "w"),
    ]

    # there are two possible correct isomorphisms
    # it currently returns isomorphism1
    # but the second is also correct
    isomorphism1 = [
        ("a", "n"),
        ("b", "q"),
        ("c", "o"),
        ("d", "p"),
        ("e", "v"),
        ("f", "u"),
        ("g", "s"),
        ("h", "r"),
        ("i", "t"),
        ("j", "y"),
        ("k", "z"),
        ("l", "x"),
        ("m", "w"),
    ]

    # could swap y and z
    isomorphism2 = [
        ("a", "n"),
        ("b", "q"),
        ("c", "o"),
        ("d", "p"),
        ("e", "v"),
        ("f", "u"),
        ("g", "s"),
        ("h", "r"),
        ("i", "t"),
        ("j", "z"),
        ("k", "y"),
        ("l", "x"),
        ("m", "w"),
    ]

    t1 = nx.Graph()
    t1.add_edges_from(edges_1)
    root1 = "a"

    t2 = nx.Graph()
    t2.add_edges_from(edges_2)
    root2 = "n"

    isomorphism = sorted(rooted_tree_isomorphism(t1, root1, t2, root2))

    # is correct by hand
    assert isomorphism in (isomorphism1, isomorphism2)

    # check algorithmically
    assert check_isomorphism(t1, t2, isomorphism)

    # try again as digraph
    t1 = nx.DiGraph()
    t1.add_edges_from(edges_1)
    root1 = "a"

    t2 = nx.DiGraph()
    t2.add_edges_from(edges_2)
    root2 = "n"

    isomorphism = sorted(rooted_tree_isomorphism(t1, root1, t2, root2))

    # is correct by hand
    assert isomorphism in (isomorphism1, isomorphism2)

    # check algorithmically
    assert check_isomorphism(t1, t2, isomorphism)


# randomly swap a tuple (a,b)
def random_swap(t):
    (a, b) = t
    if random.randint(0, 1) == 1:
        return (a, b)
    else:
        return (b, a)


# given a tree t1, create a new tree t2
# that is isomorphic to t1, with a known isomorphism
# and test that our algorithm found the right one
def positive_single_tree(t1):
    assert nx.is_tree(t1)

    nodes1 = list(t1.nodes())
    # get a random permutation of this
    nodes2 = nodes1.copy()
    random.shuffle(nodes2)

    # this is one isomorphism, however they may be multiple
    # so we don't necessarily get this one back
    someisomorphism = list(zip(nodes1, nodes2))

    # map from old to new
    map1to2 = dict(someisomorphism)

    # get the edges with the transformed names
    edges2 = [random_swap((map1to2[u], map1to2[v])) for (u, v) in t1.edges()]
    # randomly permute, to ensure we're not relying on edge order somehow
    random.shuffle(edges2)

    # so t2 is isomorphic to t1
    t2 = nx.Graph()
    t2.add_edges_from(edges2)

    # lets call our code to see if t1 and t2 are isomorphic
    isomorphism = tree_isomorphism(t1, t2)

    # make sure we got a correct solution
    # although not necessarily someisomorphism
    assert len(isomorphism) > 0
    assert check_isomorphism(t1, t2, isomorphism)


# run positive_single_tree over all the
# non-isomorphic trees for k from 4 to maxk
# k = 4 is the first level that has more than 1 non-isomorphic tree
# k = 13 takes about 2.86 seconds to run on my laptop
# larger values run slow down significantly
# as the number of trees grows rapidly
def test_positive(maxk=14):
    print("positive test")

    for k in range(2, maxk + 1):
        start_time = time.time()
        trial = 0
        for t in nx.nonisomorphic_trees(k):
            positive_single_tree(t)
            trial += 1
        print(k, trial, time.time() - start_time)


# test the trivial case of a single node in each tree
# note that nonisomorphic_trees doesn't work for k = 1
def test_trivial():
    print("trivial test")

    # back to an undirected graph
    t1 = nx.Graph()
    t1.add_node("a")
    root1 = "a"

    t2 = nx.Graph()
    t2.add_node("n")
    root2 = "n"

    isomorphism = rooted_tree_isomorphism(t1, root1, t2, root2)

    assert isomorphism == [("a", "n")]

    assert check_isomorphism(t1, t2, isomorphism)


# test another trivial case where the two graphs have
# different numbers of nodes
def test_trivial_2():
    print("trivial test 2")

    edges_1 = [("a", "b"), ("a", "c")]

    edges_2 = [("v", "y")]

    t1 = nx.Graph()
    t1.add_edges_from(edges_1)

    t2 = nx.Graph()
    t2.add_edges_from(edges_2)

    isomorphism = tree_isomorphism(t1, t2)

    # they cannot be isomorphic,
    # since they have different numbers of nodes
    assert isomorphism == []


# the function nonisomorphic_trees generates all the non-isomorphic
# trees of a given size.  Take each pair of these and verify that
# they are not isomorphic
# k = 4 is the first level that has more than 1 non-isomorphic tree
# k = 11 takes about 4.76 seconds to run on my laptop
# larger values run slow down significantly
# as the number of trees grows rapidly
def test_negative(maxk=11):
    print("negative test")

    for k in range(4, maxk + 1):
        test_trees = list(nx.nonisomorphic_trees(k))
        start_time = time.time()
        trial = 0
        for i in range(len(test_trees) - 1):
            for j in range(i + 1, len(test_trees)):
                trial += 1
                assert tree_isomorphism(test_trees[i], test_trees[j]) == []
        print(k, trial, time.time() - start_time)
