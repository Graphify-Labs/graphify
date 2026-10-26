"""A community relabelled only by case keeps its wiki article (#4508)."""
from __future__ import annotations

from pathlib import Path

import networkx as nx

import graphify.wiki as wiki
from graphify.paths import write_text_atomic_if_changed


def _graph():
    G = nx.Graph()
    G.add_node("n1", label="parse", file_type="code", source_file="a.py", community=0)
    G.add_node("n2", label="render", file_type="code", source_file="b.py", community=1)
    G.add_edge("n1", "n2", relation="calls", confidence="EXTRACTED", weight=1.0)
    return G, {0: ["n1"], 1: ["n2"]}


def _case_insensitive_write(path, text):
    """Stand-in for APFS/NTFS: a name that differs from an existing entry only by
    case is written into that entry, which keeps its old case. Linux cannot do
    this, so the new-case name is made a symlink to the old entry."""
    path = Path(path)
    for entry in path.parent.iterdir():
        if entry.name != path.name and entry.name.lower() == path.name.lower():
            if not path.exists():
                path.symlink_to(entry.name)
            path = entry
            break
    return write_text_atomic_if_changed(path, text)


def test_case_only_relabel_keeps_article_on_case_insensitive_fs(tmp_path, monkeypatch):
    G, communities = _graph()
    monkeypatch.setattr(wiki, "write_text_atomic_if_changed", _case_insensitive_write)
    wiki.to_wiki(G, communities, tmp_path, community_labels={0: "groups", 1: "other"})
    wiki.to_wiki(G, communities, tmp_path, community_labels={0: "Groups", 1: "other"})
    assert (tmp_path / "Groups.md").is_file()
    assert "(Groups.md)" in (tmp_path / "index.md").read_text(encoding="utf-8")
    assert sorted(p.name for p in tmp_path.glob("*.md")) == ["Groups.md", "index.md", "other.md"]


def test_case_only_relabel_drops_old_page_on_case_sensitive_fs(tmp_path):
    G, communities = _graph()
    wiki.to_wiki(G, communities, tmp_path, community_labels={0: "groups", 1: "other"})
    wiki.to_wiki(G, communities, tmp_path, community_labels={0: "Groups", 1: "other"})
    assert sorted(p.name for p in tmp_path.glob("*.md")) == ["Groups.md", "index.md", "other.md"]
