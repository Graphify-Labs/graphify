"""INC-QML-15: constructor joins consume accepted file and class source bounds."""
from __future__ import annotations

import copy

import pytest

from graphify.extract import extract_cpp
from graphify.extractors.cpp_constructors import bind_cpp_constructors, constructor_merge_allowed
from tests.test_cpp_overload_identity import constructors, source_pair


def direct_pair(root, *, padding=False):
    """Retain real extracted containment while mutating only transported source proof."""
    paths = source_pair(root, "Backend(int);", "Backend::Backend(int) {}")
    if padding:
        paths[0].write_bytes(paths[0].read_bytes()
                            + b" void unrelated_function_with_enough_source_bytes_to_hold_fake_span() {}")
    extracted = [extract_cpp(path) for path in paths]
    nodes = copy.deepcopy([node for result in extracted for node in result["nodes"]])
    edges = copy.deepcopy([edge for result in extracted for edge in result["edges"]])
    found = constructors({"nodes": nodes})
    prototype = next(node for node in found if node["metadata"]["cpp_constructor"]["role"] == "declaration")
    definition = next(node for node in found if node["metadata"]["cpp_constructor"]["role"] == "definition")
    return paths, nodes, edges, prototype, definition


def assert_unbound(nodes, edges, definition):
    """Reject canonical merge; the direct header's existing same-ID method edge remains a source fact."""
    bind_cpp_constructors(nodes, edges)
    assert definition["metadata"]["cpp_constructor"].get("owner_bound") is not True
    assert not constructor_merge_allowed(constructors({"nodes": nodes}))


@pytest.mark.parametrize("role", ["declaration", "definition"])
def test_req_qml008_ac03_out_of_file_constructor_transport_cannot_bind(tmp_path, role):
    """A plausible same-line signature moved beyond the accepted file size has no source authority."""
    _, nodes, edges, prototype, definition = direct_pair(tmp_path)
    candidate = prototype if role == "declaration" else definition
    span = candidate["metadata"]["cpp_constructor"]["span"]
    span["start_byte"] += 1_000_000
    span["end_byte"] += 1_000_000
    assert_unbound(nodes, edges, definition)


def test_req_qml008_ac03_in_file_prototype_outside_class_cannot_bind(tmp_path):
    """A forged prototype on an unrelated same-line function remains inside the file, outside its class."""
    paths, nodes, edges, prototype, definition = direct_pair(tmp_path, padding=True)
    original_class_end = paths[0].read_bytes().index(b" void unrelated")
    span = prototype["metadata"]["cpp_constructor"]["span"]
    width = span["end_byte"] - span["start_byte"]
    start = original_class_end + 6
    span.update(start_byte=start, end_byte=start + width, start_column=start, end_column=start + width)
    assert span["end_byte"] <= len(paths[0].read_bytes())
    assert_unbound(nodes, edges, definition)


@pytest.mark.parametrize("corruption", ["missing", "duplicate", "size_bool", "size_negative", "version_bool", "foreign_label"])
def test_req_qml008_ac03_file_bound_transport_cannot_authorize_constructor(tmp_path, corruption):
    """Absent, conflicting or corrupt admitted file authority cannot validate an otherwise plausible body."""
    _, nodes, edges, _, definition = direct_pair(tmp_path)
    file = next(node for node in nodes if node["label"] == "backend.cpp")
    proof = file["metadata"]["cpp_constructor_types"]
    if corruption == "missing":
        file["metadata"].pop("cpp_constructor_types")
    elif corruption == "duplicate":
        nodes.append(copy.deepcopy(file))
    elif corruption == "size_bool":
        proof["source_size"] = True
    elif corruption == "size_negative":
        proof["source_size"] = -1
    elif corruption == "version_bool":
        proof["contract_version"] = True
    else:
        file["label"] = "foreign.cpp"
    assert_unbound(nodes, edges, definition)


@pytest.mark.parametrize("inline", [False, True])
def test_req_qml008_ac03_out_of_file_class_span_cannot_authorize_constructor(tmp_path, inline):
    """A complete class moved beyond its admitted file cannot authorize inline or out-of-line bodies."""
    if inline:
        path = tmp_path / "inline.cpp"
        path.write_bytes(b"class Backend {public: Backend(int) {}};")
        result = extract_cpp(path)
        nodes, edges = copy.deepcopy(result["nodes"]), copy.deepcopy(result["edges"])
        definition = constructors({"nodes": nodes})[0]
    else:
        _, nodes, edges, _, definition = direct_pair(tmp_path)
    owner = next(node for node in nodes if node.get("_callable_class"))
    span = owner["metadata"]["cpp_class"]["span"]
    span["start_byte"] += 1_000_000
    span["end_byte"] += 1_000_000
    assert_unbound(nodes, edges, definition)


def test_req_qml008_ac02_original_file_and_class_bounds_accept_without_source_rereads(tmp_path, monkeypatch):
    """Accepted EOF body bounds bind from existing AST facts even when corpus reads are unavailable."""
    from pathlib import Path

    paths, nodes, edges, prototype, definition = direct_pair(tmp_path)
    assert definition["metadata"]["cpp_constructor"]["span"]["end_byte"] == len(paths[1].read_bytes())

    def unavailable_read(*args, **kwargs):
        raise AssertionError("Constructor binding must consume existing admitted AST proof")

    monkeypatch.setattr(Path, "read_bytes", unavailable_read)
    monkeypatch.setattr(Path, "read_text", unavailable_read)
    bind_cpp_constructors(nodes, edges)
    assert definition["metadata"]["cpp_constructor"]["owner_bound"] is True
    assert constructor_merge_allowed([prototype, definition])


@pytest.mark.parametrize("prefix", [b"#include HEADER_MACRO\n", b"#include <QObject>\n" * 51])
def test_req_qml008_ac02_builtin_signature_file_bounds_independent_of_include_completeness(tmp_path, prefix):
    """Conservative SDK include exclusion cannot remove accepted builtin constructor equivalence."""
    paths = source_pair(tmp_path, "Backend(int);", "Backend::Backend(int) {}")
    paths[1].write_bytes(prefix + paths[1].read_bytes())
    result = [extract_cpp(path) for path in paths]
    nodes = [node for item in result for node in item["nodes"]]
    edges = [edge for item in result for edge in item["edges"]]
    prototype, definition = constructors({"nodes": nodes})
    file = next(node for node in nodes if node["label"] == "backend.cpp")
    assert file["metadata"]["cpp_constructor_types"]["complete"] is False
    bind_cpp_constructors(nodes, edges)
    assert definition["metadata"]["cpp_constructor"]["owner_bound"] is True
    assert constructor_merge_allowed([prototype, definition])
