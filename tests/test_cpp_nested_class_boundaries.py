"""INC-QML-109: incomplete or damaged ancestry cannot authorize free lookup."""
from __future__ import annotations

from copy import deepcopy

import pytest

from graphify.extractors.cpp_free_calls import resolve_free_function_calls
from graphify.extractors.resolution import _merge_decl_def_classes
from tests.cpp_nested_helpers import class_by_name, nested_source, produce, source_call_edges


@pytest.mark.parametrize("damage", [
    "missing_edge", "inferred_edge", "foreign_edge", "wrong_relation", "wrong_parent",
    "missing_parent", "foreign_parent", "duplicate_parent", "ambiguous_parent",
    "forward_parent", "bad_span", "wrong_scope", "malformed_scope",
])
def test_req_qml022_ac06_nested_ancestry_damage_declines_instead_of_using_global(tmp_path, damage):
    """Replay real source facts after damage; an omitted parent is not a namespace."""
    result = deepcopy(produce(tmp_path, nested_source()))
    outer, inner = class_by_name(result, "Outer"), class_by_name(result, "Inner")
    edge, = [edge for edge in result["edges"] if edge.get("relation") == "contains"
             and (edge.get("source"), edge.get("target")) == (outer["id"], inner["id"])]
    proof = outer["metadata"]["cpp_class"]
    if damage == "missing_edge":
        result["edges"].remove(edge)
    elif damage == "inferred_edge":
        edge["confidence"] = "INFERRED"
    elif damage == "foreign_edge":
        edge["source_file"] = "foreign.cpp"
    elif damage == "wrong_relation":
        edge["relation"] = "method"
    elif damage == "wrong_parent":
        edge["source"] = inner["id"]
    elif damage == "missing_parent":
        result["nodes"].remove(outer)
        result["edges"][:] = [value for value in result["edges"] if outer["id"] not in (value.get("source"), value.get("target"))]
    elif damage == "foreign_parent":
        outer["source_file"] = "foreign.cpp"
    elif damage == "duplicate_parent":
        duplicate = deepcopy(outer)
        duplicate["id"] += "_duplicate"
        result["nodes"].append(duplicate)
    elif damage == "ambiguous_parent":
        proof["ambiguous"] = True
    elif damage == "forward_parent":
        proof["is_definition"] = False
    elif damage == "bad_span":
        proof["span"]["end_byte"] = inner["metadata"]["cpp_class"]["span"]["start_byte"]
    elif damage == "wrong_scope":
        proof["scope_b64"] = "T3RoZXI="
    else:
        proof["scope_b64"] = []
    result["edges"][:] = [edge for edge in result["edges"] if edge.get("relation") != "calls"]
    nodes = deepcopy(result["nodes"])
    resolve_free_function_calls(result["nodes"], result["edges"], result["raw_calls"])
    assert not source_call_edges(result)
    assert result["nodes"] == nodes


@pytest.mark.parametrize("body", [False, True])
def test_req_qml022_ac06_conditional_nested_owner_cannot_supply_namespace_or_members(tmp_path, body):
    """A selected preprocessor branch is not established by ordinary static analysis."""
    raw = nested_source(shadow="static void (*helper)();")
    if body:
        raw = raw.replace(b"void Outer::Inner::run()", b"#if FEATURE\nvoid Outer::Inner::run()") + b"#endif\n"
    else:
        raw = raw.replace(b"struct Outer", b"#if FEATURE\nstruct Outer").replace(b"void Outer::Inner", b"#endif\nvoid Outer::Inner")
    result = produce(tmp_path, raw)
    assert not source_call_edges(result)


def test_req_qml022_ac06_nested_qualified_name_does_not_select_foreign_same_label(tmp_path):
    """Foreign class declarations cannot replace actual enclosing source ownership."""
    raw = nested_source(namespace="Actual", shadow="static void helper();")
    raw += b"namespace Other {struct Outer {struct Inner {void run();};};}\n"
    result = produce(tmp_path, raw, mode="facade")
    assert not source_call_edges(result)


def test_req_qml022_ac06_canonical_method_edge_cannot_change_source_proven_owner(tmp_path):
    """An actual foreign class edge cannot replace the canonical member's original owner."""
    raw = (b"void helper(){} class Panel{public:static void (*helper)();void run();}; "
           b"class Other{}; void Panel::run(){helper();}")
    result = produce(tmp_path, raw)
    _merge_decl_def_classes(result["nodes"], result["edges"], result["raw_calls"])
    panel, other = class_by_name(result, "Panel"), class_by_name(result, "Other")
    assert not source_call_edges(result)
    edge, = [edge for edge in result["edges"] if edge.get("relation") == "method" and edge["source"] == panel["id"]]
    edge["source"] = other["id"]
    before = deepcopy(result["nodes"])
    resolve_free_function_calls(result["nodes"], result["edges"], result["raw_calls"])
    assert not source_call_edges(result) and result["nodes"] == before
