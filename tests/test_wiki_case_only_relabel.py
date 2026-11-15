"""#4508 — a community relabelled only by letter case lost its article.

`to_wiki` writes each article through `write_text_atomic_if_changed`, then sweeps
`*.md` files the run did not produce. On a case-preserving, case-insensitive
filesystem (APFS, NTFS) an existing directory entry keeps its old case, so the
write for `Groups.md` replaced the contents of `groups.md` without renaming it.
The sweep then compared names case-sensitively, saw `"groups.md" not in
{"Groups.md"}`, unlinked the file the same run had just written, and left
`index.md` linking to a `Groups.md` that no longer existed.

Regression shape: on unmodified v8 `to_wiki` leaves no article at all after the
case-only relabel, so both the article-exists assertion and the link-resolves
assertion fail.
"""
from __future__ import annotations

import re

import networkx as nx

from graphify.wiki import to_wiki


def _graph() -> nx.Graph:
    g = nx.Graph()
    g.add_node("a", label="parse()", source_file="src/a.py", file_type="code")
    g.add_node("b", label="tokenize()", source_file="src/b.py", file_type="code")
    g.add_edge("a", "b", relation="calls")
    return g


def _inline_links(text: str) -> list[tuple[str, str]]:
    return re.findall(r"\[([^\]]*)\]\(([^)]+\.md)\)", text)


def test_case_only_relabel_keeps_the_article(tmp_path):
    """`groups` -> `Groups` must leave one article behind, not zero."""
    g = _graph()
    to_wiki(g, {0: ["a", "b"]}, tmp_path, community_labels={0: "groups"})
    assert (tmp_path / "groups.md").exists()

    to_wiki(g, {0: ["a", "b"]}, tmp_path, community_labels={0: "Groups"})

    articles = sorted(p.name for p in tmp_path.glob("*.md") if p.name != "index.md")
    assert len(articles) == 1, articles


def test_case_only_relabel_puts_the_new_case_on_disk(tmp_path):
    """The rename must reach disk, so the link in index.md resolves."""
    g = _graph()
    to_wiki(g, {0: ["a", "b"]}, tmp_path, community_labels={0: "groups"})
    to_wiki(g, {0: ["a", "b"]}, tmp_path, community_labels={0: "Groups"})

    # Case-insensitive filesystems match either spelling, so compare what the
    # directory actually reports: the entry must now carry the new case.
    listed = {p.name for p in tmp_path.iterdir()}
    assert "Groups.md" in listed, listed


def test_case_only_relabel_leaves_no_dangling_link(tmp_path):
    """index.md must not point at an article the sweep deleted."""
    g = _graph()
    to_wiki(g, {0: ["a", "b"]}, tmp_path, community_labels={0: "groups"})
    to_wiki(g, {0: ["a", "b"]}, tmp_path, community_labels={0: "Groups"})

    text = (tmp_path / "index.md").read_text(encoding="utf-8")
    missing = [target for _, target in _inline_links(text) if not (tmp_path / target).exists()]
    assert missing == [], missing


def test_case_only_relabel_keeps_the_new_content_not_the_stale_twin(tmp_path):
    """The surviving article must carry the NEW label's body, not the stale one.

    On a case-sensitive filesystem (ext4, most Linux CI) the relabel writes the
    correct `# Groups` article to a distinct `Groups.md`, while `groups.md` lingers
    with the old `# groups` heading. Renaming the stale twin over the fresh file
    (instead of unlinking it) silently restores the old body: no missing file, no
    dangling link, just wrong content. The other tests pass on both filesystems
    even with that bug, so this content check is the one that catches it on
    case-sensitive hosts.
    """
    g = _graph()
    to_wiki(g, {0: ["a", "b"]}, tmp_path, community_labels={0: "groups"})
    to_wiki(g, {0: ["a", "b"]}, tmp_path, community_labels={0: "Groups"})

    articles = [p for p in tmp_path.glob("*.md") if p.name != "index.md"]
    assert len(articles) == 1, [p.name for p in articles]
    body = articles[0].read_text(encoding="utf-8")
    assert "# Groups" in body, body
    assert "# groups" not in body, body


def test_a_genuinely_absent_article_is_still_swept(tmp_path):
    """The folded comparison must not keep unrelated stale articles alive."""
    g = _graph()
    to_wiki(g, {0: ["a", "b"]}, tmp_path, community_labels={0: "Core"})
    stale = tmp_path / "leftover-from-an-older-run.md"
    stale.write_text("# stale\n", encoding="utf-8")

    to_wiki(g, {0: ["a", "b"]}, tmp_path, community_labels={0: "Core"})

    assert not stale.exists()
