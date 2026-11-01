"""D33: one raw baseline validates before parser/cache work and stays unmodified."""
from __future__ import annotations

import copy
import json

import pytest

import graphify.build as builder
import graphify.extract as extraction
import graphify.watch as watcher
from tests.test_qt_cpp_file_roles import cpp_fixture
from tests.test_qt_import_retention import FIELD, payload


def test_raw_loader_keeps_provenance_and_four_tuple_loader_compatibility(tmp_path):
    """The raw owner returns fresh unmodified data; the legacy adapter alone stamps."""
    data = payload()
    data["nodes"].append({"id": "backend", "label": "backend.cpp", "file_type": "code",
                          "source_file": "backend.cpp", "source_location": "L1", "_origin": "ast"})
    data["links"] = [{"source": "backend", "target": "missing", "relation": "imports", "context": "import",
                      "source_file": "backend.cpp", "source_location": "L1", "confidence": "EXTRACTED"}]
    path = tmp_path / "graph.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    raw = builder._read_existing_graph_data(path)
    assert raw is not None and raw == data and "_origin" not in raw["links"][0]
    before = copy.deepcopy(raw)
    policy = {}
    loaded = builder._load_existing_graph(path, retention_policy=policy)
    assert loaded is not None and len(loaded) == 4 and loaded[1][0]["_origin"] == "ast"
    assert policy["ids"] == frozenset({"missing"}) and raw == before


def test_raw_loader_retains_missing_parse_and_size_cap_outcomes(tmp_path, monkeypatch):
    """The new early owner does not reinterpret existing load failure contracts."""
    import graphify.security as security
    path = tmp_path / "graph.json"
    assert builder._read_existing_graph_data(path) is None
    assert builder._load_existing_graph(path) is None
    path.write_bytes(b"{")
    with pytest.raises(RuntimeError, match="Cannot read"):
        builder._read_existing_graph_data(path)
    with pytest.raises(RuntimeError, match="Cannot read"):
        builder._load_existing_graph(path)
    path.write_text(json.dumps(payload()), encoding="utf-8")
    monkeypatch.setenv("GRAPHIFY_MAX_GRAPH_BYTES", "1")
    assert security._max_graph_file_bytes() == 1
    with pytest.raises(ValueError):
        builder._read_existing_graph_data(path)
    with pytest.raises(ValueError):
        builder._load_existing_graph(path)


def test_watch_passes_single_raw_baseline_before_dispatch_without_borrowed_mutation(tmp_path, monkeypatch):
    """The real watcher binds raw load → extract → reconcile, without a second baseline."""
    cpp_fixture(tmp_path)
    keep = tmp_path / "keep.py"
    keep.write_text("def keep(): return 7\n", encoding="utf-8")
    assert watcher._rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    output = tmp_path / "graphify-out/graph.json"
    data = json.loads(output.read_text(encoding="utf-8"))
    edge = next(edge for edge in data["links"] if edge.get("relation") == "imports")
    edge.pop("_origin", None)
    edge["source_location"] = "L1"
    output.write_text(json.dumps(data), encoding="utf-8")
    events, snapshots = [], []
    real_load, real_extract, real_reconcile = (builder._read_existing_graph_data, extraction.extract,
                                               watcher._reconcile_existing_graph)
    def load(path):
        events.append("load")
        result = real_load(path)
        snapshots.append((result, copy.deepcopy(result)))
        return result
    def extract(*args, **kwargs):
        events.append("extract")
        return real_extract(*args, **kwargs)
    def reconcile(*args, **kwargs):
        events.append("reconcile")
        assert kwargs["preflight_done"] and kwargs["prior_graph_data"] is snapshots[0][0]
        return real_reconcile(*args, **kwargs)
    monkeypatch.setattr(builder, "_read_existing_graph_data", load)
    monkeypatch.setattr(extraction, "extract", extract)
    monkeypatch.setattr(watcher, "_reconcile_existing_graph", reconcile)
    keep.write_text("def keep(): return 8\n", encoding="utf-8")
    assert watcher._rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    assert events == ["load", "extract", "reconcile"]
    assert snapshots[0][0] == snapshots[0][1]


def test_corrupt_context_never_dispatches_an_extractor_or_creates_cache(tmp_path, monkeypatch, capsys):
    """An integrity refusal is earlier than real parser/AST-cache side effects."""
    from tests.test_qt_readonly_publication import durable
    cpp_fixture(tmp_path)
    keep = tmp_path / "keep.py"
    keep.write_text("def keep(): return 7\n", encoding="utf-8")
    assert watcher._rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    output = tmp_path / "graphify-out/graph.json"
    data = json.loads(output.read_text(encoding="utf-8"))
    data.setdefault("graph", {})[FIELD] = {"schema": 1, "ids": ["absent"]}
    output.write_text(json.dumps(data), encoding="utf-8")
    before, calls = durable(tmp_path), []
    real = extraction.extract
    def record(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)
    monkeypatch.setattr(extraction, "extract", record)
    keep.write_text("def keep(): return 8\n", encoding="utf-8")
    assert not watcher._rebuild_code(tmp_path, force=True, no_cluster=True, acquire_lock=False)
    assert calls == [] and durable(tmp_path) == before
    captured = capsys.readouterr()
    assert "QT_IMPORT_RETENTION_INVALID" in captured.out + captured.err
