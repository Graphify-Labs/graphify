"""`graphify extract` frees its whole-graph intermediates without changing output.

to_json kept copies of the old and new graphs alive through the write.
Releasing them early must not change a byte of graph.json. (Python parse trees
are covered by test_python_parse_release.py.)
"""
from __future__ import annotations

import json
import shutil

import networkx as nx
import pytest

import graphify.export as export_mod
from graphify.export import to_json

# to_json output for _graph() below, as written before the memory changes.
EXPECTED_GRAPH_JSON = (
    '{"directed":false,"multigraph":false,"graph":{"hyperedges":[{"id":"h1","nodes":["a","b","c"],'
    '"relation":"group"}],"schema_version":1},"nodes":[{"id":"a","label":"A","community":0,'
    '"file_type":"code","norm_label":"a","source_file":"a.py"},{"id":"b","label":"B","community":0,'
    '"file_type":"code","norm_label":"b","source_file":"b.py"},{"id":"c","label":"C","community":1,'
    '"file_type":"document","norm_label":"c","source_file":"c.md"}],"links":[{"source":"b",'
    '"target":"a","relation":"calls","confidence":"EXTRACTED","confidence_score":1.0},'
    '{"source":"b","target":"c","relation":"references","confidence":"INFERRED",'
    '"confidence_score":0.55}],"hyperedges":[{"id":"h1","nodes":["a","b","c"],"relation":"group"}],'
    '"built_at_commit":"abc"}'
)


def _graph(*, hyperedges: bool = True) -> nx.Graph:
    G = nx.Graph()
    # `id` stored inline on one node: canonicalization must still put it first.
    G.add_node("b", label="B", file_type="code", source_file="b.py", id="b")
    G.add_node("a", label="A", file_type="code", source_file="a.py")
    G.add_node("c", label="C", file_type="document", source_file="c.md")
    G.add_edge("a", "b", relation="calls", confidence="EXTRACTED", _src="b", _tgt="a")
    G.add_edge("b", "c", relation="references", confidence="INFERRED")
    if hyperedges:
        G.graph["hyperedges"] = [{"id": "h1", "nodes": ["a", "b", "c"], "relation": "group"}]
    return G


def test_to_json_bytes_unchanged_on_forced_and_guarded_writes(tmp_path, monkeypatch):
    monkeypatch.setattr(export_mod, "_graphify_version", lambda: None)
    communities = {0: ["a", "b"], 1: ["c"]}
    forced = tmp_path / "forced.json"
    assert to_json(_graph(), communities, str(forced), force=True, built_at_commit="abc")
    assert forced.read_text(encoding="utf-8") == EXPECTED_GRAPH_JSON

    # The guarded write parses the existing file and frees it before exporting.
    guarded = tmp_path / "guarded.json"
    shutil.copy(forced, guarded)
    assert to_json(_graph(), communities, str(guarded), force=False, built_at_commit="abc")
    assert guarded.read_bytes() == forced.read_bytes()


def test_to_json_hyperedge_wipe_warning_still_reads_previous_graph(tmp_path, capsys):
    out = tmp_path / "graph.json"
    to_json(_graph(), {0: ["a", "b", "c"]}, str(out), force=True, built_at_commit="abc")
    assert to_json(_graph(hyperedges=False), {0: ["a", "b", "c"]}, str(out),
                   force=True, built_at_commit="abc")
    assert "already holds 1 hyperedge(s)" in capsys.readouterr().err
    assert json.loads(out.read_text(encoding="utf-8"))["hyperedges"] == []
