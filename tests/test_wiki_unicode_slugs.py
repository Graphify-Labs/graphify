"""Every produced wiki page must survive cleanup under its allocated slug."""
from __future__ import annotations

import re

import networkx as nx
import pytest

from graphify.wiki import to_wiki


@pytest.mark.parametrize("labels", [("Straße", "STRASSE"), ("Σ", "ς")])
@pytest.mark.parametrize("article_kinds", ["communities", "mixed", "hubs"])
def test_casefold_colliding_articles_and_links_survive(tmp_path, labels, article_kinds):
    graph = nx.Graph()
    graph.add_node("a", label=labels[0], source_file="a.py", file_type="code")
    graph.add_node("b", label=labels[1], source_file="b.py", file_type="code")
    graph.add_edge("a", "b", relation="calls", confidence="EXTRACTED")
    communities = {0: ["a"], 1: ["b"]}
    community_labels = dict(enumerate(labels))
    hubs = []
    if article_kinds == "mixed":
        communities = {0: ["a", "b"]}
        hubs = [{"id": "b", "label": labels[1], "degree": 1}]
    elif article_kinds == "hubs":
        communities = {0: ["a", "b"]}
        community_labels = {0: "Overview"}
        hubs = [{"id": nid, "label": label, "degree": 1}
                for nid, label in zip(("a", "b"), labels)]

    previous = None
    for _ in range(2):
        count = to_wiki(graph, communities, tmp_path,
                        community_labels=community_labels, god_nodes_data=hubs)
        pages = {p.name: p.read_text(encoding="utf-8") for p in tmp_path.glob("*.md")}
        assert len(pages) == count + 1
        assert len({name.casefold() for name in pages}) == len(pages)
        for text in pages.values():
            for label, target in re.findall(r"\[([^\]]+)\]\(([^)]+\.md)\)", text):
                assert target in pages, (label, target)
                if target != "index.md":
                    assert pages[target].startswith(f"# {label}\n"), (label, target)
        index = pages["index.md"]
        for label in labels:
            assert f"[{label}](" in index
        if previous is not None:
            assert pages == previous
        previous = pages
