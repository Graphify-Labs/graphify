"""#4942: opt-in line-oriented graph.json.

The default stays the single compact line from #3413. With
``GRAPHIFY_GRAPH_JSON_LINES=1`` every project-graph writer emits one node or
link per line, sorted deterministically, while the parsed content is unchanged.
"""
from __future__ import annotations

import json
from pathlib import Path

import networkx as nx

from graphify.export import to_json
from graphify.watch import _rebuild_code


def _graph() -> nx.Graph:
    G = nx.Graph()
    # Insert out of id order: the writer must sort nodes and links itself.
    G.add_node("b", label="b", file_type="code", source_file="a.py", community=0)
    G.add_node("a", label="a", file_type="code", source_file="a.py", community=0)
    G.add_edge("b", "a", relation="calls", confidence="EXTRACTED", source_file="a.py")
    return G


def _assert_line_oriented(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    assert text.endswith("\n")
    data = json.loads(text)
    lines = text.splitlines()
    assert lines[0] == "{" and lines[-1] == "}"

    records = {line[:-1] if line.endswith(",") else line for line in lines}
    for node in data["nodes"]:
        assert json.dumps(node, ensure_ascii=False, sort_keys=True, separators=(",", ":")) in records
    for link in data["links"]:
        assert json.dumps(link, ensure_ascii=False, sort_keys=True, separators=(",", ":")) in records

    assert [node["id"] for node in data["nodes"]] == sorted(
        node["id"] for node in data["nodes"]
    )
    assert [
        (link["source"], link["target"], link["relation"]) for link in data["links"]
    ] == sorted(
        (link["source"], link["target"], link["relation"]) for link in data["links"]
    )
    return data


def test_to_json_honors_graph_json_lines(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHIFY_GRAPH_JSON_LINES", "1")
    out = tmp_path / "graph.json"

    assert to_json(_graph(), {0: ["a", "b"]}, str(out), force=True)

    data = _assert_line_oriented(out)
    assert {node["id"] for node in data["nodes"]} == {"a", "b"}
    assert len(data["links"]) == 1


def test_to_json_defaults_to_one_compact_line(tmp_path, monkeypatch):
    monkeypatch.delenv("GRAPHIFY_GRAPH_JSON_LINES", raising=False)
    out = tmp_path / "graph.json"

    assert to_json(_graph(), {0: ["a", "b"]}, str(out), force=True)

    text = out.read_text(encoding="utf-8")
    assert len(text.splitlines()) == 1
    assert json.loads(text)["nodes"]


def test_graph_json_lines_accepts_false_values(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHIFY_GRAPH_JSON_LINES", "false")
    out = tmp_path / "graph.json"

    assert to_json(_graph(), {0: ["a", "b"]}, str(out), force=True)

    assert len(out.read_text(encoding="utf-8").splitlines()) == 1



def test_enabling_the_flag_rewrites_an_existing_compact_graph(tmp_path, monkeypatch):
    (tmp_path / "app.py").write_text(
        "def alpha():\n    return beta()\n\n\ndef beta():\n    return 1\n",
        encoding="utf-8",
    )
    graph = tmp_path / "graphify-out" / "graph.json"

    monkeypatch.delenv("GRAPHIFY_GRAPH_JSON_LINES", raising=False)
    assert _rebuild_code(tmp_path, acquire_lock=False) is True
    assert len(graph.read_text(encoding="utf-8").splitlines()) == 1

    monkeypatch.setenv("GRAPHIFY_GRAPH_JSON_LINES", "1")
    assert _rebuild_code(tmp_path, acquire_lock=False) is True
    _assert_line_oriented(graph)
