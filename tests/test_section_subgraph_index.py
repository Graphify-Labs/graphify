"""get_section retry on the section view must not share the full graph's caches (#5385)."""
import networkx as nx
import pytest

from graphify.serve import _get_trigram_index, _resolve_single_node
from graphify.sections import resolve_section_query


def _graph():
    G = nx.Graph()
    G.add_node("readme_intro", label="Intro", node_kind="heading",
               source_file="README.md", source_location="L1")
    G.add_node("deploy_sh", label="deploy.sh", file_type="code", source_file="deploy.sh")
    G.add_node("deploy_sh_rationale", label="deploy.sh rationale",
               file_type="rationale", source_file="deploy.sh")
    for i in range(50):
        G.add_node(f"filler_{i}", label=f"filler {i}", file_type="code", source_file=f"f{i}.py")
    return G


@pytest.mark.parametrize("warm", [False, True])
def test_non_section_query_does_not_raise(warm):
    G = _graph()
    if warm:
        _get_trigram_index(G)
    cold = resolve_section_query(_graph(), "deploy")
    assert resolve_section_query(G, "deploy") == cold


def test_retry_does_not_replace_full_graph_index():
    G = _graph()
    resolve_section_query(G, "deploy")
    assert len(_get_trigram_index(G)["ids"]) == G.number_of_nodes()
    assert _resolve_single_node(G, "filler 7")[0] == "filler_7"


def test_heading_still_resolves_with_warm_index():
    G = _graph()
    _get_trigram_index(G)
    assert resolve_section_query(G, "Intro") == ("readme_intro", "")


def _retry_view(monkeypatch, G):
    from graphify import serve

    calls = []
    original = serve._resolve_single_node

    def spy(graph, query):
        calls.append((graph, query))
        return original(graph, query)

    monkeypatch.setattr(serve, "_resolve_single_node", spy)
    resolve_section_query(G, "deploy")
    assert len(calls) == 2
    return calls[1][0]


def test_retry_uses_isolated_section_view(monkeypatch):
    G = _graph()
    G.graph["_logical_directed"] = False
    _get_trigram_index(G)
    full_index = G.graph["_trigram_index"]

    view = _retry_view(monkeypatch, G)

    assert set(view.nodes) == {"readme_intro"}
    assert view.graph is not G.graph
    assert view.graph["_logical_directed"] is False
    assert view.graph.get("_trigram_index") is not full_index


def test_retry_drops_unknown_future_cache(monkeypatch):
    G = _graph()
    G.graph["_some_new_cache"] = {"full_graph_only": True}

    view = _retry_view(monkeypatch, G)

    assert "_some_new_cache" not in view.graph
