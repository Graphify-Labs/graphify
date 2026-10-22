"""Explicit language declarations gate native overlays at the facade boundary."""
from __future__ import annotations

import pytest

from graphify.extract import extract
from graphify.extractors.qml_facts import qml_metadata
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.rcfile import set_language_overrides
from graphify.watch import _rebuild_code
from tests.test_qt_final_incremental_parity import clean, normalized, published


PHP = "<?php\nclass QObject { public function configured() { return 7; } }\n"
NATIVE = ("class Backend : public QObject { Q_OBJECT "
          "Q_PROPERTY(int status READ status) public: int status() { return 1; } };\n")


@pytest.fixture(autouse=True)
def isolated_overrides():
    """Root declarations never become an ambient language choice for later tests."""
    set_language_overrides(None)
    yield
    set_language_overrides(None)


def native_facts(nodes):
    return [node for node in nodes if qt_metadata(node)]


def assert_php_result(result):
    """Valid PHP with a Qt-looking name must not acquire native parsing failures."""
    assert not result["failed_sources"]
    assert not result.get("qml_failures") and not result.get("qt_failures")
    assert not any(item["code"].startswith("QT_CPP_") for item in result["diagnostics"])
    assert any(node["label"] == ".configured()" for node in result["nodes"])
    assert not native_facts(result["nodes"])
    assert not any(qt_metadata(edge) for edge in result["edges"])


@pytest.mark.parametrize("suffix", [".h", ".hpp", ".cpp"])
def test_req_qml002_ac01_explicit_non_cpp_override_skips_all_native_collectors(
        tmp_path, suffix):
    """Cold/warm facade keeps PHP facts; physical native spelling grants no Qt role."""
    source = tmp_path / ("adapter" + suffix)
    source.write_text(PHP, encoding="utf-8")
    (tmp_path / ".graphifyrc").write_text(f"language{suffix}=php\n", encoding="utf-8")
    first = extract([source], root=tmp_path, cache_root=tmp_path / "cache", parallel=False)
    assert_php_result(first)
    second = extract([source], root=tmp_path, cache_root=tmp_path / "cache", parallel=False)
    assert_php_result(second)
    assert first == second


def test_req_qml002_ac01_explicit_cpp_header_keeps_native_enrichment(tmp_path):
    """A supported physical header still admits Qt when its declared language is C++."""
    source = tmp_path / "backend.h"
    source.write_text(NATIVE, encoding="utf-8")
    (tmp_path / ".graphifyrc").write_text("language.h=cpp\n", encoding="utf-8")
    for _ in range(2):
        result = extract([source], root=tmp_path, cache_root=tmp_path / "cache", parallel=False)
        assert not result["failed_sources"]
        assert any(qt_metadata(node).get("kind") == "class" for node in result["nodes"])
        assert any(qt_metadata(node).get("kind") == "property" for node in result["nodes"])


def test_req_qml002_ac01_generic_cpp_override_does_not_invent_qt_provider_scope(tmp_path):
    """Upstream nonstandard-extension C++ parsing remains generic source evidence."""
    source = tmp_path / "backend.inc"
    source.write_text(NATIVE, encoding="utf-8")
    (tmp_path / ".graphifyrc").write_text("language.inc=cpp\n", encoding="utf-8")
    for _ in range(2):
        result = extract([source], root=tmp_path, cache_root=tmp_path / "cache", parallel=False)
        assert not result["failed_sources"]
        assert any(node["label"] == "Backend" for node in result["nodes"])
        assert not native_facts(result["nodes"])
        assert not any(qml_metadata(node).get("kind") == "qt_cpp_binding" for node in result["nodes"])


def test_req_qml002_ac01_mixed_override_preserves_supported_cpp_facts(tmp_path):
    """Discard only the overridden native candidate while retaining real Qt authority."""
    generic, native = tmp_path / "adapter.h", tmp_path / "backend.hpp"
    generic.write_text(PHP, encoding="utf-8")
    native.write_text(NATIVE, encoding="utf-8")
    (tmp_path / ".graphifyrc").write_text("language.h=php\n", encoding="utf-8")
    result = extract([generic, native], root=tmp_path, cache_root=tmp_path / "cache", parallel=False)
    assert not result["failed_sources"] and not result["qml_failures"]
    assert any(node["label"] == ".configured()" for node in result["nodes"])
    facts = native_facts(result["nodes"])
    assert facts and {node["source_file"] for node in facts} == {"backend.hpp"}
    assert any(qt_metadata(node).get("kind") == "property" for node in facts)


def test_req_qml011_ac04_override_transition_removes_native_facts_and_recovers(tmp_path):
    """Real watch publication removes old Qt authority and matches clean/cached rebuilds."""
    source, config = tmp_path / "backend.h", tmp_path / ".graphifyrc"
    source.write_text(NATIVE, encoding="utf-8")
    (tmp_path / "keep.py").write_text("def keep(): return 4\n", encoding="utf-8")
    assert _rebuild_code(tmp_path, no_cluster=True)
    initial = published(tmp_path)
    assert native_facts([data for _, data in initial.nodes(data=True)])
    source.write_text(PHP, encoding="utf-8")
    config.write_text("language.h=php\n", encoding="utf-8")
    assert _rebuild_code(tmp_path, changed_paths=[source, config], no_cluster=True)
    changed = published(tmp_path)
    assert not native_facts([data for _, data in changed.nodes(data=True)])
    assert any(data["label"] == ".configured()" for _, data in changed.nodes(data=True))
    assert not any(qt_metadata(data) for _, _, data in changed.edges(data=True))
    accepted = normalized(changed)
    cache = tmp_path / ".parity-cache"
    assert normalized(clean(tmp_path, cache)) == normalized(clean(tmp_path, cache)) == accepted
    assert _rebuild_code(tmp_path, changed_paths=[config], no_cluster=True)
    assert normalized(published(tmp_path)) == accepted
    source.write_text(NATIVE, encoding="utf-8")
    config.unlink()
    assert _rebuild_code(tmp_path, changed_paths=[source, config], no_cluster=True)
    assert normalized(published(tmp_path)) == normalized(initial)
