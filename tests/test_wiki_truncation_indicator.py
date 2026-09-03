"""Wiki articles say when a bounded relationship list was cut.

`_god_node_article` caps each relation-type group at 20 entries. The header
still reported the full degree, but the body silently dropped everything past
20 with no indicator - a node with 26 `references` edges listed 20 and the
reader had no way to know 6 were missing.
"""
from __future__ import annotations

import networkx as nx

from graphify.wiki import _community_article, _god_node_article


def _star(n_refs: int, n_other: int = 0):
    G = nx.Graph()
    G.add_node("hub", label="Hub", source_file="src/hub.py")
    for i in range(n_refs):
        G.add_node(f"r{i}", label=f"Ref{i}", source_file="src/r.py")
        G.add_edge("hub", f"r{i}", relation="references", confidence="EXTRACTED")
    for i in range(n_other):
        G.add_node(f"s{i}", label=f"Share{i}", source_file="src/s.py")
        G.add_edge("hub", f"s{i}", relation="shares_data_with", confidence="EXTRACTED")
    return G


def _community_with_cross_links(n_communities: int) -> tuple[nx.Graph, dict[int, str], dict[str, int]]:
    G = nx.Graph()
    G.add_node("hub", label="Hub", source_file="src/hub.py")
    labels = {0: "Core"}
    node_community = {"hub": 0}
    for i in range(n_communities):
        nid = f"external-{i:02d}"
        cid = i + 1
        G.add_node(nid, label=f"External {i:02d}", source_file=f"src/external_{i:02d}.py")
        G.add_edge("hub", nid, relation="references", confidence="EXTRACTED")
        labels[cid] = f"Community {i:02d}"
        node_community[nid] = cid
    return G, labels, node_community


def _community_text(n_communities: int) -> str:
    G, labels, node_community = _community_with_cross_links(n_communities)
    return _community_article(
        G,
        0,
        ["hub"],
        "Core",
        labels,
        cohesion=None,
        node_community=node_community,
    )


def test_an_over_cap_group_names_how_much_was_cut():
    text = _god_node_article(_star(26, 3), "hub", labels={})
    assert text.count("- [") + text.count("- Ref") >= 20
    assert "and 6 more `references` connection(s) not listed" in text
    # the untouched small group carries no indicator
    assert "more `shares_data_with`" not in text


def test_the_header_degree_and_the_body_now_agree():
    text = _god_node_article(_star(26, 3), "hub", labels={})
    assert "29 connections" in text
    listed = text.count("\n- ") - text.count("more `")
    assert listed + 6 == 29


def test_a_group_at_or_under_the_cap_has_no_indicator():
    for n in (20, 5):
        text = _god_node_article(_star(n), "hub", labels={})
        assert "not listed" not in text


def test_an_over_cap_community_names_how_many_relationships_were_cut():
    text = _community_text(13)
    relationships = text.split("## Relationships", 1)[1].split("## Source Files", 1)[0]

    assert relationships.count("shared connections") == 12
    assert "Community 11" in relationships
    assert "Community 12" not in relationships
    assert "and 1 more cross-community relationship(s) not listed" in relationships


def test_a_community_at_the_relationship_cap_has_no_indicator():
    text = _community_text(12)
    relationships = text.split("## Relationships", 1)[1].split("## Source Files", 1)[0]

    assert relationships.count("shared connections") == 12
    assert "more cross-community relationship(s)" not in relationships
