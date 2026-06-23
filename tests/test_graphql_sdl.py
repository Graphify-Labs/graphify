import pytest

from graphify.graphql_sdl import extract_graphql_sdl

_SCHEMA = """
enum DealStatus {
    OPEN
    CLOSED
}

input CreateDealInput {
    name: String!
    status: DealStatus!
}

type Deal {
    id: ID!
    name: String!
}

type Mutation {
    createDeal(input: CreateDealInput!): Deal!
}
"""


def _write(path, content):
    path.write_text(content.lstrip(), encoding="utf-8")
    return path


def test_graphql_sdl_extracts_types_inputs_enums_and_operations(tmp_path):
    """SDL types, inputs, enums and Mutation fields become first-class nodes."""
    schema = _write(tmp_path / "schema.graphqls", _SCHEMA)

    result = extract_graphql_sdl(schema)
    nodes = {n["id"]: n for n in result["nodes"]}
    kinds = {n["id"]: n["type"] for n in result["nodes"]}

    # object type, input, enum
    assert kinds.get("gql_deal") == "gql_type"
    assert kinds.get("gql_createdealinput") == "gql_input"
    assert kinds.get("gql_dealstatus") == "gql_enum"
    # enum values
    assert kinds.get("gql_dealstatus_open") == "gql_enum_value"
    # Mutation field is an operation, not a plain type
    assert kinds.get("gql_op_createdeal") == "gql_operation"
    assert nodes["gql_op_createdeal"]["label"] == "createDeal"

    # every node carries a valid schema file_type + source location
    assert all(n["file_type"] == "code" for n in result["nodes"])
    assert nodes["gql_op_createdeal"]["source_location"].startswith("L")


def test_graphql_sdl_links_operation_to_input_and_return_type(tmp_path):
    """createDeal --references--> CreateDealInput and --returns--> Deal."""
    schema = _write(tmp_path / "schema.graphqls", _SCHEMA)

    result = extract_graphql_sdl(schema)
    edges = {(e["source"], e["relation"], e["target"]) for e in result["edges"]}

    assert ("gql_op_createdeal", "references", "gql_createdealinput") in edges
    assert ("gql_op_createdeal", "returns", "gql_deal") in edges
    # object type contains its fields
    assert ("gql_deal", "contains", "gql_deal_name") in edges


def test_graphql_sdl_malformed_schema_does_not_raise(tmp_path):
    """A broken schema yields an error marker, never an exception."""
    schema = _write(tmp_path / "bad.graphqls", "type Deal { id: ID!")  # missing brace

    result = extract_graphql_sdl(schema)
    assert result["nodes"] == []
    assert result["edges"] == []
    assert "error" in result
