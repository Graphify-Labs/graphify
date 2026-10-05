"""INC-QML-49: combined Qt/Python cache producers preserve facts and ownership."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import graphify.cache as cache
import graphify.extract as extraction
import graphify.qt_analysis_state as qt_state
from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extractors.qml_facts import qml_metadata
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.paths import load_node_link_graph
from graphify.watch import _rebuild_code
from tests.test_qt_final_incremental_parity import normalized, project, published
from tests.test_qt_product_publication import no_scratch, snapshot


@pytest.fixture
def integrated_versions(monkeypatch):
    """Isolate installed metadata; the combined release owns the actual schema."""
    real_version = qt_state.version

    def current_version(package):
        return "0.9.76" if package == "graphifyy" else real_version(package)

    monkeypatch.setattr(cache, "_EXTRACTOR_VERSION", "0.9.76")
    monkeypatch.setattr(cache, "_cleaned_ast_dirs", set())
    # Each case owns a fresh project. Keep process bookkeeping isolated, then
    # complete its real stat-index flush before fixture restoration.
    for name, value in (("_stat_index", {}), ("_stat_index_root", None),
                        ("_stat_index_anchor", None), ("_stat_index_path", None),
                        ("_stat_index_dirty", False)):
        monkeypatch.setattr(cache, name, value, raising=False)
    monkeypatch.setattr(qt_state, "version", current_version)
    yield real_version
    cache._flush_stat_index()


def semantic_entry(root):
    """Seed a real prompt-owned entry whose bytes AST migration must not touch."""
    source = root / "notes.md"
    source.write_text("Public cache integration note.\n", encoding="utf-8")
    prompt = "Public semantic extraction contract"
    cache.save_cached(source, {
        "nodes": [{"id": "public-note", "label": "note", "source_file": str(source)}],
        "edges": [],
    }, root=root, kind="semantic", prompt=prompt)
    directory = cache.cache_dir(root, "semantic", cache.prompt_fingerprint(prompt))
    entry = directory / f"{cache.file_hash(source, root)}.json"
    return source, prompt, entry, entry.read_bytes()


def assert_semantic_preserved(root, state):
    source, prompt, entry, before = state
    loaded = cache.load_cached(source, root=root, kind="semantic", prompt=prompt)
    assert loaded is not None and loaded["nodes"][0]["id"] == "public-note"
    assert entry.read_bytes() == before


def python_source(root):
    source = root / "caller.py"
    source.write_text(
        "import requests\n\ndef fetch():\n    return requests.get('/data')\n\n"
        "def shadowed(requests):\n    return requests.get('/private')\n",
        encoding="utf-8",
    )
    return source


@pytest.mark.parametrize("old_schema", [5, 12])
@pytest.mark.parametrize("old_version", ["0.9.74", "0.9.76"])
def test_req_qml003_ac04_qml018_ac05_old_namespaces_miss_and_refresh(
        tmp_path, monkeypatch, integrated_versions, old_schema, old_version):
    """Real legacy writes miss even at the same version, refresh, then warm-hit."""
    source = python_source(tmp_path)
    semantic = semantic_entry(tmp_path)
    # Both historical producers used this real cache writer. Their raw calls
    # cannot establish the integrated lexical/Qt fact contract from their epoch.
    with monkeypatch.context() as prior:
        prior.setattr(cache, "_EXTRACTOR_VERSION", old_version)
        prior.setattr(cache, "_AST_CACHE_SCHEMA", old_schema)
        cache.save_cached(source, {
            "nodes": [{"id": "old", "label": "stale", "source_file": str(source)}],
            "edges": [], "raw_calls": [{"caller_nid": "old", "callee": "get"}],
        }, root=tmp_path)
        old_directory = cache.cache_dir(tmp_path)
        assert (old_directory / f"{cache.file_hash(source, tmp_path)}.json").exists()
    assert cache.load_cached(source, root=tmp_path) is None
    assert not old_directory.exists()
    assert_semantic_preserved(tmp_path, semantic)
    cold = extraction.extract([source], root=tmp_path, cache_root=tmp_path, parallel=False)
    fresh = cache.load_cached(source, root=tmp_path)
    assert fresh is not None
    assert {item.get("_python_receiver_shadowed") for item in fresh["raw_calls"]} == {False, True}
    assert cache.cache_dir(tmp_path).name == "v0.9.76-s13"
    warm = extraction.extract([source], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert normalized(build_from_json(cold, directed=True, root=tmp_path)) == normalized(
        build_from_json(warm, directed=True, root=tmp_path))
    assert not any(node.get("label") == "stale" for node in warm["nodes"])
    assert_semantic_preserved(tmp_path, semantic)


def test_req_qml003_ac04_qml018_ac05_mixed_cold_warm_serialized_facts(
        tmp_path, monkeypatch, integrated_versions):
    """Real Qt reparse and Python warm hits agree through directed JSON reload."""
    project(tmp_path)
    source = python_source(tmp_path)
    semantic = semantic_entry(tmp_path)
    paths = extraction.collect_files(tmp_path, root=tmp_path)
    cold = extraction.extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    observed, real_extract = [], extraction._safe_extract_with_xaml_root

    def observe(extractor, path, *args, **kwargs):
        observed.append(Path(path).suffix)
        return real_extract(extractor, path, *args, **kwargs)

    monkeypatch.setattr(extraction, "_safe_extract_with_xaml_root", observe)
    warm = extraction.extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    assert observed and ".py" not in observed
    assert not warm["failed_sources"] and not warm["qml_failures"]
    assert any(qt_metadata(node).get("kind") == "property" for node in warm["nodes"])
    assert any(qml_metadata(node).get("kind") == "type_use" and
               qml_metadata(node).get("status") == "resolved" for node in warm["nodes"])
    callers = {node["label"]: node["id"] for node in warm["nodes"]
               if node.get("source_file") == "caller.py"}
    assert any(edge["source"] == callers["fetch()"] and edge["target"] == "requests"
               and edge["relation"] == "calls" for edge in warm["edges"])
    assert not any(edge["source"] == callers["shadowed()"] and edge["target"] == "requests"
                   and edge["relation"] == "calls" for edge in warm["edges"])
    raw = cache.load_cached(source, root=tmp_path)
    assert raw is not None
    assert {item.get("_python_receiver_shadowed") for item in raw["raw_calls"]} == {False, True}
    graphs = []
    for name, result in (("cold", cold), ("warm", warm)):
        graph = build_from_json(result, directed=True, root=tmp_path)
        output = tmp_path / f"{name}.json"
        assert to_json(graph, {}, str(output), force=True)
        graphs.append(load_node_link_graph(json.loads(output.read_text(encoding="utf-8"))))
    assert normalized(graphs[0]) == normalized(graphs[1])
    assert_semantic_preserved(tmp_path, semantic)


def test_req_qml011_ac03_ac04_qml018_ac06_upgrade_failure_retains_repairs_repeats(
        tmp_path, monkeypatch, integrated_versions):
    """A real schema-13 cache replacement failure cannot advance prior products."""
    project(tmp_path)
    source = python_source(tmp_path)
    semantic = semantic_entry(tmp_path)
    real_version = integrated_versions
    with monkeypatch.context() as prior:
        prior.setattr(cache, "_EXTRACTOR_VERSION", "0.9.74")
        prior.setattr(cache, "_AST_CACHE_SCHEMA", 12)
        prior.setattr(qt_state, "version", lambda name:
                      "0.9.74" if name == "graphifyy" else real_version(name))
        assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    output = tmp_path / "graphify-out"
    accepted, initial = snapshot(output), normalized(published(tmp_path))
    before_sources = {path.name: path.read_bytes() for path in tmp_path.iterdir() if path.is_file()}
    failed_targets, real_replace = [], cache._os_replace_with_fallback

    def fail_current_ast(temporary, target):
        target = Path(target)
        if target.parent.name == "v0.9.76-s13":
            # Serialization and staging must really finish before the injected
            # replacement failure reaches the actual cache persistence owner.
            assert Path(temporary).is_file()
            staged = json.loads(Path(temporary).read_text(encoding="utf-8"))
            assert staged.get("raw_calls")
            failed_targets.append(target)
            raise OSError("public combined-cache replacement failure")
        return real_replace(temporary, target)

    with monkeypatch.context() as failed:
        failed.setattr(cache, "_os_replace_with_fallback", fail_current_ast)
        assert not _rebuild_code(tmp_path, changed_paths=[], no_cluster=True, acquire_lock=False)
    assert failed_targets
    assert snapshot(output) == accepted
    assert_semantic_preserved(tmp_path, semantic)
    no_scratch(output)
    assert _rebuild_code(tmp_path, changed_paths=[], no_cluster=True, acquire_lock=False)
    assert normalized(published(tmp_path)) == initial
    repaired = snapshot(output)
    assert repaired != accepted
    assert cache.load_cached(source, root=tmp_path) is not None
    assert _rebuild_code(tmp_path, changed_paths=[], no_cluster=True, acquire_lock=False)
    assert snapshot(output) == repaired
    assert normalized(published(tmp_path)) == initial
    assert_semantic_preserved(tmp_path, semantic)
    assert before_sources == {path.name: path.read_bytes() for path in tmp_path.iterdir() if path.is_file()}
    no_scratch(output)
