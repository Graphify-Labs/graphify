"""INC-QML-93: source-owned build witnesses cross the real worker payload."""
from __future__ import annotations

import pickle

import graphify.extract as extraction
from tests.qml_test_helpers import canonical
from tests.qt_analysis_helpers import sites
from tests.test_qt_build_include_context import SOURCE, project, snapshot


def test_req_qml022_ac06_actual_worker_payload_preserves_target_context(tmp_path):
    """The accepted immutable per-file payload, rather than global metadata, admits generic typed syntax."""
    paths = project(tmp_path, source=SOURCE.replace('#include "api.h"\n#include <QtTest>', '#include "api.h"'),
                    header="#include <QtTest>\nstruct Api{};\n")
    contexts = pickle.loads(pickle.dumps(snapshot(tmp_path, paths)))
    args = (0, str(paths[0]), str(tmp_path), str(tmp_path), True, contexts.for_path(paths[0]))
    index, accepted = extraction._extract_single_file(args)
    assert index == 0 and accepted["nodes"] and not accepted.get("parse_errors")
    _, baseline = extraction._extract_single_file(args[:-1])
    assert baseline.get("parse_errors")


def test_req_qml022_ac06_real_spawn_workers_keep_build_proof_and_equal_sequential(tmp_path, monkeypatch):
    """A real pool serializes new nested dataclasses and publishes identical canonical source-only facts."""
    paths = list(project(tmp_path))
    for index in range(18):
        path = tmp_path / f"extra{index}.cpp"
        path.write_text(f"int value{index}(){{return {index};}}", encoding="utf-8")
        paths.append(path)
    ran, actual = [], extraction._extract_parallel

    def pool(*args, **kwargs):
        result = actual(*args, **kwargs)
        ran.append(result)
        return result

    monkeypatch.setattr(extraction, "_extract_parallel", pool)
    parallel = extraction.extract(paths, root=tmp_path, cache_root=tmp_path / "pool", parallel=True, max_workers=2)
    sequential = extraction.extract(paths, root=tmp_path, cache_root=tmp_path / "serial", parallel=False)
    assert ran == [True] and not parallel["failed_sources"] and not parallel.get("qml_failures")
    assert len(sites(parallel, "test_data")) == len(sites(parallel, "test_launcher")) == 1
    assert canonical(parallel) == canonical(sequential)
