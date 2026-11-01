"""INC-QML-114: source context stays bounded without changing lookup authority."""
from __future__ import annotations

import base64
from copy import deepcopy

import pytest

from graphify.extractors.cpp_type_references import make_type_reference, validate_type_references
from graphify.security import sanitize_metadata
from tests.cpp_type_reference_helpers import produce, source, unavailable, uses


def syntax(raw, wanted):
    """Use the installed production grammar, retaining its real byte-owned node."""
    from tree_sitter import Language, Parser
    import tree_sitter_cpp
    tree = Parser(Language(tree_sitter_cpp.language())).parse(raw)
    pending = [tree.root_node]
    while pending:
        node = pending.pop()
        if node.type == "type_identifier" and raw[node.start_byte:node.end_byte] == wanted:
            return node
        pending.extend(reversed(node.named_children))
    raise AssertionError("expected real type identifier")


@pytest.mark.parametrize("length", [383, 384])
def test_req_qml014_ac03_literal_and_scope_bound_survive_sanitation(length):
    """Maximum semantic fields fit the actual512-character metadata string boundary."""
    name, scope = "N" * length, "S" * length
    raw = ("struct Holder{" + name + " value;};").encode()
    fact = make_type_reference(name, scope, syntax(raw, name.encode()), raw)
    assert fact["scope_complete"] is True
    assert base64.b64decode(fact["raw_name_b64"]) == name.encode()
    assert base64.b64decode(fact["lexical_scope_b64"]) == scope.encode()
    assert sanitize_metadata({"cpp_type_reference": fact})["cpp_type_reference"] == fact


def test_req_qml014_ac03_oversized_named_scope_is_unavailable_without_truncated_names(tmp_path):
    """A real over-limit enclosing name retains rejection without claiming a shortened scope."""
    raw = ("namespace Left{using Count=int;}\nnamespace " + "N" * 385
           + "{struct Holder{Count value;};}\n").encode()
    result = produce(tmp_path, raw)
    edge, target = uses(result)[0]
    fact = edge["metadata"]["cpp_type_reference"]
    assert not target["source_file"] and fact["scope_complete"] is False and fact["lexical_scope_b64"] is None
    assert base64.b64decode(fact["raw_name_b64"]) == b"Count"
    validate_type_references(result["nodes"], result["edges"])


def test_req_qml014_ac03_unrepresentable_literal_is_controlled_not_truncated():
    """The encoder rejects oversized actual spelling rather than publishing a partial identity."""
    name = "N" * 385
    raw = ("struct Holder{" + name + " value;};").encode()
    with pytest.raises(ValueError, match="^CPP_REFERENCE_CONTEXT_INVALID:"):
        make_type_reference(name, "Holder", syntax(raw, name.encode()), raw)


@pytest.mark.parametrize("argument", ["source", "syntax", "empty_lookup", "surrogate_lookup"])
def test_req_qml014_ac03_encoder_rejects_invalid_source_inputs_with_bounded_error(argument):
    """Already-read bytes and an actual syntax context cannot be replaced by malformed inputs."""
    raw = b"struct Holder{Count value;};"
    node = syntax(raw, b"Count")
    lookup = "" if argument == "empty_lookup" else "\ud800" if argument == "surrogate_lookup" else "Count"
    with pytest.raises(ValueError, match="CPP_REFERENCE_CONTEXT_INVALID"):
        make_type_reference("Count", "Holder", None if argument == "syntax" else node,
                            "source" if argument == "source" else raw, lookup=lookup)


@pytest.mark.parametrize("malformed", [False, None, 3, b"source"])
def test_req_qml014_ac03_encoder_does_not_borrow_an_invalid_source_scope(malformed):
    """A source-owned rejection cannot be manufactured from a non-scope argument."""
    raw = b"struct Holder{Count value;};"
    with pytest.raises(ValueError, match="CPP_REFERENCE_CONTEXT_INVALID"):
        make_type_reference("Count", malformed, syntax(raw, b"Count"), raw)


# Semantic case IDs survive pytest changes to automatic long-value identifiers.
@pytest.mark.parametrize("lookup", ["Owner<int>::Inner::Count", "N" * 385],
                         ids=["opaque-template", "oversize-lookup"])
def test_req_qml014_ac03_opaque_lookup_and_global_scope_never_gain_positive_authority(lookup):
    """Written template qualification is retained opaquely, and over-limit spelling stays unavailable."""
    raw = b"struct Holder{Count value;};"
    fact = make_type_reference("Count", "", syntax(raw, b"Count"), raw, lookup=lookup)
    assert fact["scope_complete"] is True and fact["lexical_scope_b64"] == ""
    assert fact["lookup_complete"] is (len(lookup.encode()) <= 384)
    if fact["lookup_complete"]:
        assert base64.b64decode(fact["lookup_b64"]).decode() == lookup
    else:
        assert fact["lookup_b64"] is None
    assert sanitize_metadata({"cpp_type_reference": fact})["cpp_type_reference"] == fact


def test_req_qml014_ac03_actual_oversized_qualifier_keeps_unavailable_leaf(tmp_path):
    """The real producer carries an over-limit written path without shortening it into a binding."""
    raw = ("namespace Left{using Count=int;}\nstruct Holder{" + "N" * 385 + "::Count value;};\n").encode()
    result = produce(tmp_path, raw)
    edge, target = uses(result)[0]
    fact = edge["metadata"]["cpp_type_reference"]
    assert not target["source_file"] and base64.b64decode(fact["raw_name_b64"]) == b"Count"
    assert fact["lookup_complete"] is False and fact["lookup_b64"] is None


def test_req_qml014_ac03_actual_missing_or_mismatched_promise_never_changes_source(tmp_path):
    """Validation borrows facts read-only, including incomplete-scope promises."""
    result = produce(tmp_path, source(), "direct")
    edge = unavailable(result)[0]
    fact = edge["metadata"]["cpp_type_reference"]
    fact["scope_complete"], fact["lexical_scope_b64"] = False, None
    before = deepcopy(result)
    validate_type_references(result["nodes"], result["edges"])
    assert result == before
    fact["lexical_scope_b64"] = "SG9sZGVy"
    with pytest.raises(ValueError, match="CPP_REFERENCE_CONTEXT_INVALID"):
        validate_type_references(result["nodes"], result["edges"])
