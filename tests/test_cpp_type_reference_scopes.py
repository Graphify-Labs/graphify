"""INC-QML-114: only actual lexical decisions constrain generic type fallback."""
from __future__ import annotations

import base64

import pytest

from graphify.extract import extract
from graphify.extractors.cpp_type_references import validate_type_references
from tests.cpp_type_reference_helpers import produce, unavailable, uses


@pytest.mark.parametrize("kind", ["class", "alias"])
@pytest.mark.parametrize("later", [False, True])
@pytest.mark.parametrize("mechanism", ["field", "base"])
def test_req_qml014_ac03_foreign_literal_scope_and_source_order_remain_unavailable(tmp_path, kind, later, mechanism):
    """A known declaration in another scope cannot become visible through source order or inheritance."""
    declaration = "using Count=int;" if kind == "alias" else "class Count {};"
    provider = "namespace Left{" + declaration + "}\n"
    owner = ("namespace Right{struct Holder{Count value;};}\n" if mechanism == "field" else
             "namespace Right{struct Holder:Count{};}\n")
    raw = ((owner + provider) if later else (provider + owner)).encode()
    result = produce(tmp_path, raw)
    edge, target = uses(result)[0]
    assert not target["source_file"] and edge["cpp_type_reference_version"] == 1
    fact = edge["metadata"]["cpp_type_reference"]
    assert base64.b64decode(fact["raw_name_b64"]) == b"Count"
    assert base64.b64decode(fact["lookup_b64"]) == b"Count"
    validate_type_references(result["nodes"], result["edges"])


def test_req_qml014_ac03_actual_qualified_template_argument_cannot_supply_unqualified_peer(tmp_path):
    """Two real argument nodes retain their own qualification and original context spans."""
    raw = (b"namespace Left{using Count=int;}\nnamespace Right{struct Holder{\n"
           b"Box<Left::Count> good; Box<Count> bad;\n};}\n")
    result = produce(tmp_path, raw)
    arguments = [(edge, target) for edge, target in uses(result)
                 if edge.get("context") == "generic_arg" and target.get("label") == "Count"]
    assert len(arguments) == 2
    accepted = [(edge, target) for edge, target in arguments if target.get("source_file")]
    rejected = [(edge, target) for edge, target in arguments if not target.get("source_file")]
    assert len(accepted) == len(rejected) == 1
    assert "cpp_type_reference_version" not in accepted[0][0]
    edge = rejected[0][0]
    fact = edge["metadata"]["cpp_type_reference"]
    assert base64.b64decode(fact["lookup_b64"]) == b"Count"
    span = fact["type_span"]
    assert raw[span["start_byte"]:span["end_byte"]] == b"Count"


def test_req_qml014_ac03_shared_actual_cpp_stub_copies_keep_parameter_positive(tmp_path):
    """Two actual source producers share one bare type identity without sharing rejection policy."""
    header, body = tmp_path / "a.hpp", tmp_path / "b.cpp"
    header.write_bytes(b"namespace Left{class Thing{};}\nnamespace Right{class Holder{Thing *value;};}\n")
    body.write_bytes(b'#include "a.hpp"\nusing namespace Left;void allowed(Thing *arg){}\n')
    result = extract([header, body], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert not result.get("failed_sources") and not result.get("qml_failures")
    edge, target = uses(result)[0]
    assert not target["source_file"] and edge["cpp_type_reference_version"] == 1
    parameter = uses(result, "allowed()")
    assert len(parameter) == 1 and parameter[0][1]["source_file"] == "a.hpp"
    assert "cpp_type_reference_version" not in parameter[0][0]
    validate_type_references(result["nodes"], result["edges"])


def test_req_qml014_ac03_opaque_templated_qualifier_remains_unavailable(tmp_path):
    """A known leaf cannot erase the actually written unsupported templated owner path."""
    raw = (b"namespace Left{using Count=int;}\nnamespace Right{struct Holder{\n"
           b"Owner<int>::Inner::Count value;\n};}\n")
    result = produce(tmp_path, raw)
    edge, target = next((edge, target) for edge, target in uses(result) if target.get("label") == "Count")
    assert not target["source_file"] and edge["cpp_type_reference_version"] == 1
    fact = edge["metadata"]["cpp_type_reference"]
    assert fact["lookup_complete"] is True
    assert base64.b64decode(fact["raw_name_b64"]) == b"Count"
    assert base64.b64decode(fact["lookup_b64"]) == b"Owner<int>::Inner::Count"
    assert len(unavailable(result)) == 1


def test_req_qml014_ac03_same_literal_other_language_reference_does_not_inherit_cpp_policy(tmp_path):
    """Python's existing isolated unknown keeps its uncertainty and independent valid calls."""
    cpp, python = tmp_path / "types.cpp", tmp_path / "consumer.py"
    cpp.write_bytes(b"namespace Left{class Thing{};}\nnamespace Right{class Holder{Thing *value;};}\n"
                    b"using namespace Left;void allowed(Thing *arg){}\n")
    python.write_bytes(b"def helper():return 1\n\ndef python_use(value: Thing):return helper()\n")
    result = extract([cpp, python], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert not result.get("failed_sources")
    nodes = {node["id"]: node for node in result["nodes"]}
    rejected, stub = uses(result)[0]
    assert rejected["cpp_type_reference_version"] == 1 and not stub["source_file"]
    python_refs = [edge for edge in result["edges"] if edge.get("source_file") == "consumer.py"
                   and edge.get("relation") == "references" and nodes.get(edge.get("target"), {}).get("label") == "Thing"]
    assert python_refs and all("cpp_type_reference_version" not in edge and not nodes[edge["target"]]["source_file"]
                               for edge in python_refs)
    assert any(edge.get("relation") == "calls" and edge.get("source_file") == "consumer.py"
               and nodes.get(edge.get("target"), {}).get("label", "").startswith("helper") for edge in result["edges"])
