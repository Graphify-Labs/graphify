"""INC-QML-34: update shortcuts and raw writers reject corrupt logical pairs."""
from __future__ import annotations

import copy
import json
import os

import networkx as nx
import pytest

import graphify.__main__ as entrypoint
import graphify.build as builder
import graphify.export as export
import graphify.watch as watch
from graphify.cache import cache_dir
from graphify.paths import load_node_link_graph
from tests.test_qt_json_direction import damage


def update(root, monkeypatch, operation, *, raw, force=False):
    """An unchanged full refresh reaches comparison rather than the empty-batch shortcut."""
    if operation == "manual":
        monkeypatch.setattr(entrypoint, "_check_skill_version", lambda *_: None)
        monkeypatch.setattr(entrypoint, "_refresh_stale_skills", lambda: None)
        arguments = ["graphify", "update", str(root)]
        if raw:
            arguments.append("--no-cluster")
        if force:
            arguments.append("--force")
        monkeypatch.setattr(entrypoint.sys, "argv", arguments)
        entrypoint.main()
        return True
    return watch._rebuild_code(root, no_cluster=raw, force=force)


def snapshot(root, *, pin=False):
    output = root / "graphify-out"
    names = ("graph.json", ".graphify_root", "manifest.json", ".qt_analysis.json", "GRAPH_REPORT.md",
             ".graphify_labels.json", ".graphify_labels.json.sig")
    result = {}
    for name in names:
        path = output / name
        if path.is_file():
            if pin:
                before = path.stat()
                os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns - 10_000_000_000))
            result[name] = path.read_bytes(), path.stat().st_mtime_ns
    return result


def project(root, monkeypatch, operation, *, raw, directed=False):
    """Actual source-backed containment and QML reads supply both producer paths."""
    (root / "Main.qml").write_bytes(b"import QtQml\nQtObject { property int input: 1; property int output: input }")
    (root / "keep.py").write_bytes(b"def retained(): return 7\n")
    monkeypatch.chdir(root)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    assert update(root, monkeypatch, operation, raw=raw)
    if directed:
        # Directed updates inherit this public persisted profile. Serialized
        # endpoints are already their accepted logical pair in the real output.
        path = root / "graphify-out/graph.json"
        payload = json.loads(path.read_bytes())
        payload["directed"] = True
        path.write_text(json.dumps(payload), encoding="utf-8")
    assert update(root, monkeypatch, operation, raw=raw)
    assert load_node_link_graph(root / "graphify-out/graph.json").is_directed() == directed


def fault_actual_pair(monkeypatch, *, raw, corruption):
    """Fault only the actual builder/deduper output; never fake extraction or validation."""
    observed: dict = {"json_calls": 0}
    original_json = export.to_json

    def counted_json(*args, **kwargs):
        observed["json_calls"] += 1
        return original_json(*args, **kwargs)

    monkeypatch.setattr(export, "to_json", counted_json)
    if raw:
        original = builder.dedupe_edges

        def malformed_raw(edges):
            result = original(edges)
            edge = next(data for data in result if data.get("relation") == "contains")
            damage(edge, corruption, edge["source"], edge["target"])
            observed["before"] = copy.deepcopy(result)
            observed["output"] = result
            return result

        monkeypatch.setattr(builder, "dedupe_edges", malformed_raw)
    else:
        original = builder.build_from_json

        def malformed_graph(*args, **kwargs):
            graph = original(*args, **kwargs)
            source, target, edge = next((u, v, data) for u, v, data in graph.edges(data=True)
                                        if data.get("relation") == "contains"
                                        and (data.get("_src"), data.get("_tgt")) == (u, v))
            damage(edge, corruption, source, target)
            observed["before"] = copy.deepcopy(nx.node_link_data(graph, edges="links"))
            observed["output"] = graph
            return graph

        monkeypatch.setattr(builder, "build_from_json", malformed_graph)
    return observed


def assert_rejected(root, monkeypatch, operation, *, raw, force):
    if operation == "manual":
        with pytest.raises(SystemExit) as rejected:
            update(root, monkeypatch, operation, raw=raw, force=force)
        assert rejected.value.code == 1
    else:
        assert not update(root, monkeypatch, operation, raw=raw, force=force)


@pytest.mark.parametrize("operation", ["manual", "watch"])
@pytest.mark.parametrize("raw", [False, True])
@pytest.mark.parametrize("force", [False, True])
@pytest.mark.parametrize("corruption", ["partial_source", "partial_target", "foreign_source", "foreign_target",
                                      "list", "null", "collapsed", "reversed"])
def test_actual_corrupt_candidate_refuses_shortcut_publication_and_repairs(tmp_path, monkeypatch, capsys,
                                                                        operation, raw, force, corruption):
    """Force cannot grant invalid transport; the old cohort and cache survive refusal then a corrected retry."""
    project(tmp_path, monkeypatch, operation, raw=raw, directed=corruption == "reversed")
    prior = snapshot(tmp_path, pin=True)
    cached = {path: path.read_bytes() for path in cache_dir(tmp_path).rglob("*.json")}
    assert cached
    with monkeypatch.context() as fault:
        observed = fault_actual_pair(fault, raw=raw, corruption=corruption)
        assert_rejected(tmp_path, monkeypatch, operation, raw=raw, force=force)
    assert observed["json_calls"] == 0
    unchanged = observed["output"] if raw else nx.node_link_data(observed["output"], edges="links")
    assert unchanged == observed["before"]
    assert snapshot(tmp_path) == prior and all(path.read_bytes() == data for path, data in cached.items())
    diagnostic = capsys.readouterr().err
    assert "QT_EXPORT_DIRECTION" in diagnostic
    assert "private-needle" not in diagnostic and "forged diagnostic" not in diagnostic
    output = tmp_path / "graphify-out"
    assert not (output / ".graph.tmp.json").exists() and not list(output.glob(".gfy-publish-*"))
    assert update(tmp_path, monkeypatch, operation, raw=raw, force=force)
    assert snapshot(tmp_path) == prior
    assert update(tmp_path, monkeypatch, operation, raw=raw, force=force)
    assert snapshot(tmp_path) == prior
    # A real source change remains publishable after rejection and does not
    # become an idempotence shortcut because only run metadata was normalized.
    source = tmp_path / "Main.qml"
    source.write_bytes(source.read_bytes().replace(b"input", b"adjustment"))
    assert update(tmp_path, monkeypatch, operation, raw=raw, force=force)
    assert snapshot(tmp_path)["graph.json"][0] != prior["graph.json"][0]


@pytest.mark.parametrize("operation", ["manual", "watch"])
@pytest.mark.parametrize("raw", [False, True])
def test_complete_reverse_pair_remains_accepted_on_undirected_storage(tmp_path, monkeypatch, operation, raw):
    """A full reversal is permitted for undirected storage; only invalid pairs are refused."""
    project(tmp_path, monkeypatch, operation, raw=raw)
    with monkeypatch.context() as fault:
        fault_actual_pair(fault, raw=raw, corruption="reversed")
        assert update(tmp_path, monkeypatch, operation, raw=raw)
    assert (tmp_path / "graphify-out/graph.json").is_file()
