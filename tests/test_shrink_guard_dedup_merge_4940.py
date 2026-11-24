"""#4940: the #479 write guard must tell a node that entity dedup folded into a
twin from a node that was lost.

The tests assert on what reaches graph.json and on whether ``to_json`` wrote,
never on how the guard is wired, so they hold for any fix of the same bug.
"""
from __future__ import annotations

import json

import networkx as nx

from graphify.build import build_merge
from graphify.cluster import cluster
from graphify.export import to_json


def _node(nid: str, label: str, source_file: str) -> dict:
    return {"id": nid, "label": label, "file_type": "concept",
            "source_file": source_file, "_origin": "semantic"}


def _edge(source: str, target: str, source_file: str) -> dict:
    return {"source": source, "target": target, "relation": "references",
            "confidence": "EXTRACTED", "source_file": source_file, "_origin": "semantic"}


def _seed(path, nodes, edges=()):
    G = nx.Graph()
    for n in nodes:
        G.add_node(n["id"], **{k: v for k, v in n.items() if k != "id"})
    for e in edges:
        G.add_edge(e["source"], e["target"],
                   **{k: v for k, v in e.items() if k not in ("source", "target")})
    to_json(G, {0: [n["id"] for n in nodes]}, str(path), force=True)


def _merge_and_write(tmp_path, saved, fresh, saved_edges=(), tamper=None):
    """Seed graph.json, merge ``fresh`` into it the way ``--update`` does, then
    write with the default (guarded) ``to_json``. ``tamper`` edits the merged
    graph to stand in for a loss that happens after dedup."""
    graph_path = tmp_path / "graph.json"
    _seed(graph_path, saved, saved_edges)
    G = build_merge([{"nodes": fresh, "edges": [], "hyperedges": []}],
                    graph_path=graph_path, root=str(tmp_path))
    if tamper is not None:
        tamper(G)
    written = to_json(G, cluster(G), str(graph_path))
    return written, json.loads(graph_path.read_text())


ALPHA = _node("claude_a", "Alpha concept", "CLAUDE.md")
BRAVO = _node("glossary_b", "Bravo concept", "GLOSSARY.md")


# The guard's existing job. These pass before the fix and must keep passing.

def test_update_with_nothing_merged_or_lost_is_written(tmp_path):
    written, disk = _merge_and_write(tmp_path, [ALPHA, BRAVO], [BRAVO])
    assert written is True
    assert {n["id"] for n in disk["nodes"]} == {"claude_a", "glossary_b"}


def test_a_saved_node_that_is_gone_is_still_refused(tmp_path, capsys):
    written, disk = _merge_and_write(
        tmp_path, [ALPHA, BRAVO], [BRAVO], tamper=lambda G: G.remove_node("claude_a"),
    )
    assert written is False
    assert "claude_a" in capsys.readouterr().err
    assert {n["id"] for n in disk["nodes"]} == {"claude_a", "glossary_b"}


def test_a_re_extracted_node_dropped_after_the_merge_is_still_refused(tmp_path):
    written, disk = _merge_and_write(
        tmp_path, [ALPHA, BRAVO], [BRAVO], tamper=lambda G: G.remove_node("glossary_b"),
    )
    assert written is False
    assert "glossary_b" in {n["id"] for n in disk["nodes"]}


# What dedup reports.

def test_dedup_reports_each_id_it_merged_away():
    from graphify.dedup import deduplicate_entities

    nodes = [_node("glossary_the_nudge", "The nudge", "GLOSSARY.md"),
             _node("glossary_the_nudge_2", "The nudge", "GLOSSARY.md"),
             _node("claude_a", "Alpha concept", "CLAUDE.md")]
    remap: dict[str, str] = {}
    kept, _ = deduplicate_entities(nodes, [], communities={}, remap_out=remap)
    survivors = {n["id"] for n in kept}
    assert len(remap) == 1
    (loser, winner), = remap.items()
    assert loser in {"glossary_the_nudge", "glossary_the_nudge_2"}
    assert winner in survivors and loser not in survivors


def test_dedup_reports_nothing_when_it_merged_nothing():
    from graphify.dedup import deduplicate_entities

    remap: dict[str, str] = {}
    deduplicate_entities([ALPHA, BRAVO], [], communities={}, remap_out=remap)
    assert remap == {}


# What build() carries to the writer.

def test_build_carries_the_dedup_map_and_take_dedup_remap_pops_it():
    from graphify.build import build, take_dedup_remap

    G = build([{"nodes": [_node("glossary_the_nudge", "The nudge", "GLOSSARY.md"),
                          _node("glossary_the_nudge_2", "The nudge", "GLOSSARY.md")],
                "edges": [], "hyperedges": []}])
    remap = G.graph["_dedup_remap"]
    assert len(remap) == 1 and set(remap.values()) <= set(G.nodes)
    assert take_dedup_remap(G) == remap
    assert "_dedup_remap" not in G.graph
    assert take_dedup_remap(G) == {}


def test_build_leaves_no_map_when_nothing_merged():
    from graphify.build import build

    G = build([{"nodes": [ALPHA, BRAVO], "edges": [], "hyperedges": []}])
    assert "_dedup_remap" not in G.graph


def test_the_dedup_map_is_never_written_into_graph_json(tmp_path):
    from graphify.build import build

    G = build([{"nodes": [_node("glossary_the_nudge", "The nudge", "GLOSSARY.md"),
                          _node("glossary_the_nudge_2", "The nudge", "GLOSSARY.md")],
                "edges": [], "hyperedges": []}])
    assert G.graph.get("_dedup_remap")
    out = tmp_path / "graph.json"
    assert to_json(G, cluster(G), str(out)) is True
    assert "_dedup_remap" not in json.dumps(json.loads(out.read_text()))


# The bug: a merge dedup performed read as a loss.

TWINS = [_node("claude_the_nudge", "The nudge", "CLAUDE.md"),
         _node("claude_first_contact", "First contact", "CLAUDE.md"),
         _node("glossary_the_nudge", "The nudge", "GLOSSARY.md"),
         _node("glossary_first_contact", "First contact", "GLOSSARY.md")]
GLOSSARY_ALONE = [_node("glossary_the_nudge", "The nudge", "GLOSSARY.md"),
                  _node("glossary_first_contact", "First contact", "GLOSSARY.md")]


def test_re_extracting_a_doc_alone_writes_when_dedup_folds_it_into_its_twins(tmp_path):
    # The issue: GLOSSARY.md is re-extracted alone, dedup merges its concepts
    # into the untouched CLAUDE.md twins, and the saved glossary_* ids vanish.
    written, disk = _merge_and_write(tmp_path, TWINS, GLOSSARY_ALONE)
    assert written is True
    assert sorted(n["label"] for n in disk["nodes"]) == ["First contact", "The nudge"]


def test_an_edge_to_the_merged_away_id_is_kept_and_rewired(tmp_path):
    hub = _node("claude_hub", "Hub", "CLAUDE.md")
    written, disk = _merge_and_write(
        tmp_path, TWINS + [hub], GLOSSARY_ALONE,
        saved_edges=[_edge("claude_hub", "glossary_the_nudge", "CLAUDE.md")],
    )
    ids = {n["id"] for n in disk["nodes"]}
    links = disk.get("links", disk.get("edges", []))
    assert written is True
    assert [link for link in links if "claude_hub" in (link["source"], link["target"])]
    assert all(link["source"] in ids and link["target"] in ids for link in links)


def test_same_file_exact_duplicates_do_not_block_the_write(tmp_path):
    saved = [_node("glossary_the_nudge", "The nudge", "GLOSSARY.md"),
             _node("glossary_the_nudge_2", "The nudge", "GLOSSARY.md"),
             _node("claude_x", "X thing", "CLAUDE.md")]
    written, disk = _merge_and_write(tmp_path, saved, saved[:2])
    assert written is True
    assert "The nudge" in {n["label"] for n in disk["nodes"]}


def test_two_saved_ids_folded_into_one_new_survivor_write(tmp_path):
    # The node count drops by one although nothing was lost: both saved ids
    # live on in a survivor that is new this run.
    saved = [_node("glossary_the_nudge_c1", "The nudge", "GLOSSARY.md"),
             _node("glossary_the_nudge_c2", "The nudge", "GLOSSARY.md"), ALPHA]
    fresh = [_node("glossary_nudge", "The nudge", "GLOSSARY.md"), saved[0], saved[1]]
    written, disk = _merge_and_write(tmp_path, saved, fresh)
    assert written is True
    assert sorted(n["label"] for n in disk["nodes"]) == ["Alpha concept", "The nudge"]


def test_the_updated_graph_has_one_node_per_concept(tmp_path):
    _, disk = _merge_and_write(tmp_path, TWINS, GLOSSARY_ALONE)
    labels = [n["label"] for n in disk["nodes"]]
    assert len(labels) == len(set(labels))


def test_full_rebuild_that_merges_the_same_twins_writes(tmp_path):
    from graphify.build import build

    graph_path = tmp_path / "graph.json"
    _seed(graph_path, TWINS)
    G = build([{"nodes": [dict(n) for n in TWINS], "edges": [], "hyperedges": []}],
              root=str(tmp_path))
    assert G.number_of_nodes() < len(TWINS)
    assert to_json(G, cluster(G), str(graph_path)) is True


# The guard must not go blind to a real loss that sits beside a merge.

def test_a_real_loss_next_to_a_merge_is_refused_and_only_it_is_named(tmp_path, capsys):
    written, _ = _merge_and_write(
        tmp_path, TWINS, GLOSSARY_ALONE,
        tamper=lambda G: G.remove_node("claude_first_contact"),
    )
    named = capsys.readouterr().err.split("missing from the new graph:")[-1]
    assert written is False
    assert "claude_first_contact" in named
    assert "glossary_the_nudge" not in named


def test_a_survivor_that_is_itself_gone_excuses_nothing():
    from graphify.build import _lost_saved_semantic_nodes

    saved = [_node("loser", "The nudge", "GLOSSARY.md")]
    assert _lost_saved_semantic_nodes(saved, [], set(), dedup_remap={"loser": "winner"}) == saved
    kept = [_node("winner", "The nudge", "GLOSSARY.md")]
    assert _lost_saved_semantic_nodes(saved, kept, set(), dedup_remap={"loser": "winner"}) == []


def test_the_allowance_counts_only_merges_whose_survivor_is_present():
    from graphify.build import _dedup_shrink_allowance

    remap = {"a": "w", "b": "w", "c": "gone"}
    # w is new this run: two saved ids became one node, so the graph may be one smaller.
    assert _dedup_shrink_allowance({"a", "b", "c"}, {"w"}, remap) == 1
    # w is itself a saved id: both losers are accounted for.
    assert _dedup_shrink_allowance({"a", "b", "w"}, {"w"}, remap) == 2
    assert _dedup_shrink_allowance({"a"}, set(), remap) == 0
