"""INC-QML-78: immutable include context survives actual worker retry paths."""
from __future__ import annotations

import concurrent.futures

import pytest

import graphify.extract as extraction
from graphify.extractors.qt_cpp_test_context import build_qt_test_contexts
from tests.qt_analysis_helpers import sites
from tests.qml_test_helpers import canonical
from tests.test_qt_test_include_context import write_project


def test_req_qml022_ac03_failed_future_retry_preserves_context_and_native_cache_policy(tmp_path, monkeypatch):
    """Only the pool failure is fake; the production retry reparses inherited QtTest syntax."""
    paths = write_project(tmp_path)
    consumer = tmp_path / "checks.hpp"

    class Future:
        def __init__(self, value=None, *, failed=False):
            self.value, self.failed = value, failed

        def result(self):
            if self.failed:
                raise RuntimeError("isolated worker acquisition failure")
            return self.value

    class Pool:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def submit(self, function, item):
            if item[1] == str(consumer):
                return Future(failed=True)
            return Future(function(item))

    monkeypatch.setattr(concurrent.futures, "ProcessPoolExecutor", Pool)
    monkeypatch.setattr(concurrent.futures, "as_completed", lambda futures: iter(futures))
    monkeypatch.setattr(extraction, "_PARALLEL_THRESHOLD", 1)
    monkeypatch.setattr(extraction, "_spawn_cannot_reimport_main", lambda: False)
    retried, actual = [], extraction._extract_sequential

    def retry(work, *args, **kwargs):
        retried.append(([path for _, path in work], kwargs))
        return actual(work, *args, **kwargs)

    monkeypatch.setattr(extraction, "_extract_sequential", retry)
    result = extraction.extract(paths, root=tmp_path, cache_root=tmp_path, parallel=True, max_workers=2)
    assert not result["failed_sources"] and not result["qml_failures"]
    assert len(sites(result, "test_data")) == len(sites(result, "test_assertion")) == 1
    assert len(retried) == 1 and retried[0][0] == [consumer]
    assert retried[0][1]["native_cache_bypass"] is True
    assert retried[0][1]["qt_test_contexts"].for_path(consumer) is not None
    assert not list((tmp_path / "graphify-out/cache/ast").glob("*.json"))


@pytest.mark.parametrize("arity", [0, 1, 2])
def test_req_qml022_ac03_worker_incomplete_tuple_has_bounded_arity_failure(arity):
    """Incomplete internal work items reject before any path, cache or source operation."""
    with pytest.raises(ValueError, match="^worker arguments require at least three items$"):
        extraction._extract_single_file(("private-value",) * arity)


@pytest.mark.parametrize("arity", [3, 4, 5, 6])
def test_req_qml022_ac03_worker_tuple_compatibility_and_context(tmp_path, arity):
    """Legacy worker tuples remain accepted; the new payload alone supplies transitive context."""
    paths = write_project(tmp_path)
    path = tmp_path / "checks.hpp"
    snapshot = build_qt_test_contexts(paths, root=tmp_path)
    args = (0, str(path), str(tmp_path), str(tmp_path), True, snapshot.for_path(path))
    index, result = extraction._extract_single_file(args[:arity])
    assert index == 0 and result["nodes"]
    assert bool(result.get("parse_errors")) is (arity != 6)


def test_req_qml022_ac03_real_spawn_workers_match_sequential_include_context(tmp_path, monkeypatch):
    """Typed immutable witnesses must actually cross the worker serialization boundary."""
    paths = write_project(tmp_path)
    for index in range(18):
        path = tmp_path / f"extra{index}.cpp"
        path.write_text(f"int value{index}(){{return {index};}}")
        paths.append(path)
    ran, actual = [], extraction._extract_parallel

    def pool(*args, **kwargs):
        result = actual(*args, **kwargs)
        ran.append(result)
        return result

    monkeypatch.setattr(extraction, "_extract_parallel", pool)
    parallel = extraction.extract(paths, root=tmp_path, cache_root=tmp_path / "pool", parallel=True, max_workers=2)
    sequential = extraction.extract(paths, root=tmp_path, cache_root=tmp_path / "serial", parallel=False)
    assert ran == [True]
    assert not parallel["failed_sources"] and not parallel["qml_failures"]
    assert len(sites(parallel, "test_data")) == 1
    assert canonical(parallel) == canonical(sequential)
