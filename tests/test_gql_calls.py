"""Tests for GraphQL operation call-site extraction and linking:
  - graphql_calls.find_gql_operation_calls  (gql`...` root selections, Go tags)
  - graphql_calls.extract_gql_calls         (gql_call node shape)
  - extract._link_gql_calls_to_operations   (per-repo call -> operation)
  - global_graph._stitch_gql_calls          (cross-repo call -> operation)
"""
import networkx as nx

from graphify.graphql_calls import find_gql_operation_calls, extract_gql_calls
from graphify.extract import _link_gql_calls_to_operations
from graphify.global_graph import _stitch_gql_calls


TS_DOC = """
import { gql } from '@apollo/client'

export const ADD_EDUCATION_BOOKING = gql`
  mutation CreateEducationBooking($input: CreateEducationBookingInput!) {
    createEducationBooking(input: $input) {
      id
      status
      course {
        id
        name
      }
    }
  }
`
"""


def test_ts_root_mutation_call_is_found():
    """The root field of a mutation document is the operation it calls; nested
    fields (id/status/course/name) are not."""
    calls = find_gql_operation_calls(TS_DOC, ".ts")
    names = [n for n, _ in calls]
    assert names == ["createEducationBooking"]
    # line points at the root selection, not the `mutation` keyword line
    (_, line), = calls
    assert TS_DOC.splitlines()[line - 1].strip().startswith("createEducationBooking")


def test_ts_query_with_args_and_alias():
    """Args (with a variable) don't break brace tracking; aliases resolve to the
    real field name."""
    doc = """
    const Q = gql`
      query StoreProductVersion($id: ID!) {
        ver: storeProductVersion(id: $id) {
          id
          versions { id }
        }
      }
    `
    """
    names = [n for n, _ in find_gql_operation_calls(doc, ".ts")]
    assert names == ["storeProductVersion"]


def test_ts_inline_object_argument_does_not_leak_depth():
    """An inline object value in arguments must not be counted as a subselection."""
    doc = 'const Q = gql`mutation M { doThing(input: {a: 1, b: 2}) { ok } }`'
    names = [n for n, _ in find_gql_operation_calls(doc, ".ts")]
    assert names == ["doThing"]


def test_ts_fragment_spread_ignored():
    doc = """
    const Q = gql`
      query Q {
        storeProductVersions {
          ...VersionFields
        }
      }
    `
    """
    names = [n for n, _ in find_gql_operation_calls(doc, ".ts")]
    assert names == ["storeProductVersions"]


def test_go_graphql_tag_call():
    """A Go client struct tag names the operation it queries."""
    go = '''
    type q struct {
        ProductVersion `graphql:"storeProductVersionByProductIDAndNameOrDate(productID: $productID, name: $name, date: $date)"`
    }
    '''
    calls = find_gql_operation_calls(go, ".go")
    assert calls and calls[0][0] == "storeProductVersionByProductIDAndNameOrDate"


def test_non_graphql_file_yields_nothing():
    assert find_gql_operation_calls("const x = `just a template ${y}`", ".ts") == []


def test_extract_gql_calls_node_shape(tmp_path):
    f = tmp_path / "booking.ts"
    f.write_text(TS_DOC)
    out = extract_gql_calls(f)
    assert len(out["nodes"]) == 1
    n = out["nodes"][0]
    assert n["type"] == "gql_call"
    assert n["label"] == "createEducationBooking"
    assert n["op_name"] == "createEducationBooking"
    assert n["file_type"] == "code"
    assert n["source_location"].startswith("L")


def test_link_call_to_operation_same_repo():
    """A gql_call links to the gql_operation of the same name (per-repo pass)."""
    nodes = [
        {"id": "gql_op_createeducationbooking", "label": "createEducationBooking",
         "type": "gql_operation", "file_type": "code"},
        {"id": "gqlcall_x", "label": "createEducationBooking", "op_name": "createEducationBooking",
         "type": "gql_call", "file_type": "code", "source_file": "f.ts", "source_location": "L5"},
    ]
    edges = []
    assert _link_gql_calls_to_operations(nodes, edges) == 1
    e, = edges
    assert e["relation"] == "calls"
    assert e["source"] == "gqlcall_x"
    assert e["target"] == "gql_op_createeducationbooking"


def test_link_call_no_matching_operation_adds_nothing():
    nodes = [
        {"id": "gqlcall_x", "label": "ghostOp", "op_name": "ghostOp",
         "type": "gql_call", "file_type": "code"},
    ]
    edges = []
    assert _link_gql_calls_to_operations(nodes, edges) == 0
    assert edges == []


def test_stitch_gql_calls_cross_repo():
    """A frontend gql_call (repo adsw) links to the backend gql_operation (repo
    education) of the same name."""
    G = nx.Graph()
    G.add_node("education::gql_op_createeducationbooking", type="gql_operation",
               label="createEducationBooking", repo="education")
    G.add_node("adsw::gqlcall_1", type="gql_call", op_name="createEducationBooking",
               label="createEducationBooking", repo="adsw")
    G.add_node("network::gqlcall_2", type="gql_call", op_name="createEducationBooking",
               label="createEducationBooking", repo="network")
    added = _stitch_gql_calls(G)

    assert added == 2
    assert G.has_edge("adsw::gqlcall_1", "education::gql_op_createeducationbooking")
    assert G.has_edge("network::gqlcall_2", "education::gql_op_createeducationbooking")
    assert G["adsw::gqlcall_1"]["education::gql_op_createeducationbooking"]["relation"] == "calls"


def test_stitch_gql_calls_idempotent():
    G = nx.Graph()
    G.add_node("education::gql_op_x", type="gql_operation", label="x", repo="education")
    G.add_node("adsw::gqlcall_1", type="gql_call", op_name="x", label="x", repo="adsw")
    assert _stitch_gql_calls(G) == 1
    assert _stitch_gql_calls(G) == 1
    calls = [d for _, _, d in G.edges(data=True) if d.get("relation") == "calls"]
    assert len(calls) == 1
