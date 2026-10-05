"""INC-QML-49: preserved upstream links share Qt's durable export validation."""
from __future__ import annotations

import copy
import json

import networkx as nx
import pytest

import graphify.__main__ as mainmod
from graphify.export import to_json
from graphify.extractors.qml_facts import qml_metadata
from graphify.paths import load_node_link_graph
from tests.test_qt_json_direction import actual_graph, damage


def mixed_graph(root):
    """Real QML facts and ordinary parallel transport exercise one output boundary."""
    graph, source, target = actual_graph(root)
    # Reverse undirected insertion order to make raw storage differ from the
    # accepted QML read direction; generic links have no Qt marker transport.
    reversed_graph = nx.Graph()
    reversed_graph.add_node(target, **graph.nodes[target])
    reversed_graph.add_nodes_from((key, data) for key, data in graph.nodes(data=True) if key != target)
    reversed_graph.add_edges_from((v, u, copy.deepcopy(data)) for u, v, data in graph.edges(data=True))
    reversed_graph.add_node("ordinary_caller", label="caller", source_file="ordinary.py", file_type="code")
    reversed_graph.add_node("ordinary_target", label="target", source_file="ordinary.py", file_type="code")
    reversed_graph.add_edge("ordinary_caller", "ordinary_target", relation="calls", confidence="EXTRACTED")
    links = copy.deepcopy(nx.node_link_data(reversed_graph, edges="links")["links"])
    links.append({"source": "ordinary_caller", "target": "ordinary_target",
                  "relation": "imports", "confidence": "EXTRACTED"})
    return reversed_graph, links, source, target


def assert_preserved(path, source, target):
    """The durable file keeps both generic mechanisms and the actual QML proof."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    ordinary = [link for link in payload["links"] if link["source"] == "ordinary_caller"]
    assert {link["relation"] for link in ordinary} == {"calls", "imports"} and len(ordinary) == 2
    read = next(link for link in payload["links"] if link.get("context") == "qml_binding_read")
    assert (read["source"], read["target"]) == (source, target)
    assert read["source_location"] and qml_metadata(read)
    assert "_src" not in read and "_tgt" not in read
    loaded = load_node_link_graph(path)
    assert loaded.has_edge(source, target)
    assert loaded.nodes[source]["source_file"] == "Main.qml"
    return payload


def test_req_qml_010_ac02_original_parallel_links_retain_qml_direction(tmp_path):
    """Upstream's original-link path preserves distinct relations and Qt source provenance."""
    graph, links, source, target = mixed_graph(tmp_path)
    before = copy.deepcopy(nx.node_link_data(graph, edges="links")), copy.deepcopy(links)
    path = tmp_path / "graph.json"
    assert to_json(graph, {}, str(path), original_links=links, built_at_commit="fixed")
    assert_preserved(path, source, target)
    assert (nx.node_link_data(graph, edges="links"), links) == before
    accepted = path.read_bytes()
    assert to_json(graph, {}, str(path), original_links=links, built_at_commit="fixed")
    assert path.read_bytes() == accepted


@pytest.mark.parametrize("force", [False, True])
@pytest.mark.parametrize("corruption", ["partial_source", "foreign_target", "list", "collapsed"])
def test_req_qml_018_ac06_preserved_invalid_link_refuses_replacement(tmp_path, capsys, force, corruption):
    """A corrupt original link cannot hide behind the simple graph's accepted edge."""
    graph, links, source, target = mixed_graph(tmp_path)
    path = tmp_path / "previous.json"
    assert to_json(graph, {}, str(path), original_links=links, built_at_commit="fixed")
    accepted, stamp = path.read_bytes(), path.stat().st_mtime_ns
    malformed = copy.deepcopy(links)
    read = next(link for link in malformed if link.get("context") == "qml_binding_read")
    damage(read, corruption, source, target)
    before = copy.deepcopy(malformed), copy.deepcopy(nx.node_link_data(graph, edges="links"))
    assert to_json(graph, {}, str(path), original_links=malformed, force=force, built_at_commit="fixed") is False
    assert path.read_bytes() == accepted and path.stat().st_mtime_ns == stamp
    diagnostic = capsys.readouterr().err
    assert "QT_EXPORT_DIRECTION" in diagnostic and "private-needle" not in diagnostic
    assert (malformed, nx.node_link_data(graph, edges="links")) == before
    assert to_json(graph, {}, str(path), original_links=links, built_at_commit="fixed")
    assert path.read_bytes() == accepted
    assert_preserved(path, source, target)


def test_req_qml_018_ac04_real_recluster_keeps_parallel_and_qml_links(tmp_path, monkeypatch, capsys):
    """The production offline CLI reloads and writes every original relationship twice."""
    graph, links, source, target = mixed_graph(tmp_path)
    out = tmp_path / "graphify-out"
    out.mkdir()
    path = out / "graph.json"
    assert to_json(graph, {}, str(path), original_links=links, built_at_commit="fixed")
    previous = assert_preserved(path, source, target)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv", ["graphify", "cluster-only", str(tmp_path), "--no-viz", "--no-label"])
    for _ in range(2):
        mainmod.main()
        current = assert_preserved(path, source, target)
        assert current["links"] == previous["links"]
        assert current["built_at_commit"] == "fixed"
        assert "Done -" in capsys.readouterr().out
