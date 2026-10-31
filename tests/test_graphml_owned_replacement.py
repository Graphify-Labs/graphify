"""REQ-QML-012/013/018: GraphML owns its product rejection and recovery policy."""
from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
import stat

import networkx as nx
import pytest

import graphify.export as export


def graph():
    """Nested attributes expose accidental caller mutation during serialization."""
    result = nx.Graph(review={"labels": ["retained"]})
    result.add_node("a", label="A", metadata={"roles": ["source"]})
    result.add_node("b", label="B")
    result.add_edge("a", "b", relation="uses", confidence="EXTRACTED")
    return result


def snapshot(value):
    return deepcopy((value.graph, list(value.nodes(data=True)), list(value.edges(data=True))))


def assert_published(target, original, before):
    """Actual GraphML reload and repeat export prove a completed, stable write."""
    loaded = nx.read_graphml(target)
    assert loaded.nodes["a"]["label"] == "A" and loaded.has_edge("a", "b")
    accepted = target.read_bytes()
    export.to_graphml(original, {}, str(target))
    assert target.read_bytes() == accepted
    assert snapshot(original) == before
    assert not target.with_name(target.name + ".tmp").exists()


@pytest.mark.skipif(os.name != "nt", reason="Native Windows read-only destination contract")
def test_req_qml018_ac06_graphml_rejects_readonly_output_and_recovers(tmp_path):
    """An owning graph writer rejects even though raw owned moves permit replacement."""
    value = graph()
    before = snapshot(value)
    target = tmp_path / "graph.graphml"
    target.write_bytes(b"PREVIOUS VALID PRODUCT")
    target.chmod(stat.S_IREAD)
    mode = target.stat().st_mode
    try:
        with pytest.raises(PermissionError, match="GraphML destination is read-only"):
            export.to_graphml(value, {}, str(target))
        assert target.read_bytes() == b"PREVIOUS VALID PRODUCT"
        assert target.stat().st_mode == mode
        assert snapshot(value) == before
        assert {path.name for path in tmp_path.iterdir()} == {"graph.graphml"}
    finally:
        target.chmod(stat.S_IWRITE)
    export.to_graphml(value, {}, str(target))
    assert_published(target, value, before)


@pytest.mark.parametrize("failure", ["serialize", "replace"])
def test_req_qml018_ac06_graphml_failed_write_preserves_product(tmp_path, monkeypatch, failure):
    """Fail the real owning serialization/replace boundary, then repair and repeat."""
    value = graph()
    before = snapshot(value)
    target = tmp_path / "graph.graphml"
    target.write_bytes(b"PREVIOUS VALID PRODUCT")
    with monkeypatch.context() as patch:
        if failure == "serialize":
            def fail_serializer(_graph, path):
                Path(path).write_bytes(b"PARTIAL")
                raise OSError("injected GraphML serialization failure")
            patch.setattr(nx, "write_graphml", fail_serializer)
        else:
            def fail_replace(source, destination):
                assert Path(source).read_bytes() and Path(destination) == target
                raise OSError("injected GraphML replacement failure")
            patch.setattr(export, "os_replace_with_fallback", fail_replace)
        with pytest.raises(OSError, match="injected GraphML"):
            export.to_graphml(value, {}, str(target))
    assert target.read_bytes() == b"PREVIOUS VALID PRODUCT"
    assert snapshot(value) == before
    assert {path.name for path in tmp_path.iterdir()} == {"graph.graphml"}
    export.to_graphml(value, {}, str(target))
    assert_published(target, value, before)


def test_req_qml018_ac06_graphml_never_replaces_a_directory(tmp_path):
    """A directory and its data survive rejection by the actual move boundary."""
    value = graph()
    before = snapshot(value)
    target = tmp_path / "graph.graphml"
    target.mkdir()
    (target / "keep").write_bytes(b"OWNED ELSEWHERE")
    with pytest.raises(OSError):
        export.to_graphml(value, {}, str(target))
    assert (target / "keep").read_bytes() == b"OWNED ELSEWHERE"
    assert snapshot(value) == before
    assert {path.name for path in tmp_path.iterdir()} == {"graph.graphml"}


def test_req_qml018_ac06_graphml_replaces_link_without_changing_target(tmp_path):
    """A supported real symlink is a replaceable entry; its target remains read-only."""
    value = graph()
    before = snapshot(value)
    target, referent = tmp_path / "graph.graphml", tmp_path / "separate.graphml"
    referent.write_bytes(b"SEPARATE PRODUCT")
    referent.chmod(stat.S_IREAD)
    mode = referent.stat().st_mode
    try:
        try:
            target.symlink_to(referent)
        except OSError:
            pytest.skip("Real symlink creation unavailable on this platform/account")
        export.to_graphml(value, {}, str(target))
        assert not target.is_symlink()
        assert referent.read_bytes() == b"SEPARATE PRODUCT"
        assert referent.stat().st_mode == mode
        assert_published(target, value, before)
    finally:
        referent.chmod(stat.S_IWRITE)
