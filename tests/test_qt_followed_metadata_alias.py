"""INC-QML-50: typed producers preserve admitted lexical source owners."""
from __future__ import annotations

import json
import os
import copy
from pathlib import Path
from typing import Protocol

import pytest

import graphify.extract as extraction
from graphify.export import to_json
from graphify.extractors import LANGUAGE_EXTRACTORS
from graphify.extractors.qml_facts import qml_metadata
from graphify.paths import load_node_link_graph
from graphify.watch import _rebuild_code
from graphify.qt_project_index import QtProjectIndex
from graphify.qt_project_membership import resolve_project_memberships
from tests.test_qt_final_incremental_parity import normalized, run
from tests.test_qt_product_publication import no_scratch, snapshot
from tests.test_qt_short_leaf_aliases import short_leaf
from tests.test_source_alias_provenance import directory_alias  # noqa: F401
from tests.test_upstream_qt_discovery_integration import corpus, direct, assert_membership
from tests.test_watch_physical_coowners import cache_bytes


CASES = [
    ("Main.qml", "qml", "// Ω\nimport QtQml\nQtObject { property int localValue: 7; "
                         "property int doubled: localValue * 2; function fetch() { "
                         "function inner() { return doubled } return inner() } }\n"),
    ("qmldir", "qmldir", "# Ω\nmodule Public.Hidden\nHidden 1.0 Main.qml\n"),
    ("CMakeLists.txt", "cmake", "# Ω\nqt_add_qml_module(hidden URI Public.Hidden VERSION 1.0 QML_FILES Main.qml)\n"),
    ("module.cmake", "cmake", "# Ω\nqt_add_qml_module(hidden URI Public.Hidden VERSION 1.0)\n"),
    ("tools.pro", "qmake", "# Ω\nQML_IMPORT_NAME = Public.Hidden\nQML_IMPORT_VERSION = 1.0\n"),
    ("tools.pri", "qmake", "# Ω\nQML_IMPORT_NAME = Public.Hidden\nQML_IMPORT_VERSION = 1.0\n"),
    ("resources.qrc", "qrc", '<!-- Ω -->\n<RCC><qresource prefix="/ui"><file alias="Main.qml">Main.qml</file></qresource></RCC>\n'),
    ("plugins.qmltypes", "qmltypes", '// Ω\nimport QtQuick.tooling 1.2\nModule { Component { name: "Hidden"; exports: ["Public.Hidden/Hidden 1.0"] } }\n'),
]


class QtReader(Protocol):
    def __call__(self, path: Path, *, root: Path | None = None) -> dict: ...


READERS: dict[str, QtReader] = {
    "qml": extraction.extract_qml, "qmldir": extraction.extract_qmldir,
    "cmake": extraction.extract_cmake, "qmake": extraction.extract_qmake,
    "qrc": extraction.extract_qrc, "qmltypes": extraction.extract_qmltypes,
}


def reader_for(key: str) -> QtReader:
    """Check the selected production registry interface without casting its heterogeneous seed."""
    reader = READERS[key]
    assert LANGUAGE_EXTRACTORS[key] is reader
    return reader


def owned_facts(result, expected, raw):
    """Read exact producer facts and verify locations against original BOM/CRLF bytes."""
    assert not result.get("error") and not result.get("qml_failures"), result
    nodes, edges = result["nodes"], result["edges"]
    assert nodes and all(item.get("source_file") == expected for item in nodes + edges)
    ids = {node["id"] for node in nodes}
    assert all(edge["source"] in ids and edge["target"] in ids for edge in edges)
    spans = []
    for node in nodes:
        metadata = qml_metadata(node)
        assert all(not metadata.get(key) or metadata[key] in ids
                   for key in ("owner_id", "lexical_target_id", "callback_lexical_target_id"))
        span = metadata["span"]
        start, end = span["start_byte"], span["end_byte"]
        assert 0 <= start < end <= len(raw)
        assert raw[start:end].decode("utf-8")
        prefix = raw[:start]
        assert span["start_row"] == prefix.count(b"\n")
        assert span["start_column"] == len(prefix.rsplit(b"\n", 1)[-1])
        spans.append((qml_metadata(node)["kind"], span))
    scopes = {qml_metadata(node)[key] for node in nodes
              for key in ("component_key", "object_scope_key") if qml_metadata(node).get(key)}
    if expected.endswith("Main.qml"):
        assert any(qml_metadata(node).get("owner_id") for node in nodes)
        assert any(qml_metadata(node).get("lexical_target_id") for node in nodes)
    return ids, spans, scopes


@pytest.mark.parametrize("name,key,text", CASES, ids=[case[0] for case in CASES])
@pytest.mark.parametrize("aliased_root", [False, True])
def test_req_qml020_ac02_typed_producers_keep_distinct_alias_facts_and_original_spans(
        tmp_path, directory_alias, name, key, text, aliased_root):
    """Real directory links keep separate source IDs, even beneath an aliased scan root."""
    root = tmp_path / "repo"
    real = root / "real"
    real.mkdir(parents=True)
    raw = b"\xef\xbb\xbf" + text.replace("\n", "\r\n").encode("utf-8")
    (real / name).write_bytes(raw)
    directory_alias(root / "linked", real)
    scan = directory_alias(tmp_path / "scan", root) if aliased_root else root
    reader = reader_for(key)
    physical = owned_facts(reader(scan / "real" / name, root=scan), f"real/{name}", raw)
    alias = owned_facts(reader(scan / "linked" / name, root=scan), f"linked/{name}", raw)
    assert physical[0].isdisjoint(alias[0]) and physical[1] == alias[1]
    assert physical[2].isdisjoint(alias[2])
    assert (real / name).read_bytes() == raw


def test_req_qml020_ac02_followed_metadata_facade_keeps_every_owner_cold_warm_and_reload(
        tmp_path, directory_alias):
    """The original failing graph assertion survives as ordinary producer/facade acceptance."""
    root = tmp_path / "repo"
    corpus(root)
    directory_alias(root / "linked module Ω", root / "qmltools")
    cold = direct(root, tmp_path / "cache", True)
    warm = direct(root, tmp_path / "cache", True)
    assert normalized(cold) == normalized(warm)
    assert_membership(warm)
    for name in ("qmldir", "tools.pro", "Hidden.qml"):
        canonical = {identity for identity, node in warm.nodes(data=True)
                     if node.get("source_file") == f"qmltools/{name}"}
        alias = {identity for identity, node in warm.nodes(data=True)
                 if node.get("source_file") == f"linked module Ω/{name}"}
        assert canonical and alias and canonical.isdisjoint(alias)
    target = tmp_path / "reloaded.json"
    assert to_json(warm, {}, str(target), force=True)
    assert normalized(load_node_link_graph(json.loads(target.read_text(encoding="utf-8")))) == normalized(warm)


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml020_ac03_typed_alias_updates_remove_stale_facts_and_match_full_rebuild(
        tmp_path, monkeypatch, directory_alias, operation):
    """One physical QML/metadata edit refreshes each admitted owner; deletion retires only the alias."""
    root = tmp_path / "repo"
    corpus(root)
    directory_alias(root / "linked", root / "qmltools")
    monkeypatch.chdir(root)
    initial = run(root, monkeypatch, operation, follow_symlinks=True)
    source = root / "qmltools/Hidden.qml"
    source.write_text("import QtQml\nQtObject { property int replacement: 11 }\n", encoding="utf-8")
    edited = run(root, monkeypatch, operation, [source], follow_symlinks=True)
    assert normalized(edited) != normalized(initial)
    assert normalized(edited) == normalized(direct(root, tmp_path / "clean", True))
    for owner in ("qmltools/Hidden.qml", "linked/Hidden.qml"):
        names = {qml_metadata(node).get("raw_name") for _, node in edited.nodes(data=True)
                 if node.get("source_file") == owner}
        assert "replacement" in names and "localValue" not in names
    # Retain the owned link for fixture teardown while removing it from the scan.
    (root / ".graphifyignore").write_text("blocked/\nlinked/\n", encoding="utf-8")
    retired = run(root, monkeypatch, operation, [root / ".graphifyignore"], follow_symlinks=True)
    assert not any(node.get("source_file", "").startswith("linked/") for _, node in retired.nodes(data=True))
    assert normalized(retired) == normalized(direct(root, tmp_path / "retired", True))
    accepted = snapshot(root / "graphify-out")
    assert normalized(run(root, monkeypatch, operation, [], follow_symlinks=True)) == normalized(retired)
    assert snapshot(root / "graphify-out") == accepted


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml020_ac03_alias_read_failure_retains_cohort_cache_and_repairs(
        tmp_path, monkeypatch, directory_alias, operation):
    """A malformed shared typed input rejects publication and repair restores both source owners."""
    root = tmp_path / "repo"
    corpus(root)
    directory_alias(root / "linked", root / "qmltools")
    monkeypatch.chdir(root)
    initial = run(root, monkeypatch, operation, follow_symlinks=True)
    source, output = root / "qmltools/qmldir", root / "graphify-out"
    original, before, cached = source.read_bytes(), snapshot(output), cache_bytes(output)
    source.write_bytes(b"\xff\x00")
    if operation == "manual":
        with pytest.raises(SystemExit) as rejected:
            run(root, monkeypatch, operation, follow_symlinks=True)
        assert rejected.value.code == 1
    else:
        assert not _rebuild_code(root, changed_paths=[source], no_cluster=True, follow_symlinks=True)
    assert snapshot(output) == before and cache_bytes(output) == cached
    no_scratch(output)
    source.write_bytes(original)
    repaired = run(root, monkeypatch, operation, [source], follow_symlinks=True)
    assert normalized(repaired) == normalized(initial) == normalized(direct(root, tmp_path / "clean", True))
    accepted = snapshot(output)
    assert normalized(run(root, monkeypatch, operation, [], follow_symlinks=True)) == normalized(repaired)
    assert snapshot(output) == accepted


@pytest.mark.parametrize("name,key,text", CASES, ids=[case[0] for case in CASES])
def test_req_qml020_ac02_typed_alias_cannot_authorize_foreign_physical_source(
        tmp_path, directory_alias, name, key, text):
    """A lexically in-root link cannot borrow containment for an external source."""
    root, foreign = tmp_path / "repo", tmp_path / "foreign"
    root.mkdir()
    foreign.mkdir()
    (foreign / name).write_text(text, encoding="utf-8")
    directory_alias(root / "outside", foreign)
    result = reader_for(key)(root / "outside" / name, root=root)
    assert result.get("error") and not result["nodes"] and not result["edges"]
    assert not extraction.collect_files(root, root=root, follow_symlinks=True)


@pytest.mark.parametrize("name,key,text", CASES, ids=[case[0] for case in CASES])
def test_req_qml020_ac02_malformed_typed_alias_keeps_lexical_diagnostic_context(
        tmp_path, directory_alias, name, key, text):
    """Unreadable original bytes fail safely under the actual source owner, without partial facts."""
    root = tmp_path / "repo"
    real = root / "real"
    real.mkdir(parents=True)
    (real / name).write_bytes(b"\xff\x00")
    directory_alias(root / "linked", real)
    result = reader_for(key)(root / "linked" / name, root=root)
    assert result.get("error") and not result["nodes"] and not result["edges"]
    assert result["diagnostics"] and all(
        item["source_file"] == f"linked/{name}" for item in result["diagnostics"])


def test_req_qml020_ac02_membership_rejects_another_walked_owner_of_same_physical_input(
        tmp_path, directory_alias):
    """Physical equality cannot legitimize declaration facts borrowed from a different admitted owner."""
    root = tmp_path / "repo"
    corpus(root)
    directory_alias(root / "linked", root / "qmltools")
    result = extraction.extract(extraction.collect_files(root, root=root, follow_symlinks=True),
                                root=root, cache_root=tmp_path / "cache", parallel=False)
    assert not result["failed_sources"] and not result["qml_failures"]
    nodes, edges = copy.deepcopy((result["nodes"], result["edges"]))
    declaration = next(node for node in nodes if node.get("source_file") == "qmltools/tools.pro"
                       and qml_metadata(node).get("kind") == "qt_source")
    active = {root / "linked/tools.pro": {"nodes": [declaration], "edges": []}}
    index = QtProjectIndex(nodes, edges, root=root)
    before = copy.deepcopy((nodes, edges, active))
    with pytest.raises(ValueError, match="QML_METADATA: membership declaration source is not accepted"):
        resolve_project_memberships(active, nodes, edges, root=root, project_index=index)
    assert (nodes, edges, active) == before


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml020_ac03_policy21_alias_products_refresh_retain_and_recover(
        tmp_path, monkeypatch, directory_alias, operation):
    """No-edit epoch refresh executes actual producers; failed staged publication retains the prior cohort."""
    import graphify.qt_analysis_state as state
    import graphify.qt_incremental as policy

    root = tmp_path / "repo"
    corpus(root)
    directory_alias(root / "linked", root / "qmltools")
    monkeypatch.chdir(root)
    with monkeypatch.context() as prior:
        prior.setattr(policy, "QT_POLICY_VERSION", 21)
        run(root, prior, operation, follow_symlinks=True)
    output = root / "graphify-out"
    before, cached, old_stamp = snapshot(output), cache_bytes(output), state.read_qt_fingerprint(output)
    observed, real_extract = [], extraction.extract

    def record(paths, *args, **kwargs):
        paths = list(paths)
        observed.append({path.relative_to(root).as_posix() for path in paths})
        return real_extract(paths, *args, **kwargs)

    monkeypatch.setattr(extraction, "extract", record)
    real_commit = state.commit_qt_analysis

    def reject_after_staging(*args, **kwargs):
        real_commit(*args, **kwargs)
        raise OSError("Public alias fixture publication failure")

    with monkeypatch.context() as failed:
        failed.setattr(state, "commit_qt_analysis", reject_after_staging)
        if operation == "manual":
            with pytest.raises(SystemExit) as rejection:
                run(root, failed, operation, [], follow_symlinks=True)
            assert rejection.value.code == 1
        else:
            assert not _rebuild_code(root, changed_paths=[], no_cluster=True, follow_symlinks=True)
    assert snapshot(output) == before and cache_bytes(output) == cached
    assert state.read_qt_fingerprint(output) == old_stamp
    no_scratch(output)
    repaired = run(root, monkeypatch, operation, [], follow_symlinks=True)
    assert state.read_qt_fingerprint(output) != old_stamp
    required = {f"{owner}/{name}" for owner in ("qmltools", "linked")
                for name in ("qmldir", "tools.pro", "Hidden.qml")}
    assert observed and required <= set.union(*observed)
    assert required <= {node.get("source_file") for _, node in repaired.nodes(data=True)}
    assert normalized(repaired) == normalized(direct(root, tmp_path / "clean", True))
    accepted = snapshot(output)
    assert normalized(run(root, monkeypatch, operation, [], follow_symlinks=True)) == normalized(repaired)
    assert snapshot(output) == accepted


@pytest.mark.skipif(os.name != "nt", reason="Actual NTFS short-file spelling")
@pytest.mark.parametrize("name,key,text", [CASES[0], CASES[2], CASES[7]], ids=["qml", "cmake", "qmltypes"])
def test_req_qml020_ac01_direct_typed_reader_short_leaf_is_an_alternate_spelling(
        tmp_path, name, key, text):
    """Real native leaf aliases canonicalize before source IDs, independently of facade admission."""
    path = tmp_path / ("LongCanonical" + name if name != "CMakeLists.txt" else name)
    path.write_text(text, encoding="utf-8")
    reader = reader_for(key)
    assert reader(short_leaf(path), root=tmp_path) == reader(path, root=tmp_path)
