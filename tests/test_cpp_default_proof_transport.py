"""INC-QML-86: optional arity consumes typed, source-bounded default evidence."""
from __future__ import annotations

from copy import deepcopy

import pytest

from graphify.extract import extract_cpp
from graphify.extractors.cpp_functions import free_definition_fact


@pytest.mark.parametrize("corruption", ["row", "column", "outside", "mechanism", "span_type", "required_count", "duplicate"])
def test_req_qml022_ac06_malformed_erased_default_proof_never_lends_optional_arity(tmp_path, corruption):
    """Persisted proof cannot move original coordinates or change the source-required count."""
    path = tmp_path / "api.cpp"
    path.write_text("template<class T>struct Box{};void f(Box<int> value={}){}")
    node = deepcopy(next(node for node in extract_cpp(path)["nodes"] if node["label"] == "f()"))
    assert free_definition_fact(node)
    fact = node["metadata"]["cpp_function"]
    proof = fact["erased_default_parameters"][0]
    if corruption in {"row", "column"}:
        suffix = "row" if corruption == "row" else "column"
        for side in ("start_", "end_"):
            proof["default_span"][side + suffix] += 1
    elif corruption == "outside":
        proof["default_span"]["end_byte"] = fact["span"]["end_byte"] + 1
        proof["default_span"]["end_column"] = fact["span"]["end_column"] + 1
    elif corruption == "mechanism":
        proof["mechanism"] = "guessed_default"
    elif corruption == "span_type":
        proof["parameter_span"] = []
    elif corruption == "required_count":
        fact["ast_required_args"] = 0
    else:
        fact["erased_default_parameters"].append(deepcopy(proof))
    assert free_definition_fact(node) == {}
