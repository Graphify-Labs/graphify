"""Retained community-state tests omitted during the native serve conversion."""

from graphify.serve import _communities_from_graph
from graphify.helix.state import community_records, new_state
from tests.native_helpers import make_loaded


def _loaded(nodes, communities):
    state = new_state(communities=community_records(communities))
    return make_loaded(nodes=nodes, state=state)


def test_communities_from_graph_basic():
    loaded = _loaded(
        [{"id": "n1"}, {"id": "n2"}, {"id": "n3"}],
        {0: ["n1", "n2"], 1: ["n3"]},
    )
    assert _communities_from_graph(loaded) == {0: ["n1", "n2"], 1: ["n3"]}


def test_communities_from_graph_no_community_attr():
    loaded = _loaded([{"id": "a", "label": "foo"}], {})
    assert _communities_from_graph(loaded) == {}


def test_communities_from_graph_isolated():
    loaded = _loaded([{"id": "a"}, {"id": "b"}], {0: ["a"], 2: ["b"]})
    assert _communities_from_graph(loaded) == {0: ["a"], 2: ["b"]}
