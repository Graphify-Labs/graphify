"""INC-QML-108: callback shadowing survives cached and durable public workflows."""
from copy import deepcopy
import errno

import pytest

from graphify import cache
from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extract import extract, extract_cpp
from graphify.source_relationships import logical_endpoints
from tests.cpp_local_callback_helpers import callback_sites, caller, helper_edges, source
from tests.cpp_same_unit_helpers import project
from tests.qt_publication_faults import publication_fault
from tests.test_cpp_allocated_member_updates import cold_reference, full_fields
from tests.test_cpp_same_unit_updates import rejected
from tests.test_qt_final_incremental_parity import run, unrelated
from tests.test_qt_semantic_correction_updates import products


def global_helper_calls(graph):
    """Only the C++ free target counts, regardless of undirected storage order."""
    targets = {identity for identity, node in graph.nodes(data=True)
               if node.get("source_file") == "panel.cpp" and node.get("label") == "helper()"}
    return [(source, target) for left, right, data in graph.edges(data=True)
            if data.get("relation") == "calls"
            for source, target in [logical_endpoints(graph, left, right, data)] if target in targets]


def test_req_qml022_ac06_pre_callback_schema_cannot_replay_false_global_target(tmp_path, monkeypatch):
    """The successful predecessor34 payload lacks source binding proof and must miss."""
    path = tmp_path / "unit.cpp"
    path.write_bytes(source("void (*helper)()=nullptr;helper();").encode())
    prior = deepcopy(extract_cpp(path))
    actual_caller = caller(prior)["id"]
    site, = callback_sites(prior)
    assert site["cpp_free_call"]["shadowed"] is True and not helper_edges(prior)
    # The exact observed predecessor omission is a false raw shadow flag plus
    # its corresponding source-owned free-call edge, not an error-cache entry.
    site["cpp_free_call"]["shadowed"] = False
    target, = [node["id"] for node in prior["nodes"] if node["label"] == "helper()"
               and node.get("metadata", {}).get("cpp_function", {}).get("max_args") == 0]
    prior["edges"].append({"source": actual_caller, "target": target, "relation": "calls",
                           "context": "cpp_free_function", "confidence": "EXTRACTED", "weight": 1.0,
                           "source_file": str(path), "source_location": site["source_location"]})
    assert cache._AST_CACHE_SCHEMA > 34
    with monkeypatch.context() as old:
        old.setattr(cache, "_AST_CACHE_SCHEMA", 34)
        cache.save_cached(path, prior, tmp_path, cache_root=tmp_path)
        loaded = cache.load_cached(path, tmp_path, cache_root=tmp_path)
        assert loaded is not None and helper_edges(loaded)
    assert cache.load_cached(path, tmp_path, cache_root=tmp_path) is None
    state = path.read_bytes(), path.stat().st_mtime_ns
    cold = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    warm = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert cold == warm and not helper_edges(warm) and not warm["failed_sources"]
    assert (path.read_bytes(), path.stat().st_mtime_ns) == state


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml022_ac06_callback_edit_removes_stale_target_and_recovers_by_scope(tmp_path, monkeypatch, operation):
    """Real updates remove the false target, preserve other languages, then regain a global call."""
    path = project(tmp_path)
    monkeypatch.chdir(tmp_path)
    initial = run(tmp_path, monkeypatch, operation)
    assert len(global_helper_calls(initial)) == 1
    valid = path.read_bytes().replace(b"{ helper(); }", b"{ void (*helper)()=nullptr; helper(); }")
    assert valid != path.read_bytes()
    path.write_bytes(valid)
    blocked = run(tmp_path, monkeypatch, operation, [path])
    assert not global_helper_calls(blocked) and unrelated(initial) == unrelated(blocked)
    assert full_fields(blocked) == full_fields(cold_reference(tmp_path, monkeypatch, operation))
    # Independent QML/build metadata changes must not revive old cached calls.
    qml, metadata = tmp_path / "Main.qml", tmp_path / "CMakeLists.txt"
    qml.write_bytes(qml.read_bytes() + b"// caller cohort refresh\n")
    metadata.write_bytes(metadata.read_bytes() + b"# literal metadata refresh\n")
    refreshed = run(tmp_path, monkeypatch, operation, [qml, metadata])
    assert not global_helper_calls(refreshed)
    assert full_fields(refreshed) == full_fields(cold_reference(tmp_path, monkeypatch, operation))
    path.write_bytes(valid.replace(b"(*helper)", b"(*callback)"))
    restored = run(tmp_path, monkeypatch, operation, [path])
    assert len(global_helper_calls(restored)) == 1 and unrelated(initial) == unrelated(restored)
    assert full_fields(restored) == full_fields(cold_reference(tmp_path, monkeypatch, operation))
    stable = products(tmp_path)
    run(tmp_path, monkeypatch, operation, [path, qml, metadata])
    assert products(tmp_path) == stable


@pytest.mark.parametrize("operation", ["manual", "watch"])
@pytest.mark.parametrize("failure", ["syntax", "replace"])
def test_req_qml022_ac06_callback_public_rejection_retains_then_recovers(tmp_path, monkeypatch, capsys, operation, failure):
    """Actual parser rejection and graph-target EIO retain the accepted target until recovery."""
    path = project(tmp_path)
    monkeypatch.chdir(tmp_path)
    initial = run(tmp_path, monkeypatch, operation)
    assert len(global_helper_calls(initial)) == 1
    accepted = products(tmp_path)
    valid = path.read_bytes().replace(b"{ helper(); }", b"{ void (*helper)()=nullptr; helper(); }")
    path.write_bytes(valid[:-2] if failure == "syntax" else valid)
    if failure == "replace":
        with publication_fault(tmp_path / "graphify-out/graph.json", "replace", monkeypatch) as fault:
            for _ in range(2):
                rejected(tmp_path, monkeypatch, operation, path)
                assert products(tmp_path) == accepted
            assert fault.hits >= 2
    else:
        for _ in range(2):
            rejected(tmp_path, monkeypatch, operation, path)
            assert products(tmp_path) == accepted
    captured = capsys.readouterr()
    assert ("GRAPH_PUBLICATION_FAILED" if failure == "replace" else "QML_GRAPH_PRESERVED") in captured.out + captured.err
    if failure == "syntax":
        path.write_bytes(valid)
    recovered = run(tmp_path, monkeypatch, operation, [path])
    assert not global_helper_calls(recovered) and unrelated(initial) == unrelated(recovered)
    assert full_fields(recovered) == full_fields(cold_reference(tmp_path, monkeypatch, operation))
    stable = products(tmp_path)
    run(tmp_path, monkeypatch, operation, [path])
    assert products(tmp_path) == stable and not list((tmp_path / "graphify-out").glob(".gfy-*.tmp"))


@pytest.mark.parametrize("force", [False, True])
def test_req_qml022_ac06_callback_direct_export_failure_keeps_original_graph(tmp_path, monkeypatch, force):
    """Direct graph replacement really fails twice and then adopts the corrected no-target graph."""
    path = tmp_path / "unit.cpp"
    path.write_bytes(source("helper();").encode())
    output = tmp_path / "accepted.json"
    assert to_json(build_from_json(extract_cpp(path), root=tmp_path), {}, str(output), force=True)
    before = output.read_bytes()
    path.write_bytes(source("void (*helper)()=nullptr;helper();").encode())
    result = extract_cpp(path)
    assert not helper_edges(result)
    graph = build_from_json(result, root=tmp_path)
    with publication_fault(output, "replace", monkeypatch) as fault:
        for _ in range(2):
            with pytest.raises(OSError) as failure:
                to_json(graph, {}, str(output), force=force)
            assert failure.value.errno == errno.EIO and output.read_bytes() == before
        assert fault.hits >= 2
    assert to_json(graph, {}, str(output), force=force)
    accepted = output.read_bytes()
    assert accepted != before and to_json(graph, {}, str(output), force=force)
    assert output.read_bytes() == accepted and not list(tmp_path.glob(".gfy-*.tmp"))
