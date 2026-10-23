"""get_neighbors names the files that import a file.

`from pkg.cache import save` is extracted as an edge to `save()`, not to
`cache.py`, so a file's own predecessors missed every importer that imports
names rather than the module. Agents asking "which modules import cache.py?"
got half the answer (#985 benchmark).
"""
import networkx as nx

from graphify.serve import _file_importers, _is_file_node, _neighbors_text


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



def test_is_file_node_matches_label_to_file_name():
    G = _graph()
    assert _is_file_node(G.nodes["cache"])
    assert not _is_file_node(G.nodes["save"])
    assert _is_file_node({"label": "x.py", "source_file": "a\\b\\x.py"})
    assert not _is_file_node({"label": "x.py"})


def test_file_importers_rolls_symbol_imports_up_to_the_file():
    importers = _file_importers(_graph(), "cache")
    assert set(importers) == {"cli", "detect", "test_cache"}
    assert sorted(importers["cli"]) == ["load", "save"]
    assert importers["detect"] == []  # direct module import


def test_neighbors_of_file_names_every_importer_first():
    out = _neighbors_text(_graph(), "cache")
    lines = out.splitlines()
    assert lines[0] == "Neighbors of cache.py:"
    # Source files before tests in the summary line.
    assert lines[1] == "  Imported by 3 (directly or via symbols defined here): cli.py, detect.py, test_cache.py"
    assert lines[2].startswith("  <-- cli.py [imports] [EXTRACTED] via ")
    assert "save()" in lines[2] and "load()" in lines[2] and lines[2].endswith("at=pkg/cli.py:L3")
    # The direct module import joins the top section (an agent reading only the
    # importer lines missed it when it sat below the contains list) and is not
    # repeated in the regular section.
    assert lines[3] == "  <-- detect.py [imports_from] [EXTRACTED] at=pkg/detect.py:L5"
    assert lines[4].startswith("  <-- test_cache.py [imports] [EXTRACTED] via save()")
    assert sum("<-- detect.py [imports_from]" in l for l in lines) == 1


def test_neighbors_importer_rollup_respects_relation_filter():
    G = _graph()
    assert "Imported by" not in _neighbors_text(G, "cache", "contains")
    assert "Imported by" in _neighbors_text(G, "cache", "import")


def test_neighbors_of_symbol_or_unimported_file_is_unchanged():
    G = _graph()
    # A symbol node gets no roll-up.
    assert "Imported by" not in _neighbors_text(G, "save")
    # A file only imported as a module keeps the old output exactly.
    G.remove_edge("cli", "save")
    G.remove_edge("cli", "load")
    G.remove_edge("test_cache", "save")
    out = _neighbors_text(G, "cache")
    assert out == "\n".join([
        "Neighbors of cache.py:",
        "  --> save() [contains] [EXTRACTED]",
        "  --> load() [contains] [EXTRACTED]",
        "  <-- detect.py [imports_from] [EXTRACTED] at=pkg/detect.py:L5",
    ])
