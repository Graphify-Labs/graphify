"""D31: every admitted partial-work selector participates in bounded closure."""
from __future__ import annotations

import pytest

import graphify.extract as extraction
import graphify.filename_cohorts as cohorts
from graphify.build import _norm_source_file, build_from_json
from graphify.watch import _StoredSourcePaths, _rebuild_code
from tests.test_qt_final_incremental_parity import normalized, published
from tests.test_qt_initial_repeat import pin_graph_mtime
from tests.test_qt_product_publication import no_scratch, snapshot
from tests.test_source_alias_provenance import directory_alias  # noqa: F401


def corpus(root):
    """Two Terraform/JavaScript identity pairs require both forward and reverse expansion."""
    sources = {
        "main.mjs": "export function mainWork(){return 1;}\n",
        "main.tf": 'variable "region" { default = "west" }\n',
        "other.mjs": "export function otherWork(){return 2;}\n",
        "other.tf": 'output "region" { value = var.region }\n',
        "unrelated.py": "def unrelated(): return 7\n",
    }
    for name, source in sources.items():
        (root / name).write_text(source, encoding="utf-8")
    assert _rebuild_code(root, no_cluster=True, acquire_lock=False)
    return [root / name for name in sources]


@pytest.mark.parametrize("trigger", ["terraform", "filename"])
def test_req_qml011_ac03_terraform_and_filename_work_reach_joint_closure(tmp_path, monkeypatch, trigger):
    """Either selector can introduce the other's work; publication matches full without unrelated parses."""
    paths = corpus(tmp_path)
    initial = normalized(published(tmp_path))
    source = tmp_path / ("other.tf" if trigger == "terraform" else "main.mjs")
    addition = ('output "extra" { value = var.region }\n' if trigger == "terraform"
                else "export function added(){return mainWork();}\n")
    source.write_text(source.read_text(encoding="utf-8") + addition, encoding="utf-8")
    observed, real_extract = [], extraction.extract

    def observe(targets, **kwargs):
        observed.append(set(targets))
        return real_extract(targets, **kwargs)

    monkeypatch.setattr(extraction, "extract", observe)
    assert _rebuild_code(tmp_path, changed_paths=[source], no_cluster=True, acquire_lock=False)
    accepted = set(paths) - {tmp_path / "unrelated.py"}
    assert observed and set.union(*observed) == accepted
    current = normalized(published(tmp_path))
    clean = real_extract(paths, root=tmp_path, cache_root=tmp_path / ".clean", parallel=False)
    assert not clean["failed_sources"]
    assert current == normalized(build_from_json(clean, root=tmp_path))
    assert current != initial
    unrelated_ids = {identity for identity, data in published(tmp_path).nodes(data=True)
                     if data.get("source_file") == "unrelated.py"}
    assert unrelated_ids and all(current[0][identity] == initial[0][identity] for identity in unrelated_ids)
    graph = tmp_path / "graphify-out/graph.json"
    original, timestamp = pin_graph_mtime(graph)
    assert _rebuild_code(tmp_path, changed_paths=[source], no_cluster=True, acquire_lock=False)
    assert graph.read_bytes() == original and graph.stat().st_mtime_ns == timestamp
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    assert normalized(published(tmp_path)) == current


@pytest.mark.parametrize("violation", ["foreign", "discarded"])
def test_req_qml011_ac04_invalid_selector_result_retains_and_recovers(tmp_path, monkeypatch, capsys, violation):
    """The watch owner rejects an invalid selector result before accepting any product mutation."""
    corpus(tmp_path)
    output = tmp_path / "graphify-out"
    before = snapshot(output)
    assert before["graph.json"] is not None and before["manifest.json"] is not None
    source = tmp_path / "main.mjs"
    source.write_text(source.read_text(encoding="utf-8") + "export function added(){return 4;}\n", encoding="utf-8")
    original = cohorts.expand_filename_cohorts
    outside = tmp_path.parent / "unadmitted-private-source.py"

    def corrupted_result(selected, accepted, *, root, retired=()):
        result = original(selected, accepted, root=root, retired=retired)
        return [*result, outside] if violation == "foreign" else []

    capsys.readouterr()
    with monkeypatch.context() as failure:
        failure.setattr(cohorts, "expand_filename_cohorts", corrupted_result)
        assert not _rebuild_code(tmp_path, changed_paths=[source], no_cluster=True, acquire_lock=False)
    diagnostics = capsys.readouterr()
    assert "WATCH_SOURCE_IDENTITY_FAILED" in diagnostics.out + diagnostics.err
    assert str(outside) not in diagnostics.out + diagnostics.err
    assert snapshot(output) == before
    no_scratch(output)
    assert _rebuild_code(tmp_path, changed_paths=[source], no_cluster=True, acquire_lock=False)
    repaired = snapshot(output)
    assert repaired != before
    assert _rebuild_code(tmp_path, changed_paths=[source], no_cluster=True, acquire_lock=False)
    assert snapshot(output) == repaired
    no_scratch(output)


@pytest.mark.parametrize("prefix", ["real", "real2"])
def test_req_qml020_ac01_saved_root_alias_recognizes_only_exact_project_prefix(
        tmp_path, directory_alias, monkeypatch, prefix):
    """The verified canonical root prefix preserves CWD anchoring; a neighboring spelling cannot."""
    physical = tmp_path / "real"
    physical.mkdir()
    scan = directory_alias(tmp_path / "scan", physical)
    output = scan / "graphify-out"
    output.mkdir()
    (output / ".graphify_root").write_text("scan", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    source = f"{prefix}/retained.py"
    existing = {"nodes": [{"id": "retained", "source_file": source}]}
    paths = _StoredSourcePaths(existing, out=output, project_root=tmp_path,
                               watch_root=physical, normalize_source=_norm_source_file)
    assert paths.project_root == tmp_path
    assert paths.legacy_watch_relative == (prefix != "real")
    expected = tmp_path / source if prefix == "real" else physical / source
    assert paths.identity(source) == expected.as_posix()
