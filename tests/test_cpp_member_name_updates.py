"""INC-QML-111: literal member identities survive cached and durable workflows."""
import errno

import pytest

from graphify import cache
from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extract import extract_cpp
from graphify.extractors.cpp_member_names import CppMemberNames
from graphify.source_relationships import logical_endpoints
from tests.cpp_member_name_helpers import facade, owned, project, source
from tests.qt_publication_faults import publication_fault
from tests.test_cpp_allocated_member_updates import cold_reference, full_fields
from tests.test_cpp_same_unit_updates import rejected
from tests.test_qt_final_incremental_parity import run, unrelated
from tests.test_qt_semantic_correction_updates import products


def native_targets(graph):
    return {target for left, right, data in graph.edges(data=True) if data.get("context") == "qml_js_call"
            for _, target in [logical_endpoints(graph, left, right, data)]}


def field_nodes(graph):
    return {node["label"]: identity for identity, node in graph.nodes(data=True)
            if node.get("source_file") == "unit.cpp"
            and node.get("metadata", {}).get("cpp_declarator", {}).get("kind") == "field"}


def test_req_qml022_ac06_pre_literal_member_schema_misses_successful_omitted_facts(tmp_path, monkeypatch):
    """The real old allocator shape is a successful35 payload, not a cache error."""
    path = project(tmp_path, source().encode())
    # Reproduce the observed predecessor owner: ordinary producer code runs,
    # but the new source-name candidate boundary deliberately returns its input.
    with monkeypatch.context() as predecessor:
        predecessor.setattr(CppMemberNames, "candidate", lambda index, syntax, legacy, **kwargs: legacy)
        prior = extract_cpp(path)
    assert {node["label"] for node in owned(prior)} == {"Field", "Callback", ".Run()"}
    assert cache._AST_CACHE_SCHEMA > 35
    with monkeypatch.context() as old:
        old.setattr(cache, "_AST_CACHE_SCHEMA", 35)
        cache.save_cached(path, prior, tmp_path, cache_root=tmp_path)
        loaded = cache.load_cached(path, tmp_path, cache_root=tmp_path)
        assert loaded is not None and len(owned(loaded)) == 3
    assert cache.load_cached(path, tmp_path, cache_root=tmp_path) is None
    state = path.read_bytes(), path.stat().st_mtime_ns
    repaired = facade(tmp_path)
    assert len(owned(repaired)) == 6
    assert (path.read_bytes(), path.stat().st_mtime_ns) == state


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml022_ac06_member_case_rename_removal_and_context_refresh_retire_old_ids(tmp_path, monkeypatch, operation):
    """Source/QML/metadata edits retain exact spelling, stale retirement and full parity."""
    original = source(native=True, out_of_line=True).encode()
    path = project(tmp_path, original, native=True)
    monkeypatch.chdir(tmp_path)
    initial = run(tmp_path, monkeypatch, operation)
    targets = native_targets(initial)
    assert len(targets) == 2 and set(field_nodes(initial)) == {"Field", "field", "Callback", "callback"}
    old_fields = set(field_nodes(initial).values())
    path.write_bytes(original.replace(b"UpperType Field;", b"UpperType UpperField;"))
    renamed = run(tmp_path, monkeypatch, operation, [path])
    assert "Field" not in field_nodes(renamed) and "UpperField" in field_nodes(renamed)
    assert not old_fields.intersection(field_nodes(renamed).values()) - {
        field_nodes(initial)["Callback"], field_nodes(initial)["callback"]}
    assert native_targets(renamed) == targets and unrelated(initial) == unrelated(renamed)
    assert full_fields(renamed) == full_fields(cold_reference(tmp_path, monkeypatch, operation))
    # Both declaration and body are removed: this remains valid C++ source.
    removed = original.replace(b"Q_INVOKABLE void Run();\n", b"").replace(b"void Panel::Run(){upper();}\n", b"")
    path.write_bytes(removed)
    unavailable = run(tmp_path, monkeypatch, operation, [path])
    assert len(native_targets(unavailable)) == 1 and not targets.intersection(native_targets(unavailable))
    assert full_fields(unavailable) == full_fields(cold_reference(tmp_path, monkeypatch, operation))
    path.write_bytes(original)
    repaired = run(tmp_path, monkeypatch, operation, [path])
    assert native_targets(repaired) == targets
    qml = tmp_path / "Main.qml"
    qml_source = qml.read_bytes()
    qml.write_bytes(qml_source.replace(b"Run();", b"rUn();"))
    qml_only = run(tmp_path, monkeypatch, operation, [qml])
    assert len(native_targets(qml_only)) == 1 and native_targets(qml_only) < targets
    qml.write_bytes(qml_source)
    metadata = tmp_path / "CMakeLists.txt"
    module_source = metadata.read_bytes()
    metadata.write_bytes(module_source.replace(b"Public.MemberNames", b"Public.Retargeted"))
    metadata_only = run(tmp_path, monkeypatch, operation, [metadata, qml])
    assert not native_targets(metadata_only) and len(field_nodes(metadata_only)) == 4
    metadata.write_bytes(module_source)
    settled = run(tmp_path, monkeypatch, operation, [metadata])
    assert native_targets(settled) == targets and unrelated(initial) == unrelated(settled)
    assert full_fields(settled) == full_fields(cold_reference(tmp_path, monkeypatch, operation))
    stable = products(tmp_path)
    run(tmp_path, monkeypatch, operation, [path, qml, metadata])
    assert products(tmp_path) == stable


@pytest.mark.parametrize("operation", ["manual", "watch"])
@pytest.mark.parametrize("failure", ["syntax", "replace"])
def test_req_qml022_ac06_member_name_failure_keeps_accepted_graph_before_recovery(tmp_path, monkeypatch, capsys, operation, failure):
    """Actual source rejection and graph EIO retain all accepted identities, then recover."""
    path = project(tmp_path, source(native=True, out_of_line=True).encode(), native=True)
    monkeypatch.chdir(tmp_path)
    initial = run(tmp_path, monkeypatch, operation)
    accepted = products(tmp_path)
    targets = native_targets(initial)
    valid = path.read_bytes().replace(b"UpperType Field;", b"UpperType UpperField;")
    path.write_bytes(valid[:-2] if failure == "syntax" else valid)
    unchanged = path.read_bytes(), path.stat().st_mtime_ns
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
    repaired = run(tmp_path, monkeypatch, operation, [path])
    assert native_targets(repaired) == targets and "UpperField" in field_nodes(repaired)
    if failure == "replace":
        assert (path.read_bytes(), path.stat().st_mtime_ns) == unchanged
    assert unrelated(initial) == unrelated(repaired)
    assert full_fields(repaired) == full_fields(cold_reference(tmp_path, monkeypatch, operation))
    stable = products(tmp_path)
    run(tmp_path, monkeypatch, operation, [path])
    assert products(tmp_path) == stable and not list((tmp_path / "graphify-out").glob(".gfy-*.tmp"))


def test_req_qml022_ac06_direct_member_repair_export_eio_retains_then_repeats(tmp_path, monkeypatch):
    """Direct typed field/method output is adopted only after real replacement completes."""
    path = project(tmp_path, source().encode())
    output = tmp_path / "accepted.json"
    assert to_json(build_from_json(extract_cpp(path), root=tmp_path), {}, str(output), force=True)
    accepted = output.read_bytes()
    path.write_bytes(path.read_bytes().replace(b"UpperType Field;", b"UpperType UpperField;"))
    graph = build_from_json(extract_cpp(path), root=tmp_path)
    with publication_fault(output, "replace", monkeypatch) as fault:
        for _ in range(2):
            with pytest.raises(OSError) as failure:
                to_json(graph, {}, str(output), force=True)
            assert failure.value.errno == errno.EIO and output.read_bytes() == accepted
        assert fault.hits >= 2
    assert to_json(graph, {}, str(output), force=True)
    current = output.read_bytes()
    assert current != accepted and to_json(graph, {}, str(output), force=True)
    assert output.read_bytes() == current
