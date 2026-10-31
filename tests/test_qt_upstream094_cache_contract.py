"""INC-QML-59: combined cache producers and lexical header dispatch contracts."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import graphify.cache as cache
import graphify.extract as extraction
from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extractors.qml_facts import qml_metadata
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.paths import load_node_link_graph
from tests.test_qt_final_incremental_parity import normalized, project
from tests.test_upstream_qt_cache_integration import (
    assert_semantic_preserved,
    python_source,
    semantic_entry,
)


@pytest.fixture
def cache_profile(monkeypatch):
    """Use a single package identity; flush real process-owned cache bookkeeping."""
    monkeypatch.setattr(cache, "_EXTRACTOR_VERSION", "0.9.94")
    monkeypatch.setattr(cache, "_cleaned_ast_dirs", set())
    for name, value in (("_stat_index", {}), ("_stat_index_root", None),
                        ("_stat_index_anchor", None), ("_stat_index_path", None),
                        ("_stat_index_dirty", False)):
        monkeypatch.setattr(cache, name, value, raising=False)
    yield
    cache._flush_stat_index()


@pytest.mark.parametrize("old_schema", [18, 22])
def test_req_qml011_ac01_ac03_ac04_predecessor_ast_misses_semantic_survives(
        tmp_path, monkeypatch, cache_profile, old_schema):
    """Real same-version predecessor writes cannot prove the combined producer."""
    source = python_source(tmp_path)
    semantic = semantic_entry(tmp_path)
    with monkeypatch.context() as old:
        old.setattr(cache, "_AST_CACHE_SCHEMA", old_schema)
        cache.save_cached(source, {
            "nodes": [{"id": "old-producer", "label": "stale", "source_file": str(source)}],
            "edges": [], "raw_calls": [{"caller_nid": "old-producer", "callee": "get"}],
        }, root=tmp_path)
        prior_directory = cache.cache_dir(tmp_path)
        assert list(prior_directory.glob("*.json"))
    assert cache._AST_CACHE_SCHEMA == 32
    assert cache.load_cached(source, root=tmp_path) is None
    assert not prior_directory.exists()
    cold = extraction.extract([source], root=tmp_path, cache_root=tmp_path, parallel=False)
    cached = cache.load_cached(source, root=tmp_path)
    assert cached and cached["raw_calls"]
    assert cache.cache_dir(tmp_path).name == f"v0.9.94-s32-g{cache._grammar_fingerprint()}"
    warm = extraction.extract([source], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert normalized(build_from_json(cold, directed=True, root=tmp_path)) == normalized(
        build_from_json(warm, directed=True, root=tmp_path))
    assert not any(node.get("label") == "stale" for node in warm["nodes"])
    assert_semantic_preserved(tmp_path, semantic)


def test_req_qml014_ac03_mixed_cold_warm_skip_and_qt_failures(tmp_path, monkeypatch, cache_profile):
    """Warm generic facts coexist with Qt reparsing and deliberately declined JSON."""
    project(tmp_path)
    python_source(tmp_path)
    declined = tmp_path / "measurements.json"
    declined.write_text('[1, 2, 3]\n', encoding="utf-8")
    paths = extraction.collect_files(tmp_path, root=tmp_path)
    cold = extraction.extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    observed, real_extract = [], extraction._safe_extract_with_xaml_root

    def observe(extractor, path, *args, **kwargs):
        observed.append(Path(path).suffix)
        return real_extract(extractor, path, *args, **kwargs)

    monkeypatch.setattr(extraction, "_safe_extract_with_xaml_root", observe)
    warm = extraction.extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    assert observed and ".py" not in observed
    assert str(declined) in cold["skipped_sources"] == warm["skipped_sources"]
    assert str(declined) not in warm["failed_sources"]
    assert not warm["qml_failures"] and not warm["qt_failures"]
    assert "diagnostics" in warm
    assert any(qt_metadata(node).get("kind") == "property" for node in warm["nodes"])
    assert any(qml_metadata(node).get("kind") == "type_use" and
               qml_metadata(node).get("status") == "resolved" for node in warm["nodes"])
    graphs = []
    for name, result in (("cold", cold), ("warm", warm)):
        graph = build_from_json(result, directed=True, root=tmp_path)
        output = tmp_path / f"{name}.json"
        assert to_json(graph, {}, str(output), force=True)
        graphs.append(load_node_link_graph(json.loads(output.read_text(encoding="utf-8"))))
    assert normalized(graphs[0]) == normalized(graphs[1])


@pytest.mark.parametrize("declaration", [
    'extern "C" { int bridge(void); }',
    'extern "C" int bridge(void);',
    'extern /* linkage */ "C" { int bridge(void); }',
    'extern\n"C" { int bridge(void); }',
])
def test_req_qml002_ac01_qml014_ac03_extern_c_header_uses_cpp(tmp_path, cache_profile, declaration):
    """The production facade admits actual C linkage and recovers its declaration."""
    source = tmp_path / "bridge.h"
    source.write_text(declaration + "\n", encoding="utf-8")
    assert extraction._get_extractor(source) is extraction.extract_cpp
    result = extraction.extract([source], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert not result["failed_sources"]
    assert any("bridge" in node.get("label", "") and node.get("source_file") == "bridge.h"
               for node in result["nodes"])


@pytest.mark.parametrize("inert", [
    '// extern "C" {',
    '/* extern "C" { */',
    'const char *message = "extern \\"C\\" {";',
    'const char *message = R"tag(extern "C" {)tag";',
    'const char *message = "unterminated extern \\"C\\" {',
    'const char *message = "prefix"; /* extern */ "C";',
    'extern_name "C";',
    'extern "C++" { int bridge(void); }',
])
def test_req_qml002_ac03_inert_linkage_does_not_select_cpp(tmp_path, inert):
    """Comments, literals, malformed strings and nonmatching spellings keep C dispatch."""
    source = tmp_path / "plain.h"
    source.write_text(inert + "\nstruct Record { int value; };\n", encoding="utf-8")
    assert extraction._get_extractor(source) is extraction.extract_c


def test_req_qml002_ac03_objc_priority_survives_c_linkage(tmp_path):
    """The shared .h suffix still routes actual Objective-C directives first."""
    source = tmp_path / "native.h"
    source.write_text('@interface Native\n@end\nextern "C" { int bridge(void); }\n', encoding="utf-8")
    assert extraction._get_extractor(source) is extraction.extract_objc
