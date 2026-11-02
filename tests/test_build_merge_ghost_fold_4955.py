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


# --- to_json: a ghost fold is not a lost saved node ---

def test_to_json_accepts_a_method_ghost_fold(tmp_path):
    # #3705: Pass 2's method branch folds `run` into `.run()`. to_json's own
    # shrink guard used to read the saved `run` as a lost semantic node.
    path = _save(tmp_path, [_n("c_run", ".run()", "src/c.py", "L3"),
                            _n("run", "run", "src/c.py")])
    G = build_merge([dict(EMPTY)], graph_path=str(path), dedup=True)
    assert set(G.nodes) == {"c_run"}
    assert to_json(G, {}, str(path)) is True
    assert [n["id"] for n in json.loads(path.read_text())["nodes"]] == ["c_run"]


def test_ghost_fold_map_is_not_written_to_graph_json(tmp_path):
    path = _save(tmp_path, [_n("src_client", "client.py", "src/client.py", "L1"),
                            _n("client_py", "client.py", "src/client.py")])
    G = build_merge([dict(EMPTY)], graph_path=str(path), dedup=True)
    assert to_json(G, {}, str(path)) is True
    assert "_dedup_remap" not in json.loads(path.read_text()).get("graph", {})


# --- build_merge(dedup=False): intentional folds are not unexplained drops ---

def test_same_file_same_label_twin_is_not_an_unexplained_drop(tmp_path):
    # #1145, the issue's first case
    G = _merge(tmp_path, [_n("src_client", "client.py", "src/client.py", "L1"),
                          _n("client_py", "client.py", "src/client.py")])
    assert set(G.nodes) == {"src_client"}


def test_document_naming_a_file_is_not_an_unexplained_drop(tmp_path):
    # #3344, the issue's second case
    G = _merge(tmp_path, [_n("src_client", "client.py", "src/client.py", "L1"),
                          _n("plan_client", "src/client.py", "docs/plan.md")])
    assert set(G.nodes) == {"src_client"}


def test_directory_qualified_file_label_folds(tmp_path):
    G = _merge(tmp_path, [
        _n("app_index", "index.ts", "apps/customer-app/index.ts", "L1"),
        _n("memo_idx", "customer-app/index.ts", "docs/memo.md"),
    ])
    assert set(G.nodes) == {"app_index"}


def test_method_ghost_is_not_an_unexplained_drop(tmp_path):
    # #3705: the branch of Pass 2 that has no dedup check of its own
    G = _merge(tmp_path, [_n("c_run", ".run()", "src/c.py", "L3"),
                          _n("run", "run", "src/c.py")])
    assert set(G.nodes) == {"c_run"}


# --- the surrounding paths the fix must also hold ---

def test_edge_into_the_ghost_is_repointed_to_the_survivor(tmp_path):
    G = _merge(
        tmp_path,
        [_n("src_client", "client.py", "src/client.py", "L1"),
         _n("client_py", "client.py", "src/client.py"),
         _n("other", "Other", "src/o.py", "L1")],
        links=[{"source": "other", "target": "client_py",
                "relation": "references", "confidence": "INFERRED"}],
    )
    assert G.has_edge("other", "src_client")


def test_incremental_update_folds_new_ast_node_into_saved_semantic_twin(tmp_path):
    # An ordinary `update`: the file is re-extracted and a saved semantic twin
    # of it exists. This raised before, not only for an empty chunk.
    G = _merge(
        tmp_path,
        [_n("client_py", "client.py", "src/client.py")],
        chunk_nodes=[_n("src_client", "client.py", "src/client.py", "L1", _origin="ast")],
    )
    assert set(G.nodes) == {"src_client"}


def test_merge_then_write_round_trips_each_fold(tmp_path):
    # build_merge(dedup=False) followed by to_json is the persist path.
    cases = {
        "1145": [_n("src_client", "client.py", "src/client.py", "L1"),
                 _n("client_py", "client.py", "src/client.py")],
        "3344": [_n("src_client", "client.py", "src/client.py", "L1"),
                 _n("plan_client", "src/client.py", "docs/plan.md")],
        "3705": [_n("c_run", ".run()", "src/c.py", "L3"),
                 _n("run", "run", "src/c.py")],
    }
    for name, disk in cases.items():
        sub = tmp_path / name
        sub.mkdir()
        path = _save(sub, disk)
        G = build_merge([dict(EMPTY)], graph_path=str(path), dedup=False)
        assert to_json(G, {}, str(path)) is True, name
        assert len(json.loads(path.read_text())["nodes"]) == 1, name
