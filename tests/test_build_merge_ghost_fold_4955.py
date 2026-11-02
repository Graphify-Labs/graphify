"""#4955: build_merge's #479 guard and to_json's write guard must not count
the intentional ghost folds of build_from_json (#1145, #3344, #3705) as drops.
"""
import json

from graphify.build import build_merge
from graphify.export import to_json

EMPTY = {"nodes": [], "edges": [], "hyperedges": []}


def _n(id_, label, sf, loc=None, **kw):
    return {"id": id_, "label": label, "file_type": "code",
            "source_file": sf, "source_location": loc, **kw}


def _save(tmp_path, nodes, links=()):
    path = tmp_path / "graph.json"
    path.write_text(json.dumps({"directed": False, "multigraph": False, "graph": {},
                                "nodes": nodes, "links": list(links)}), encoding="utf-8")
    return path


def _merge(tmp_path, disk, chunk_nodes=(), dedup=False, links=(), **kw):
    path = _save(tmp_path, disk, links)
    chunk = {**EMPTY, "nodes": list(chunk_nodes)}
    return build_merge([chunk], graph_path=str(path), dedup=dedup, **kw)


# --- controls: the guard keeps protecting everything it protected before ---

def test_clean_graph_is_untouched(tmp_path):
    disk = [_n("a", "A", "a.py", "L1"), _n("b", "B", "b.py", "L2")]
    assert set(_merge(tmp_path, disk).nodes) == {"a", "b"}


def test_semantic_duplicates_are_not_folded_when_dedup_off(tmp_path):
    disk = [_n("s1", "Idea", "docs/a.md"), _n("s2", "Idea", "docs/a.md")]
    assert len(_merge(tmp_path, disk).nodes) == 2


def test_ghost_with_its_own_rationale_is_kept(tmp_path):  # #4896
    G = _merge(tmp_path, [
        _n("src_client", "client.py", "src/client.py", "L1"),
        _n("plan_client", "src/client.py", "docs/plan.md", rationale="why"),
    ])
    assert len(G.nodes) == 2


def test_ambiguous_file_label_is_not_folded(tmp_path):
    G = _merge(tmp_path, [
        _n("a", "index.ts", "a/index.ts", "L1"),
        _n("b", "index.ts", "b/index.ts", "L1"),
        _n("m", "index.ts", "docs/m.md"),
    ])
    assert len(G.nodes) == 3


def test_prune_sources_still_removes(tmp_path):
    disk = [_n("a", "A", "a.py", "L1"), _n("b", "B", "b.py", "L2")]
    assert set(_merge(tmp_path, disk, prune_sources=["b.py"]).nodes) == {"a"}
