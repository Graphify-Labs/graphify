"""Real Qt configuration refresh and successful-publication stamp ordering."""
from __future__ import annotations

import json
import pytest

import graphify.__main__ as mainmod
import graphify.extract as extraction
import graphify.qt_analysis_state as state
from graphify.extractors.qml_facts import qml_metadata
from graphify.paths import load_node_link_graph
from graphify.watch import _rebuild_code


def _write(root, path, source):
    destination = root / path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(source, encoding="utf-8")
    return destination


def _project(root):
    _write(root, "Main.qml", "import Public.Tools 1.0\nService { property int displayed: value }\n")
    _write(root, "keep.py", "\n".join(f"def retained_{index}(): return {index}" for index in range(20)))
    for directory, value in (("first", 1), ("second", 2)):
        _write(root, f"{directory}/Public/Tools/qmldir", "module Public.Tools\nService 1.0 Service.qml\n")
        _write(root, f"{directory}/Public/Tools/Service.qml", f"QtObject {{ property int value: {value} }}\n")


def _run(root, monkeypatch, operation, *, initial=False, changes=None, force=False):
    if operation == "watch":
        return _rebuild_code(root, changed_paths=None if initial else (changes or []),
                             no_cluster=True, acquire_lock=False, force=force)
    argv = ["graphify", "extract", str(root), "--code-only", "--no-cluster"]
    if force:
        argv += ["--force", "--allow-partial"]
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod, "_refresh_stale_skills", lambda: None)
    monkeypatch.setattr(mainmod.sys, "argv", argv)
    try:
        mainmod.main()
    except SystemExit as exc:
        return exc.code in (None, 0)
    return True


def _graph(root):
    return load_node_link_graph(json.loads((root / "graphify-out/graph.json").read_text(encoding="utf-8")))


def _provider(root):
    graph = _graph(root)
    sites = [identity for identity, node in graph.nodes(data=True)
             if node.get("source_file") == "Main.qml" and qml_metadata(node).get("kind") == "type_use"]
    assert len(sites) == 1
    assert qml_metadata(graph.nodes[sites[0]])["status"] == "resolved"
    links = [data.get("_tgt", target) for source, target, data in graph.edges(data=True)
             if data.get("_src", source) == sites[0] and data.get("relation") == "uses"]
    assert len(links) == 1
    return graph.nodes[links[0]]["source_file"]


def _stamp(root):
    return json.loads((root / "graphify-out" / state.QT_STATE_FILE).read_text(encoding="utf-8"))


def _snapshot(root):
    out = root / "graphify-out"
    return {name: (out / name).read_bytes() for name in
            ("graph.json", "manifest.json", state.QT_STATE_FILE)}


@pytest.mark.parametrize("operation", ["watch", "extract"])
def test_qml011_ac03_import_root_order_refreshes_unchanged_source_provider(tmp_path, monkeypatch, operation):
    _project(tmp_path)
    monkeypatch.setenv("GRAPHIFY_QML_IMPORT_ROOTS", '["first", "second"]')
    assert _run(tmp_path, monkeypatch, operation, initial=True)
    assert _provider(tmp_path) == "first/Public/Tools/Service.qml"
    before = _stamp(tmp_path)
    observed, real = [], extraction.extract

    def observe(paths, **kwargs):
        observed.extend(paths)
        return real(paths, **kwargs)

    monkeypatch.setattr(extraction, "extract", observe)
    monkeypatch.setenv("GRAPHIFY_QML_IMPORT_ROOTS", '["second", "first"]')
    assert _run(tmp_path, monkeypatch, operation)
    assert tmp_path / "Main.qml" in observed
    assert _provider(tmp_path) == "second/Public/Tools/Service.qml"
    assert _stamp(tmp_path)["fingerprint"] != before["fingerprint"]


@pytest.mark.parametrize("operation", ["watch", "extract"])
def test_qml011_ac03_package_version_change_reanalyzes_unchanged_corpus(tmp_path, monkeypatch, operation):
    _write(tmp_path, "Main.qml", "QtObject { property int value: 1 }\n")
    assert _run(tmp_path, monkeypatch, operation, initial=True)
    before = _stamp(tmp_path)
    real_version, real_extract, observed = state.version, extraction.extract, []

    def changed_version(package):
        original = real_version(package)
        return original + "+contract-probe" if package == "tree-sitter" else original

    def observe(paths, **kwargs):
        observed.extend(paths)
        return real_extract(paths, **kwargs)

    monkeypatch.setattr(state, "version", changed_version)
    monkeypatch.setattr(extraction, "extract", observe)
    assert _run(tmp_path, monkeypatch, operation)
    assert tmp_path / "Main.qml" in observed
    assert _stamp(tmp_path)["fingerprint"] != before["fingerprint"]
    assert all(qml_metadata(node).get("contract_version") == 1 for _, node in _graph(tmp_path).nodes(data=True))


@pytest.mark.parametrize("operation", ["watch", "extract"])
def test_qml011_ac02_last_qt_source_deletion_cleans_facts_and_commits_nonqt_state(tmp_path, monkeypatch, operation):
    source = _write(tmp_path, "Main.qml", "QtObject { property int value: 1 }\n")
    _write(tmp_path, "keep.py", "\n".join(f"def retained_{index}(): return {index}" for index in range(20)))
    assert _run(tmp_path, monkeypatch, operation, initial=True)
    assert _stamp(tmp_path)["has_qt"] is True
    source.unlink()
    assert _run(tmp_path, monkeypatch, operation, changes=[source])
    graph = _graph(tmp_path)
    assert not any(qml_metadata(node) for _, node in graph.nodes(data=True))
    assert any(node.get("label") == "retained_0()" for _, node in graph.nodes(data=True))
    assert _stamp(tmp_path)["has_qt"] is False
    before = _snapshot(tmp_path)
    assert _run(tmp_path, monkeypatch, operation)
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize("operation", ["watch", "extract"])
@pytest.mark.parametrize("name,invalid", [
    ("Broken.qml", "Item { property int value: }"),
    ("broken.qrc", '<!DOCTYPE RCC [<!ENTITY x SYSTEM "file:///outside">]><RCC/>'),
    ("new.cmake", "if(ENABLE)\nqt_add_qml_module(app URI Public.Tools)\nendif()"),
])
def test_qml012_ac02_malformed_new_source_preserves_graph_manifest_and_stamp(tmp_path, monkeypatch, operation, name, invalid):
    _write(tmp_path, "Main.qml", "QtObject { property int value: 1 }\n")
    assert _run(tmp_path, monkeypatch, operation, initial=True)
    before = _snapshot(tmp_path)
    source = _write(tmp_path, name, invalid)
    assert not _run(tmp_path, monkeypatch, operation, changes=[source], force=True)
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize("operation", ["watch", "extract"])
@pytest.mark.parametrize("config", ["not JSON", '["../outside"]', '["/absolute"]'])
def test_qml012_ac02_invalid_import_configuration_preserves_prior_stamp(tmp_path, monkeypatch, operation, config):
    _write(tmp_path, "Main.qml", "QtObject { property int value: 1 }\n")
    assert _run(tmp_path, monkeypatch, operation, initial=True)
    before = _snapshot(tmp_path)
    monkeypatch.setenv("GRAPHIFY_QML_IMPORT_ROOTS", config)
    assert not _run(tmp_path, monkeypatch, operation, force=True)
    assert _snapshot(tmp_path) == before
