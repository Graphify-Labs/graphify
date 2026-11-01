"""INC128: old publication projections recover once without invalidating raw ASTs."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from graphify.accepted_link_frame import BUILD_PROJECTION_VERSION
import graphify.extract as extraction
import graphify.watch as watch
from tests.qt_publication_faults import publication_fault
from tests.source_relationship_projection_watch_helpers import (
    VERSION_KEY, caches, cold, legacy, prior_cache_retained, products, project,
    run, spy_extract, state,
)
from tests.test_cpp_allocated_member_updates import full_fields


@pytest.mark.parametrize("old", [0, True, 1.0, "1", None, [], {}, 1, 2.0, "2", 2, 3.0, "3", 3, 4.0, "4"],
                         ids=["old", "bool", "float", "text", "null", "list", "object",
                              "prior-int-one", "current-equal-float", "current-equal-text",
                              "prior-int-two", "v3-equal-float", "v3-equal-text",
                              "prior-int-three", "v4-equal-float", "v4-equal-text"])
def test_req_qml011_ac04_noncurrent_strict_projection_refreshes_once(tmp_path, monkeypatch, old):
    """Equal-looking scalars cannot let unchanged inputs skip a required projection."""
    root = project(tmp_path / "case", monkeypatch)
    run(root, monkeypatch)
    legacy(root, old)
    calls = spy_extract(monkeypatch)
    before_cache = caches(root)
    run(root, monkeypatch)
    assert len(calls) == 1 and set(calls[0]) == {"first.py", "second.py", "untouched.py"}
    assert type(state(root)[VERSION_KEY]) is int
    assert state(root)[VERSION_KEY] == BUILD_PROJECTION_VERSION
    prior_cache_retained(root, before_cache)
    accepted = products(root), caches(root)
    calls.clear()
    run(root, monkeypatch)
    assert not calls and (products(root), caches(root)) == accepted


@pytest.mark.parametrize("raw", [True, False], ids=["raw", "clustered"])
def test_req_qml011_ac04_missing_version_republishes_even_equal_topology(tmp_path, monkeypatch, raw):
    """A score excluded by topology comparison still needs real product replacement."""
    root = project(tmp_path / "case", monkeypatch)
    run(root, monkeypatch, raw=raw)
    legacy(root, missing=True, obsolete_score=True)
    graph_path = root / "graphify-out/graph.json"
    obsolete = graph_path.read_bytes()
    calls = spy_extract(monkeypatch)
    run(root, monkeypatch, raw=raw)
    assert calls and graph_path.read_bytes() != obsolete
    assert b"0.1234" not in graph_path.read_bytes()
    assert state(root)[VERSION_KEY] == BUILD_PROJECTION_VERSION
    assert full_fields(run(root, monkeypatch, raw=raw)) == cold(root, raw)
    accepted = products(root), caches(root)
    calls.clear()
    run(root, monkeypatch, raw=raw)
    assert not calls and (products(root), caches(root)) == accepted


def test_req_qml011_ac04_current_projection_and_raw_cache_keep_existing_policy(tmp_path, monkeypatch):
    """Reprojection consumes actual warm fragments; a current stamp keeps the fast gate."""
    root = project(tmp_path / "case", monkeypatch)
    run(root, monkeypatch)
    legacy(root, missing=True)
    before = caches(root)
    calls = spy_extract(monkeypatch)

    def unexpected(*args, **kwargs):
        pytest.fail("Projection-only recovery reparsed an already valid raw fragment")

    with monkeypatch.context() as patch:
        patch.setattr(extraction, "_safe_extract", unexpected)
        run(root, monkeypatch)
    assert len(calls) == 1 and set(calls[0]) == {"first.py", "second.py", "untouched.py"}
    assert caches(root) == before
    assert state(root)[VERSION_KEY] == BUILD_PROJECTION_VERSION
    accepted = products(root), caches(root)
    calls = spy_extract(monkeypatch)
    run(root, monkeypatch)
    assert not calls and (products(root), caches(root)) == accepted


def test_req_qml011_ac04_current_strict_version_keeps_existing_skip(tmp_path, monkeypatch):
    """An already accepted current version alone cannot invalidate unchanged source."""
    root = project(tmp_path / "case", monkeypatch)
    run(root, monkeypatch)
    legacy(root, BUILD_PROJECTION_VERSION)
    accepted = products(root), caches(root)
    calls = spy_extract(monkeypatch)
    run(root, monkeypatch)
    assert not calls and (products(root), caches(root)) == accepted


@pytest.mark.parametrize("damage", ["missing", "malformed", "list-root", "read-error"],
                         ids=["missing", "malformed", "list-root", "read-error"])
def test_req_qml011_ac04_unavailable_state_promotes_partial_event(tmp_path, monkeypatch, damage):
    """Missing/corrupt/unreadable publication evidence cannot retain a partial projection."""
    root = project(tmp_path / "case", monkeypatch)
    run(root, monkeypatch)
    stamp = root / "graphify-out" / watch._BUILD_STATE_NAME
    if damage == "missing":
        stamp.unlink()
    elif damage in {"malformed", "list-root"}:
        stamp.write_text("{" if damage == "malformed" else "[]", encoding="utf-8")
    else:
        read = Path.read_text

        def denied(path, *args, **kwargs):
            if path == stamp:
                raise PermissionError("Test-owned prior-state read denial")
            return read(path, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", denied)
    calls = spy_extract(monkeypatch)
    run(root, monkeypatch, changes=[root / "first.py"])
    assert len(calls) == 1 and set(calls[0]) == {"first.py", "second.py", "untouched.py"}
    if damage == "read-error":
        monkeypatch.setattr(Path, "read_text", read)
    assert state(root)[VERSION_KEY] == BUILD_PROJECTION_VERSION


@pytest.mark.parametrize("profile", ["python", "csharp", "qt"], ids=["python", "csharp", "qt"])
@pytest.mark.parametrize("change", ["edit", "delete"], ids=["edit", "delete"])
def test_req_qml011_ac04_partial_event_promotes_full_admitted_corpus(tmp_path, monkeypatch, profile, change):
    """An unchanged source must enter recovery, preserving mixed/typed facts and cold parity."""
    root = project(tmp_path / "case", monkeypatch, profile)
    run(root, monkeypatch)
    legacy(root)
    target = root / ("keep.py" if profile == "qt" else "second.py")
    if change == "edit":
        target.write_bytes(target.read_bytes() + b"\ndef added(): return 3\n")
    else:
        target.unlink()
    calls = spy_extract(monkeypatch)
    graph = run(root, monkeypatch, changes=[target])
    admitted = {path.name for path in root.iterdir() if path.is_file()}
    assert len(calls) == 1 and set(calls[0]) == admitted
    assert state(root)["full_clean"] is True
    assert state(root)[VERSION_KEY] == BUILD_PROJECTION_VERSION
    assert full_fields(graph) == cold(root, True)
    if profile == "csharp":
        assert any(data.get("metadata", {}).get("csharp_local_function") for _, data in graph.nodes(data=True))
    if profile == "qt":
        assert any(data.get("metadata", {}).get("qml") for _, data in graph.nodes(data=True))
    accepted = products(root), caches(root)
    calls.clear()
    run(root, monkeypatch)
    assert not calls and (products(root), caches(root)) == accepted
    # An explicit event retains the existing incremental-mode stamp policy. It
    # cannot change graph/source facts or the successful projection version.
    previous_state = state(root)
    repeated = run(root, monkeypatch, changes=[target])
    assert full_fields(repeated) == full_fields(graph)
    after = products(root)
    assert {k: v for k, v in after.items() if k != watch._BUILD_STATE_NAME} == {
        k: v for k, v in accepted[0].items() if k != watch._BUILD_STATE_NAME}
    previous_state["full_clean"] = False
    assert state(root) == previous_state


@pytest.mark.parametrize("raw", [True, False], ids=["raw", "clustered"])
@pytest.mark.parametrize("operation", ["manual", "watch"], ids=["manual", "watch"])
def test_req_qml012_ac02_projection_failed_publication_retains_then_recovers(
        tmp_path, monkeypatch, capsys, raw, operation):
    """Actual replacement EIO cannot stamp success; repair republishes before a stable no-op."""
    root = project(tmp_path / "case", monkeypatch)
    run(root, monkeypatch, raw=raw, operation=operation)
    legacy(root, obsolete_score=True)
    before, before_cache = products(root), caches(root)
    with publication_fault(root / "graphify-out/graph.json", "replace", monkeypatch) as fault:
        for _ in range(2):
            if operation == "manual":
                with pytest.raises(SystemExit) as error:
                    run(root, monkeypatch, raw=raw, operation=operation)
                assert error.value.code == 1
            else:
                assert not watch._rebuild_code(root, no_cluster=raw)
            assert products(root) == before
            prior_cache_retained(root, before_cache)
        assert fault.hits >= 2
    assert "GRAPH_PUBLICATION_FAILED" in capsys.readouterr().out
    assert state(root)[VERSION_KEY] == 0
    graph = run(root, monkeypatch, raw=raw, operation=operation)
    assert state(root)[VERSION_KEY] == BUILD_PROJECTION_VERSION
    assert full_fields(graph) == cold(root, raw)
    accepted = products(root), caches(root)
    run(root, monkeypatch, raw=raw, operation=operation)
    assert (products(root), caches(root)) == accepted


def test_req_qml012_ac02_projection_contention_keeps_state_and_pending_request(tmp_path, monkeypatch):
    """A real native contender cannot stamp the new projection before its owning publication."""
    root = project(tmp_path / "case", monkeypatch)
    run(root, monkeypatch)
    legacy(root)
    accepted = products(root), caches(root)
    calls = spy_extract(monkeypatch)
    output = root / "graphify-out"
    with watch._rebuild_lock(output, blocking=False) as held:
        assert held
        assert not watch._rebuild_code(root, no_cluster=True)
        assert not calls and (products(root), caches(root)) == accepted
        assert (output / ".pending_full").exists()
    run(root, monkeypatch)
    assert state(root)[VERSION_KEY] == BUILD_PROJECTION_VERSION


def test_req_qml012_ac02_projection_cannot_adopt_invalid_prior_source_transport(tmp_path, monkeypatch):
    """A version mismatch never bypasses the existing typed-source integrity guard."""
    root = project(tmp_path / "case", monkeypatch)
    run(root, monkeypatch)
    legacy(root)
    path = root / "graphify-out/graph.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["graph"] = {"graphify_source_relationships": {"contract_version": True}}
    path.write_text(json.dumps(data), encoding="utf-8")
    accepted = products(root), caches(root)
    calls = spy_extract(monkeypatch)
    assert not watch._rebuild_code(root, no_cluster=True)
    assert not calls and (products(root), caches(root)) == accepted
    assert state(root)[VERSION_KEY] == 0
