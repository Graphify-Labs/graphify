"""INC-QML-109: bounded original scope roles survive sanitation and reject damage."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extractors.cpp_class_scopes import CppClassScopes
from graphify.extractors.cpp_class_proof import class_fact
from graphify.extractors.cpp_free_calls import resolve_free_function_calls
from graphify.extractors.cpp_functions import decoded
from graphify.paths import load_node_link_graph
from graphify.security import sanitize_metadata
from tests.cpp_nested_helpers import class_by_name, nested_source, produce, source_call_edges
from tests.cpp_same_unit_helpers import validate_span


@pytest.mark.parametrize("damage", [
    "missing", "version_bool", "complete_int", "conditional_int", "conditional_true",
    "scopes_mapping", "over_limit", "kind_list", "kind_unknown", "bad_name",
    "bad_span", "namespace_after_class", "omitted_class", "parent_witness",
])
def test_req_qml022_ac06_scope_role_transport_rejects_malformed_or_incomplete_proof(tmp_path, damage):
    """Actual source facts cross the public resolver without repairing promised roles."""
    result = produce(tmp_path, nested_source(namespace="Public"))
    outer, inner = class_by_name(result, "Outer"), class_by_name(result, "Inner")
    fact = inner["metadata"]["cpp_class"]
    proof = fact["lexical_scope_proof"]
    if damage == "missing":
        del fact["lexical_scope_proof"]
    elif damage == "version_bool":
        proof["contract_version"] = True
    elif damage == "complete_int":
        proof["complete"] = 1
    elif damage == "conditional_int":
        proof["conditional"] = 0
    elif damage == "conditional_true":
        proof["conditional"] = True
    elif damage == "scopes_mapping":
        proof["scopes"] = {}
    elif damage == "over_limit":
        proof["scopes"] *= 26
    elif damage == "kind_list":
        proof["scopes"][0]["kind"] = []
    elif damage == "kind_unknown":
        proof["scopes"][0]["kind"] = "unknown"
    elif damage == "bad_name":
        proof["scopes"][0]["name_b64"] = "not base64"
    elif damage == "bad_span":
        proof["scopes"][0]["span"]["end_column"] += 1
    elif damage == "namespace_after_class":
        proof["scopes"][-1]["kind"] = "namespace"
    elif damage == "omitted_class":
        proof["scopes"].pop()
    else:
        outer["metadata"]["cpp_class"]["lexical_scope_proof"]["complete"] = False
    result["edges"][:] = [edge for edge in result["edges"] if edge.get("relation") != "calls"]
    before = deepcopy(result["nodes"])
    resolve_free_function_calls(result["nodes"], result["edges"], result["raw_calls"])
    assert not source_call_edges(result) and result["nodes"] == before


@pytest.mark.parametrize("field,value", [("confidence", []), ("confidence", {}),
                                         ("source_location", []), ("source_location", {}),
                                         ("source_file", []), ("source_file", {})])
def test_req_qml022_ac06_malformed_parent_edge_declines_without_hashing_untrusted_values(tmp_path, field, value):
    """Actual produced ancestry is replayed with a malformed edge scalar, not a guessed parent."""
    result = produce(tmp_path, nested_source())
    outer, inner = class_by_name(result, "Outer"), class_by_name(result, "Inner")
    edge, = [edge for edge in result["edges"] if edge.get("relation") == "contains"
             and (edge.get("source"), edge.get("target")) == (outer["id"], inner["id"])]
    edge[field] = value
    result["edges"][:] = [edge for edge in result["edges"] if edge.get("relation") != "calls"]
    before = deepcopy(result["nodes"])
    resolve_free_function_calls(result["nodes"], result["edges"], result["raw_calls"])
    assert not source_call_edges(result) and result["nodes"] == before


@pytest.mark.parametrize("damage", ["namespace_inside_class", "qualified_class_entry", "unpromised_container"])
def test_req_qml022_ac06_contradicted_source_scope_roles_cannot_replace_actual_classes(tmp_path, damage):
    """Consistent flattened spelling cannot repair a false class/namespace role."""
    result = produce(tmp_path, nested_source(namespace="Public", depth=2))
    inner = class_by_name(result, "Inner")
    scopes = inner["metadata"]["cpp_class"]["lexical_scope_proof"]["scopes"]
    if damage == "namespace_inside_class":
        scopes[-1]["kind"] = "namespace"
    elif damage == "qualified_class_entry":
        scopes[1]["name_b64"] = "T3V0ZXI6Ok5lc3RlZA=="
    else:
        for scope in scopes:
            scope["kind"] = "namespace"
        classes = {node["id"] for node in result["nodes"] if node.get("_callable_class")}
        result["edges"][:] = [edge for edge in result["edges"]
                              if not (edge.get("relation") == "contains" and edge.get("source") in classes)]
    result["edges"][:] = [edge for edge in result["edges"] if edge.get("relation") != "calls"]
    before = deepcopy(result["nodes"])
    resolve_free_function_calls(result["nodes"], result["edges"], result["raw_calls"])
    assert not source_call_edges(result) and result["nodes"] == before


@pytest.mark.parametrize("source_file", [[], {}, ["foreign"], None, ""])
def test_req_qml022_ac06_invalid_parent_source_scalar_declines_before_indexing(tmp_path, source_file):
    """A promised class parent with damaged provenance cannot become a namespace or a hash key."""
    result = produce(tmp_path, nested_source())
    outer = class_by_name(result, "Outer")
    outer["source_file"] = source_file
    result["edges"][:] = [edge for edge in result["edges"] if edge.get("relation") != "calls"]
    before = deepcopy(result["nodes"])
    assert CppClassScopes(result["nodes"], result["edges"]).scope(outer["id"]) is None
    resolve_free_function_calls(result["nodes"], result["edges"], result["raw_calls"])
    assert not source_call_edges(result) and result["nodes"] == before


@pytest.mark.parametrize("extra", [123, {"unrelated": []}, ["Rm9yZWlnbg=="]])
def test_req_qml022_ac06_constructor_cannot_consume_member_only_using_transport(tmp_path, extra):
    """Unrelated constructor metadata cannot lend a member-family namespace or break an ordinary call."""
    raw = b"void helper(){} class Panel{public:Panel(){helper();}};"
    result = produce(tmp_path, raw)
    constructor, = [node for node in result["nodes"] if node.get("metadata", {}).get("cpp_constructor")]
    target, = [node for node in result["nodes"] if node.get("label") == "helper()"]
    constructor["metadata"]["cpp_constructor"]["using_b64"] = extra
    result["edges"][:] = [edge for edge in result["edges"] if edge.get("relation") != "calls"]
    before = deepcopy(result["nodes"])
    resolve_free_function_calls(result["nodes"], result["edges"], result["raw_calls"])
    calls = [edge for edge in result["edges"] if edge.get("relation") == "calls"
             and (edge["source"], edge["target"]) == (constructor["id"], target["id"])]
    assert len(calls) == 1 and result["nodes"] == before


def test_req_qml022_ac06_constructor_extra_using_cannot_authorize_a_foreign_owner(tmp_path):
    """A member-only extra cannot expand an actual constructor's exact owner spelling."""
    raw = b"void helper(){} class Panel{public:Panel(){helper();}};namespace Foreign {class Panel{};}"
    result = produce(tmp_path, raw)
    constructor, = [node for node in result["nodes"] if node.get("metadata", {}).get("cpp_constructor")]
    foreign, = [node for node in result["nodes"] if decoded(class_fact(node).get("qualified_name_b64")) == "Foreign::Panel"]
    constructor["metadata"]["cpp_constructor"]["using_b64"] = ["Rm9yZWlnbg=="]
    edge, = [edge for edge in result["edges"] if edge.get("relation") == "method" and edge["target"] == constructor["id"]]
    edge["source"] = foreign["id"]
    result["edges"][:] = [edge for edge in result["edges"] if edge.get("relation") != "calls"]
    before = deepcopy(result["nodes"])
    resolve_free_function_calls(result["nodes"], result["edges"], result["raw_calls"])
    assert not [edge for edge in result["edges"] if edge.get("relation") == "calls"]
    assert result["nodes"] == before


@pytest.mark.parametrize("count,available", [(49, True), (50, False)])
def test_req_qml022_ac06_scope_role_limit_is_explicit_before_sanitation(tmp_path, count, available):
    """The exact50-entry metadata boundary never truncates into lookup authority."""
    raw = b"".join(f"namespace N{number}{{\n".encode() for number in range(count))
    raw += nested_source() + b"}\n" * count
    result = produce(tmp_path, raw)
    inner = class_by_name(result, "Inner")
    witness = inner["metadata"]["cpp_class"]["lexical_scope_proof"]
    assert witness["complete"] is available
    assert len(witness["scopes"]) == (50 if available else 0)
    assert len(source_call_edges(result)) == int(available)
    for node in result["nodes"]:
        metadata = node.get("metadata", {})
        if "cpp_class" in metadata:
            assert sanitize_metadata(metadata) == metadata
            for role in metadata["cpp_class"]["lexical_scope_proof"]["scopes"]:
                assert validate_span(raw, role)
    output = tmp_path / "scope.json"
    assert to_json(build_from_json(result, root=tmp_path), {}, str(output), force=True)
    restored = load_node_link_graph(json.loads(output.read_text(encoding="utf-8")))
    assert restored.nodes[inner["id"]]["metadata"]["cpp_class"]["lexical_scope_proof"] == witness


def test_req_qml022_ac06_scope_view_is_read_only_and_run_local(tmp_path):
    """Two distinct actual source cohorts do not borrow an earlier parent's namespace."""
    first = produce(tmp_path, nested_source(namespace="First"))
    second = produce(tmp_path, nested_source(namespace="Second"))
    snapshots = deepcopy((first, second))
    left, right = (CppClassScopes(result["nodes"], result["edges"]) for result in (first, second))
    for result, view, namespace in ((first, left, "First"), (second, right, "Second")):
        inner = class_by_name(result, "Inner")
        outer = class_by_name(result, "Outer")
        assert view.scope(inner["id"]) == (namespace, (outer["id"], inner["id"]))
        assert view.scope(inner["id"]) == (namespace, (outer["id"], inner["id"]))
    assert left.scope(class_by_name(second, "Inner")["id"]) is None
    assert (first, second) == snapshots


@pytest.mark.parametrize("prefix", ["", "#ifndef OWNED_HEADER\n#define OWNED_HEADER\n"])
def test_req_qml022_ac06_scope_witness_preserves_conventional_guard_and_original_bytes(tmp_path, prefix):
    """The existing literal include-guard predicate supplies no feature-branch selection."""
    raw = b"\xef\xbb\xbf// \xcf\x80\r\n" + prefix.encode() + nested_source(namespace="Public")
    if prefix:
        raw += b"#endif\n"
    raw = raw.replace(b"\n", b"\r\n")
    result = produce(tmp_path, raw, filename="nested.hpp")
    assert len(source_call_edges(result)) == 1
    for node in result["nodes"]:
        if fact := node.get("metadata", {}).get("cpp_class"):
            assert validate_span(raw, fact)
            assert fact["lexical_scope_proof"]["conditional"] is False


def test_req_qml022_ac06_scope_helper_first_import_preserves_producer_import_direction():
    """The class producer's local hook prevents a helper-first constructor import cycle."""
    code = ("from graphify.extractors.cpp_class_scopes import CppClassScopes; "
            "from graphify.extract import extract_cpp; print('ready')")
    result = subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[1],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ready"


@pytest.mark.parametrize("raw,label", [
    (b"void helper(){} union Outer {struct Inner {void run(){helper();}};};", "Inner"),
    (b"void helper(){} template<class T>struct Outer {struct Inner {void run(){helper();}};};", "Inner"),
    (b"void helper(){} struct Outer {struct Inner;}; struct Outer::Inner {void run(){helper();}};", "Outer::Inner"),
    (b"void helper(){} void outer(){struct Local {void run(){helper();}};}", "Local"),
    (b"namespace {void helper(){} struct Inner {void run(){helper();}};}", "Inner"),
])
def test_req_qml022_ac06_unsupported_class_scope_shapes_gain_no_new_scope_authority(tmp_path, raw, label):
    """Unproved semantic/anonymous/local/template scopes keep their explicit unsupported boundary."""
    result = produce(tmp_path, raw)
    owners = [node for node in result["nodes"] if node.get("_callable_class") and node.get("label") == label]
    view = CppClassScopes(result["nodes"], result["edges"])
    if label == "Local":
        assert not owners  # The generic producer does not admit function-local class declarations.
    else:
        owner, = owners
        assert view.scope(owner["id"]) is None
    assert not [edge for edge in source_call_edges(result) if edge.get("context") == "cpp_free_function"]
