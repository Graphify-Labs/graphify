"""Merged (multi-repo) graphs: file identity in ambiguity refusals is repo-qualified.

`source_file` is repo-relative, so a merged graph can hold nodes from
different repos whose relative path is identical (`web/dup.py` and `ml/dup.py`,
or any repeated `__init__.py` / `index.ts`). Deciding same-file vs cross-file
from `source_file` alone sent that case to the same-file refusal, which listed
line numbers only — the message no longer identified which file (or repo) each
candidate was in (#4512). File identity is now `(repo, source_file)` when a
merge `repo` tag is present.
"""

from __future__ import annotations

import networkx as nx

from graphify.serve import _resolve_single_node


def _merged_graph() -> nx.Graph:
    """Two nodes from different repos with an identical relative path."""
    G = nx.Graph()
    G.add_node(
        "web::dup_config", label="Config", source_file="dup.py", source_location="L1", repo="web"
    )
    G.add_node(
        "ml::dup_config", label="Config", source_file="dup.py", source_location="L1", repo="ml"
    )
    return G


def test_merged_same_basename_takes_cross_file_form():
    nid, err = _resolve_single_node(_merged_graph(), "Config")
    assert nid is None
    assert err is not None
    assert "matches 2 nodes in different files." in err
    # each candidate names its repo-qualified path
    assert "web/dup.py" in err
    assert "ml/dup.py" in err
    # the actionable hint is the cross-file one
    assert "path::symbol" in err


def test_merged_same_file_stays_same_file_form():
    G = nx.Graph()
    G.add_node("web::a", label="Config", source_file="dup.py", source_location="L1", repo="web")
    G.add_node("web::b", label="Config", source_file="dup.py", source_location="L9", repo="web")
    nid, err = _resolve_single_node(G, "Config")
    assert nid is None
    assert err is not None and "matches 2 nodes in web/dup.py." in err
    assert "different files" not in err


def test_single_repo_graph_unchanged():
    G = nx.Graph()
    G.add_node("a", label="Config", source_file="pkg/a.py", source_location="L1")
    G.add_node("b", label="Config", source_file="pkg/sub/a.py", source_location="L4")
    nid, err = _resolve_single_node(G, "Config")
    assert nid is None
    assert err is not None
    assert "matches 2 nodes in different files." in err
    assert "pkg/a.py" in err and "pkg/sub/a.py" in err
