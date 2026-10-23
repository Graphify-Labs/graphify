"""query_graph seeds from a file the question names, and lists who imports it.

Term splitting turned `pkg/cache.py` into `pkg`, `cache`, `py`, so the file was
not even a seed, and the traversal missed importers that import names rather
than the module (#985 benchmark).
"""
import networkx as nx

from graphify.serve import _mentioned_file_nodes, _query_graph_text


def _graph() -> nx.DiGraph:
    G = nx.DiGraph()
    G.add_node("cache", label="cache.py", source_file="pkg/cache.py", source_location="L1")
    G.add_node("save", label="save()", source_file="pkg/cache.py", source_location="L10")
    G.add_node("load", label="load()", source_file="pkg/cache.py", source_location="L20")
    G.add_node("cli", label="cli.py", source_file="pkg/cli.py", source_location="L1")
    G.add_node("detect", label="detect.py", source_file="pkg/detect.py", source_location="L1")
    G.add_node("test_cache", label="test_cache.py", source_file="tests/test_cache.py", source_location="L1")
    G.add_edge("cache", "save", relation="contains", confidence="EXTRACTED")
    G.add_edge("cache", "load", relation="contains", confidence="EXTRACTED")
    # cli.py: `from pkg.cache import save, load` -> edges to the symbols only.
    G.add_edge("cli", "save", relation="imports", confidence="EXTRACTED",
               source_file="pkg/cli.py", source_location="L3")
    G.add_edge("cli", "load", relation="imports", confidence="EXTRACTED",
               source_file="pkg/cli.py", source_location="L3")
    # detect.py: `from pkg import cache` -> edge to the module.
    G.add_edge("detect", "cache", relation="imports_from", confidence="EXTRACTED",
               source_file="pkg/detect.py", source_location="L5")
    G.add_edge("test_cache", "save", relation="imports", confidence="EXTRACTED",
               source_file="tests/test_cache.py", source_location="L2")
    return G



def test_mentioned_file_resolves_by_path_or_unique_name():
    G = _graph()
    assert _mentioned_file_nodes(G, "who imports pkg/cache.py?") == ["cache"]
    assert _mentioned_file_nodes(G, "who imports cache.py and ./pkg\\cli.py") == ["cache", "cli"]
    # Not file names: abbreviations, versions, words.
    assert _mentioned_file_nodes(G, "e.g. in v0.9 the cache") == []


def test_mentioned_file_that_names_several_files_seeds_none():
    G = _graph()
    G.add_node("init_a", label="__init__.py", source_file="pkg/__init__.py")
    G.add_node("init_b", label="__init__.py", source_file="other/__init__.py")
    assert _mentioned_file_nodes(G, "what imports __init__.py") == []
    assert _mentioned_file_nodes(G, "what imports other/__init__.py") == ["init_b"]


def test_query_naming_a_file_seeds_it_and_lists_its_importers():
    G = _graph()
    # An exact `cache` label outscores the file on the split term and took its seat.
    G.add_node("cache_fn", label="cache()", source_file="pkg/memo.py", source_location="L3")
    out = _query_graph_text(G, "which modules import pkg/cache.py?",
                            mode="bfs", depth=1, token_budget=2000)
    assert "Start: ['cache.py'" in out
    assert ("cache.py is imported by 3 files (directly or via symbols defined in it): "
            "pkg/cli.py, pkg/detect.py, tests/test_cache.py") in out


def test_query_importer_summary_needs_a_directed_graph():
    # The CLI loads the graph undirected; importers cannot be told apart there.
    out = _query_graph_text(_graph().to_undirected(), "which modules import pkg/cache.py?",
                            mode="bfs", depth=1, token_budget=2000)
    assert "Start: ['cache.py'" in out
    assert "is imported by" not in out
