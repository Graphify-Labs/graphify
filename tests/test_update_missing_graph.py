"""A manifest cannot stand in for the graph an incremental update merges into."""

import json

import pytest

from graphify.watch import _rebuild_code


@pytest.mark.parametrize("change_one_source", [False, True])
def test_update_recreates_missing_graph_with_all_sources(tmp_path, change_one_source):
    first = tmp_path / "first.py"
    first.write_text("def first(): return 1\n", encoding="utf-8")
    (tmp_path / "second.py").write_text("def second(): return 2\n", encoding="utf-8")
    out = tmp_path / "graphify-out"
    graph = out / "graph.json"
    assert _rebuild_code(tmp_path, no_cluster=True)
    assert (out / "manifest.json").is_file()
    graph.unlink()
    if change_one_source:
        first.write_text("def renamed(): return 123\n", encoding="utf-8")

    assert _rebuild_code(tmp_path, no_cluster=True, incremental=True)

    labels = {node["label"] for node in json.loads(graph.read_text(encoding="utf-8"))["nodes"]}
    assert "second()" in labels
    assert ("renamed()" if change_one_source else "first()") in labels
