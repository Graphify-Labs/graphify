"""Re-extraction must collect the placeholders it strands, not only prunes (#4399).

build_merge drops the old nodes and edges of re-extracted files by source_file.
A source-less placeholder (an external type like `List`, a namespace node) is
owned by no file, so it survived with no edges, and the #2807 sweep only ran
under prune_sources. Two ways to get there: per-file stubs re-pointed at a shared
node (#4247 upgrade), and an edit that removes a type's last reference.
"""
import json
from pathlib import Path

from networkx.readwrite import json_graph

from graphify.build import build_from_json, build_merge, take_shrink_accounting


def _x(nodes, edges):
    return {"nodes": nodes, "edges": edges, "hyperedges": []}


def _n(nid, sf=None, ft="code"):
    d = {"id": nid, "label": nid, "file_type": ft}
    if sf:
        d["source_file"] = sf
    return d


def _e(s, t, sf, rel="references"):
    return {"source": s, "target": t, "relation": rel,
            "confidence": "EXTRACTED", "source_file": sf}


def _save(extraction, tmp_path) -> str:
    gp = Path(tmp_path) / "graph.json"
    G = build_from_json(extraction)
    gp.write_text(json.dumps(json_graph.node_link_data(G, edges="links")), encoding="utf-8")
    return str(gp)


def test_stale_per_file_stubs_are_collected_after_a_rebind(tmp_path):
    """Path 1: old per-file stubs lose their edges to a shared placeholder."""
    gp = _save(_x(
        [_n("a", "A.cs"), _n("b", "B.cs"), _n("a_cs_list"), _n("b_cs_list")],
        [_e("a", "a_cs_list", "A.cs"), _e("b", "b_cs_list", "B.cs")],
    ), tmp_path)
    G = build_merge([_x(
        [_n("a", "A.cs"), _n("b", "B.cs"), _n("list")],
        [_e("a", "list", "A.cs"), _e("b", "list", "B.cs")],
    )], graph_path=gp, root=".")
    assert "a_cs_list" not in G and "b_cs_list" not in G
    assert G.degree("list") == 2
    assert take_shrink_accounting(G)[1] == 2  # swept disk nodes are excused


def test_shared_placeholder_is_collected_when_its_last_reference_is_edited_away(tmp_path):
    """Path 2: both referrers are edited, nothing is deleted."""
    gp = _save(_x(
        [_n("a", "A.cs"), _n("b", "B.cs"), _n("list"), _n("ns")],
        [_e("a", "list", "A.cs"), _e("b", "list", "B.cs"),
         _e("a", "ns", "A.cs", "imports"), _e("b", "ns", "B.cs", "imports")],
    ), tmp_path)
    G = build_merge([_x([_n("a", "A.cs"), _n("b", "B.cs")], [])], graph_path=gp, root=".")
    assert sorted(G.nodes) == ["a", "b"]


def test_external_namespace_stub_is_collected(tmp_path):
    """#2873 import stubs are file_type 'concept' but machine-minted."""
    stub = {"id": "system_collections_generic", "label": "system_collections_generic",
            "file_type": "concept", "type": "external", "external": True, "source_file": ""}
    gp = _save(_x([_n("a", "A.cs"), stub],
                  [_e("a", "system_collections_generic", "A.cs", "imports")]), tmp_path)
    G = build_merge([_x([_n("a", "A.cs")], [])], graph_path=gp, root=".")
    assert "system_collections_generic" not in G


def test_placeholder_still_referenced_elsewhere_survives(tmp_path):
    gp = _save(_x(
        [_n("a", "A.cs"), _n("b", "B.cs"), _n("list")],
        [_e("a", "list", "A.cs"), _e("b", "list", "B.cs")],
    ), tmp_path)
    G = build_merge([_x([_n("a", "A.cs")], [])], graph_path=gp, root=".")
    assert G.degree("list") == 1


def test_a_node_already_isolated_on_disk_is_kept(tmp_path):
    gp = _save(_x(
        [_n("a", "A.cs"), _n("list"), _n("lonely")],
        [_e("a", "list", "A.cs")],
    ), tmp_path)
    G = build_merge([_x([_n("a", "A.cs")], [])], graph_path=gp, root=".")
    assert "lonely" in G
    assert "list" not in G


def test_a_fresh_isolated_placeholder_is_kept(tmp_path):
    """The extractor's own isolated output matches a from-scratch build."""
    gp = _save(_x([_n("a", "A.cs")], []), tmp_path)
    G = build_merge([_x([_n("a", "A.cs"), _n("solo")], [])], graph_path=gp, root=".")
    assert "solo" in G


def test_a_sourceless_semantic_node_is_untouched(tmp_path):
    """Off the prune path only file_type == 'code' placeholders are collected."""
    gp = _save(_x(
        [_n("a", "A.cs"), _n("concept", ft="concept"), _n("doc_idea", ft="document")],
        [_e("a", "concept", "A.cs", "mentions"), _e("a", "doc_idea", "A.cs", "mentions")],
    ), tmp_path)
    G = build_merge([_x([_n("a", "A.cs")], [])], graph_path=gp, root=".")
    assert "concept" in G and "doc_idea" in G
