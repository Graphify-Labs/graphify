"""Actual workers, parser cache retention and native scope-root publication."""
from __future__ import annotations

from pathlib import Path

import pytest

import graphify.extract as extraction
from graphify.cache import save_cached
from graphify.extractors.qml_facts import qml_metadata
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.qt_analysis_state import inspect_qt_analysis
from graphify.watch import _rebuild_code
from tests.qml_test_helpers import canonical
from tests.test_qt_config_incremental import _project, _snapshot, _write


CPP = """#include <QObject>
class Backend : public QObject {
 Q_OBJECT
public: void tick() { emit ready(1); }
signals: void ready(int value);
};
"""


def _provider(result):
    nodes = {node["id"]: node for node in result["nodes"]}
    sites = [node for node in nodes.values() if node["source_file"] == "Main.qml" and
             qml_metadata(node).get("kind") == "type_use"]
    assert len(sites) == 1 and qml_metadata(sites[0])["status"] == "resolved"
    links = [edge for edge in result["edges"] if edge["source"] == sites[0]["id"] and edge["relation"] == "uses"]
    assert len(links) == 1
    return nodes[links[0]["target"]]["source_file"]


@pytest.mark.parametrize("roots,expected", [
    ('["first", "second"]', "first/Public/Tools/Service.qml"),
    ('["second", "first"]', "second/Public/Tools/Service.qml"),
])
def test_qml010_ac01_actual_workers_preserve_configured_roots_script_and_native_facts(tmp_path, monkeypatch, roots, expected):
    _project(tmp_path)
    _write(tmp_path, "Main.qml", 'import Public.Tools 1.0\nimport "helpers.js" as Tools\nService { property int displayed: Tools.compute(value) }\n')
    _write(tmp_path, "helpers.js", ".pragma library\nfunction compute(value) { return value * 2; }\n")
    _write(tmp_path, "backend.cpp", CPP)
    for index in range(18):
        _write(tmp_path, f"panels/Panel{index}.qml", f"QtObject {{ property int value: {index} }}\n")
    paths = extraction.collect_files(tmp_path, root=tmp_path)
    monkeypatch.setenv("GRAPHIFY_QML_IMPORT_ROOTS", roots)
    analysis = inspect_qt_analysis(tmp_path, tmp_path / "state-output", paths)
    ran, real_pool = [], extraction._extract_parallel

    def observe_pool(*args, **kwargs):
        succeeded = real_pool(*args, **kwargs)
        ran.append(succeeded)
        return succeeded

    monkeypatch.setattr(extraction, "_extract_parallel", observe_pool)
    parallel = extraction.extract(paths, root=tmp_path, cache_root=tmp_path / "pool-cache",
                                  qml_import_roots=analysis.import_roots, parallel=True, max_workers=2)
    assert ran == [True]
    sequential = extraction.extract(list(reversed(paths)), root=tmp_path, cache_root=tmp_path / "serial-cache",
                                    qml_import_roots=analysis.import_roots, parallel=False)
    warm = extraction.extract(paths, root=tmp_path, cache_root=tmp_path / "serial-cache",
                              qml_import_roots=analysis.import_roots, parallel=False)
    assert not parallel["qml_failures"] and not parallel["failed_sources"]
    assert _provider(parallel) == expected
    assert any(edge.get("context") == "qml_script_call" for edge in parallel["edges"])
    assert any(qt_metadata(node).get("kind") == "emission" for node in parallel["nodes"])
    assert canonical(parallel) == canonical(sequential) == canonical(warm)


def _ast_snapshot(root):
    base = root / "graphify-out/cache/ast"
    return {path.relative_to(base).as_posix(): path.read_bytes() for path in base.rglob("*.json")}


@pytest.mark.parametrize("force", [False, True])
def test_qml012_ac02_failed_native_parser_keeps_prior_real_ast_cache_and_products(tmp_path, force):
    source = _write(tmp_path, "backend.cpp", CPP)
    # Model an existing production cache from before native compatibility bypass;
    # use the real generic extractor and cache serializer, not arbitrary bytes.
    syntax = extraction.extract_cpp(source)
    assert syntax["nodes"]
    save_cached(source, syntax, root=tmp_path, cache_root=tmp_path)
    cache_before = _ast_snapshot(tmp_path)
    assert cache_before
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    assert _ast_snapshot(tmp_path) == cache_before
    products_before = _snapshot(tmp_path)
    source.write_text("class Backend : public QObject { Q_OBJECT public: void tick( { }", encoding="utf-8")
    assert not _rebuild_code(tmp_path, changed_paths=[source], no_cluster=True,
                             acquire_lock=False, force=force)
    assert _ast_snapshot(tmp_path) == cache_before
    assert _snapshot(tmp_path) == products_before
    source.write_text(CPP, encoding="utf-8")
    assert _rebuild_code(tmp_path, changed_paths=[source], no_cluster=True, acquire_lock=False)
    assert _ast_snapshot(tmp_path) == cache_before


@pytest.mark.parametrize("native", [True, False], ids=["qt-scoped-source", "ordinary-cpp"])
def test_qml010_ac02_cpp_subfolder_rebase_rejects_only_native_scoped_facts(tmp_path, monkeypatch, capsys, native):
    project = tmp_path / "project"
    project.mkdir()
    _write(project, "backend.cpp", CPP if native else "int add(int value) { return value + 1; }\n")
    assert _rebuild_code(project, no_cluster=True, acquire_lock=False)
    before = _snapshot(project)
    monkeypatch.chdir(tmp_path)
    succeeded = _rebuild_code(Path("project"), force=True, no_cluster=True, acquire_lock=False)
    if native:
        assert not succeeded
        assert _snapshot(project) == before
        assert "QML_ROOT_MISMATCH" in capsys.readouterr().out
    else:
        assert succeeded
