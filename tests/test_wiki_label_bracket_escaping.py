"""Regression tests for issue #3547: a node label that literally contains
`[[...]]` (extracted from source content — a doc discussing or demonstrating
wikilink syntax, for example) must not be printed raw into a generated
article. `_md_link` already escapes `[`/`]` for anything it links, but three
other sites print a label directly into the article body without going
through it: a community's own title, its "Key Concepts" node listing, and a
god node's own title. Printed unescaped, `[[wikilink]]` renders as a real
(and always dead — the wiki export never writes bracket-style links) wikilink
instead of the plain text it actually is.
"""
from __future__ import annotations

import networkx as nx

from graphify.wiki import _community_article, _god_node_article, _escape_md_brackets, to_wiki


def test_escape_md_brackets_escapes_both_brackets():
    assert _escape_md_brackets("[[wikilink]]") == r"\[\[wikilink\]\]"
    assert _escape_md_brackets("plain text") == "plain text"


def test_escape_md_brackets_stringifies_a_non_string_node_id_fallback():
    # A networkx node id is not always a string (int and tuple ids are
    # legal). The label callers fall back to a node's own id when it has no
    # `label` attribute, so this must stringify instead of raising.
    assert _escape_md_brackets(1) == "1"
    assert _escape_md_brackets(("a", "b")) == "('a', 'b')"


def test_community_article_handles_a_node_with_no_label_and_a_non_string_id():
    G = nx.Graph()
    G.add_nodes_from([(1, {}), (2, {}), (3, {})])
    G.add_edges_from([(1, 2, {}), (1, 3, {}), (2, 3, {})])
    article = _community_article(G, 0, [1, 2, 3], "hello world", {0: "hello world"},
                                  None, {1: 0, 2: 0, 3: 0}, {})
    assert "**1**" in article


def test_community_title_escapes_bracket_label():
    G = nx.Graph()
    G.add_node("n1", label="sym", file_type="code", source_file="a.py")
    article = _community_article(G, 0, ["n1"], "[[Foo Bar Baz]]", {0: "[[Foo Bar Baz]]"},
                                  None, {"n1": 0}, {})
    assert "# \\[\\[Foo Bar Baz\\]\\]" in article
    assert "# [[Foo Bar Baz]]" not in article


def test_community_key_concepts_escapes_node_label():
    G = nx.Graph()
    G.add_node("n1", label="[[wikilink]]", file_type="concept", source_file="doc.md")
    G.add_node("n2", label="ordinary", file_type="code", source_file="a.py")
    G.add_edge("n1", "n2", relation="related")
    article = _community_article(G, 0, ["n1", "n2"], "Community 0", {0: "Community 0"},
                                  None, {"n1": 0, "n2": 0}, {})
    assert r"\[\[wikilink\]\]" in article
    assert "[[wikilink]]" not in article


def test_god_node_title_escapes_bracket_label():
    G = nx.Graph()
    G.add_node("n1", label="[[...]]", file_type="concept", source_file="doc.md")
    G.add_node("n2", label="caller", file_type="code", source_file="a.py")
    G.add_edge("n1", "n2", relation="calls", confidence="EXTRACTED")
    article = _god_node_article(G, "n1", {0: "Community 0"}, {"n1": 0, "n2": 0}, {})
    assert "# \\[\\[...\\]\\]" in article  # only [ and ] are escaped, not the dots
    assert "# [[...]]" not in article


def test_end_to_end_wiki_export_has_no_literal_wikilinks(tmp_path):
    """A label with content that resembles wikilink placeholder text ("[[link]]",
    "[[new_stem]]", empty "[[]]", per the issue's own examples) must not survive
    verbatim into any generated page."""
    G = nx.Graph()
    G.add_node("n1", label="[[link]]", file_type="concept", source_file="a.md", community=0)
    G.add_node("n2", label="[[new_stem]]", file_type="concept", source_file="a.md", community=0)
    G.add_node("n3", label="[[]]", file_type="concept", source_file="b.md", community=0)
    G.add_edge("n1", "n2", relation="related")
    G.add_edge("n2", "n3", relation="related")
    communities = {0: ["n1", "n2", "n3"]}

    out = tmp_path / "wiki"
    to_wiki(G, communities, out, community_labels={0: "Community 0"})

    for md in out.glob("*.md"):
        text = md.read_text(encoding="utf-8")
        assert "[[link]]" not in text, f"{md.name} still has a literal placeholder wikilink"
        assert "[[new_stem]]" not in text, f"{md.name} still has a literal placeholder wikilink"
        assert "[[]]" not in text, f"{md.name} still has a literal empty wikilink"
