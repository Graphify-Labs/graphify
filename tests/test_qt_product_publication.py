"""INC-QML-25: real manual/watch updates publish one accepted product cohort."""
from __future__ import annotations

import os
from pathlib import Path
import stat
import sys

import pytest

import graphify.detect as detection
import graphify.qt_analysis_state as qt_state
import graphify.publication as publication
import graphify.watch as watch
from tests.test_qt_final_incremental_parity import clean, normalized, project, run


PRODUCTS = ("graph.json", ".graphify_root", "manifest.json", ".qt_analysis.json")


def snapshot(output):
    """Compare durable accepted bytes, including absent first-build products."""
    return {name: (output / name).read_bytes() if (output / name).exists() else None
            for name in PRODUCTS}


def no_scratch(output):
    assert not list(output.glob(".gfy-publish-*"))
    assert not (output / ".graph.tmp.json").exists()


def reject(root, monkeypatch, operation, source):
    if operation == "manual":
        with pytest.raises(SystemExit) as result:
            run(root, monkeypatch, operation, [source])
        assert result.value.code == 1
    else:
        assert not watch._rebuild_code(root, changed_paths=[source], no_cluster=True)


def accepted_project(root, monkeypatch, operation):
    source = project(root)
    monkeypatch.chdir(root)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(root, monkeypatch, operation)
    source.write_text(source.read_text(encoding="utf-8").replace("adjustment", "offset"),
                      encoding="utf-8", newline="")
    return source, initial, root / "graphify-out"


@pytest.mark.skipif(os.name != "nt", reason="Actual Windows read-only attribute")
@pytest.mark.parametrize("name", PRODUCTS)
@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_inc25_readonly_each_product_preserves_cohort_and_retries(tmp_path, monkeypatch, capsys, name, operation):
    """Each changed output rejects before any accepted sibling advances, then recovers."""
    source, initial, output = accepted_project(tmp_path, monkeypatch, operation)
    if name == ".graphify_root":
        marker = output / name
        marker.write_bytes(b"\xef\xbb\xbf" + marker.read_bytes() + b"\r\n")
    if name == ".qt_analysis.json":
        (tmp_path / "extra").mkdir()
        monkeypatch.setenv("GRAPHIFY_QML_IMPORT_ROOTS", '[".","extra"]')
    before = snapshot(output)
    target = output / name
    target.chmod(stat.S_IREAD)
    try:
        reject(tmp_path, monkeypatch, operation, source)
        assert snapshot(output) == before
        assert not target.stat().st_mode & stat.S_IWRITE
        assert "GRAPH_PUBLICATION_FAILED" in capsys.readouterr().out
        no_scratch(output)
    finally:
        target.chmod(stat.S_IWRITE)
    repaired = run(tmp_path, monkeypatch, operation, [source])
    assert normalized(repaired) != normalized(initial)
    # Clean extraction uses the same configured import roots, not a copied resolver.
    assert normalized(repaired) == normalized(clean(tmp_path, tmp_path / ".clean"))
    current = snapshot(output)
    assert normalized(run(tmp_path, monkeypatch, operation, [])) == normalized(repaired)
    assert snapshot(output) == current
    no_scratch(output)


@pytest.mark.parametrize("fault", ["manifest", "stamp", "replace"])
@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_inc25_preparation_and_late_replace_faults_preserve_then_retry(tmp_path, monkeypatch, capsys, fault, operation):
    """Real serializers run before an injected failure; a late replacement rolls back disk."""
    source, _, output = accepted_project(tmp_path, monkeypatch, operation)
    before = snapshot(output)
    with monkeypatch.context() as failure:
        if fault in {"manifest", "stamp"}:
            module, name = ((detection, "save_manifest") if fault == "manifest"
                            else (qt_state, "commit_qt_analysis"))
            original = getattr(module, name)

            def write_then_fail(*args, **kwargs):
                original(*args, **kwargs)
                raise OSError("public test preparation failure")

            failure.setattr(module, name, write_then_fail)
        else:
            original = watch.os_replace_with_fallback

            def fail_late(src, dst):
                if dst.name == "manifest.json":
                    raise OSError("public test publication failure")
                return original(src, dst)

            failure.setattr(watch, "os_replace_with_fallback", fail_late)
        reject(tmp_path, monkeypatch, operation, source)
    assert snapshot(output) == before
    assert "GRAPH_PUBLICATION_FAILED" in capsys.readouterr().out
    no_scratch(output)
    repaired = run(tmp_path, monkeypatch, operation, [source])
    assert normalized(repaired) == normalized(clean(tmp_path, tmp_path / ".clean"))
    current = snapshot(output)
    run(tmp_path, monkeypatch, operation, [])
    assert snapshot(output) == current


def test_inc25_clustered_report_failure_preserves_graph_and_sidecars(tmp_path, monkeypatch):
    """Clustering/report preparation cannot publish graph before a failed report write."""
    source = project(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert watch._rebuild_code(tmp_path)
    output = tmp_path / "graphify-out"
    names = (*PRODUCTS, "GRAPH_REPORT.md", ".graphify_labels.json", ".graphify_labels.json.sig")
    before = {name: (output / name).read_bytes() for name in names}
    source.write_text(source.read_text(encoding="utf-8").replace("adjustment", "offset"), encoding="utf-8")
    original = watch.write_text_atomic

    def report_fault(path, text, **kwargs):
        if path.name == "GRAPH_REPORT.md":
            raise OSError("public test report failure")
        return original(path, text, **kwargs)

    with monkeypatch.context() as failure:
        failure.setattr(watch, "write_text_atomic", report_fault)
        assert not watch._rebuild_code(tmp_path, changed_paths=[source])
    assert {name: (output / name).read_bytes() for name in names} == before
    no_scratch(output)
    assert watch._rebuild_code(tmp_path, changed_paths=[source])


def test_inc25_successful_ast_cache_does_not_authorize_failed_products(tmp_path, monkeypatch):
    """Content-keyed valid syntax may be reusable despite rejected graph publication."""
    source = tmp_path / "sample.py"
    source.write_text("def initial():\n    return 1\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert watch._rebuild_code(tmp_path, no_cluster=True)
    output = tmp_path / "graphify-out"
    before = snapshot(output)
    cache_root = output / "cache"
    caches = {path.relative_to(cache_root): path.read_bytes() for path in cache_root.rglob("*") if path.is_file()}
    source.write_text("def initial():\n    return 1\n\ndef added():\n    return initial()\n", encoding="utf-8")
    with monkeypatch.context() as failure:
        failure.setattr(detection, "save_manifest", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("failed manifest")))
        assert not watch._rebuild_code(tmp_path, changed_paths=[source], no_cluster=True)
    assert snapshot(output) == before
    after = {path.relative_to(cache_root): path.read_bytes() for path in cache_root.rglob("*") if path.is_file()}
    assert all(after.get(key) == original for key, original in caches.items())
    assert set(after) > set(caches)
    no_scratch(output)
    assert watch._rebuild_code(tmp_path, changed_paths=[source], no_cluster=True)


@pytest.mark.parametrize("no_cluster", [True, False])
def test_inc25_unchanged_graph_manifest_fault_is_still_rejected(tmp_path, monkeypatch, capsys, no_cluster):
    """An unchanged topology still needs committed input hashes before success."""
    source = tmp_path / "sample.py"
    source.write_text("def unchanged():\n    return 1\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert watch._rebuild_code(tmp_path, no_cluster=no_cluster)
    # Legacy raw output receives reconciliation provenance on its first reload;
    # establish that accepted steady-state before exercising the fast path.
    assert watch._rebuild_code(tmp_path, no_cluster=no_cluster)
    output = tmp_path / "graphify-out"
    before = snapshot(output)
    # A value-only edit changes accepted input bytes without changing declarations.
    source.write_text(source.read_text(encoding="utf-8").replace("return 1", "return 2"), encoding="utf-8")
    original = detection.save_manifest

    def fault(*args, **kwargs):
        original(*args, **kwargs)
        raise OSError("manifest preparation failed")

    with monkeypatch.context() as failure:
        failure.setattr(detection, "save_manifest", fault)
        assert not watch._rebuild_code(tmp_path, changed_paths=[source], no_cluster=no_cluster)
    assert snapshot(output) == before
    assert "GRAPH_PUBLICATION_FAILED" in capsys.readouterr().out
    no_scratch(output)
    assert watch._rebuild_code(tmp_path, changed_paths=[source], no_cluster=no_cluster)
    assert (output / "graph.json").read_bytes() == before["graph.json"]
    assert (output / "manifest.json").read_bytes() != before["manifest.json"]


def test_inc25_first_build_failure_publishes_no_acceptance_products(tmp_path, monkeypatch):
    """Failed preparation cannot bless a new graph with absent acceptance sidecars."""
    source = project(tmp_path)
    monkeypatch.chdir(tmp_path)
    output = tmp_path / "graphify-out"
    with monkeypatch.context() as failure:
        failure.setattr(detection, "save_manifest", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("manifest failure")))
        assert not watch._rebuild_code(tmp_path, changed_paths=[source], no_cluster=True)
    assert snapshot(output) == {name: None for name in PRODUCTS}
    no_scratch(output)
    assert watch._rebuild_code(tmp_path, changed_paths=[source], no_cluster=True)
    assert all((output / name).exists() for name in PRODUCTS)


@pytest.mark.parametrize("operation", ["manual", "watch"])
@pytest.mark.parametrize("phase", ["output_dir", "scratch_dir"])
def test_inc25_actual_caller_setup_failure_retains_and_redacts(tmp_path, monkeypatch, capsys, operation, phase):
    """The real driver logs only safe setup diagnostics, preserving all accepted bytes."""
    source, initial, output = accepted_project(tmp_path, monkeypatch, operation)
    before = snapshot(output)
    capsys.readouterr()
    private_marker = "synthetic-sensitive-location"
    error = PermissionError(13, private_marker + "\nbody", str(tmp_path / private_marker))
    mkdir = Path.mkdir

    def failed_mkdir(path, *args, **kwargs):
        # Isolate only the external transaction-directory syscall; queue/lock
        # setup and the real serializer/driver continue unchanged.
        if path == output and sys._getframe(1).f_code is publication.ProductPublication.__init__.__code__:
            raise error
        return mkdir(path, *args, **kwargs)

    def failed_scratch(*args, **kwargs):
        raise error

    with monkeypatch.context() as failure:
        if phase == "output_dir":
            failure.setattr(Path, "mkdir", failed_mkdir)
        else:
            failure.setattr(publication.tempfile, "mkdtemp", failed_scratch)
        reject(tmp_path, monkeypatch, operation, source)
    captured = capsys.readouterr()
    assert "GRAPH_PUBLICATION_FAILED" in captured.out
    assert private_marker not in captured.out + captured.err
    # The existing CLI progress message names its target. The new rejection
    # diagnostic must expose neither that path nor the underlying error body.
    diagnostic = next(line for line in captured.out.splitlines() if "Rebuild failed:" in line)
    assert str(tmp_path) not in diagnostic
    assert snapshot(output) == before
    no_scratch(output)
    repaired = run(tmp_path, monkeypatch, operation, [source])
    assert normalized(repaired) != normalized(initial)
    current = snapshot(output)
    run(tmp_path, monkeypatch, operation, [])
    assert snapshot(output) == current
    no_scratch(output)
