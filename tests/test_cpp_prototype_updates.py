"""INC-QML-70: source-only prototype identities follow actual durable updates."""
from __future__ import annotations

import errno
import os
from pathlib import Path

import pytest

from graphify.watch import _rebuild_code
from tests.test_qt_final_incremental_parity import clean, manual_update, normalized, published, run, unrelated
from tests.test_qt_semantic_correction_updates import products


SOURCE = "struct Value; int work(Value &value); int work(Value &&value);\n"


def fixture(root):
    path = root / "api.h"
    path.write_text(SOURCE, encoding="utf-8")
    (root / "keep.py").write_text("def helper(): return 7\n\ndef retained(): return helper()\n", encoding="utf-8")
    return path


def declarations(graph):
    return {identity: data for identity, data in graph.nodes(data=True) if data.get("metadata", {}).get("cpp_prototype")}


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml022_ac06_prototype_edits_retire_old_overloads_and_match_full_scan(tmp_path, monkeypatch, operation):
    """A real changed header removes renamed/removed declarations through the persisted graph."""
    path = fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(tmp_path, monkeypatch, operation)
    before = declarations(initial)
    assert len(before) == 2
    path.write_text("struct Value; int renamed(Value &value);\n", encoding="utf-8")
    updated = run(tmp_path, monkeypatch, operation, [path])
    assert len(declarations(updated)) == 1 and set(before).isdisjoint(updated)
    assert normalized(updated) == normalized(clean(tmp_path, tmp_path / ".cold"))
    assert normalized(updated) == normalized(clean(tmp_path, tmp_path / ".warm"))
    assert unrelated(initial) == unrelated(updated)
    durable = products(tmp_path)
    assert normalized(run(tmp_path, monkeypatch, operation, [])) == normalized(updated)
    assert products(tmp_path) == durable


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml022_ac06_prototype_failed_publication_retains_cohort_then_recovers(tmp_path, monkeypatch, operation):
    """Reject the real OS graph replacement after staging; no manifest/state may advance."""
    path = fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(tmp_path, monkeypatch, operation)
    assert len(declarations(initial)) == 2
    before = products(tmp_path)
    path.write_text("struct Value; int renamed(Value &value);\n", encoding="utf-8")
    replace = os.replace

    def reject(source, target):
        if Path(target).resolve() == (tmp_path / "graphify-out/graph.json").resolve():
            raise OSError(errno.EIO, "simulated prototype publication failure")
        return replace(source, target)

    with monkeypatch.context() as guarded:
        guarded.setattr(os, "replace", reject)
        if operation == "manual":
            with pytest.raises(SystemExit) as failure:
                manual_update(tmp_path, monkeypatch)
            assert failure.value.code == 1
        else:
            assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True) is False
    assert products(tmp_path) == before
    assert declarations(published(tmp_path)) == declarations(initial)
    recovered = run(tmp_path, monkeypatch, operation, [path])
    assert len(declarations(recovered)) == 1
    assert all(data["label"] == "renamed()" for data in declarations(recovered).values())
    assert normalized(recovered) == normalized(clean(tmp_path, tmp_path / ".recovered"))
