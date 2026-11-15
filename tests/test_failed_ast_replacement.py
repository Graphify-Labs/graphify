"""A failed producer cannot authorize replacement of its last good graph data."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

import graphify.__main__ as mainmod
import graphify.extract as extractmod
from graphify.build import build_merge, merge_raw_extraction


@pytest.mark.parametrize("empty", [False, True])
def test_failed_sources_are_not_successful_extraction_provenance(tmp_path, monkeypatch, empty):
    paths = [tmp_path / name for name in ("bad.py", "good.py", "skipped.py")]
    for path in paths:
        path.write_text("def helper(): return 1\n", encoding="utf-8")
    original = extractmod._DISPATCH[".py"]

    def extractor(path):
        if path.name == "bad.py":
            result: dict = {"nodes": [], "edges": []}
            if not empty:
                result["error"] = "simulated parser failure"
            return result
        if path.name == "skipped.py":
            return {"nodes": [], "edges": [], "skipped": "deliberate decline"}
        return original(path)

    monkeypatch.setitem(extractmod._DISPATCH, ".py", extractor)
    monkeypatch.setenv("GRAPHIFY_MAX_WORKERS", "1")
    result = extractmod.extract(paths, root=tmp_path, cache_root=tmp_path / "cache")

    assert result["failed_sources"] == [str(paths[0])]
    assert set(result["extracted_sources"]) == {str(paths[1]), str(paths[2])}
    assert result["skipped_sources"] == [str(paths[2])]


def _node(nid, source):
    return {"id": nid, "label": nid, "source_file": source, "source_location": "L1",
            "file_type": "code", "_origin": "ast"}


def test_error_payload_does_not_publish_partial_ast_records(tmp_path, monkeypatch):
    path = tmp_path / "bad.py"
    path.write_text("def helper(): return 1\n")
    monkeypatch.setenv("GRAPHIFY_MAX_WORKERS", "1")
    monkeypatch.setitem(extractmod._DISPATCH, ".py", lambda p: {
        "nodes": [_node("partial", str(p))], "edges": [], "error": "failed after one node",
    })
    result = extractmod.extract([path], root=tmp_path, cache_root=tmp_path / "cache")
    assert result["nodes"] == []
    assert result["failed_sources"] == [str(path)]
    assert result["extracted_sources"] == []


@pytest.mark.parametrize("raw", [False, True])
@pytest.mark.parametrize("explicit", [False, True])
def test_merge_preserves_failed_source_even_with_explicit_provenance(tmp_path, raw, explicit):
    graph_path = tmp_path / "graph.json"
    old = {"nodes": [_node("a", "bad.py"), _node("child", "bad.py"),
                     _node("b", "good.py"), _node("old", "good.py")],
           "edges": [{"source": "a", "target": "child", "relation": "calls",
                      "confidence": "EXTRACTED", "source_file": "bad.py"}],
           "hyperedges": [{"id": "group", "nodes": ["a", "child", "b"],
                           "label": "Group", "source_file": "bad.py",
                           "confidence": "INFERRED"}]}
    graph_path.write_text(json.dumps(old), encoding="utf-8")
    dispatched = [str(tmp_path / "bad.py"), str(tmp_path / "good.py")]
    fresh = {"nodes": [_node(nid, "good.py") for nid in ("b", "new1", "new2", "new3")],
             "edges": [], "extracted_sources": dispatched, "failed_sources": ["bad.py"]}
    if raw:
        result = merge_raw_extraction(deepcopy(fresh), graph_path, root=tmp_path,
                                      ast_sources=dispatched if explicit else None)
        ids = {n["id"] for n in result["nodes"]}
        assert any(e["source"] == "a" and e["target"] == "child" for e in result["edges"])
        assert result["hyperedges"] == old["hyperedges"]
    else:
        graph = build_merge([deepcopy(fresh)], graph_path=str(graph_path), root=tmp_path,
                            directed=True, dedup=False,
                            ast_sources=dispatched if explicit else None)
        ids = set(graph.nodes)
        assert graph.has_edge("a", "child")
        assert graph.nodes["a"]["source_file"] == "bad.py"
        assert graph.graph["hyperedges"][0]["nodes"] == ["a", "child", "b"]
    assert {"a", "child", "b", "new1", "new2", "new3"} == ids
    assert "old" not in ids


@pytest.mark.parametrize("raw", [False, True])
def test_deliberately_skipped_source_still_replaces_old_nodes(tmp_path, raw):
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps({"nodes": [_node("a", "bad.py")], "edges": []}))
    fresh = {"nodes": [], "edges": [], "extracted_sources": [str(tmp_path / "bad.py")],
             "skipped_sources": [str(tmp_path / "bad.py")], "failed_sources": []}
    if raw:
        assert merge_raw_extraction(fresh, graph_path, root=tmp_path)["nodes"] == []
    else:
        assert build_merge([fresh], graph_path=str(graph_path), root=tmp_path,
                           dedup=False).number_of_nodes() == 0


@pytest.mark.parametrize("raw", [False, True])
@pytest.mark.parametrize("no_dedup", [False, True])
@pytest.mark.parametrize("empty", [False, True])
def test_cli_retains_failed_records_updates_healthy_source_and_retries(
    tmp_path, monkeypatch, capsys, raw, no_dedup, empty,
):
    root = tmp_path / "project"
    root.mkdir()
    bad = root / "bad.py"
    good = root / "good.py"
    bad.write_text("def helper(): return leaf()\n\ndef leaf(): return 1\n")
    good.write_text("def old(): return 1\n")
    monkeypatch.setenv("GRAPHIFY_MAX_WORKERS", "1")
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    argv = ["graphify", "extract", str(root), "--code-only"]
    if raw:
        argv.append("--no-cluster")
    if no_dedup:
        argv.append("--no-dedup")

    def run():
        monkeypatch.setattr(mainmod.sys, "argv", argv)
        try:
            mainmod.main()
        except SystemExit as exc:
            assert exc.code in (None, 0)

    graph_path = root / "graphify-out/graph.json"
    run()
    before = json.loads(graph_path.read_text())
    old_bad = {n["id"]: n for n in before["nodes"] if n.get("source_file") == "bad.py"}
    assert len(old_bad) == 3
    capsys.readouterr()
    bad.write_text("def helper(): return 2\n\ndef added(): return 3\n")
    good.write_text("\n".join(f"def new{i}(): return {i}\n" for i in range(4)))
    original = extractmod._DISPATCH[".py"]
    state = {"fail": True}

    def extractor(path):
        if path == bad and state["fail"]:
            return {"nodes": [], "edges": [], **({} if empty else {"error": "simulated failure"})}
        return original(path)

    monkeypatch.setitem(extractmod._DISPATCH, ".py", extractor)
    run()
    output = capsys.readouterr()
    after = json.loads(graph_path.read_text())
    by_id = {n["id"]: n for n in after["nodes"]}
    for nid, node in old_bad.items():
        assert nid in by_id
        for key in ("label", "source_file", "source_location", "_origin"):
            assert by_id[nid].get(key) == node.get(key)
    labels = {n["label"] for n in after["nodes"]}
    assert "new3()" in labels and "old()" not in labels
    edges = after.get("edges", after.get("links", []))
    assert any(e.get("source_file") == "bad.py" and e.get("relation") == "calls" for e in edges)
    assert "incomplete" in (output.out + output.err).lower()
    manifest = json.loads((root / "graphify-out/manifest.json").read_text())
    assert not manifest["bad.py"]["ast_hash"]
    assert manifest["good.py"]["ast_hash"]

    state["fail"] = False
    run()
    recovered = json.loads(graph_path.read_text())
    labels = {n["label"] for n in recovered["nodes"] if n.get("source_file") == "bad.py"}
    assert "added()" in labels and "leaf()" not in labels
    manifest = json.loads((root / "graphify-out/manifest.json").read_text())
    assert manifest["bad.py"]["ast_hash"]
