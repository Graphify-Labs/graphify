"""Pruning a source file must not leave its external-import nodes behind.

`prune_sources` matches nodes on `source_file`. Extractors create a per-file node
for each IMPORTED EXTERNAL symbol -- `Path` from pathlib, `Counter` from
collections -- and those carry no `source_file`, because they are defined outside
the corpus. Every edge they have points at symbols in the one file they were
created for, so pruning that file left them at degree 0: named after a file the
corpus no longer contains, counted in every total that reads the graph, exported
as a note of their own, and unreachable by any future prune since there is no
`source_file` to match on (#2807).

On graphify's own package, pruning `graphify/callflow_html.py` removed 137 of its
139 nodes and stranded `graphify_callflow_html_py_path` (label `Path`) and
`graphify_callflow_html_py_counter` (label `Counter`) permanently.

The sweep is deliberately scoped to nodes THIS prune isolated: a source-less node
that was already isolated beforehand is a different question and must survive.
"""
import json
import tempfile
from pathlib import Path

import pytest
from networkx.readwrite import json_graph

from graphify.build import build_from_json, build_merge


def _write_graph(G, tmp_path) -> str:
    gp = Path(tmp_path) / "graph.json"
    gp.write_text(json.dumps(json_graph.node_link_data(G, edges="links")), encoding="utf-8")
    return str(gp)


def _extraction(nodes, edges):
    return {"nodes": nodes, "edges": edges, "hyperedges": []}


def _corpus_graph():
    """One file with a real symbol plus an imported external symbol that has no
    source_file -- the exact shape the extractors emit."""
    nodes = [
        {"id": "mod_a_run", "label": "run()", "file_type": "code",
         "source_file": "a.py"},
        {"id": "mod_a_path", "label": "Path", "file_type": "code"},  # external
        {"id": "mod_b_keep", "label": "keep()", "file_type": "code",
         "source_file": "b.py"},
    ]
    edges = [
        {"source": "mod_a_run", "target": "mod_a_path", "relation": "references",
         "confidence": "EXTRACTED", "source_file": "a.py"},
        {"source": "mod_b_keep", "target": "mod_a_run", "relation": "calls",
         "confidence": "EXTRACTED", "source_file": "b.py"},
    ]
    return build_from_json(_extraction(nodes, edges))


def _prune(G, tmp_path, sources):
    return build_merge([_extraction([], [])], graph_path=_write_graph(G, tmp_path),
                       prune_sources=sources, root=".")


# ---------------------------------------------------------------------------
# The bug
# ---------------------------------------------------------------------------

def test_external_import_node_goes_with_its_file(tmp_path):
    G = _prune(_corpus_graph(), tmp_path, ["a.py"])
    assert "mod_a_run" not in G.nodes, "the file's own node should be pruned"
    assert "mod_a_path" not in G.nodes, (
        "the source-less external-import node was stranded at degree 0")
    assert "mod_b_keep" in G.nodes, "an unrelated file's node was swept up"


def test_no_sourceless_orphans_remain_after_a_prune(tmp_path):
    """Only source-less orphans are the bug. `mod_b_keep` is also isolated after
    this prune — its one edge pointed into a.py — but it is a real symbol in a
    file that still exists, so it must stay. Pruning it would be data loss, and
    it remains prunable through the normal path if b.py ever goes."""
    G = _prune(_corpus_graph(), tmp_path, ["a.py"])
    stranded = [n for n, d in G.nodes(data=True)
                if G.degree(n) == 0 and not d.get("source_file")]
    assert stranded == []
    assert "mod_b_keep" in G.nodes and G.degree("mod_b_keep") == 0


def test_a_shared_external_node_survives_while_still_referenced(tmp_path):
    """The sweep must key on being isolated, not on lacking a source_file: an
    external symbol two files reference is still live after one of them goes."""
    nodes = [
        {"id": "a_run", "label": "run()", "file_type": "code", "source_file": "a.py"},
        {"id": "b_run", "label": "run()", "file_type": "code", "source_file": "b.py"},
        {"id": "shared_path", "label": "Path", "file_type": "code"},
    ]
    edges = [
        {"source": "a_run", "target": "shared_path", "relation": "references",
         "confidence": "EXTRACTED", "source_file": "a.py"},
        {"source": "b_run", "target": "shared_path", "relation": "references",
         "confidence": "EXTRACTED", "source_file": "b.py"},
    ]
    G = _prune(build_from_json(_extraction(nodes, edges)), tmp_path, ["a.py"])
    assert "shared_path" in G.nodes, "still referenced by b.py — must not be swept"
    assert G.degree("shared_path") == 1


# ---------------------------------------------------------------------------
# What must NOT be swept
# ---------------------------------------------------------------------------

def test_a_node_isolated_before_the_prune_survives(tmp_path):
    """Scoped to what this prune orphans. A source-less node that was already
    isolated is a different problem and is left alone."""
    nodes = [
        {"id": "a_run", "label": "run()", "file_type": "code", "source_file": "a.py"},
        {"id": "lonely", "label": "Preexisting", "file_type": "code"},
        {"id": "b_keep", "label": "keep()", "file_type": "code", "source_file": "b.py"},
    ]
    edges = [{"source": "b_keep", "target": "a_run", "relation": "calls",
              "confidence": "EXTRACTED", "source_file": "b.py"}]
    G = _prune(build_from_json(_extraction(nodes, edges)), tmp_path, ["a.py"])
    assert "lonely" in G.nodes, "a pre-existing isolate was swept by an unrelated prune"


def test_an_isolated_node_that_has_a_source_file_survives(tmp_path):
    """Only source-less nodes are swept. A node with a real source_file is
    prunable through the normal path and must not be second-guessed here."""
    nodes = [
        {"id": "a_run", "label": "run()", "file_type": "code", "source_file": "a.py"},
        {"id": "b_solo", "label": "solo()", "file_type": "code", "source_file": "b.py"},
    ]
    edges = [{"source": "a_run", "target": "a_run", "relation": "calls",
              "confidence": "EXTRACTED", "source_file": "a.py"}]
    G = _prune(build_from_json(_extraction(nodes, edges)), tmp_path, ["a.py"])
    assert "b_solo" in G.nodes


def test_nothing_is_swept_when_no_prune_is_requested(tmp_path):
    """The sweep lives inside the prune branch; a plain merge must not touch
    isolated nodes."""
    G0 = _corpus_graph()
    G = build_merge([_extraction([], [])], graph_path=_write_graph(G0, tmp_path),
                    prune_sources=None, root=".")
    assert "mod_a_path" in G.nodes
    assert G.number_of_nodes() == G0.number_of_nodes()


def test_a_prune_that_matches_nothing_sweeps_nothing(tmp_path):
    G0 = _corpus_graph()
    G = _prune(G0, tmp_path, ["does_not_exist.py"])
    assert G.number_of_nodes() == G0.number_of_nodes()


def test_pruning_every_file_leaves_an_empty_graph(tmp_path):
    G = _prune(_corpus_graph(), tmp_path, ["a.py", "b.py"])
    assert G.number_of_nodes() == 0, sorted(G.nodes)


def test_sweeping_an_orphan_does_not_trip_the_shrink_guard(tmp_path):
    """The #479 shrink guard raises on unexplained node loss. Swept orphans are
    source-less, so they must be treated as explained: build_merge completes
    (does not raise) and returns the pruned graph with the orphan gone."""
    # build_merge itself runs the guard; this pruning both a file AND sweeping
    # its stranded stub must not raise.
    G = _prune(_corpus_graph(), tmp_path, ["a.py"])
    assert "mod_a_path" not in G.nodes  # swept orphan
    assert "mod_b_keep" in G.nodes      # unrelated file survives


def test_a_stub_referenced_by_a_surviving_file_is_not_swept(tmp_path):
    """A stub shared by two files must survive when only one referrer is pruned
    (single-pass sweep only removes it once it is genuinely degree 0)."""
    nodes = [
        {"id": "mod_a_run", "label": "run()", "file_type": "code", "source_file": "a.py"},
        {"id": "mod_b_run", "label": "run()", "file_type": "code", "source_file": "b.py"},
        {"id": "ext_path", "label": "Path", "file_type": "code"},  # shared external stub
    ]
    edges = [
        {"source": "mod_a_run", "target": "ext_path", "relation": "references",
         "confidence": "EXTRACTED", "source_file": "a.py"},
        {"source": "mod_b_run", "target": "ext_path", "relation": "references",
         "confidence": "EXTRACTED", "source_file": "b.py"},
    ]
    G = _prune(build_from_json(_extraction(nodes, edges)), tmp_path, ["a.py"])
    assert "ext_path" in G.nodes, "stub still referenced by b.py must not be swept"
    assert "mod_b_run" in G.nodes
