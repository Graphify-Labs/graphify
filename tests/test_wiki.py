"""Tests for graphify.wiki — Wikipedia-style article generation."""
import re
import urllib.parse
import pytest
from pathlib import Path
import networkx as nx
from graphify.wiki import to_wiki, _index_md, _community_article, _god_node_article

_MD_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def _inline_links(text):
    """Yield (display, decoded_target) for each inline markdown link, skipping
    external URLs. Targets are URL-decoded so they can be checked against the
    on-disk filename. (Display text with an escaped `]` isn't matched, but the
    generated labels used in link position never contain brackets.)"""
    for display, target in _MD_LINK.findall(text):
        if "://" in target:
            continue
        yield display, urllib.parse.unquote(target)


def _make_graph():
    G = nx.Graph()
    G.add_node("n1", label="parse", file_type="code", source_file="parser.py", community=0)
    G.add_node("n2", label="validate", file_type="code", source_file="parser.py", community=0)
    G.add_node("n3", label="render", file_type="code", source_file="renderer.py", community=1)
    G.add_node("n4", label="stream", file_type="code", source_file="renderer.py", community=1)
    G.add_edge("n1", "n2", relation="calls", confidence="EXTRACTED", weight=1.0)
    G.add_edge("n1", "n3", relation="references", confidence="INFERRED", weight=1.0)
    G.add_edge("n3", "n4", relation="calls", confidence="EXTRACTED", weight=1.0)
    return G


COMMUNITIES = {0: ["n1", "n2"], 1: ["n3", "n4"]}
LABELS = {0: "Parsing Layer", 1: "Rendering Layer"}
COHESION = {0: 0.85, 1: 0.72}
GOD_NODES = [{"id": "n1", "label": "parse", "degree": 2}]


def test_to_wiki_writes_index(tmp_path):
    G = _make_graph()
    n = to_wiki(G, COMMUNITIES, tmp_path, community_labels=LABELS, cohesion=COHESION, god_nodes_data=GOD_NODES)
    assert (tmp_path / "index.md").exists()


def test_to_wiki_returns_article_count(tmp_path):
    G = _make_graph()
    # 2 communities + 1 god node = 3
    n = to_wiki(G, COMMUNITIES, tmp_path, community_labels=LABELS, cohesion=COHESION, god_nodes_data=GOD_NODES)
    assert n == 3


def test_to_wiki_community_articles_created(tmp_path):
    G = _make_graph()
    to_wiki(G, COMMUNITIES, tmp_path, community_labels=LABELS)
    assert (tmp_path / "Parsing_Layer.md").exists()
    assert (tmp_path / "Rendering_Layer.md").exists()


def test_to_wiki_god_node_article_created(tmp_path):
    G = _make_graph()
    to_wiki(G, COMMUNITIES, tmp_path, community_labels=LABELS, god_nodes_data=GOD_NODES)
    assert (tmp_path / "parse.md").exists()


def test_index_links_all_communities(tmp_path):
    G = _make_graph()
    to_wiki(G, COMMUNITIES, tmp_path, community_labels=LABELS)
    index = (tmp_path / "index.md").read_text()
    assert "[Parsing Layer](Parsing_Layer.md)" in index
    assert "[Rendering Layer](Rendering_Layer.md)" in index


def test_index_lists_god_nodes(tmp_path):
    G = _make_graph()
    to_wiki(G, COMMUNITIES, tmp_path, community_labels=LABELS, god_nodes_data=GOD_NODES)
    index = (tmp_path / "index.md").read_text()
    assert "[parse](parse.md)" in index
    assert "2 connections" in index


def test_community_article_has_cross_links(tmp_path):
    G = _make_graph()
    to_wiki(G, COMMUNITIES, tmp_path, community_labels=LABELS)
    parsing = (tmp_path / "Parsing_Layer.md").read_text()
    # n1 (parsing) references n3 (rendering) → cross-community link
    assert "[Rendering Layer](Rendering_Layer.md)" in parsing


def test_community_article_shows_cohesion(tmp_path):
    G = _make_graph()
    to_wiki(G, COMMUNITIES, tmp_path, community_labels=LABELS, cohesion=COHESION)
    parsing = (tmp_path / "Parsing_Layer.md").read_text()
    assert "cohesion 0.85" in parsing


def test_community_article_has_audit_trail(tmp_path):
    G = _make_graph()
    to_wiki(G, COMMUNITIES, tmp_path, community_labels=LABELS)
    parsing = (tmp_path / "Parsing_Layer.md").read_text()
    assert "EXTRACTED" in parsing
    assert "INFERRED" in parsing


def test_god_node_article_has_connections(tmp_path):
    G = _make_graph()
    to_wiki(G, COMMUNITIES, tmp_path, community_labels=LABELS, god_nodes_data=GOD_NODES)
    article = (tmp_path / "parse.md").read_text()
    # parse's neighbours (validate, render) have no article of their own, so the
    # connections list shows them as plain text rather than as links.
    assert "validate" in article and "render" in article
    assert "[[" not in article
    assert "](validate.md)" not in article and "](render.md)" not in article


def test_god_node_article_links_community(tmp_path):
    G = _make_graph()
    to_wiki(G, COMMUNITIES, tmp_path, community_labels=LABELS, god_nodes_data=GOD_NODES)
    article = (tmp_path / "parse.md").read_text()
    assert "[Parsing Layer](Parsing_Layer.md)" in article


def test_to_wiki_skips_missing_god_node_ids(tmp_path):
    """God node with bad ID should not crash."""
    G = _make_graph()
    bad_gods = [{"id": "nonexistent", "label": "ghost", "degree": 99}]
    n = to_wiki(G, COMMUNITIES, tmp_path, community_labels=LABELS, god_nodes_data=bad_gods)
    # 2 communities + 0 god nodes (nonexistent skipped) = 2
    assert n == 2


def test_to_wiki_no_labels_uses_fallback(tmp_path):
    G = _make_graph()
    to_wiki(G, COMMUNITIES, tmp_path)  # no labels
    assert (tmp_path / "Community_0.md").exists()
    assert (tmp_path / "Community_1.md").exists()
    # fallback "Community N" labels still produce links that resolve to the file
    targets = [t for _, t in _inline_links((tmp_path / "index.md").read_text())]
    assert "Community_0.md" in targets and (tmp_path / "Community_0.md").exists()


def test_article_navigation_footer(tmp_path):
    G = _make_graph()
    to_wiki(G, COMMUNITIES, tmp_path, community_labels=LABELS)
    article = (tmp_path / "Parsing_Layer.md").read_text()
    assert "[index](index.md)" in article


def test_community_article_truncation_notice(tmp_path):
    """Communities with more than 25 nodes show a truncation notice."""
    G = nx.Graph()
    nodes = [f"n{i}" for i in range(30)]
    for nid in nodes:
        G.add_node(nid, label=f"concept_{nid}", file_type="code", source_file="a.py", community=0)
    for i in range(len(nodes) - 1):
        G.add_edge(nodes[i], nodes[i + 1], relation="calls", confidence="EXTRACTED", weight=1.0)
    communities = {0: nodes}
    to_wiki(G, communities, tmp_path, community_labels={0: "Big Community"})
    article = (tmp_path / "Big_Community.md").read_text()
    assert "and 5 more nodes" in article


# Regression tests for #925 - cross-community links always empty when node attrs lack community
def test_cross_community_links_without_node_community_attrs(tmp_path):
    """Cross-community links must work even when nodes have no 'community' attribute (#925)."""
    G = nx.Graph()
    G.add_node("n1", label="parse", file_type="code", source_file="parser.py")
    G.add_node("n2", label="render", file_type="code", source_file="renderer.py")
    G.add_edge("n1", "n2", relation="references", confidence="INFERRED", weight=1.0)
    communities = {0: ["n1"], 1: ["n2"]}
    labels = {0: "Parsing", 1: "Rendering"}
    to_wiki(G, communities, tmp_path, community_labels=labels)
    article = (tmp_path / "Parsing.md").read_text()
    assert "[Rendering](Rendering.md)" in article


def test_god_node_article_community_without_node_attr(tmp_path):
    """God node article must show community name even when node has no 'community' attr (#925)."""
    G = nx.Graph()
    G.add_node("n1", label="parse", file_type="code", source_file="parser.py")
    G.add_node("n2", label="validate", file_type="code", source_file="parser.py")
    G.add_edge("n1", "n2", relation="calls", confidence="EXTRACTED", weight=1.0)
    communities = {0: ["n1", "n2"]}
    labels = {0: "Core Logic"}
    god_nodes = [{"id": "n1", "label": "parse", "degree": 1}]
    to_wiki(G, communities, tmp_path, community_labels=labels, god_nodes_data=god_nodes)
    article = (tmp_path / "parse.md").read_text()
    assert "[Core Logic](Core_Logic.md)" in article


# Regression tests for #936 - stale community node IDs crash to_wiki after dedup/re-extract

def test_to_wiki_drops_stale_community_nodes(tmp_path):
    """Stale node IDs in communities dict are silently dropped without crash (#936)."""
    G = _make_graph()
    # Add a stale ID that exists in communities but not in G
    communities = {0: ["n1", "n2", "stale_ghost"], 1: ["n3", "n4"]}
    n = to_wiki(G, communities, tmp_path, community_labels=LABELS)
    assert n == 2  # both community articles still written
    article = (tmp_path / "Parsing_Layer.md").read_text()
    assert "parse" in article
    assert "stale_ghost" not in article


def test_to_wiki_all_stale_raises(tmp_path):
    """If every community node is stale, raise ValueError with a helpful message (#936)."""
    G = _make_graph()
    all_stale = {0: ["ghost1", "ghost2"], 1: ["ghost3"]}
    with pytest.raises(ValueError, match="stale"):
        to_wiki(G, all_stale, tmp_path, community_labels=LABELS)


def test_to_wiki_stale_nodes_prints_warning(tmp_path, capsys):
    """Stale node IDs trigger a stderr warning showing the drop count (#936)."""
    G = _make_graph()
    communities = {0: ["n1", "stale1", "stale2"], 1: ["n3", "n4"]}
    to_wiki(G, communities, tmp_path, community_labels=LABELS)
    err = capsys.readouterr().err
    assert "2" in err  # dropped count
    assert "stale" in err.lower()


def test_community_article_handles_null_source_file(tmp_path):
    """source_file=None on a node must not crash sorted() with TypeError (#1016)."""
    G = nx.Graph()
    G.add_node("n1", label="parse", file_type="code", source_file=None, community=0)
    G.add_node("n2", label="validate", file_type="code", source_file="parser.py", community=0)
    G.add_edge("n1", "n2", relation="calls", confidence="EXTRACTED", weight=1.0)
    communities = {0: ["n1", "n2"]}
    labels = {0: "Parsing Layer"}
    # Must not raise TypeError
    to_wiki(G, communities, tmp_path, community_labels=labels)
    assert (tmp_path / "index.md").exists()


def test_to_wiki_case_only_distinct_labels_dont_overwrite(tmp_path):
    """Two community labels differing only by case must each get their own
    article. The slug-dedup set folds case, so on case-insensitive filesystems
    (macOS/APFS, Windows/NTFS) the second article gets a numeric suffix instead
    of silently overwriting the first."""
    G = nx.Graph()
    G.add_node("n1", label="parse", file_type="code", source_file="a.py", community=0)
    G.add_node("n2", label="render", file_type="code", source_file="b.py", community=1)
    G.add_edge("n1", "n2", relation="calls", confidence="EXTRACTED", weight=1.0)
    communities = {0: ["n1"], 1: ["n2"]}
    labels = {0: "Parser", 1: "parser"}
    n = to_wiki(G, communities, tmp_path, community_labels=labels)
    articles = [p for p in tmp_path.glob("*.md") if p.name != "index.md"]
    # both communities survive as separate files on disk (no silent overwrite)
    assert len(articles) == n == 2, [p.name for p in articles]
    # filenames are distinct even when compared case-insensitively
    lowered = [p.stem.lower() for p in articles]
    assert len(set(lowered)) == len(lowered), [p.name for p in articles]


def test_to_wiki_god_node_label_case_collides_with_community(tmp_path):
    """Community and god-node articles share one slug-dedup set, so a god-node
    label differing only by case from a community label must still get its own
    file rather than overwriting the community article."""
    G = nx.Graph()
    G.add_node("n1", label="parse", file_type="code", source_file="a.py", community=0)
    G.add_node("n2", label="run", file_type="code", source_file="b.py", community=0)
    G.add_edge("n1", "n2", relation="calls", confidence="EXTRACTED", weight=1.0)
    communities = {0: ["n1", "n2"]}
    labels = {0: "Parser"}
    god_nodes = [{"id": "n1", "label": "parser", "degree": 1}]
    n = to_wiki(G, communities, tmp_path, community_labels=labels, god_nodes_data=god_nodes)
    articles = [p for p in tmp_path.glob("*.md") if p.name != "index.md"]
    assert len(articles) == n == 2, [p.name for p in articles]
    lowered = [p.stem.lower() for p in articles]
    assert len(set(lowered)) == len(lowered), [p.name for p in articles]


# Regression tests for portable wiki links - Obsidian [[wikilinks]] break in
# every non-Obsidian renderer (VS Code preview, GitHub, GitLab, plain browsers).


def test_wiki_emits_no_obsidian_wikilinks(tmp_path):
    """No generated file may contain Obsidian [[...]] syntax. Those links resolve
    only inside Obsidian (by note title); everywhere else [[Domain Data Models]]
    points at a literal `Domain Data Models.md` that doesn't exist."""
    G = _make_graph()
    to_wiki(G, COMMUNITIES, tmp_path, community_labels=LABELS, cohesion=COHESION, god_nodes_data=GOD_NODES)
    for md in tmp_path.glob("*.md"):
        assert "[[" not in md.read_text(), md.name


def test_wiki_links_resolve_to_real_files(tmp_path):
    """Every inline markdown link target across the whole wiki must point at a
    file that actually exists on disk. The display text may keep spaces/special
    characters, but the target is the URL-encoded slug, so it has to round-trip
    back to a real filename in any renderer."""
    G = _make_graph()
    to_wiki(G, COMMUNITIES, tmp_path, community_labels=LABELS, cohesion=COHESION, god_nodes_data=GOD_NODES)
    seen_link = False
    for md in tmp_path.glob("*.md"):
        for display, target in _inline_links(md.read_text()):
            seen_link = True
            assert (tmp_path / target).exists(), f"{md.name}: [{display}] -> {target} is dead"
    # guard against the test passing vacuously if links ever stop being emitted
    assert seen_link, "expected the wiki to contain inline markdown links"


def test_wiki_link_display_keeps_label_but_target_is_filename(tmp_path):
    """The fix's whole point: a link's display text is the human label (with
    spaces) while its target is the on-disk slug (underscores). This is what
    [[Domain Data Models]] could never express portably."""
    G = _make_graph()
    to_wiki(G, COMMUNITIES, tmp_path, community_labels=LABELS)
    index = (tmp_path / "index.md").read_text()
    assert "[Parsing Layer](Parsing_Layer.md)" in index
    assert "Parsing Layer.md" not in index  # the broken Obsidian-only target


def test_wiki_special_characters_in_label_resolve(tmp_path):
    """Labels with spaces, &, #, and parentheses must still produce a link whose
    URL-encoded target decodes back to the real (underscored) filename, so it
    works in CommonMark renderers and Obsidian alike. # is the dangerous one —
    left raw in a relative link it would be misread as a fragment."""
    G = nx.Graph()
    G.add_node("n1", label="a", file_type="code", source_file="a.py", community=0)
    G.add_node("n2", label="b", file_type="code", source_file="b.py", community=1)
    G.add_edge("n1", "n2", relation="references", confidence="INFERRED", weight=1.0)
    communities = {0: ["n1"], 1: ["n2"]}
    labels = {0: "C# & Auth (v2)", 1: "Other"}
    to_wiki(G, communities, tmp_path, community_labels=labels)
    article = (tmp_path / "Other.md").read_text()
    # the cross-link to the special-char community resolves to its real file
    targets = [t for _, t in _inline_links(article)]
    assert "C#_&_Auth_(v2).md" in targets
    assert (tmp_path / "C#_&_Auth_(v2).md").exists()
    # the raw target is fully percent-encoded — no bare ( ) that would terminate
    # the link early, no bare # that would be misread as a fragment
    assert "C%23_%26_Auth_%28v2%29.md" in article


def test_wiki_link_with_bracketed_label_resolves(tmp_path):
    """A label containing `[` / `]` (e.g. a generic like `Array[T]`) still
    produces a resolvable link: the brackets are escaped in the display text so
    they don't break the markdown, and percent-encoded in the target so it
    decodes back to the real file. (`_safe_filename` keeps brackets in the slug,
    so they reach the link target.)"""
    G = nx.Graph()
    G.add_node("n1", label="a", file_type="code", source_file="a.py", community=0)
    G.add_node("n2", label="b", file_type="code", source_file="b.py", community=1)
    G.add_edge("n1", "n2", relation="references", confidence="INFERRED", weight=1.0)
    communities = {0: ["n1"], 1: ["n2"]}
    labels = {0: "Array[T] Models", 1: "Other"}
    to_wiki(G, communities, tmp_path, community_labels=labels)
    article = (tmp_path / "Other.md").read_text()
    assert r"[Array\[T\] Models](Array%5BT%5D_Models.md)" in article
    assert (tmp_path / "Array[T]_Models.md").exists()


def test_wiki_links_to_nodes_without_articles_are_plain_text(tmp_path):
    """A god node links its neighbours, but only communities and god nodes get
    article files — neighbours without one must render as plain text, not as a
    link (dead even inside Obsidian)."""
    G = _make_graph()
    # only `parse` (n1) is a god node; its neighbours validate/render are not,
    # and have no article of their own
    to_wiki(G, COMMUNITIES, tmp_path, community_labels=LABELS, god_nodes_data=GOD_NODES)
    article = (tmp_path / "parse.md").read_text()
    assert "validate" in article and "render" in article
    # they appear as plain list items, not links
    assert "- validate" in article and "- render" in article
    # not wrapped in an Obsidian wikilink (the old form — dead even in Obsidian
    # since validate/render have no article)...
    assert "[[validate]]" not in article and "[[render]]" not in article
    # ...nor in a standard link to a non-existent article file
    for _, target in _inline_links(article):
        assert target not in ("validate.md", "render.md"), target


def test_wiki_links_use_collision_suffixed_slug(tmp_path):
    """When two labels collide on disk and the second article gets a numeric
    suffix (`parser_2.md`), links to it must target the suffixed slug, not the
    bare label. The resolver records the exact filename each article was written
    under, so the link target tracks the collision suffix."""
    G = nx.Graph()
    G.add_node("n1", label="a", file_type="code", source_file="a.py", community=0)
    G.add_node("n2", label="b", file_type="code", source_file="b.py", community=1)
    G.add_edge("n1", "n2", relation="references", confidence="INFERRED", weight=1.0)
    communities = {0: ["n1"], 1: ["n2"]}
    labels = {0: "Parser", 1: "parser"}  # collide case-insensitively
    to_wiki(G, communities, tmp_path, community_labels=labels)
    index_targets = [t for _, t in _inline_links((tmp_path / "index.md").read_text())]
    assert "parser_2.md" in index_targets  # link points at the suffixed file...
    for t in index_targets:
        assert (tmp_path / t).exists(), t  # ...and every target is a real file
