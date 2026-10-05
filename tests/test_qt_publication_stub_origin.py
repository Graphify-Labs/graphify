"""INC-QML-38: raw publication owns provenance of only its newly minted stubs."""
from __future__ import annotations

import json
import os

import pytest

import graphify.watch as watch
from graphify.cache import cache_dir
from tests.test_qt_initial_repeat import pin_graph_mtime, update


PRODUCTS = ("graph.json", "manifest.json", ".qt_analysis.json", ".graphify_root")


def corpus(root, language, *, imported=True):
    """Write a genuinely cold public corpus; fixture setup never extracts it."""
    if language == "cpp":
        (root / "Main.qml").write_bytes(b"import QtQuick\nItem {}\n")
        (root / "CMakeLists.txt").write_bytes(
            b"qt_add_qml_module(app URI Public.Tools VERSION 1.0 "
            b"QML_FILES Main.qml SOURCES backend.cpp)\n")
        path = root / "backend.cpp"
        source = b'#include "missing.hpp"\n' if imported else b""
        path.write_bytes(source + b"int original() { return 7; }\n")
    else:
        path = root / "keep.py"
        source = b"import missing\n" if imported else b""
        path.write_bytes(source + b"def original(): return 7\n")
    return path


def payload(root):
    return json.loads((root / "graphify-out/graph.json").read_bytes())


def nodes(root):
    return {node["id"]: node for node in payload(root)["nodes"]}


def prepare(root, monkeypatch, language, *, imported=True):
    source = corpus(root, language, imported=imported)
    monkeypatch.chdir(root)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    assert not (root / "graphify-out/graph.json").exists()
    assert not list(cache_dir(root).rglob("*.json"))
    return source


@pytest.mark.parametrize("operation", ["manual", "watch"])
@pytest.mark.parametrize("language", ["cpp", "python"])
def test_first_raw_stub_has_explicit_semantic_origin(tmp_path, monkeypatch, operation, language):
    """Canonical import minting stamps its sourceless placeholder on the first publication."""
    prepare(tmp_path, monkeypatch, language)
    assert update(tmp_path, monkeypatch, operation)
    published = nodes(tmp_path)
    assert published["missing"] == {
        "id": "missing", "label": "missing", "type": "external", "external": True,
        "file_type": "concept", "source_file": "", "_origin": "semantic"}
    source_nodes = [node for node in published.values() if node.get("source_file")]
    assert source_nodes and all(node.get("_origin") == "ast" for node in source_nodes)


@pytest.mark.parametrize("operation", ["manual", "watch"])
@pytest.mark.parametrize("language", ["cpp", "python"])
def test_first_raw_import_repeat_preserves_bytes_mtime_and_genuine_edit(tmp_path, monkeypatch,
                                                                    operation, language):
    """An unchanged refresh is durable-idempotent; a real source rename still publishes."""
    source = prepare(tmp_path, monkeypatch, language)
    assert update(tmp_path, monkeypatch, operation)
    graph = tmp_path / "graphify-out/graph.json"
    original, timestamp = pin_graph_mtime(graph)
    assert update(tmp_path, monkeypatch, operation)
    assert graph.read_bytes() == original and graph.stat().st_mtime_ns == timestamp
    source.write_bytes(source.read_bytes().replace(b"original", b"renamed"))
    assert update(tmp_path, monkeypatch, operation, [source])
    assert graph.read_bytes() != original and graph.stat().st_mtime_ns != timestamp
    assert any("renamed" in node["label"] for node in nodes(tmp_path).values())
    current, timestamp = pin_graph_mtime(graph)
    assert update(tmp_path, monkeypatch, operation)
    assert graph.read_bytes() == current and graph.stat().st_mtime_ns == timestamp


@pytest.mark.parametrize("operation", ["manual", "watch"])
@pytest.mark.parametrize("origin", [None, "manual", "semantic", "ast"])
def test_existing_authored_endpoint_is_not_stamped_by_minting(tmp_path, monkeypatch, operation, origin):
    """Only appended builder nodes are owned here; an existing authored endpoint retains its role."""
    source = prepare(tmp_path, monkeypatch, "cpp")
    assert update(tmp_path, monkeypatch, operation)
    graph = tmp_path / "graphify-out/graph.json"
    existing = payload(tmp_path)
    authored = {"id": "authored", "label": "authored", "type": "external", "external": True,
                "file_type": "concept", "source_file": "", "_origin": origin,
                "metadata": {"ownership": "authored"}}
    existing["nodes"].append(authored)
    graph.write_text(json.dumps(existing), encoding="utf-8")
    source.write_bytes(b'#include "authored.hpp"\n#include "created.hpp"\nint original() { return 7; }\n')
    assert update(tmp_path, monkeypatch, operation, [source])
    published = nodes(tmp_path)
    assert published["authored"] == authored
    assert published["created"]["_origin"] == "semantic"
    # The previous import loses its only accepted source reference (INC35).
    assert "missing" not in published


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_first_stamped_cpp_import_deletion_restoration_and_repeat(tmp_path, monkeypatch, operation):
    """First-publication provenance remains eligible for exact prior-import orphan cleanup."""
    source = prepare(tmp_path, monkeypatch, "cpp")
    original = source.read_bytes()
    assert update(tmp_path, monkeypatch, operation)
    first = payload(tmp_path)
    source.unlink()
    assert update(tmp_path, monkeypatch, operation, [source])
    assert "missing" not in nodes(tmp_path)
    source.write_bytes(original)
    assert update(tmp_path, monkeypatch, operation, [source])
    # Run metadata is transient, but all original node/edge facts must return.
    assert payload(tmp_path)["nodes"] == first["nodes"]
    assert payload(tmp_path)["links"] == first["links"]
    graph = tmp_path / "graphify-out/graph.json"
    restored, timestamp = pin_graph_mtime(graph)
    assert update(tmp_path, monkeypatch, operation)
    assert graph.read_bytes() == restored and graph.stat().st_mtime_ns == timestamp


@pytest.mark.parametrize("operation", ["manual", "watch"])
@pytest.mark.parametrize("language", ["cpp", "python"])
def test_new_stub_replacement_failure_retains_cohort_cache_then_retries(tmp_path, monkeypatch,
                                                                    operation, language):
    """Real replacement failure cannot accept a newly stamped graph; retry commits once."""
    source = prepare(tmp_path, monkeypatch, language, imported=False)
    # Qt refreshes may omit per-file AST cache admission; a real unchanged
    # Python file supplies durable cache bytes rather than a vacuous snapshot.
    (tmp_path / "unrelated.py").write_bytes(b"def untouched(): return 9\n")
    assert update(tmp_path, monkeypatch, operation)
    output = tmp_path / "graphify-out"
    graph = output / "graph.json"
    pin_graph_mtime(graph)
    before = {name: ((output / name).read_bytes(), (output / name).stat().st_mtime_ns) for name in PRODUCTS}
    caches = {path: path.read_bytes() for path in cache_dir(tmp_path).rglob("*.json")}
    assert caches and "missing" not in nodes(tmp_path)
    corpus(tmp_path, language)
    replace = watch.os_replace_with_fallback

    def reject_graph(staged, destination, **kwargs):
        if os.fspath(destination).endswith("graph.json"):
            raise OSError("simulated graph replacement failure")
        return replace(staged, destination, **kwargs)

    with monkeypatch.context() as failure:
        failure.setattr(watch, "os_replace_with_fallback", reject_graph)
        if operation == "manual":
            with pytest.raises(SystemExit) as rejected:
                update(tmp_path, monkeypatch, operation, [source])
            assert rejected.value.code == 1
        else:
            assert not update(tmp_path, monkeypatch, operation, [source])
    assert all((output / name).read_bytes() == data and (output / name).stat().st_mtime_ns == mtime
               for name, (data, mtime) in before.items())
    assert all(path.exists() and path.read_bytes() == data for path, data in caches.items())
    assert not list(output.glob(".gfy-publish-*"))
    assert update(tmp_path, monkeypatch, operation, [source])
    assert nodes(tmp_path)["missing"]["_origin"] == "semantic"
    accepted, timestamp = pin_graph_mtime(graph)
    assert update(tmp_path, monkeypatch, operation)
    assert graph.read_bytes() == accepted and graph.stat().st_mtime_ns == timestamp
