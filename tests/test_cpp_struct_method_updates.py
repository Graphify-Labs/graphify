"""INC-QML-113: real dispatch changes retire stale facts without losing products."""
from __future__ import annotations

from contextlib import contextmanager
import os

import pytest

import graphify.watch as watch

from graphify import cache
from graphify.extract import extract, extract_c
from tests.qt_publication_faults import publication_fault
from tests.test_cpp_allocated_member_updates import cold_reference, full_fields
from tests.test_cpp_same_unit_updates import rejected
from tests.test_qt_final_incremental_parity import project, run, unrelated
from tests.test_qt_semantic_correction_updates import products


def fixture(root):
    """The added ordinary header is admitted to the real mixed-source project."""
    project(root)
    path = root / "panel.h"
    path.write_bytes(b"struct Panel { void run(); };\n")
    metadata = root / "CMakeLists.txt"
    metadata.write_bytes(metadata.read_bytes().replace(b"backend.h loader.cpp", b"backend.h loader.cpp panel.h"))
    return path



@contextmanager
def publication_after_mutex(root, kind, monkeypatch):
    """Arm real native writer denial only after actual lock acquisition and queue drain."""
    destination = root / "graphify-out/graph.json"
    modes = destination.stat().st_mode, destination.parent.stat().st_mode
    factory, mutex, observations = watch.ProductPublication, watch._rebuild_lock, []

    @contextmanager
    def failing_publication(*args, **kwargs):
        assert args[0] == destination.parent
        assert (destination.stat().st_mode, destination.parent.stat().st_mode) == modes
        lock = destination.parent / ".rebuild.lock"
        holder = lock.read_bytes()
        assert holder == f"{os.getpid()}{os.linesep}".encode()
        with mutex(destination.parent, blocking=False) as contender:
            assert contender is False
        assert lock.read_bytes() == holder
        # Transaction construction owns preparation too. Denial starts before
        # invoking the real factory, and ends before late queue/lock cleanup.
        with publication_fault(destination, kind, monkeypatch) as observation:
            observations.append(observation)
            with factory(*args, **kwargs) as publication:
                yield publication
        assert (destination.stat().st_mode, destination.parent.stat().st_mode) == modes

    with monkeypatch.context() as patch:
        patch.setattr(watch, "ProductPublication", failing_publication)
        yield observations
    assert watch.ProductPublication is factory


def members(graph):
    return {identity: data for identity, data in graph.nodes(data=True)
            if data.get("source_file") == "panel.h" and data.get("label") in {"Panel", ".run()", ".advance()"}}


def test_req_qml022_ac06_pre_struct_callable_schema_reparses_actual_c_payload(tmp_path, monkeypatch):
    """An actual successful C-producer35 payload cannot replay the lost class."""
    path = tmp_path / "panel.h"
    raw = b"struct Panel { void run(); };\n"
    path.write_bytes(raw)
    prior = extract_c(path)
    assert not prior.get("error") and not any(node["label"] == ".run()" for node in prior["nodes"])
    with monkeypatch.context() as old:
        old.setattr(cache, "_AST_CACHE_SCHEMA", 35)
        cache.save_cached(path, prior, root=tmp_path)
        assert cache.load_cached(path, root=tmp_path) == prior
    assert cache._AST_CACHE_SCHEMA == 40 and cache.load_cached(path, root=tmp_path) is None
    cold = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    warm = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert cold == warm and not cold["failed_sources"]
    assert any(node["label"] == ".run()" and node.get("_callable") for node in cold["nodes"])
    assert path.read_bytes() == raw


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml022_ac06_struct_callable_edit_changes_dispatch_then_recovers(tmp_path, monkeypatch, operation):
    """Replacing the sole C++ cue removes old facts; repair restores exact cold output."""
    path = fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    initial = run(tmp_path, monkeypatch, operation)
    identities = set(members(initial))
    assert len(identities) == 2
    path.write_bytes(b"struct Panel { void (*run)(int); };\n")
    removed = run(tmp_path, monkeypatch, operation, [path])
    assert identities.isdisjoint(removed) and not members(removed)
    assert full_fields(removed) == full_fields(cold_reference(tmp_path, monkeypatch, operation))
    assert unrelated(initial) == unrelated(removed)
    path.write_bytes(b"struct Panel { void run(); };\n")
    restored = run(tmp_path, monkeypatch, operation, [path])
    assert set(members(restored)) == identities
    assert full_fields(restored) == full_fields(cold_reference(tmp_path, monkeypatch, operation))
    accepted = products(tmp_path)
    run(tmp_path, monkeypatch, operation, [path])
    assert products(tmp_path) == accepted


@pytest.mark.parametrize("operation", ["manual", "watch"])
@pytest.mark.parametrize("fault_kind", ["readonly", "replace"])
def test_req_qml022_ac06_struct_callable_publication_failure_retains_then_recovers(
        tmp_path, monkeypatch, capsys, operation, fault_kind):
    """Actual platform denial and target EIO retain all products through two attempts."""
    path = fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    initial = run(tmp_path, monkeypatch, operation)
    old = set(members(initial))
    assert len(old) == 2
    accepted = products(tmp_path)
    path.write_bytes(b"struct Panel { void advance(); };\n")
    input_before = path.read_bytes(), path.stat().st_mtime_ns
    with publication_after_mutex(tmp_path, fault_kind, monkeypatch) as observations:
        for _ in range(2):
            if operation == "manual":
                rejected(tmp_path, monkeypatch, operation, path)
            else:
                assert not watch._rebuild_code(tmp_path, changed_paths=[path], no_cluster=True)
            assert products(tmp_path) == accepted
            assert (path.read_bytes(), path.stat().st_mtime_ns) == input_before
            assert not (tmp_path / "graphify-out/.rebuild.lock").exists()
            assert not list((tmp_path / "graphify-out").glob(".gfy-publish-*"))
        assert len(observations) == 2 and all(observation.qualified for observation in observations)
        assert fault_kind == "readonly" or sum(observation.hits for observation in observations) >= 2
    captured = capsys.readouterr()
    assert "GRAPH_PUBLICATION_FAILED" in captured.out + captured.err
    assert "REBUILD_SETUP_FAILED" not in captured.out + captured.err
    restored = run(tmp_path, monkeypatch, operation, [path])
    new = set(members(restored))
    assert len(new) == 2 and len(old - new) == len(new - old) == 1
    assert unrelated(initial) == unrelated(restored)
    assert full_fields(restored) == full_fields(cold_reference(tmp_path, monkeypatch, operation))
    stable = products(tmp_path)
    run(tmp_path, monkeypatch, operation, [path])
    assert products(tmp_path) == stable and not list((tmp_path / "graphify-out").glob(".gfy-*.tmp"))
