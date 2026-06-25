"""Tests for the GraphQL federation / contract-to-code wiring:
  - extract._consolidate_gql_duplicates  (private+public dedup, entity wins)
  - extract._link_gql_operations_to_resolvers  (operation -> resolver)
  - global_graph._stitch_federation  (cross-repo @key linking)
"""
import networkx as nx

from graphify.extract import (
    _consolidate_gql_duplicates,
    _link_gql_operations_to_resolvers,
)
from graphify.global_graph import _stitch_federation


def test_consolidate_keeps_one_node_and_entity_wins():
    """A type declared in both private (entity) and public (plain) schema of one
    repo collapses to a single node; the @key entity marking + key fields win."""
    nodes = [
        {"id": "gql_deal", "label": "Deal", "type": "gql_type", "file_type": "code"},
        {"id": "gql_deal", "label": "Deal", "type": "gql_entity", "file_type": "code",
         "federation": "entity", "key_fields": ["id"]},
        {"id": "code_foo", "label": ".Foo()", "file_type": "code"},
    ]
    dropped = _consolidate_gql_duplicates(nodes)

    assert dropped == 1
    deals = [n for n in nodes if n["id"] == "gql_deal"]
    assert len(deals) == 1
    assert deals[0]["type"] == "gql_entity"
    assert deals[0]["federation"] == "entity"
    assert deals[0]["key_fields"] == ["id"]
    # non-gql nodes are untouched
    assert any(n["id"] == "code_foo" for n in nodes)


def test_consolidate_entity_first_then_plain_stays_entity():
    """Order-independent: entity marking survives even if the plain type comes last."""
    nodes = [
        {"id": "gql_deal", "label": "Deal", "type": "gql_entity", "file_type": "code",
         "federation": "entity", "key_fields": ["id"]},
        {"id": "gql_deal", "label": "Deal", "type": "gql_type", "file_type": "code"},
    ]
    assert _consolidate_gql_duplicates(nodes) == 1
    assert nodes[0]["type"] == "gql_entity"


def test_link_operation_to_resolver_by_name():
    """gql_operation `createDeal` links to the Go resolver labelled `.CreateDeal()`."""
    nodes = [
        {"id": "gql_op_createdeal", "label": "createDeal", "type": "gql_operation",
         "file_type": "code", "source_file": "schema.graphqls", "source_location": "L1"},
        {"id": "graph_resolver_createdeal", "label": ".CreateDeal()", "file_type": "code"},
    ]
    edges = []
    added = _link_gql_operations_to_resolvers(nodes, edges)

    assert added == 1
    assert any(e["relation"] == "implemented_by"
               and e["source"] == "gql_op_createdeal"
               and e["target"] == "graph_resolver_createdeal"
               for e in edges)


def test_link_operation_no_match_adds_nothing():
    """No callable with a matching name -> no edge (no false positives)."""
    nodes = [
        {"id": "gql_op_createdeal", "label": "createDeal", "type": "gql_operation",
         "file_type": "code"},
        {"id": "gql_deal", "label": "Deal", "type": "gql_type", "file_type": "code"},  # a type, not callable
    ]
    edges = []
    assert _link_gql_operations_to_resolvers(nodes, edges) == 0
    assert edges == []


def _entity(nid, repo, federation, label="Deal"):
    return (nid, {"type": "gql_entity", "federation": federation, "label": label, "repo": repo})


def test_stitch_federation_links_extends_to_owner():
    """An entity owned in repo A (`type X @key`) and referenced in repo B
    (`extend type X @key`) gets a cross-repo federation_key edge B -> A."""
    G = nx.Graph()
    G.add_nodes_from([
        _entity("a::gql_deal", "a", "entity"),
        _entity("b::gql_deal", "b", "extends"),
        _entity("a::gql_deal_dup", "a", "extends"),  # same repo as owner -> must be skipped
    ])
    added = _stitch_federation(G)

    assert added == 1
    assert G.has_edge("b::gql_deal", "a::gql_deal")
    assert G["b::gql_deal"]["a::gql_deal"]["relation"] == "federation_key"
    # no self-repo link
    assert not G.has_edge("a::gql_deal_dup", "a::gql_deal")


def test_stitch_federation_is_idempotent():
    """Re-running drops prior federation_key edges first, so the count is stable."""
    G = nx.Graph()
    G.add_nodes_from([
        _entity("a::gql_deal", "a", "entity"),
        _entity("b::gql_deal", "b", "extends"),
    ])
    assert _stitch_federation(G) == 1
    assert _stitch_federation(G) == 1
    fed = [d for _, _, d in G.edges(data=True) if d.get("relation") == "federation_key"]
    assert len(fed) == 1
