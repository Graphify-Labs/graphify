"""REQ-QML-020: unchanged native products refresh after alias policy upgrades."""
from __future__ import annotations

import pytest

import graphify.extract as extraction
import graphify.qt_analysis_state as state
import graphify.qt_incremental as policy
from graphify.watch import _rebuild_code
from tests.test_qt_final_incremental_parity import clean, normalized, project, run
from tests.test_qt_product_publication import no_scratch, snapshot


@pytest.mark.parametrize("operation", ["manual", "watch"])
@pytest.mark.parametrize("corpus", ["mixed", "cpp_only"])
def test_req_qml020_ac03_policy18_no_change_upgrade_retains_repairs_and_repeats(
        tmp_path, monkeypatch, capsys, operation, corpus):
    """A prior valid cohort refreshes without edits; failed stamp publication retains it."""
    project(tmp_path)
    if corpus == "cpp_only":
        # An ordinary native-only corpus also owns a Qt analysis stamp. Remove
        # QML/build/resource inputs before admission and use no Qt annotations.
        for name in ("Main.qml", "CMakeLists.txt", "resources.qrc", "backend.h"):
            (tmp_path / name).unlink()
        (tmp_path / "loader.cpp").write_bytes(b"int helper(){return 7;} int caller(){return helper();}\n")
    required_inputs = ({"loader.cpp"} if corpus == "cpp_only" else
                       {"Main.qml", "backend.h", "loader.cpp", "CMakeLists.txt", "resources.qrc"})
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    # Produce the prior stamp through the real owner rather than constructing a
    # counterfeit manifest. The source bytes and accepted graph stay unchanged.
    with monkeypatch.context() as prior:
        prior.setattr(policy, "QT_POLICY_VERSION", 18)
        initial = run(tmp_path, prior, operation)
    output = tmp_path / "graphify-out"
    before = snapshot(output)
    prior_fingerprint = state.read_qt_fingerprint(output)
    source_bytes = {path.name: path.read_bytes() for path in tmp_path.iterdir() if path.is_file()}
    observed, real_extract = [], extraction.extract

    def record_inputs(paths, *args, **kwargs):
        paths = list(paths)
        observed.append({path.name for path in paths})
        return real_extract(paths, *args, **kwargs)

    monkeypatch.setattr(extraction, "extract", record_inputs)
    committed, real_commit = [], state.commit_qt_analysis

    def stage_then_fail(*args, **kwargs):
        # Candidate stamp serialization really completes. Failure before cohort
        # replacement cannot authorize any graph/manifest/root/stamp advancement.
        real_commit(*args, **kwargs)
        committed.append(True)
        raise OSError("public policy upgrade publication failure")

    with monkeypatch.context() as failed:
        failed.setattr(state, "commit_qt_analysis", stage_then_fail)
        if operation == "manual":
            with pytest.raises(SystemExit) as rejected:
                run(tmp_path, failed, operation, [])
            assert rejected.value.code == 1
        else:
            assert not _rebuild_code(tmp_path, changed_paths=[], no_cluster=True)
    assert committed == [True]
    assert snapshot(output) == before
    assert state.read_qt_fingerprint(output) == prior_fingerprint
    assert "GRAPH_PUBLICATION_FAILED" in capsys.readouterr().out
    assert observed and required_inputs <= set.union(*observed)
    no_scratch(output)

    observed.clear()
    repaired = run(tmp_path, monkeypatch, operation, [])
    assert normalized(repaired) == normalized(initial)
    assert state.read_qt_fingerprint(output) != prior_fingerprint
    assert observed and required_inputs <= set.union(*observed)
    assert normalized(repaired) == normalized(clean(tmp_path, tmp_path / ".clean-cache"))
    accepted = snapshot(output)
    observed.clear()
    repeated = run(tmp_path, monkeypatch, operation, [])
    assert normalized(repeated) == normalized(repaired)
    assert snapshot(output) == accepted
    if operation == "watch":
        assert not any(observed)
    assert source_bytes == {path.name: path.read_bytes() for path in tmp_path.iterdir() if path.is_file()}
    no_scratch(output)
