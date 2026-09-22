"""A god-node article says when a relation group was cut (#3127).

`_god_node_article` caps each relation-type group at 20 entries. The header
still reported the full degree, but the body silently dropped everything past
20 with no indicator - a node with 26 `references` edges listed 20 and the
reader had no way to know 6 were missing.
"""
from __future__ import annotations

import networkx as nx

from graphify.wiki import _god_node_article


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
