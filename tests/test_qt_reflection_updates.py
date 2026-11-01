"""REQ-QML-017-AC04: SDK reflection refresh, rejection and durable recovery."""
from __future__ import annotations

import pytest

from graphify.extractors.qt_cpp_facts import qt_metadata
from tests.test_qt_final_incremental_parity import clean, normalized, run, unrelated
from tests.test_qt_loader_updates import products
from tests.test_qt_reflection_type_identity import OPERATIONS, QML, TARGET_CONTEXTS, source


def cpp_source(root, operation, shadow="sdk_control"):
    """Use a public accepted resource alias so metadata-only changes matter."""
    return source(root, operation, shadow).replace((root / "Main.qml").as_uri(), "qrc:/ui/Main.qml").encode()


def fixture(root, operation):
    for name, content in {
        "access.cpp": cpp_source(root, operation), "Main.qml": QML.encode(),
        "CMakeLists.txt": b"qt_add_qml_module(app URI Public.Tools VERSION 1.0 QML_FILES Main.qml SOURCES access.cpp)\n",
        "ui.qrc": b'<RCC><qresource prefix="/ui"><file alias="Main.qml">Main.qml</file></qresource></RCC>',
        "keep.py": b"def helper(): return 7\n\ndef retained(): return helper()\n",
    }.items():
        (root / name).write_bytes(content)
    return root / "access.cpp"


def reflection(graph):
    """Only the reflection access sites own these endpoints, never loader edges."""
    sites = {identity: qt_metadata(data) for identity, data in graph.nodes(data=True)
             if qt_metadata(data).get("kind") == "qml_access"}
    edges = [(data.get("_src", a), data.get("_tgt", b), data)
             for a, b, data in graph.edges(data=True)
             if data.get("context") in TARGET_CONTEXTS and data.get("_src", a) in sites]
    return sites, edges


def accepted(graph, operation):
    sites, edges = reflection(graph)
    assert len(sites) == len(edges) == (2 if operation == "property_handle" else 1)
    assert all(md["status"] == "resolved" for md in sites.values())
    assert all(target == sites[identity]["target_id"] and graph.nodes[target]["source_file"] == "Main.qml"
               for identity, target, _ in edges)
    return sites, edges


@pytest.mark.parametrize("operation", list(OPERATIONS))
@pytest.mark.parametrize("mode", ["manual", "watch"])
def test_req_qml017_ac04_reflection_source_qml_metadata_edits_remove_stale_targets(tmp_path, monkeypatch, operation, mode):
    """Cold/warm/full/update retain every public fact while authority changes."""
    cpp = fixture(tmp_path, operation)
    monkeypatch.chdir(tmp_path)
    cold = clean(tmp_path, tmp_path / ".cold")
    assert normalized(cold) == normalized(clean(tmp_path, tmp_path / ".cold"))
    initial = run(tmp_path, monkeypatch, mode)
    assert normalized(initial) == normalized(cold)
    original_sites, _ = accepted(initial, operation)
    untouched, valid_cpp = unrelated(initial), cpp.read_bytes()

    cpp.write_bytes(cpp_source(tmp_path, operation, "local_alias"))
    rejected = run(tmp_path, monkeypatch, mode, [cpp])
    assert not reflection(rejected)[1]
    assert all(md["status"] != "resolved" and not md.get("target_id") for md in reflection(rejected)[0].values())
    assert normalized(rejected) == normalized(clean(tmp_path, tmp_path / ".shadow-cold"))
    cpp.write_bytes(valid_cpp)
    assert normalized(run(tmp_path, monkeypatch, mode, [cpp])) == normalized(initial)

    qml = tmp_path / "Main.qml"
    valid_qml = qml.read_bytes()
    qml.write_bytes(valid_qml.replace(b"count:", b"renamed:").replace(b"function refresh()", b"function revised()"))
    qml_changed = run(tmp_path, monkeypatch, mode, [qml])
    assert set(reflection(qml_changed)[0]) == set(original_sites) and cpp.read_bytes() == valid_cpp
    assert not reflection(qml_changed)[1]
    assert normalized(qml_changed) == normalized(clean(tmp_path, tmp_path / ".qml-cold"))
    qml.write_bytes(valid_qml)
    accepted(run(tmp_path, monkeypatch, mode, [qml]), operation)

    resource = tmp_path / "ui.qrc"
    valid_resource = resource.read_bytes()
    resource.write_bytes(valid_resource.replace(b'alias="Main.qml"', b'alias="Other.qml"'))
    metadata_changed = run(tmp_path, monkeypatch, mode, [resource])
    assert set(reflection(metadata_changed)[0]) == set(original_sites)
    assert not reflection(metadata_changed)[1] and cpp.read_bytes() == valid_cpp
    assert normalized(metadata_changed) == normalized(clean(tmp_path, tmp_path / ".metadata-cold"))
    resource.write_bytes(valid_resource)
    accepted(run(tmp_path, monkeypatch, mode, [resource]), operation)

    cpp.write_bytes(valid_cpp.replace(OPERATIONS[operation][1].encode(), b""))
    removed = run(tmp_path, monkeypatch, mode, [cpp])
    assert reflection(removed) == ({}, [])
    assert normalized(removed) == normalized(clean(tmp_path, tmp_path / ".removed-cold"))
    assert unrelated(removed) == untouched
    durable = products(tmp_path)
    assert normalized(run(tmp_path, monkeypatch, mode, [])) == normalized(removed)
    assert products(tmp_path) == durable


@pytest.mark.parametrize("operation", list(OPERATIONS))
@pytest.mark.parametrize("mode", ["manual", "force", "watch"])
def test_req_qml017_ac04_reflection_parse_failure_retains_four_products_and_recovers(tmp_path, monkeypatch, operation, mode):
    """A real malformed reflected source fails before accepted publication."""
    cpp = fixture(tmp_path, operation)
    monkeypatch.chdir(tmp_path)
    normal = "manual" if mode == "force" else mode
    initial = run(tmp_path, monkeypatch, normal)
    accepted(initial, operation)
    valid, durable = cpp.read_bytes(), products(tmp_path)
    cpp.write_bytes(valid + b"\r\nvoid broken({")
    if mode == "watch":
        from graphify.watch import _rebuild_code
        assert not _rebuild_code(tmp_path, changed_paths=[cpp], no_cluster=True)
    else:
        with pytest.raises(SystemExit) as failure:
            if mode == "force":
                from tests.test_qt_cpp_upgrade_invalidation import cli
                cli(tmp_path, monkeypatch, "update", force=True)
            else:
                run(tmp_path, monkeypatch, normal, [cpp])
        assert failure.value.code == 1
    assert products(tmp_path) == durable
    cpp.write_bytes(valid)
    recovered = run(tmp_path, monkeypatch, normal, [cpp])
    assert normalized(recovered) == normalized(initial)
    repeated = products(tmp_path)
    assert normalized(run(tmp_path, monkeypatch, normal, [])) == normalized(recovered)
    assert products(tmp_path) == repeated


@pytest.mark.parametrize("operation", list(OPERATIONS))
@pytest.mark.parametrize("mode", ["manual", "watch"])
def test_req_qml017_ac04_reflection_write_failure_retains_four_products_and_retries(tmp_path, monkeypatch, operation, mode):
    """Inject only the external replacement boundary after real analysis work."""
    import graphify.watch as watch
    cpp = fixture(tmp_path, operation)
    monkeypatch.chdir(tmp_path)
    initial = run(tmp_path, monkeypatch, mode)
    accepted(initial, operation)
    durable = products(tmp_path)
    cpp.write_bytes(cpp_source(tmp_path, operation, "local_alias"))
    real_replace = watch.os_replace_with_fallback

    def fail_replace(start, destination):
        if str(destination).endswith("graph.json"):
            raise PermissionError("injected reflection replacement failure")
        return real_replace(start, destination)

    with monkeypatch.context() as failure:
        failure.setattr(watch, "os_replace_with_fallback", fail_replace)
        if mode == "manual":
            with pytest.raises(SystemExit) as rejected:
                run(tmp_path, failure, mode, [cpp])
            assert rejected.value.code == 1
        else:
            assert not watch._rebuild_code(tmp_path, changed_paths=[cpp], no_cluster=True)
    assert products(tmp_path) == durable
    recovered = run(tmp_path, monkeypatch, mode, [cpp])
    assert not reflection(recovered)[1]
    assert normalized(recovered) != normalized(initial)
    assert normalized(recovered) == normalized(clean(tmp_path, tmp_path / ".recovered-cold"))
    repeated = products(tmp_path)
    assert normalized(run(tmp_path, monkeypatch, mode, [])) == normalized(recovered)
    assert products(tmp_path) == repeated
