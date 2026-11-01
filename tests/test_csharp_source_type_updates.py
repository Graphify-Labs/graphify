"""INC-QML-91/94: source type corrections survive real updates and publication failure."""
from __future__ import annotations

import errno
import os
from pathlib import Path

import pytest

from graphify.watch import _rebuild_code
from tests.test_qt_final_incremental_parity import clean, manual_update, normalized, run, unrelated
from tests.test_qt_semantic_correction_updates import products


def fixture(root, family, *, changed=False):
    path = root / "Members.cs"
    declarations = "namespace Domain{class Widget{}class Other{}}class Worker{public void Run(){}}class T{public void Run(){}}"
    if family == "property":
        member = "public " + ("T" if changed else "Worker") + " Item{get;set;}void Use(){Item.Run();}"
    else:
        member = "System.Collections.Generic.Dictionary<string,Domain." + ("Other" if changed else "Widget") + "> values;"
    path.write_text(declarations + "class Holder<T>{" + member + "}")
    (root / "keep.py").write_text("def helper():return 1\n\ndef retained():return helper()\n")
    return path


def assert_meaning(graph, family, *, changed):
    if family == "property":
        # Legacy undirected C# storage has no reload-direction promise, and
        # assembly qualifies method display labels with their actual class.
        pairs = [set((graph.nodes[source]["label"], graph.nodes[target]["label"]))
                 for source, target, data in graph.edges(data=True)
                 if data.get("relation") == "calls" and "Holder.Use()" in
                 {graph.nodes[source]["label"], graph.nodes[target]["label"]}]
        assert bool(pairs) is not changed
        if not changed:
            assert pairs == [{"Holder.Use()", "Worker.Run()"}]
    else:
        expected = "Other" if changed else "Widget"
        facts = [(set((graph.nodes[source]["label"], graph.nodes[target]["label"])), data)
                 for source, target, data in graph.edges(data=True)
                 if data.get("relation") == "references" and data.get("context") == "generic_arg"]
        assert len(facts) == 1 and facts[0][0] == {"Holder", expected}
        assert facts[0][1]["metadata"]["ref_token"] == expected


@pytest.mark.parametrize("family", ["property", "qualified_argument"])
@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml022_ac06_source_type_edits_retire_old_edges_and_settle(tmp_path, monkeypatch, family, operation):
    """Actual source type changes retire false/stale relationships and match cold results after durable publication."""
    path = fixture(tmp_path, family)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(tmp_path, monkeypatch, operation)
    assert_meaning(initial, family, changed=False)
    fixture(tmp_path, family, changed=True)
    updated = run(tmp_path, monkeypatch, operation, [path])
    assert_meaning(updated, family, changed=True)
    assert normalized(updated) == normalized(clean(tmp_path, tmp_path / ".cold"))
    assert unrelated(initial) == unrelated(updated)
    before = products(tmp_path)
    assert normalized(run(tmp_path, monkeypatch, operation, [])) == normalized(updated)
    assert products(tmp_path) == before


@pytest.mark.parametrize("family", ["property", "qualified_argument"])
@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml022_ac06_source_type_write_failure_retains_then_recovers(tmp_path, monkeypatch, family, operation):
    """A real graph replacement failure retains the accepted source interpretation until a successful retry."""
    path = fixture(tmp_path, family)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(tmp_path, monkeypatch, operation)
    before = products(tmp_path)
    fixture(tmp_path, family, changed=True)
    actual = os.replace

    def reject(source, target):
        if Path(target).resolve() == (tmp_path / "graphify-out/graph.json").resolve():
            raise OSError(errno.EIO, "isolated C# source type publication failure")
        return actual(source, target)

    with monkeypatch.context() as scope:
        scope.setattr(os, "replace", reject)
        if operation == "manual":
            with pytest.raises(SystemExit) as failure:
                manual_update(tmp_path, monkeypatch)
            assert failure.value.code == 1
        else:
            assert not _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True)
    assert products(tmp_path) == before
    assert_meaning(initial, family, changed=False)
    recovered = run(tmp_path, monkeypatch, operation, [path])
    assert_meaning(recovered, family, changed=True)
    assert normalized(recovered) == normalized(clean(tmp_path, tmp_path / ".recovered"))
