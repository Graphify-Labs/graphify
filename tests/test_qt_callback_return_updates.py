"""INC-QML-80: callback-return ownership survives real update/publication paths."""
from __future__ import annotations

import pytest

from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.extract import extract
from graphify.qt_analysis_state import QT_STATE_FILE
from graphify.watch import _rebuild_code
from tests.test_qt_callback_return_ownership import sources
from tests.test_qt_cmake_mutation_updates import compare_clean, normalized, published


def _project(root):
    for name, source in sources("Service *").items():
        (root / name).write_bytes(source.encode())


def _factory(root):
    return {identity: qt_metadata(node) for identity, node in published(root).nodes(data=True)
            if qt_metadata(node).get("kind") == "member" and qt_metadata(node).get("raw_name") == "factory"}


def test_req_qml022_ac06_callback_return_cold_warm_header_source_cleanup_matches_full(tmp_path):
    """Each source/header edit replaces original facts while actual parameters stay empty."""
    _project(tmp_path)
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    original = _factory(tmp_path)
    assert len(original) == 2 and all(md["parameter_types"] == [] for md in original.values())
    path = tmp_path / "backend.cpp"
    baseline = normalized(published(tmp_path))
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    assert normalized(published(tmp_path)) == baseline
    path.write_bytes(path.read_bytes().replace(b"callbackValue", b"callbackArgument"))
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    changed = _factory(tmp_path)
    assert len(changed) == 2 and all(md["parameter_types"] == [] for md in changed.values())
    assert any("callbackArgument" in md["api_type_spelling"] for md in changed.values())
    assert not (set(original) - set(changed)) & set(published(tmp_path))
    compare_clean(tmp_path)
    header = tmp_path / "backend.hpp"
    header.write_bytes(header.read_bytes().replace(b"callbackValue", b"callbackParameter"))
    assert _rebuild_code(tmp_path, changed_paths=[header], no_cluster=True, acquire_lock=False)
    assert any("callbackParameter" in md["api_type_spelling"] for md in _factory(tmp_path).values())
    assert all(md["api_type_status"] == "unsupported" for md in _factory(tmp_path).values())
    compare_clean(tmp_path)


@pytest.mark.parametrize("force", [False, True])
def test_req_qml022_ac06_malformed_callback_return_retains_products_then_repairs(tmp_path, force):
    """Rejected source never replaces accepted original ownership; retry/repair is safe."""
    _project(tmp_path)
    path = tmp_path / "backend.cpp"
    source = path.read_bytes()
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    out = tmp_path / "graphify-out"
    (out / "report.md").write_bytes(b"Previously accepted callback ownership report\n")
    names = ("graph.json", "manifest.json", "report.md", QT_STATE_FILE)
    prior = {name: (out / name).read_bytes() for name in names}
    path.write_bytes(source.replace(b")(int callbackValue)", b")(int callbackValue"))
    for _ in range(2):
        assert not _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False, force=force)
        assert {name: (out / name).read_bytes() for name in names} == prior
    path.write_bytes(source)
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    assert len(_factory(tmp_path)) == 2 and all(md["parameter_types"] == [] for md in _factory(tmp_path).values())
    compare_clean(tmp_path)
    accepted = (out / "graph.json").read_bytes()
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    assert (out / "graph.json").read_bytes() == accepted


def test_req_qml022_ac06_callback_raw_type_transport_limit_is_explicit_and_retains_graph(tmp_path):
    """New opaque source spelling obeys the existing metadata bound and retention contract."""
    _project(tmp_path)
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    out = tmp_path / "graphify-out"
    (out / "report.md").write_bytes(b"Previously accepted callback metadata report\n")
    names = ("graph.json", "manifest.json", "report.md", QT_STATE_FILE)
    prior = {name: (out / name).read_bytes() for name in names}
    header = tmp_path / "backend.hpp"
    original = header.read_bytes()
    header.write_bytes(original.replace(b"callbackValue", b"callback" + b"Parameter" * 60))
    result = extract([header, tmp_path / "backend.cpp"], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert any(item["code"] == "QT_CPP_LIMIT" for item in result.get("diagnostics", []))
    assert not _rebuild_code(tmp_path, changed_paths=[header], no_cluster=True, acquire_lock=False)
    assert {name: (out / name).read_bytes() for name in names} == prior
    header.write_bytes(original)
    assert _rebuild_code(tmp_path, changed_paths=[header], no_cluster=True, acquire_lock=False)
    compare_clean(tmp_path)
