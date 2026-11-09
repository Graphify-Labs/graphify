"""Exporters must not rewrite a page whose content did not change (#3060).

An export re-runs on every graph.json change, and the wiki/Obsidian writers used
to regenerate and rewrite the entire page set unconditionally — tens of thousands
of identical files per run, each rewrite also firing inotify / re-index / sync.
"""
from __future__ import annotations

import os
from pathlib import Path

import networkx as nx

from graphify.paths import write_text_atomic_if_changed
from graphify.export import to_obsidian
from graphify.wiki import to_wiki


def _mtime(p: Path) -> int:
    return os.stat(p).st_mtime_ns


def test_write_text_atomic_if_changed_skips_identical(tmp_path):
    target = tmp_path / "note.md"

    # Missing file -> writes, reports True.
    assert write_text_atomic_if_changed(target, "hello\nworld\n") is True
    assert target.read_text(encoding="utf-8") == "hello\nworld\n"
    before = _mtime(target)

    # Identical content -> no write, reports False, mtime untouched.
    assert write_text_atomic_if_changed(target, "hello\nworld\n") is False
    assert _mtime(target) == before

    # Different content -> writes, reports True.
    assert write_text_atomic_if_changed(target, "hello\nworld!\n") is True
    assert target.read_text(encoding="utf-8") == "hello\nworld!\n"


def _two_node_graph():
    G = nx.Graph()
    G.add_node("n1", label="Database", community=0, source_file="app/db.py", type="code")
    G.add_node("n2", label="Server", community=0, source_file="app/srv.py", type="code")
    G.add_edge("n1", "n2")
    return G, {0: ["n1", "n2"]}


def test_to_obsidian_rerun_does_not_rewrite_unchanged_notes(tmp_path):
    """A second identical export leaves each note's bytes and mtime untouched,
    yet the note stays owned (not pruned)."""
    G, communities = _two_node_graph()
    out = tmp_path / "obsidian"
    to_obsidian(G, communities, str(out), community_labels={0: "Backend"})

    note = out / "Database.md"
    assert note.exists()
    before = _mtime(note)

    to_obsidian(G, communities, str(out), community_labels={0: "Backend"})

    assert note.exists(), "an unchanged, owned note must not be pruned"
    assert _mtime(note) == before, "an unchanged note must not be rewritten (#3060)"


def test_to_obsidian_rerun_still_rewrites_changed_notes(tmp_path):
    """Skipping identical writes must not skip real changes: giving Database a new
    neighbor changes Database.md's body (same filename), so it is rewritten."""
    G, communities = _two_node_graph()
    out = tmp_path / "obsidian"
    to_obsidian(G, communities, str(out), community_labels={0: "Backend"})
    note = out / "Database.md"
    before_text = note.read_text(encoding="utf-8")

    G.add_node("n3", label="Cache", community=0, source_file="app/cache.py", type="code")
    G.add_edge("n1", "n3")
    to_obsidian(G, {0: ["n1", "n2", "n3"]}, str(out), community_labels={0: "Backend"})

    assert note.read_text(encoding="utf-8") != before_text, "a changed note must be rewritten"


def test_to_wiki_rerun_does_not_rewrite_unchanged_articles(tmp_path):
    G, communities = _two_node_graph()
    out = tmp_path / "wiki"
    to_wiki(G, communities, str(out), community_labels={0: "Backend"})

    index = out / "index.md"
    community = out / "Backend.md"
    assert index.exists() and community.exists()
    i_before, c_before = _mtime(index), _mtime(community)

    to_wiki(G, communities, str(out), community_labels={0: "Backend"})

    assert index.exists() and community.exists()
    assert _mtime(index) == i_before, "unchanged index must not be rewritten (#3060)"
    assert _mtime(community) == c_before, "unchanged article must not be rewritten (#3060)"


def test_to_wiki_rerun_sweeps_orphaned_relabelled_article(tmp_path):
    """The end-of-run orphan sweep still removes a page the run did not produce
    (a community relabelled to a new slug)."""
    G, communities = _two_node_graph()
    out = tmp_path / "wiki"
    to_wiki(G, communities, str(out), community_labels={0: "Backend"})
    assert (out / "Backend.md").exists()

    to_wiki(G, communities, str(out), community_labels={0: "Infrastructure"})
    assert (out / "Infrastructure.md").exists()
    assert not (out / "Backend.md").exists(), "the relabelled community's stale page must be swept"
