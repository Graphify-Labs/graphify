"""_lost_saved_semantic_nodes: a semantic ghost deduplicated into its AST twin
(#1145 extended) is preserved, not lost."""
from __future__ import annotations

import json
from pathlib import Path

from graphify.build import _lost_saved_semantic_nodes, build_from_json
from graphify.export import to_json
from graphify.watch import _check_shrink


def _sem(node_id: str, label: str, sf: str) -> dict:
    return {
        "id": node_id,
        "label": label,
        "file_type": "code",
        "source_file": sf,
        "source_location": None,
        "_origin": "semantic",
    }


def _ast(node_id: str, label: str, sf: str) -> dict:
    return {
        "id": node_id,
        "label": label,
        "file_type": "code",
        "source_file": sf,
        "source_location": "L10",
        "_origin": "ast",
    }


def test_same_id_present_is_not_lost():
    saved = [_sem("foo_bar", "bar", "src/foo.py")]
    new = [_sem("foo_bar", "bar", "src/foo.py")]
    assert _lost_saved_semantic_nodes(saved, new) == []


def test_deduplicated_into_ast_node_is_not_lost():
    saved = [_sem("ghost_bar", "bar", "src/foo.py")]
    new = [_ast("foo_py_bar", "bar", "src/foo.py")]
    assert _lost_saved_semantic_nodes(saved, new) == []


def test_non_ast_replacement_is_not_excused():
    saved = [_sem("ghost_bar", "bar", "src/foo.py")]
    new = [_sem("other_bar", "bar", "src/foo.py")]
    lost = _lost_saved_semantic_nodes(saved, new)
    assert [n["id"] for n in lost] == ["ghost_bar"]


def test_ast_label_collision_is_not_excused():
    saved = [_sem("ghost_bar", "bar", "src/foo.py")]
    new = [
        _ast("foo_py_bar_1", "bar", "src/foo.py"),
        _ast("foo_py_bar_2", "bar", "src/foo.py"),
    ]
    lost = _lost_saved_semantic_nodes(saved, new)
    assert [n["id"] for n in lost] == ["ghost_bar"]


def test_ast_collision_after_normalization_is_not_excused():
    saved = [_sem("ghost_bar", "bar", "src/foo.py")]
    new = [
        _ast("foo_py_bar_1", "bar", "src/foo.py"),
        _ast("foo_py_bar_2", "bar", "src\\foo.py"),
    ]
    lost = _lost_saved_semantic_nodes(saved, new)
    assert [n["id"] for n in lost] == ["ghost_bar"]


def test_dedup_match_normalizes_source_file():
    saved = [_sem("ghost_bar", "bar", "src\\foo.py")]
    new = [_ast("foo_py_bar", "bar", "src/foo.py")]
    assert _lost_saved_semantic_nodes(saved, new) == []


def test_genuinely_lost_node_is_reported():
    saved = [_sem("ghost_bar", "bar", "src/foo.py")]
    new = [
        _ast("foo_py_baz", "baz", "src/foo.py"),
        _ast("other_py_bar", "bar", "src/other.py"),
    ]
    lost = _lost_saved_semantic_nodes(saved, new)
    assert [n["id"] for n in lost] == ["ghost_bar"]


def test_node_in_deleted_source_is_not_lost():
    saved = [_sem("ghost_bar", "bar", "src/foo.py")]
    assert _lost_saved_semantic_nodes(saved, [], {"src/foo.py"}) == []


def test_node_in_other_file_not_excused_by_deleted_source():
    saved = [_sem("ghost_bar", "bar", "src/foo.py")]
    lost = _lost_saved_semantic_nodes(saved, [], {"src/other.py"})
    assert [n["id"] for n in lost] == ["ghost_bar"]


def test_malformed_non_string_source_file_does_not_crash():
    # Truthy non-string source_file in new_nodes or saved_nodes must not raise AttributeError
    saved = [{"id": "s1", "label": "S1", "source_file": 123, "_origin": "semantic"}]
    new = [{"id": "n1", "label": "N1", "source_file": True}]
    lost = _lost_saved_semantic_nodes(saved, new)
    assert [n["id"] for n in lost] == ["s1"]


# --- end-to-end: the write paths that call the guard (#4389) ---


def _saved_graph(tmp_path: Path, sem: dict) -> tuple[Path, dict]:
    out = tmp_path / "graph.json"
    assert to_json(build_from_json({"nodes": [sem], "edges": []}), {}, str(out), force=True)
    return out, json.loads(out.read_text(encoding="utf-8"))


def _node_data(G) -> dict:
    return {"nodes": [{"id": nid, **attrs} for nid, attrs in G.nodes(data=True)], "links": []}


def test_to_json_writes_after_ghost_dedup(tmp_path):
    sem = _sem("src_models_user_ts_user", "User", "src/models/user.ts")
    out, _ = _saved_graph(tmp_path, sem)
    G = build_from_json({"nodes": [sem, _ast("user_user", "User", "src/models/user.ts")], "edges": []})
    assert list(G.nodes) == ["user_user"]  # ghost id folded into its AST twin
    assert to_json(G, {}, str(out)) is True


def test_to_json_still_refuses_genuine_loss(tmp_path, capsys):
    sem = _sem("src_models_user_ts_user", "User", "src/models/user.ts")
    out, _ = _saved_graph(tmp_path, sem)
    G = build_from_json({"nodes": [_ast("user_account", "Account", "src/models/user.ts")], "edges": []})
    assert to_json(G, {}, str(out)) is False
    assert "src_models_user_ts_user" in capsys.readouterr().err


def test_check_shrink_allows_ghost_dedup(tmp_path):
    sem = _sem("src_models_user_ts_user", "User", "src/models/user.ts")
    _, existing = _saved_graph(tmp_path, sem)
    G = build_from_json({"nodes": [sem, _ast("user_user", "User", "src/models/user.ts")], "edges": []})
    assert _check_shrink(force=False, existing_data=existing, new_data=_node_data(G)) is True


# --- label-only file twin: build_from_json Pass 2b (#3344) folds a document's
# mention of a file into that file's AST node (#4389 cluster-only follow-up) ---


def _mention(node_id: str, label: str, doc: str) -> dict:
    return {"id": node_id, "label": label, "file_type": "code", "source_file": doc, "_origin": "semantic"}


def _ast_file(node_id: str, sf: str) -> dict:
    return {
        "id": node_id,
        "label": sf.rsplit("/", 1)[-1],
        "file_type": "code",
        "source_file": sf,
        "source_location": "L1",
        "_origin": "ast",
    }


def test_file_mention_folded_into_ast_file_node_is_not_lost():
    saved = [_mention("readme_config", "src/config.php", "README.md")]
    new = [_ast_file("src_config", "src/config.php")]
    folded: dict[str, str] = {}
    assert _lost_saved_semantic_nodes(saved, new, None, folded) == []
    assert folded == {"readme_config": "src_config"}


def test_file_mention_matching_two_ast_files_is_still_lost():
    # Pass 2b leaves an ambiguous label unmerged, so its absence is a real loss.
    saved = [_mention("readme_index", "index.ts", "README.md")]
    new = [_ast_file("a_index", "a/index.ts"), _ast_file("b_index", "b/index.ts")]
    lost = _lost_saved_semantic_nodes(saved, new)
    assert [n["id"] for n in lost] == ["readme_index"]


def _mixed_saved_graph(tmp_path: Path) -> Path:
    # A saved graph that still holds the mention beside its AST file node,
    # as reported on #4389 for graphifyy 0.9.95.
    out = tmp_path / "graph.json"
    out.write_text(json.dumps({
        "directed": False,
        "multigraph": False,
        "graph": {},
        "nodes": [
            _ast_file("src_config", "src/config.php"),
            _mention("readme_config", "src/config.php", "README.md"),
            {"id": "readme", "label": "README.md", "file_type": "document",
             "source_file": "README.md", "_origin": "semantic"},
        ],
        "links": [{"source": "readme", "target": "readme_config", "relation": "describes",
                   "confidence": "EXTRACTED", "source_file": "README.md"}],
    }), encoding="utf-8")
    return out


def test_to_json_writes_recluster_that_folds_file_mention(tmp_path):
    out = _mixed_saved_graph(tmp_path)
    G = build_from_json(json.loads(out.read_text(encoding="utf-8")))
    assert sorted(G.nodes) == ["readme", "src_config"]
    assert G.has_edge("readme", "src_config")  # the edge follows the fold
    assert to_json(G, {}, str(out)) is True


def test_to_json_new_twin_does_not_offset_another_loss(tmp_path, capsys):
    # The twin is new in this run, so the fold is not a saved duplicate going
    # away: losing src_other must still refuse the write.
    out = tmp_path / "graph.json"
    out.write_text(json.dumps({"nodes": [
        _mention("readme_config", "src/config.php", "README.md"),
        _ast_file("src_other", "src/other.php"),
    ], "links": []}), encoding="utf-8")
    G = build_from_json({"nodes": [_ast_file("src_config", "src/config.php")], "edges": []})
    assert to_json(G, {}, str(out)) is False
    assert "new graph has 1 nodes" in capsys.readouterr().err
