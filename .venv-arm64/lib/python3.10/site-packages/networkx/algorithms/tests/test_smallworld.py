import pytest

pytest.importorskip("numpy")

import random

import networkx as nx
from networkx import lattice_reference, omega, random_reference, sigma

rng = 42


def test_random_reference():
    G = nx.connected_watts_strogatz_graph(50, 6, 0.1, seed=rng)
    Gr = random_reference(G, niter=1, seed=rng)
    C = nx.average_clustering(G)
    Cr = nx.average_clustering(Gr)
    assert C > Cr

    with pytest.raises(nx.NetworkXError):
        next(random_reference(nx.Graph()))
    with pytest.raises(nx.NetworkXNotImplemented):
        next(random_reference(nx.DiGraph()))

    H = nx.Graph(((0, 1), (2, 3)))
    Hl = random_reference(H, niter=1, seed=rng)


def test_lattice_reference():
    G = nx.connected_watts_strogatz_graph(50, 6, 1, seed=rng)
    Gl = lattice_reference(G, niter=1, seed=rng)
    L = nx.average_shortest_path_length(G)
    Ll = nx.average_shortest_path_length(Gl)
    assert Ll > L

    pytest.raises(nx.NetworkXError, lattice_reference, nx.Graph())
    pytest.raises(nx.NetworkXNotImplemented, lattice_reference, nx.DiGraph())

    H = nx.Graph(((0, 1), (2, 3)))
    Hl = lattice_reference(H, niter=1)


def test_sigma():
    Gs = nx.connected_watts_strogatz_graph(50, 6, 0.1, seed=rng)
    Gr = nx.connected_watts_strogatz_graph(50, 6, 1, seed=rng)
    sigmas = sigma(Gs, niter=1, nrand=2, seed=rng)
    sigmar = sigma(Gr, niter=1, nrand=2, seed=rng)
    assert sigmar < sigmas


def test_omega():
    Gl = nx.connected_watts_strogatz_graph(50, 6, 0, seed=rng)
    Gr = nx.connected_watts_strogatz_graph(50, 6, 1, seed=rng)
    Gs = nx.connected_watts_strogatz_graph(50, 6, 0.1, seed=rng)
    omegal = omega(Gl, niter=1, nrand=1, seed=rng)
    omegar = omega(Gr, niter=1, nrand=1, seed=rng)
    omegas = omega(Gs, niter=1, nrand=1, seed=rng)
    assert omegal < omegas and omegas < omegar

    # Test that omega lies within the [-1, 1] bounds
    G_barbell = nx.barbell_graph(5, 1)
    G_karate = nx.karate_club_graph()

    omega_barbell = nx.omega(G_barbell)
    omega_karate = nx.omega(G_karate, nrand=2)

    omegas = (omegal, omegar, omegas, omega_barbell, omega_karate)

    for o in omegas:
        assert -1 <= o <= 1


@pytest.mark.parametrize("f", (nx.random_reference, nx.lattice_reference))
def test_graph_no_edges(f):
    G = nx.Graph()
    G.add_nodes_from([0, 1, 2, 3])
    with pytest.raises(nx.NetworkXError, match="Graph has fewer that 2 edges"):
        f(G)
