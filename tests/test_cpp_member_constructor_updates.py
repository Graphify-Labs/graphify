"""INC-QML-111: an ID reused as data cannot retain old constructor authority."""
import pytest

from graphify.extractors.cpp_constructors import _fact
from graphify.source_relationships import logical_endpoints
from tests.qt_publication_faults import publication_fault
from tests.test_cpp_allocated_member_updates import cold_reference, full_fields
from tests.test_cpp_member_constructor_reservations import constructor_field
from tests.test_cpp_same_unit_updates import rejected
from tests.test_qt_final_incremental_parity import run, unrelated
from tests.test_qt_semantic_correction_updates import products


def data_node(graph, field):
    nodes = [(identity, node) for identity, node in graph.nodes(data=True) if node.get("label") == field]
    assert len(nodes) == 1
    identity, node = nodes[0]
    assert node.get("_callable") is not True and "cpp_constructor" not in node.get("metadata", {})
    assert node["metadata"]["cpp_declarator"]["kind"] == "field"
    return identity


def constructors(graph):
    return {identity for identity, node in graph.nodes(data=True) if _fact({"id": identity, **node}, "cpp_constructor")}


def native_targets(graph):
    return {target for left, right, attributes in graph.edges(data=True) if attributes.get("context") == "qml_js_call"
            for _, target in [logical_endpoints(graph, left, right, attributes)]}


def assert_data_only(graph, identity):
    """Real logical endpoints must not retain any method/call/native role for data."""
    for left, right, attributes in graph.edges(data=True):
        source, target = logical_endpoints(graph, left, right, attributes)
        if identity in {source, target}:
            assert attributes.get("relation") not in {"method", "calls", "indirect_call"}
            assert attributes.get("context") != "qml_js_call"


@pytest.mark.parametrize("operation", ["manual", "watch"])
@pytest.mark.parametrize("failure", [None, "replace", "syntax"])
def test_req_qml022_ac06_constructor_removal_cannot_leave_authority_on_same_id_field(tmp_path, monkeypatch, capsys, operation, failure):
    """Removing and restoring a constructor changes data identity without borrowing old roles."""
    path, field, _, with_ctor, without_ctor = constructor_field(
        tmp_path, field_first=True, parameter="int value=0", native=True)
    qml = tmp_path / "Main.qml"
    qml.write_bytes(b"import Public.MemberNames 1.0\nCaseOwner{function invoke(){ping();}}\n")
    monkeypatch.chdir(tmp_path)
    initial = run(tmp_path, monkeypatch, operation)
    ctor, = constructors(initial)
    native = native_targets(initial)
    assert len(native) == 1 and ctor not in native
    escaped = data_node(initial, field)
    assert escaped != ctor
    accepted = products(tmp_path)
    path.write_bytes(without_ctor[:-2] if failure == "syntax" else without_ctor)
    if failure == "replace":
        with publication_fault(tmp_path / "graphify-out/graph.json", "replace", monkeypatch) as fault:
            for _ in range(2):
                rejected(tmp_path, monkeypatch, operation, path)
                assert products(tmp_path) == accepted
            assert fault.hits >= 2
    elif failure == "syntax":
        for _ in range(2):
            rejected(tmp_path, monkeypatch, operation, path)
            assert products(tmp_path) == accepted
        path.write_bytes(without_ctor)
    if failure:
        captured = capsys.readouterr()
        assert ("GRAPH_PUBLICATION_FAILED" if failure == "replace" else "QML_GRAPH_PRESERVED") in captured.out + captured.err
    current = run(tmp_path, monkeypatch, operation, [path])
    assert not constructors(current) and data_node(current, field) == ctor
    assert native_targets(current) == native
    assert_data_only(current, ctor)
    assert escaped not in current and unrelated(initial) == unrelated(current)
    assert full_fields(current) == full_fields(cold_reference(tmp_path, monkeypatch, operation))
    stable = products(tmp_path)
    run(tmp_path, monkeypatch, operation, [path])
    assert products(tmp_path) == stable
    # Exact-byte restoration must restore the original constructor ID and
    # escape the data again, without an identity or source-proof drift.
    path.write_bytes(with_ctor)
    restored = run(tmp_path, monkeypatch, operation, [path])
    assert constructors(restored) == {ctor} and data_node(restored, field) == escaped
    assert native_targets(restored) == native
    assert_data_only(restored, escaped)
    assert full_fields(restored) == full_fields(cold_reference(tmp_path, monkeypatch, operation))
    settled = products(tmp_path)
    run(tmp_path, monkeypatch, operation, [path])
    assert products(tmp_path) == settled and not list((tmp_path / "graphify-out").glob(".gfy-*.tmp"))
