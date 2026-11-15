"""Loading graph.json must not hold the parsed rows and the graph at the same time."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from networkx.readwrite import json_graph

from graphify.paths import consumed, load_node_link_graph, restore_arc_direction


def _graph_file(tmp_path: Path, nodes: list, links: list) -> Path:
    path = tmp_path / "graph.json"
    path.write_text(json.dumps({"directed": False, "multigraph": True, "graph": {}, "nodes": nodes, "links": links}))
    return path


def test_load_gives_the_same_graph_as_a_plain_load(tmp_path: Path) -> None:
    path = _graph_file(
        tmp_path,
        [{"id": "b", "source_file": "x.py"}, {"id": "a", "source_file": "x.py"}],
        [
            {"source": "b", "target": "a", "relation": "calls", "key": 0},
            {"source": "b", "target": "a", "relation": "imports", "key": 1},
            {"source": "a", "target": "b", "relation": "uses", "_src": "b", "_tgt": "a", "key": 2},
        ],
    )
    plain = json_graph.node_link_graph(restore_arc_direction(json.loads(path.read_text())), edges="links")

    loaded = load_node_link_graph(path)

    assert list(loaded.nodes(data=True)) == list(plain.nodes(data=True))
    assert list(loaded.edges(keys=True, data=True)) == list(plain.edges(keys=True, data=True))


def test_rows_share_their_repeated_strings(tmp_path: Path) -> None:
    path = _graph_file(tmp_path, [{"id": "a", "source_file": "x.py"}, {"id": "b", "source_file": "x.py"}], [])

    graph = load_node_link_graph(path)

    assert graph.nodes["a"]["source_file"] is graph.nodes["b"]["source_file"]


def test_consumed_lets_go_of_each_row_in_order() -> None:
    rows = [{"id": "a"}, {"id": "b"}]
    stream = consumed(rows)

    assert next(stream) == {"id": "a"}
    assert rows == [{"id": "b"}]
    assert next(stream) == {"id": "b"}
    assert rows == []


def test_a_bad_row_fails_and_never_gives_a_partial_graph(tmp_path: Path) -> None:
    path = _graph_file(tmp_path, [{"id": "a"}, {"id": {"unhashable": 1}}, {"id": "c"}], [])

    with pytest.raises(TypeError):
        load_node_link_graph(path)
