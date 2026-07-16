import pytest

import networkx as nx
from networkx.algorithms import flow
from networkx.utils import pairwise

flow_funcs = [
    flow.boykov_kolmogorov,
    flow.edmonds_karp,
    flow.dinitz,
    flow.preflow_push,
    flow.shortest_augmenting_path,
]


def is_path(G, path):
    return all(v in G[u] for u, v in pairwise(path))


def are_edge_disjoint_paths(G, paths):
    if not paths:
        return False
    for path in paths:
        assert is_path(G, path)
    paths_edges = [list(pairwise(p)) for p in paths]
    num_of_edges = sum(len(e) for e in paths_edges)
    num_unique_edges = len(set.union(*[set(es) for es in paths_edges]))
    if num_of_edges == num_unique_edges:
        return True
    return False


def are_node_disjoint_paths(G, paths):
    if not paths:
        return False
    for path in paths:
        assert is_path(G, path)
    # first and last nodes are source and target
    st = {paths[0][0], paths[0][-1]}
    num_of_nodes = len([n for path in paths for n in path if n not in st])
    num_unique_nodes = len({n for path in paths for n in path if n not in st})
    if num_of_nodes == num_unique_nodes:
        return True
    return False


def test_graph_from_pr_2053():
    G = nx.Graph()
    G.add_edges_from(
        [
            ("A", "B"),
            ("A", "D"),
            ("A", "F"),
            ("A", "G"),
            ("B", "C"),
            ("B", "D"),
            ("B", "G"),
            ("C", "D"),
            ("C", "E"),
            ("C", "Z"),
            ("D", "E"),
            ("D", "F"),
            ("E", "F"),
            ("E", "Z"),
            ("F", "Z"),
            ("G", "Z"),
        ]
    )
    for flow_func in flow_funcs:
        kwargs = {"flow_func": flow_func}
        errmsg = f"Assertion failed in function: {flow_func.__name__}"
        # edge disjoint paths
        edge_paths = list(nx.edge_disjoint_paths(G, "A", "Z", **kwargs))
        assert are_edge_disjoint_paths(G, edge_paths), errmsg
        assert nx.edge_connectivity(G, "A", "Z") == len(edge_paths), errmsg
        # node disjoint paths
        node_paths = list(nx.node_disjoint_paths(G, "A", "Z", **kwargs))
        assert are_node_disjoint_paths(G, node_paths), errmsg
        assert nx.node_connectivity(G, "A", "Z") == len(node_paths), errmsg


def test_florentine_families():
    G = nx.florentine_families_graph()
    for flow_func in flow_funcs:
        kwargs = {"flow_func": flow_func}
        errmsg = f"Assertion failed in function: {flow_func.__name__}"
        # edge disjoint paths
        edge_dpaths = list(nx.edge_disjoint_paths(G, "Medici", "Strozzi", **kwargs))
        assert are_edge_disjoint_paths(G, edge_dpaths), errmsg
        assert nx.edge_connectivity(G, "Medici", "Strozzi") == len(edge_dpaths), errmsg
        # node disjoint paths
        node_dpaths = list(nx.node_disjoint_paths(G, "Medici", "Strozzi", **kwargs))
        assert are_node_disjoint_paths(G, node_dpaths), errmsg
        assert nx.node_connectivity(G, "Medici", "Strozzi") == len(node_dpaths), errmsg


def test_karate():
    G = nx.karate_club_graph()
    for flow_func in flow_funcs:
        kwargs = {"flow_func": flow_func}
        errmsg = f"Assertion failed in function: {flow_func.__name__}"
        # edge disjoint paths
        edge_dpaths = list(nx.edge_disjoint_paths(G, 0, 33, **kwargs))
        assert are_edge_disjoint_paths(G, edge_dpaths), errmsg
        assert nx.edge_connectivity(G, 0, 33) == len(edge_dpaths), errmsg
        # node disjoint paths
        node_dpaths = list(nx.node_disjoint_paths(G, 0, 33, **kwargs))
        assert are_node_disjoint_paths(G, node_dpaths), errmsg
        assert nx.node_connectivity(G, 0, 33) == len(node_dpaths), errmsg


def test_petersen_disjoint_paths():
    G = nx.petersen_graph()
    for flow_func in flow_funcs:
        kwargs = {"flow_func": flow_func}
        errmsg = f"Assertion failed in function: {flow_func.__name__}"
        # edge disjoint paths
        edge_dpaths = list(nx.edge_disjoint_paths(G, 0, 6, **kwargs))
        assert are_edge_disjoint_paths(G, edge_dpaths), errmsg
        assert 3 == len(edge_dpaths), errmsg
        # node disjoint paths
        node_dpaths = list(nx.node_disjoint_paths(G, 0, 6, **kwargs))
        assert are_node_disjoint_paths(G, node_dpaths), errmsg
        assert 3 == len(node_dpaths), errmsg


def test_octahedral_disjoint_paths():
    G = nx.octahedral_graph()
    for flow_func in flow_funcs:
        kwargs = {"flow_func": flow_func}
        errmsg = f"Assertion failed in function: {flow_func.__name__}"
        # edge disjoint paths
        edge_dpaths = list(nx.edge_disjoint_paths(G, 0, 5, **kwargs))
        assert are_edge_disjoint_paths(G, edge_dpaths), errmsg
        assert 4 == len(edge_dpaths), errmsg
        # node disjoint paths
        node_dpaths = list(nx.node_disjoint_paths(G, 0, 5, **kwargs))
        assert are_node_disjoint_paths(G, node_dpaths), errmsg
        assert 4 == len(node_dpaths), errmsg


def test_icosahedral_disjoint_paths():
    G = nx.icosahedral_graph()
    for flow_func in flow_funcs:
        kwargs = {"flow_func": flow_func}
        errmsg = f"Assertion failed in function: {flow_func.__name__}"
        # edge disjoint paths
        edge_dpaths = list(nx.edge_disjoint_paths(G, 0, 6, **kwargs))
        assert are_edge_disjoint_paths(G, edge_dpaths), errmsg
        assert 5 == len(edge_dpaths), errmsg
        # node disjoint paths
        node_dpaths = list(nx.node_disjoint_paths(G, 0, 6, **kwargs))
        assert are_node_disjoint_paths(G, node_dpaths), errmsg
        assert 5 == len(node_dpaths), errmsg


def test_cutoff_disjoint_paths():
    G = nx.icosahedral_graph()
    for flow_func in flow_funcs:
        kwargs = {"flow_func": flow_func}
        errmsg = f"Assertion failed in function: {flow_func.__name__}"
        for cutoff in [2, 4]:
            kwargs["cutoff"] = cutoff
            # edge disjoint paths
            edge_dpaths = list(nx.edge_disjoint_paths(G, 0, 6, **kwargs))
            assert are_edge_disjoint_paths(G, edge_dpaths), errmsg
            assert cutoff == len(edge_dpaths), errmsg
            # node disjoint paths
            node_dpaths = list(nx.node_disjoint_paths(G, 0, 6, **kwargs))
            assert are_node_disjoint_paths(G, node_dpaths), errmsg
            assert cutoff == len(node_dpaths), errmsg


def test_missing_source_edge_paths():
    with pytest.raises(nx.NetworkXError):
        G = nx.path_graph(4)
        list(nx.edge_disjoint_paths(G, 10, 1))


def test_missing_source_node_paths():
    with pytest.raises(nx.NetworkXError):
        G = nx.path_graph(4)
        list(nx.node_disjoint_paths(G, 10, 1))


def test_missing_target_edge_paths():
    with pytest.raises(nx.NetworkXError):
        G = nx.path_graph(4)
        list(nx.edge_disjoint_paths(G, 1, 10))


def test_missing_target_node_paths():
    with pytest.raises(nx.NetworkXError):
        G = nx.path_graph(4)
        list(nx.node_disjoint_paths(G, 1, 10))


def test_not_weakly_connected_edges():
    with pytest.raises(nx.NetworkXNoPath):
        G = nx.DiGraph()
        nx.add_path(G, [1, 2, 3])
        nx.add_path(G, [4, 5])
        list(nx.edge_disjoint_paths(G, 1, 5))


def test_not_weakly_connected_nodes():
    with pytest.raises(nx.NetworkXNoPath):
        G = nx.DiGraph()
        nx.add_path(G, [1, 2, 3])
        nx.add_path(G, [4, 5])
        list(nx.node_disjoint_paths(G, 1, 5))


def test_not_connected_edges():
    with pytest.raises(nx.NetworkXNoPath):
        G = nx.Graph()
        nx.add_path(G, [1, 2, 3])
        nx.add_path(G, [4, 5])
        list(nx.edge_disjoint_paths(G, 1, 5))


def test_not_connected_nodes():
    with pytest.raises(nx.NetworkXNoPath):
        G = nx.Graph()
        nx.add_path(G, [1, 2, 3])
        nx.add_path(G, [4, 5])
        list(nx.node_disjoint_paths(G, 1, 5))


def test_isolated_edges():
    with pytest.raises(nx.NetworkXNoPath):
        G = nx.Graph()
        G.add_node(1)
        nx.add_path(G, [4, 5])
        list(nx.edge_disjoint_paths(G, 1, 5))


def test_isolated_nodes():
    with pytest.raises(nx.NetworkXNoPath):
        G = nx.Graph()
        G.add_node(1)
        nx.add_path(G, [4, 5])
        list(nx.node_disjoint_paths(G, 1, 5))


def test_invalid_auxiliary():
    with pytest.raises(nx.NetworkXError):
        G = nx.complete_graph(5)
        list(nx.node_disjoint_paths(G, 0, 3, auxiliary=G))
