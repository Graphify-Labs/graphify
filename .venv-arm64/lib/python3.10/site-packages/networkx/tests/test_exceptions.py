import pytest

import networkx as nx

# smoke tests for exceptions


def test_raises_networkxexception():
    with pytest.raises(nx.NetworkXException):
        raise nx.NetworkXException


def test_raises_networkxerr():
    with pytest.raises(nx.NetworkXError):
        raise nx.NetworkXError


def test_raises_networkx_pointless_concept():
    with pytest.raises(nx.NetworkXPointlessConcept):
        raise nx.NetworkXPointlessConcept


def test_raises_networkxalgorithmerr():
    with pytest.raises(nx.NetworkXAlgorithmError):
        raise nx.NetworkXAlgorithmError


def test_raises_networkx_unfeasible():
    with pytest.raises(nx.NetworkXUnfeasible):
        raise nx.NetworkXUnfeasible


def test_raises_networkx_no_path():
    with pytest.raises(nx.NetworkXNoPath):
        raise nx.NetworkXNoPath


def test_raises_networkx_unbounded():
    with pytest.raises(nx.NetworkXUnbounded):
        raise nx.NetworkXUnbounded
