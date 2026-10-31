"""INC-QML-107: old raw proof, publication failure and real refresh preserve calls."""
from __future__ import annotations

from copy import deepcopy
import importlib
import errno

import pytest

from graphify.build import build_from_json
from graphify.cache import _AST_CACHE_SCHEMA, cache_dir, load_cached, save_cached
from graphify.export import to_json
from graphify.extract import extract, extract_cpp
from graphify.extractors.cpp_member_identity import member_fact
from graphify.source_relationships import logical_endpoints
from tests.cpp_same_unit_helpers import members, project
from tests.qt_publication_faults import publication_fault
from tests.test_cpp_allocated_member_updates import cold_reference, full_fields
from tests.test_cpp_same_unit_updates import rejected
from tests.test_cpp_direct_member_calls import helper_edge
from tests.test_qt_final_incremental_parity import run, unrelated
from tests.test_qt_semantic_correction_updates import products


def test_req_qml022_ac06_pre107_cached_raw_body_proof_rebuilds_identical_facade(tmp_path, monkeypatch):
    """Current-epoch raw proof recovers an omitted intermediate direct edge.

    The historical AST34 run established this shape for INC107 alone. Later
    lexical witnesses require epoch35, whose predecessor retirement is tested
    separately. Keep all current producer proof, omit only the observed direct
    edge, and exercise a real cache hit with per-file extraction forbidden.
    The complete facade must still equal cold extraction in every attribute.
    """
    path = tmp_path / "panel.cpp"
    path.write_bytes(b"void helper(){} class Panel{public:void run();}; void Panel::run(){helper();}\n")
    direct = extract_cpp(path)
    body, = [node for node, fact in members(direct) if fact["role"] == "definition"]
    prior = deepcopy(direct)
    prior["edges"] = [edge for edge in prior["edges"] if edge not in helper_edge(direct, body)]
    assert not helper_edge(prior, body) and any(call.get("cpp_free_call") for call in prior["raw_calls"])
    save_cached(path, prior, tmp_path, cache_root=tmp_path)
    assert f"-s{_AST_CACHE_SCHEMA}-" in cache_dir(tmp_path).name
    loaded = load_cached(path, tmp_path, cache_root=tmp_path)
    assert loaded is not None and not helper_edge(loaded, body)
    files = {p: p.read_bytes() for p in cache_dir(tmp_path).glob("*.json")}
    module = importlib.import_module("graphify.extract")

    def unexpected_extract(*args, **kwargs):
        raise AssertionError("The actual pre107-compatible entry must be served from cache")

    with monkeypatch.context() as patch:
        patch.setattr(module, "_safe_extract_with_xaml_root", unexpected_extract)
        warm = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    cold = extract([path], root=tmp_path, cache_root=tmp_path / "fresh-cache", parallel=False)
    assert warm == cold and not warm["failed_sources"]
    canonical, = [node for node, fact in members(warm) if fact["role"] == "declaration"]
    assert len(helper_edge(warm, canonical)) == 1
    assert all(p.read_bytes() == content for p, content in files.items())


@pytest.mark.parametrize("force", [False, True])
def test_req_qml022_ac06_direct_source_call_export_replacement_retains_then_recovers(tmp_path, monkeypatch, force):
    """A real direct-graph replacement failure preserves accepted bytes and then retries."""
    path = project(tmp_path)
    first = extract_cpp(path)
    output = tmp_path / "direct.json"
    assert to_json(build_from_json(first, root=tmp_path), {}, str(output), force=True)
    accepted = output.read_bytes()
    path.write_bytes(path.read_bytes().replace(b"helper", b"replacement"))
    current = extract_cpp(path)
    graph = build_from_json(current, root=tmp_path)
    with publication_fault(output, "replace", monkeypatch) as fault:
        for _ in range(2):
            with pytest.raises(OSError) as rejected_write:
                to_json(graph, {}, str(output), force=force)
            assert rejected_write.value.errno == errno.EIO
            assert output.read_bytes() == accepted
        assert fault.hits >= 2
    assert to_json(graph, {}, str(output), force=force)
    replacement = output.read_bytes()
    assert replacement != accepted
    assert to_json(graph, {}, str(output), force=force) and output.read_bytes() == replacement
    assert not list(tmp_path.glob(".gfy-*.tmp"))


def source_calls(graph, name):
    target, = [identity for identity, node in graph.nodes(data=True)
               if node.get("label") == name + "()" and node.get("source_file") == "panel.cpp"]
    found = [(a, b) for left, right, data in graph.edges(data=True)
             if data.get("relation") == "calls"
             for a, b in [logical_endpoints(graph, left, right, data)] if b == target]
    assert len(found) == 1 and member_fact(graph.nodes[found[0][0]])["role"] == "declaration"
    return target


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml022_ac06_direct_scope_refresh_write_failure_and_callee_retirement(tmp_path, monkeypatch, operation):
    """Actual full/incremental owners retain prior calls on EIO, then retire the old callee."""
    path = project(tmp_path)
    monkeypatch.chdir(tmp_path)
    first = run(tmp_path, monkeypatch, operation)
    old = source_calls(first, "helper")
    accepted = products(tmp_path)
    path.write_bytes(path.read_bytes().replace(b"helper", b"replacement"))
    raw, modified = path.read_bytes(), path.stat().st_mtime_ns
    with publication_fault(tmp_path / "graphify-out/graph.json", "replace", monkeypatch) as fault:
        for _ in range(2):
            rejected(tmp_path, monkeypatch, operation, path)
            assert products(tmp_path) == accepted
        assert fault.hits >= 2
    refreshed = run(tmp_path, monkeypatch, operation, [path])
    assert old not in refreshed and source_calls(refreshed, "replacement") != old
    assert (path.read_bytes(), path.stat().st_mtime_ns) == (raw, modified)
    assert unrelated(first) == unrelated(refreshed)
    assert full_fields(refreshed) == full_fields(cold_reference(tmp_path, monkeypatch, operation))
    qml = tmp_path / "Main.qml"
    qml.write_bytes(qml.read_bytes() + b"// QML-only accepted snapshot refresh\n")
    qml_only = run(tmp_path, monkeypatch, operation, [qml])
    assert source_calls(qml_only, "replacement") and full_fields(qml_only) == full_fields(cold_reference(tmp_path, monkeypatch, operation))
    stable = products(tmp_path)
    run(tmp_path, monkeypatch, operation, [path, qml])
    assert products(tmp_path) == stable
