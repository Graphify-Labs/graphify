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
