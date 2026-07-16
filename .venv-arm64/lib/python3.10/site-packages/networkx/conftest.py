"""
Testing
=======

General guidelines for writing good tests:

- doctests always assume ``import networkx as nx`` so don't add that
- prefer pytest fixtures over classes with setup methods.
- use the ``@pytest.mark.parametrize``  decorator
- use ``pytest.importorskip`` for numpy, scipy, pandas, and matplotlib b/c of PyPy.
  and add the module to the relevant entries below.

"""

import os
import sys
import warnings
from importlib.metadata import entry_points

import pytest

import networkx


def pytest_addoption(parser):
    parser.addoption(
        "--runslow", action="store_true", default=False, help="run slow tests"
    )
    parser.addoption(
        "--backend",
        action="store",
        default=None,
        help="Run tests with a backend by auto-converting nx graphs to backend graphs",
    )
    parser.addoption(
        "--fallback-to-nx",
        action="store_true",
        default=False,
        help="Run nx function if a backend doesn't implement a dispatchable function"
        " (use with --backend)",
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: mark test as slow to run")
    backend = config.getoption("--backend")
    if backend is None:
        backend = os.environ.get("NETWORKX_TEST_BACKEND")
    # nx_loopback backend is only available when testing with a backend
    loopback_ep = entry_points(name="nx_loopback", group="networkx.backends")
    if not loopback_ep:
        warnings.warn(
            "\n\n             WARNING: Mixed NetworkX configuration! \n\n"
            "        This environment has mixed configuration for networkx.\n"
            "        The test object nx_loopback is not configured correctly.\n"
            "        You should not be seeing this message.\n"
            "        Try `pip install -e .`, or change your PYTHONPATH\n"
            "        Make sure python finds the networkx repo you are testing\n\n"
        )
    config.backend = backend
    if backend:
        # We will update `networkx.config.backend_priority` below in `*_modify_items`
        # to allow tests to get set up with normal networkx graphs.
        networkx.utils.backends.backends["nx_loopback"] = loopback_ep["nx_loopback"]
        networkx.utils.backends.backend_info["nx_loopback"] = {}
        networkx.config.backends = networkx.utils.Config(
            nx_loopback=networkx.utils.Config(),
            **networkx.config.backends,
        )
        fallback_to_nx = config.getoption("--fallback-to-nx")
        if not fallback_to_nx:
            fallback_to_nx = os.environ.get("NETWORKX_FALLBACK_TO_NX")
        networkx.config.fallback_to_nx = bool(fallback_to_nx)


def pytest_collection_modifyitems(config, items):
    # Setting this to True here allows tests to be set up before dispatching
    # any function call to a backend.
    if config.backend:
        # Allow pluggable backends to add markers to tests (such as skip or xfail)
        # when running in auto-conversion test mode
        backend_name = config.backend
        if backend_name != "networkx":
            networkx.utils.backends._dispatchable._is_testing = True
            networkx.config.backend_priority.algos = [backend_name]
            networkx.config.backend_priority.generators = [backend_name]
            backend = networkx.utils.backends.backends[backend_name].load()
            if hasattr(backend, "on_start_tests"):
                getattr(backend, "on_start_tests")(items)

    if config.getoption("--runslow"):
        # --runslow given in cli: do not skip slow tests
        return
    skip_slow = pytest.mark.skip(reason="need --runslow option to run")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip_slow)


# TODO: The warnings below need to be dealt with, but for now we silence them.
@pytest.fixture(autouse=True)
def set_warnings():
    warnings.filterwarnings(
        "ignore",
        category=FutureWarning,
        message="\n\nsingle_target_shortest_path_length",
    )
    warnings.filterwarnings(
        "ignore",
        category=FutureWarning,
        message="\n\nshortest_path",
    )
    warnings.filterwarnings(
        "ignore", category=DeprecationWarning, message="\n\nThe `normalized`"
    )
    warnings.filterwarnings(
        "ignore", category=DeprecationWarning, message="\n\nall_triplets"
    )
    warnings.filterwarnings(
        "ignore", category=DeprecationWarning, message="\n\nrandom_triad"
    )
    warnings.filterwarnings(
        "ignore", category=DeprecationWarning, message="minimal_d_separator"
    )
    warnings.filterwarnings(
        "ignore", category=DeprecationWarning, message="d_separated"
    )
    warnings.filterwarnings("ignore", category=DeprecationWarning, message="\n\nk_core")
    warnings.filterwarnings(
        "ignore", category=DeprecationWarning, message="\n\nk_shell"
    )
    warnings.filterwarnings(
        "ignore", category=DeprecationWarning, message="\n\nk_crust"
    )
    warnings.filterwarnings(
        "ignore", category=DeprecationWarning, message="\n\nk_corona"
    )
    warnings.filterwarnings(
        "ignore", category=DeprecationWarning, message="\n\ntotal_spanning_tree_weight"
    )
    warnings.filterwarnings(
        "ignore", category=DeprecationWarning, message=r"\n\nThe 'create=matrix'"
    )
    warnings.filterwarnings(
        "ignore", category=DeprecationWarning, message="\n\n`compute_v_structures"
    )
    warnings.filterwarnings(
        "ignore", category=DeprecationWarning, message="Keyword argument 'link'"
    )


@pytest.fixture(autouse=True)
def add_nx(doctest_namespace):
    doctest_namespace["nx"] = networkx


# What dependencies are installed?

try:
    import numpy

    has_numpy = True
except ImportError:
    has_numpy = False

try:
    import scipy

    has_scipy = True
except ImportError:
    has_scipy = False

try:
    import matplotlib

    has_matplotlib = True
except ImportError:
    has_matplotlib = False

try:
    import pandas

    has_pandas = True
except ImportError:
    has_pandas = False

try:
    import pygraphviz

    has_pygraphviz = True
except ImportError:
    has_pygraphviz = False

try:
    import pydot

    has_pydot = True
except ImportError:
    has_pydot = False

try:
    import sympy

    has_sympy = True
except ImportError:
    has_sympy = False


# List of files that pytest should ignore

collect_ignore = []

needs_numpy = [
    "algorithms/approximation/traveling_salesman.py",
    "algorithms/centrality/current_flow_closeness.py",
    "algorithms/centrality/laplacian.py",
    "algorithms/node_classification.py",
    "algorithms/non_randomness.py",
    "algorithms/polynomials.py",
    "algorithms/shortest_paths/dense.py",
    "algorithms/tree/mst.py",
    "drawing/nx_latex.py",
    "generators/expanders.py",
    "linalg/bethehessianmatrix.py",
    "linalg/laplacianmatrix.py",
    "utils/misc.py",
]
needs_scipy = [
    "algorithms/approximation/traveling_salesman.py",
    "algorithms/assortativity/correlation.py",
    "algorithms/assortativity/mixing.py",
    "algorithms/assortativity/pairs.py",
    "algorithms/bipartite/matrix.py",
    "algorithms/bipartite/spectral.py",
    "algorithms/centrality/current_flow_betweenness.py",
    "algorithms/centrality/current_flow_betweenness_subset.py",
    "algorithms/centrality/eigenvector.py",
    "algorithms/centrality/katz.py",
    "algorithms/centrality/laplacian.py",
    "algorithms/centrality/second_order.py",
    "algorithms/centrality/subgraph_alg.py",
    "algorithms/communicability_alg.py",
    "algorithms/community/divisive.py",
    "algorithms/distance_measures.py",
    "algorithms/link_analysis/hits_alg.py",
    "algorithms/link_analysis/pagerank_alg.py",
    "algorithms/node_classification.py",
    "algorithms/similarity.py",
    "algorithms/tree/mst.py",
    "algorithms/walks.py",
    "convert_matrix.py",
    "drawing/layout.py",
    "drawing/nx_pylab.py",
    "generators/spectral_graph_forge.py",
    "generators/expanders.py",
    "linalg/algebraicconnectivity.py",
    "linalg/attrmatrix.py",
    "linalg/bethehessianmatrix.py",
    "linalg/graphmatrix.py",
    "linalg/laplacianmatrix.py",
    "linalg/modularitymatrix.py",
    "linalg/spectrum.py",
    "utils/rcm.py",
]
needs_matplotlib = ["drawing/nx_pylab.py", "generators/classic.py"]
needs_pandas = ["convert_matrix.py"]
needs_pygraphviz = ["drawing/nx_agraph.py"]
needs_pydot = ["drawing/nx_pydot.py"]
needs_sympy = ["algorithms/polynomials.py"]

if not has_numpy:
    collect_ignore += needs_numpy
if not has_scipy:
    collect_ignore += needs_scipy
if not has_matplotlib:
    collect_ignore += needs_matplotlib
if not has_pandas:
    collect_ignore += needs_pandas
if not has_pygraphviz:
    collect_ignore += needs_pygraphviz
if not has_pydot:
    collect_ignore += needs_pydot
if not has_sympy:
    collect_ignore += needs_sympy
