"""INC-QML-112: alias identities survive real refresh and rejected publication."""
from __future__ import annotations

from copy import deepcopy
import errno

import pytest

import graphify.cache as cache
from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extract import extract, extract_cpp
from graphify.extractors.base import _file_stem, _make_id
from tests.cpp_alias_helpers import declarations, references, source
from tests.qt_publication_faults import publication_fault
from tests.test_cpp_allocated_member_updates import cold_reference, full_fields
from tests.test_cpp_same_unit_updates import rejected
from tests.test_qt_final_incremental_parity import run, unrelated
from tests.test_qt_semantic_correction_updates import products


def published_aliases(graph, names=("Alias", "alias")):
    return {node["label"]: identity for identity, node in graph.nodes(data=True)
            if node.get("source_file") == "types.cpp" and node.get("label") in names}


def published_references(graph, names=("Alias", "alias")):
    """Compare actual endpoints without treating undirected iteration as source direction."""
    aliases = set(published_aliases(graph, names).values())
    owners = {identity: node["label"] for identity, node in graph.nodes(data=True)
              if node.get("source_file") == "types.cpp" and node.get("label") in {"UsesUpper", "UsesLower"}}
    found = {}
    for left, right, edge in graph.edges(data=True):
        if edge.get("relation") != "references":
            continue
        if left in owners and right in aliases:
            found[owners[left]] = right
        elif right in owners and left in aliases:
            found[owners[right]] = left
    return found


@pytest.mark.parametrize("force", [False, True])
def test_req_qml022_ac06_alias_direct_export_failure_retains_then_recovers(tmp_path, monkeypatch, force):
    """A real direct JSON replacement error cannot discard the accepted literal aliases."""
    from tests.cpp_alias_helpers import produce
    first = produce(tmp_path, source())
    assert len(declarations(first)) == 2
    output = tmp_path / "aliases.json"
    assert to_json(build_from_json(first, root=tmp_path), {}, str(output), force=True)
    accepted = output.read_bytes()
    current = produce(tmp_path, source(names=("Alias", "Lower")))
    graph = build_from_json(current, root=tmp_path)
    with publication_fault(output, "replace", monkeypatch) as fault:
        for _ in range(2):
            with pytest.raises(OSError) as failure:
                to_json(graph, {}, str(output), force=force)
            assert failure.value.errno == errno.EIO and output.read_bytes() == accepted
        assert fault.hits >= 2
    assert to_json(graph, {}, str(output), force=force)
    repaired = output.read_bytes()
    assert repaired != accepted
    assert to_json(graph, {}, str(output), force=force) and output.read_bytes() == repaired


def test_req_qml022_ac06_actual_schema35_incomplete_alias_fragment_cannot_replay(tmp_path, monkeypatch):
    """The actual predecessor namespace misses, while fresh/warm aliases retain both declarations."""
    path = tmp_path / "types.cpp"
    path.write_bytes(source())
    current = extract_cpp(path)
    old = deepcopy(current)
    upper, lower = sorted(declarations(old), key=lambda node: int(node["source_location"][1:]))
    removed, before = lower["id"], upper["id"]
    legacy = _make_id(_file_stem(path), "Alias")
    old["nodes"] = [node for node in old["nodes"] if node["id"] != removed]
    upper["id"] = legacy
    old["edges"] = [edge for edge in old["edges"] if removed not in (edge.get("source"), edge.get("target"))]
    for edge in old["edges"]:
        for key in ("source", "target"):
            if edge[key] == before:
                edge[key] = legacy
    assert len(declarations(old)) == 1
    with monkeypatch.context() as prior:
        prior.setattr(cache, "_AST_CACHE_SCHEMA", 35)
        cache.save_cached(path, old, tmp_path, cache_root=tmp_path)
        directory = cache.cache_dir(tmp_path)
        assert list(directory.glob("*.json"))
    assert cache._AST_CACHE_SCHEMA == 40 and cache.load_cached(path, tmp_path, cache_root=tmp_path) is None
    cold = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    warm = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert cold == warm and len(declarations(cold)) == 2
    assert references(cold)["UsesUpper"]["id"] != references(cold)["UsesLower"]["id"]


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml022_ac06_alias_rename_eio_retention_and_context_updates(tmp_path, monkeypatch, operation):
    """Real C++ rename and QML/metadata-only updates cannot replay the other spelling's target."""
    path = tmp_path / "types.cpp"
    path.write_bytes(source())
    qml = tmp_path / "Main.qml"
    qml.write_bytes(b"import QtQuick\nItem {}\n")
    cmake = tmp_path / "CMakeLists.txt"
    cmake.write_bytes(b"qt_add_qml_module(app URI Public.Aliases VERSION 1.0 QML_FILES Main.qml SOURCES types.cpp)\n")
    (tmp_path / "keep.py").write_bytes(b"def helper():return 1\n\ndef retained():return helper()\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(tmp_path, monkeypatch, operation)
    old = published_aliases(initial)
    assert set(old) == {"Alias", "alias"} and old["Alias"] != old["alias"]
    assert published_references(initial) == {"UsesUpper": old["Alias"], "UsesLower": old["alias"]}
    original = path.read_bytes(), path.stat().st_mtime_ns
    qml.write_bytes(b"import QtQuick\nItem {property int revision:1}\n")
    qml_only = run(tmp_path, monkeypatch, operation, [qml])
    assert published_aliases(qml_only) == old and published_references(qml_only) == published_references(initial)
    assert full_fields(qml_only) == full_fields(cold_reference(tmp_path, monkeypatch, operation))
    cmake.write_bytes(cmake.read_bytes().replace(b"VERSION 1.0", b"VERSION 1.1"))
    metadata_only = run(tmp_path, monkeypatch, operation, [cmake])
    assert published_aliases(metadata_only) == old and published_references(metadata_only) == published_references(initial)
    assert full_fields(metadata_only) == full_fields(cold_reference(tmp_path, monkeypatch, operation))
    assert (path.read_bytes(), path.stat().st_mtime_ns) == original
    accepted = products(tmp_path)
    path.write_bytes(source(names=("Alias", "Lower")))
    changed = path.read_bytes()
    with publication_fault(tmp_path / "graphify-out/graph.json", "replace", monkeypatch) as fault:
        for _ in range(2):
            rejected(tmp_path, monkeypatch, operation, path)
            assert products(tmp_path) == accepted
        assert fault.hits >= 2
    renamed = run(tmp_path, monkeypatch, operation, [path])
    current = published_aliases(renamed, ("Alias", "Lower"))
    assert set(current) == {"Alias", "Lower"} and old["alias"] not in renamed
    assert published_references(renamed, ("Alias", "Lower")) == {"UsesUpper": current["Alias"], "UsesLower": current["Lower"]}
    assert full_fields(renamed) == full_fields(cold_reference(tmp_path, monkeypatch, operation))
    assert unrelated(initial) == unrelated(renamed) and path.read_bytes() == changed
    assert path.read_bytes() == changed
    before = products(tmp_path)
    run(tmp_path, monkeypatch, operation, [])
    assert products(tmp_path) == before
