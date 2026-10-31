"""INC-QML-101: actual allocated member proof survives refresh and failed publication."""
from __future__ import annotations

from collections import Counter
import errno
import json
import os
from pathlib import Path
import tempfile

import pytest

from graphify.extract import extract
from graphify.watch import _rebuild_code
from tests.test_qt_final_incremental_parity import endpoints, manual_update, normalized, run, unrelated
from tests.test_qt_semantic_correction_updates import products


def project(root, *, invokable=True, ordinary=False):
    marker = "Q_INVOKABLE " if invokable else ""
    header = root / "native.hpp"
    header.write_bytes(("\ufeff// π allocated source\nclass Hpp;\n"
                        "class Hpp : public QObject { Q_OBJECT QML_NAMED_ELEMENT(Widget)\n"
                        f"public: {marker}void ping() {{}}\n}};\n"
                        + ("void ping() {}\n" if ordinary else "")).encode())
    qml = root / "Main.qml"
    qml.write_text("import Public.Allocated 1.0\nWidget { function run() { ping() } }", encoding="utf-8")
    cmake = root / "CMakeLists.txt"
    cmake.write_text("qt_add_qml_module(app URI Public.Allocated VERSION 1.0 QML_FILES Main.qml SOURCES native.hpp)", encoding="utf-8")
    (root / "keep.py").write_text("def helper():return 1\n\ndef retained():return helper()\n", encoding="utf-8")
    return header, qml, cmake


def calls(graph):
    return [(source, target, data) for source, target, data in graph.edges(data=True)
            if data.get("context") == "qml_js_call"]


def full_fields(graph):
    """Compare all attributes; only unpromised legacy undirected orientation is canonicalized."""
    return ({identity: json.dumps(data, sort_keys=True, ensure_ascii=False)
             for identity, data in graph.nodes(data=True)},
            Counter((*endpoints(graph, source, target, data), json.dumps(data, sort_keys=True, ensure_ascii=False))
                    for source, target, data in graph.edges(data=True)))


def cold_reference(root, monkeypatch, operation):
    """Rebuild through the same raw publication owner, retaining both evidence representations.

    Assembled Graph output folds repeated forward/body evidence into also_seen;
    raw no-cluster output preserves both observations. A cold raw reference must
    therefore use the actual same-root public owner. Retain test-owned products
    outside the admitted corpus, and restore the accepted cohort even on failure.
    """
    output = root / "graphify-out"
    retained = Path(tempfile.mkdtemp(prefix="allocated-member-products-", dir=root.parent)).resolve()
    assert output.resolve().parent == root.resolve() and retained.parent == root.resolve().parent
    saved, reference = retained / "accepted", retained / "cold-reference"
    assert output.is_dir() and not saved.exists() and not reference.exists()
    before = products(root)
    output.rename(saved)
    try:
        return run(root, monkeypatch, operation)
    finally:
        if output.exists():
            output.rename(reference)
        saved.rename(output)
        assert products(root) == before


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml022_ac06_allocated_member_cpp_and_qml_updates_remove_stale_endpoint_then_recover(tmp_path, monkeypatch, operation):
    """C++-only removal and later QML-only repair use fresh proof rather than the old salted method."""
    header, qml, _ = project(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(tmp_path, monkeypatch, operation)
    assert len(calls(initial)) == 1
    old_target = calls(initial)[0][1]
    header.write_bytes(header.read_bytes().replace(b"ping", b"pong"))
    removed = run(tmp_path, monkeypatch, operation, [header])
    assert not calls(removed) and old_target not in removed
    qml.write_bytes(qml.read_bytes().replace(b"ping", b"pong"))
    recovered = run(tmp_path, monkeypatch, operation, [qml])
    assert len(calls(recovered)) == 1 and calls(recovered)[0][1] != old_target
    assert full_fields(recovered) == full_fields(cold_reference(tmp_path, monkeypatch, operation))
    assert unrelated(initial) == unrelated(recovered)
    before = products(tmp_path)
    assert normalized(run(tmp_path, monkeypatch, operation, [])) == normalized(recovered)
    assert products(tmp_path) == before


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml022_ac06_allocated_member_graph_write_failure_retains_products_and_retries(tmp_path, monkeypatch, operation):
    """A real graph replacement error cannot commit refreshed allocator/member evidence early."""
    header, _, _ = project(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(tmp_path, monkeypatch, operation)
    assert len(calls(initial)) == 1
    before = products(tmp_path)
    header.write_bytes(header.read_bytes().replace(b"void ping() {}", b"void ping() {} int added;"))
    replace = os.replace

    def failure(source, target):
        if Path(target).resolve() == (tmp_path / "graphify-out/graph.json").resolve():
            raise OSError(errno.EIO, "isolated allocated-member publication failure")
        return replace(source, target)

    with monkeypatch.context() as scoped:
        scoped.setattr(os, "replace", failure)
        if operation == "manual":
            with pytest.raises(SystemExit) as rejected:
                manual_update(tmp_path, monkeypatch)
            assert rejected.value.code == 1
        else:
            assert not _rebuild_code(tmp_path, changed_paths=[header], no_cluster=True)
    assert products(tmp_path) == before
    recovered = run(tmp_path, monkeypatch, operation, [header])
    assert len(calls(recovered)) == 1
    assert full_fields(recovered) == full_fields(cold_reference(tmp_path, monkeypatch, operation))


def test_req_qml022_ac02_noninvokable_member_cannot_borrow_same_named_global_callable(tmp_path):
    """Correct source stamping leaves native exposure and own-metaobject gates authoritative."""
    paths = project(tmp_path, invokable=False, ordinary=True)
    result = extract(list(paths), root=tmp_path, cache_root=tmp_path, parallel=False)
    assert not result["failed_sources"] and not result.get("qml_failures")
    assert not any(edge.get("context") == "qml_js_call" for edge in result["edges"])
