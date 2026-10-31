"""INC-QML-49: upstream corpus exclusions coexist with Qt metadata discovery."""
from __future__ import annotations

from pathlib import Path

import pytest

import graphify.detect as detection
import graphify.extract as extraction
from graphify.build import build_from_json
from graphify.extractors.qml_facts import qml_metadata
from graphify.watch import _rebuild_code
from tests.test_qt_final_incremental_parity import (
    assert_native_fixture, normalized, project, run,
)
from tests.test_qt_product_publication import no_scratch, snapshot
from tests.test_source_alias_provenance import directory_alias  # noqa: F401
from tests.test_watch_physical_coowners import cache_bytes


INSTALLED = ".opencode/plugins/graphify.js"
ORDINARY = "src/plugins/graphify.js"
MANIFESTS = {"CMakeLists.txt", "qmltools/qmldir", "qmltools/tools.pro"}


def corpus(root):
    """A real native bridge, independent qmake module and copied hook share one scan."""
    root.mkdir()
    project(root)
    files = {
        INSTALLED: "// graphify generated hook\nfunction copiedHook() { return 7; }\n",
        ORDINARY: "// graphify generated hook\nfunction copiedHook() { return 7; }\n",
        "qmltools/qmldir": "module Public.Hidden\nHidden 1.0 Hidden.qml\n",
        "qmltools/tools.pro": "QT += qml\nQML_IMPORT_NAME = Public.Hidden\n"
                              "QML_IMPORT_VERSION = 1.0\nQML_FILES += Hidden.qml\n",
        "qmltools/Hidden.qml": "import QtQml\nQtObject { property int localValue: 7 }\n",
        "NOT_METADATA": "Item { property int excluded: 1 }\n",
        ".graphifyignore": "blocked/\n",
    }
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    # Malformed excluded metadata must never reach an extractor or resolver.
    (root / "blocked").mkdir()
    for name in ("CMakeLists.txt", "qmldir", "Hidden.qml"):
        (root / "blocked" / name).write_bytes(b"\xff\x00")


def collected(root, follow):
    return extraction.collect_files(root, root=root, follow_symlinks=follow)


def direct(root, cache, follow):
    """Exercise the actual collector, facade, Qt resolver and graph assembly."""
    facts = extraction.extract(collected(root, follow), root=root, cache_root=cache,
                               parallel=False)
    assert not facts["failed_sources"] and not facts["qml_failures"]
    return build_from_json(facts, root=root)


def assert_membership(graph):
    sources = {node.get("source_file") for _, node in graph.nodes(data=True)}
    assert MANIFESTS <= sources and ORDINARY in sources and INSTALLED not in sources
    assert "NOT_METADATA" not in sources
    assert not any(source and source.startswith(("blocked/", "outside/")) for source in sources)
    assert any(qml_metadata(node).get("kind") == "qt_module"
               for _, node in graph.nodes(data=True) if node.get("source_file") == "CMakeLists.txt")
    assert any(qml_metadata(node).get("kind") == "module"
               for _, node in graph.nodes(data=True) if node.get("source_file") == "qmltools/qmldir")
    assert_native_fixture(graph)


@pytest.mark.parametrize("follow", [False, True])
def test_req_qml002_ac02_ac03_detect_and_collect_share_named_metadata_and_copy_exclusions(
        tmp_path, follow):
    """Both directory profiles keep exact-name manifests and reject only installed path shapes."""
    root = tmp_path / "repo"
    corpus(root)
    detected = {Path(path).relative_to(root).as_posix()
                for paths in detection.detect(root, follow_symlinks=follow)["files"].values()
                for path in paths}
    actual = {path.relative_to(root).as_posix() for path in collected(root, follow)}
    for sources in (detected, actual):
        assert MANIFESTS <= sources and ORDINARY in sources and INSTALLED not in sources
        assert "NOT_METADATA" not in sources
        assert not any(path.startswith("blocked/") for path in sources)


def test_req_qml002_ac03_ac04_followed_metadata_keeps_lexical_scope_and_rejects_foreign_input(
        tmp_path, directory_alias):
    """Actual junctions/symlinks retain portable admitted names and exclude an external malformed module."""
    root, foreign = tmp_path / "repo", tmp_path / "foreign"
    corpus(root)
    foreign.mkdir()
    for name in ("CMakeLists.txt", "qmldir", "Foreign.qml"):
        (foreign / name).write_bytes(b"\xff\x00")
    directory_alias(root / "linked module Ω", root / "qmltools")
    directory_alias(root / "outside", foreign)
    paths = {path.relative_to(root).as_posix() for path in collected(root, True)}
    assert {"linked module Ω/qmldir", "linked module Ω/tools.pro", "linked module Ω/Hidden.qml"} <= paths
    assert not any(path.startswith("outside/") for path in paths)


@pytest.mark.parametrize("follow", [False, True])
def test_req_qml002_ac02_direct_cold_warm_facts_keep_qt_metadata_and_real_application_code(
        tmp_path, follow):
    """The facade preserves metadata/native joins while the copied installed hook contributes no facts."""
    root = tmp_path / "repo"
    corpus(root)
    cold = direct(root, tmp_path / "cold", follow)
    warm = direct(root, tmp_path / "cold", follow)
    assert_membership(cold)
    assert normalized(cold) == normalized(warm)


@pytest.mark.parametrize("follow", [False, True])
@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml011_ac03_ac04_updates_preserve_exclusions_metadata_and_clean_parity(
        tmp_path, monkeypatch, operation, follow):
    """Real publication refreshes admitted metadata/code, ignores copied hook edits and is repeatable."""
    root = tmp_path / "repo"
    corpus(root)
    monkeypatch.chdir(root)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    graph = run(root, monkeypatch, operation, follow_symlinks=follow)
    assert_membership(graph)
    before = snapshot(root / "graphify-out")
    (root / INSTALLED).write_text("function replacementPoison() { return 9; }\n", encoding="utf-8")
    assert normalized(run(root, monkeypatch, operation, [], follow_symlinks=follow)) == normalized(graph)
    assert snapshot(root / "graphify-out") == before
    metadata, source = root / "qmltools/qmldir", root / ORDINARY
    metadata.write_text("module Public.Hidden\nHidden 1.0 Hidden.qml\nprefer :/hidden/\n", encoding="utf-8")
    source.write_text("function applicationEdit() { return 11; }\n", encoding="utf-8")
    updated = run(root, monkeypatch, operation, [metadata, source], follow_symlinks=follow)
    assert_membership(updated)
    assert any(qml_metadata(node).get("kind") == "prefer"
               and qml_metadata(node).get("value") == ":/hidden/"
               for _, node in updated.nodes(data=True)
               if node.get("source_file") == "qmltools/qmldir")
    assert normalized(updated) != normalized(graph)
    assert normalized(updated) == normalized(direct(root, tmp_path / "clean", follow))
    accepted = snapshot(root / "graphify-out")
    assert normalized(run(root, monkeypatch, operation, [], follow_symlinks=follow)) == normalized(updated)
    assert snapshot(root / "graphify-out") == accepted
    no_scratch(root / "graphify-out")


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml018_ac06_malformed_admitted_metadata_retains_cohort_and_recovers(
        tmp_path, monkeypatch, operation):
    """A real invalid UTF-8 manifest fails before publication; repair and repeat retain correct facts."""
    root = tmp_path / "repo"
    corpus(root)
    monkeypatch.chdir(root)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(root, monkeypatch, operation, follow_symlinks=True)
    source, output = root / "qmltools/qmldir", root / "graphify-out"
    original, before, cached = source.read_bytes(), snapshot(output), cache_bytes(output)
    assert cached
    source.write_bytes(b"\xff\x00")
    if operation == "manual":
        with pytest.raises(SystemExit) as rejected:
            run(root, monkeypatch, operation, follow_symlinks=True)
        assert rejected.value.code == 1
    else:
        assert not _rebuild_code(root, changed_paths=[source], no_cluster=True,
                                 follow_symlinks=True)
    assert snapshot(output) == before and cache_bytes(output) == cached
    no_scratch(output)
    source.write_bytes(original)
    repaired = run(root, monkeypatch, operation, [source], follow_symlinks=True)
    assert normalized(repaired) == normalized(initial)
    assert_membership(repaired)
    assert normalized(repaired) == normalized(direct(root, tmp_path / "clean", True))
    accepted = snapshot(output)
    assert normalized(run(root, monkeypatch, operation, [], follow_symlinks=True)) == normalized(repaired)
    assert snapshot(output) == accepted
